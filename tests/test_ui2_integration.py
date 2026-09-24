"""Server acknowledgments, menu state and completion feedback in the real App."""
import copy
import os
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame

from venom.client.app import App
from venom.client.render import NativeCanvas

ROOT = Path(__file__).resolve().parents[1]


class LocalConnection:
    connected = True

    def __init__(self):
        self.incoming = queue.Queue()
        self.sent = []

    def send(self, operation, **payload):
        self.sent.append((operation, payload))
        return len(self.sent)


@unittest.skipUnless((ROOT/'data/catalog.json').is_file(), 'Imported assets required')
class UI2AcknowledgmentIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(pygame.quit)
        self.enterContext(patch.object(pygame.mixer.music, 'load'))
        self.enterContext(patch.object(pygame.mixer.music, 'play'))
        self.sound = self.enterContext(patch.object(pygame.mixer, 'Sound', side_effect=lambda _: Mock()))
        self.clock = 1000
        self.enterContext(patch.object(pygame.time, 'get_ticks', side_effect=lambda: self.clock))
        args = SimpleNamespace(demo=True, demo_battle=False, dev=False, config=None,
                               size='1280x800', frames=0, screenshot=None)
        self.app = App(ROOT, args)
        self.app.args.demo = False
        self.app.connection = LocalConnection()
        self.app.now = 1.
        self.app.state['in_lab'] = True
        self.app.menu = 'lab'

    def tick(self, milliseconds=200):
        self.clock += milliseconds
        self.app.update(1/60)

    def respond(self, rid, state=None, error=None):
        packet = {'op': 'result', 'rid': rid, 'ok': error is None}
        if state is not None:
            packet['state'] = state
        if error is not None:
            packet['error'] = error
        self.app.connection.incoming.put(packet)
        self.app.poll()

    def completion_plays(self, cue):
        sound = self.app.audio.sounds.get(self.app.audio._ui_cues[cue])
        return sound.play.call_count if sound else 0

    def materialized_state(self, *, into_storage=False):
        state = copy.deepcopy(self.app.state)
        if into_storage:
            while len(state['party']) < 6:
                state['party'].append(dict(state['party'][0], uid=f'old-slot-{len(state["party"])}'))
        mon = dict(state['party'][0], uid='server-created-partner', name='New partner')
        state['storage' if into_storage else 'party'].append(mon)
        state['scan'][mon['species_id']] = 0
        state['events'] = [{'kind': 'message', 'text': 'Partner materialized.'}]
        return state, mon

    def test_materialization_waits_for_ack_then_detects_new_party_partner_and_plays_once(self):
        before = copy.deepcopy(self.app.state)
        sid = before['party'][0]['species_id']
        rid = self.app.send('materialize', species_id=sid)
        self.app.audio.cue('confirm', now=self.app.now)
        self.assertEqual(self.app.state, before)
        self.assertTrue(self.app.action_pending)
        self.assertIsNone(self.app.presentation_notice)
        self.assertEqual(self.completion_plays('scan_complete'), 0)
        state, mon = self.materialized_state()
        self.app.now += .01
        self.respond(rid, state)
        self.assertIs(self.app.state, state)
        self.assertFalse(self.app.action_pending)
        self.assertEqual(self.app.presentation_notice['name'], mon['name'])
        self.assertEqual(self.app.presentation_notice['species_id'], mon['species_id'])
        self.assertEqual(self.app.presentation_notice['theme'], 'scan')
        self.assertEqual(self.completion_plays('scan_complete'), 1)
        notice = self.app.presentation_notice
        self.app.now += .2
        self.respond(rid, copy.deepcopy(state))
        self.assertIs(self.app.presentation_notice, notice, 'Duplicate responses must not restart the celebration')
        self.assertEqual(self.completion_plays('scan_complete'), 1)

    def test_materialization_into_full_partys_bank_uses_server_partner_without_reordering(self):
        while len(self.app.state['party']) < 6:
            self.app.state['party'].append(dict(self.app.state['party'][0], uid=f'old-slot-{len(self.app.state["party"])}'))
        old_party = copy.deepcopy(self.app.state['party'])
        rid = self.app.send('materialize', species_id=old_party[0]['species_id'])
        state, mon = self.materialized_state(into_storage=True)
        self.respond(rid, state)
        self.assertEqual(self.app.state['party'], old_party)
        self.assertEqual(self.app.state['storage'][-1], mon)
        self.assertEqual(self.app.presentation_notice['name'], mon['name'])
        self.assertEqual(self.completion_plays('scan_complete'), 1)

    def test_evolution_ack_retains_server_uid_and_stats_and_changes_only_notice_metadata(self):
        before = copy.deepcopy(self.app.state)
        target = next(sid for sid in self.app.assets.species if sid != before['party'][0]['species_id'])
        rid = self.app.send('evolve', party_index=0, to=target)
        self.app.audio.cue('confirm', now=self.app.now)
        self.assertEqual(self.app.state, before)
        self.assertIsNone(self.app.presentation_notice)
        state = copy.deepcopy(before)
        state['party'][0].update(species_id=target, name='Evolved partner', level=1, abi=37, cam=68)
        state['events'] = [{'kind': 'message', 'text': 'Evolution complete.'}]
        expected = copy.deepcopy(state)
        self.app.now += .01
        self.respond(rid, state)
        self.assertEqual(self.app.state, expected)
        self.assertEqual(self.app.state['party'][0]['uid'], before['party'][0]['uid'])
        self.assertEqual(self.app.presentation_notice['theme'], 'evolution')
        self.assertEqual(self.app.presentation_notice['species_id'], target)
        self.assertEqual(self.completion_plays('evolution_complete'), 1)

    def test_failed_operations_never_change_progress_or_show_success(self):
        before = copy.deepcopy(self.app.state)
        for operation, payload, cue in (
            ('materialize', {'species_id': before['party'][0]['species_id']}, 'scan_complete'),
            ('evolve', {'party_index': 0, 'to': 'invalid'}, 'evolution_complete'),
        ):
            rid = self.app.send(operation, **payload)
            self.respond(rid, error='Requirements not met.')
            self.assertEqual(self.app.state, before)
            self.assertIsNone(self.app.presentation_notice)
            self.assertEqual(self.completion_plays(cue), 0)
            self.assertFalse(self.app.action_pending)
            self.app.now += 1.

    def test_digilab_closing_and_return_request_preserve_location_until_server_ack(self):
        self.app.menu = 'party'
        before = copy.deepcopy(self.app.state)
        self.app.close_menu()
        self.assertTrue(self.app.state['in_lab'])
        self.assertFalse(self.app.field_visible())
        with patch.object(self.app.hud, 'header'), patch.object(self.app.laboratory_screen, 'draw') as lab, \
                patch.object(self.app, 'draw_world') as field:
            self.app.draw_game()
            lab.assert_called_once()
            field.assert_not_called()
        rid = self.app.send('digilab', action='return')
        self.assertEqual(self.app.state, before)
        self.assertTrue(self.app.action_pending)
        self.respond(rid, error='Try again.')
        self.assertEqual(self.app.state, before)
        rid = self.app.send('digilab', action='return')
        state = copy.deepcopy(before)
        state.update(in_lab=False, events=[])
        self.respond(rid, state)
        self.assertFalse(self.app.state['in_lab'])
        self.assertIsNone(self.app.menu)
        self.assertTrue(self.app.field_visible())
        self.assertEqual(tuple(self.app.position), (before['x'], before['y']))

    def test_partner_modes_auth_picker_and_settings_route_actual_app_audio(self):
        self.app.menu = 'party'
        for mode, track in (('roster', 'party'), ('evolution', 'evolution'), ('storage', 'storage')):
            self.app.partner_screen.open_mode(mode)
            self.tick(); self.tick()
            self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks[track])
        self.app.toggle_settings()
        self.tick(); self.tick()
        self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks['settings'])
        self.app.toggle_settings()
        self.tick(); self.tick()
        self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks['storage'])
        self.app.state = None
        self.app.menu = None
        self.tick(); self.tick()
        self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks['auth'])
        self.app.open_picker('starter')
        self.tick(); self.tick()
        self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks['authpicker'])
        self.app.entry_screen._close_picker()
        self.tick(); self.tick()
        self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks['auth'])

    def test_battle_menu_gate_and_server_state_remove_stale_peaceful_menu(self):
        self.app.open_battle_menu('skills')
        self.assertEqual(self.app.menu, 'lab')
        state = copy.deepcopy(self.app.state)
        state.update(in_lab=False, battle={'actor': 0, 'turn': 1, 'enemies': [dict(state['party'][0])]}, events=[])
        self.app.menu = 'shop'
        self.respond(self.app.send('encounter'), state)
        self.assertIsNone(self.app.menu)
        self.app.set_menu('maps')
        self.assertIsNone(self.app.menu)
        self.app.open_battle_menu('skills')
        self.assertEqual(self.app.menu, 'skills')
        self.app.close_menu()
        self.app.action_pending = True
        self.app.open_battle_menu('battle_items')
        self.assertIsNone(self.app.menu)
        self.app.action_pending = False
        self.app.animations = [{'start': self.app.now, 'duration': 1}]
        self.app.open_battle_menu('battle_items')
        self.assertIsNone(self.app.menu)

    def test_completion_overlay_blocks_only_obscured_controls_at_native_dpi(self):
        mon = self.app.state['party'][0]
        self.app.presentation_notice = {'theme': 'scan', 'label': 'MATERIALIZATION COMPLETE',
                                        'name': mon['name'], 'species_id': mon['species_id'],
                                        'until': self.app.now+3.5}
        for scale in (1., 4/3, 2.5):
            with self.subTest(scale=scale):
                self.app.screen = NativeCanvas(pygame.Surface((1280, 800)), scale)
                self.app.ui.screen = self.app.screen
                notice = pygame.Rect((self.app.screen.get_width()-450)//2,
                                     self.app.screen.get_height()-145, 450, 105)
                blocked, outside = Mock(), Mock()
                hidden = pygame.Rect(notice.centerx-20, notice.centery-10, 40, 20)
                partial = pygame.Rect(notice.x-5, notice.y+5, 10, 20)
                safe = pygame.Rect(5, 5, 50, 25)
                safe_field = pygame.Rect(5, 40, 50, 25)
                self.app.ui.actions = [(hidden, blocked), (partial, blocked), (safe, outside)]
                self.app.ui.fields = [(hidden, 'covered'), (safe_field, 'visible')]
                self.app.ui.focus = 'covered'
                self.app.ui.values['covered'] = 'unchanged'
                self.app.hud.result()
                self.assertEqual(self.app.ui.actions, [(safe, outside)])
                self.assertEqual(self.app.ui.fields, [(safe_field, 'visible')])
                self.assertIsNone(self.app.ui.focus)
                self.app.ui.event(pygame.event.Event(pygame.TEXTINPUT, text='hidden typing'))
                self.assertEqual(self.app.ui.values['covered'], 'unchanged')
                self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                    pos=self.app.screen.to_physical_point(hidden.center)))
                blocked.assert_not_called()
                self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                    pos=self.app.screen.to_physical_point(safe.center)))
                outside.assert_called_once()
        self.app.now = self.app.presentation_notice['until']
        self.app.ui.actions = [(hidden, blocked), (safe, outside)]
        self.app.ui.fields = [(hidden, 'covered')]
        self.app.hud.result()
        self.assertEqual(len(self.app.ui.actions), 2, 'Expired results must not block any controls')
        self.assertEqual(self.app.ui.fields, [(hidden, 'covered')])

    def test_fast_purchase_and_rejection_acknowledgments_are_audible_after_click_confirmation(self):
        original = copy.deepcopy(self.app.state)
        self.app.audio.cue('confirm', now=self.app.now)
        rid = self.app.send('shop', item='hp_s', quantity=2)
        state = copy.deepcopy(original)
        state['inventory']['hp_s'] += 2
        state['credits'] -= 200
        state['events'] = [{'kind': 'message', 'text': 'Purchase confirmed.'}]
        self.app.now += .01
        self.respond(rid, state)
        self.assertEqual(self.completion_plays('purchase'), 1)
        self.assertIsNone(self.app.presentation_notice)
        self.assertEqual(original['inventory']['hp_s']+2, self.app.state['inventory']['hp_s'])
        self.app.now += 1.
        self.app.audio.cue('confirm', now=self.app.now)
        rid = self.app.send('shop', item='hp_l', quantity=99)
        self.app.now += .01
        self.respond(rid, error='Not enough credits for this purchase.')
        self.assertEqual(self.completion_plays('error'), 1)
        self.assertEqual(self.completion_plays('purchase'), 1)
        self.assertEqual(self.app.state, state)


if __name__ == '__main__':
    unittest.main()
