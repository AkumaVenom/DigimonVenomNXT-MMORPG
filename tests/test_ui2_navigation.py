"""Actual-App UI2 routing, native input, and authoritative completion checks."""
import copy
from contextlib import ExitStack
import os
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame

from tools.preview_ui_screens import ROOT, UI2_VIEWS, game_fixture, make_app, select_view
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class UI2IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.addCleanup(pygame.quit)
        self.buttons = []
        original = self.app.ui.button
        def capture(rect, label, callback, *args, **kwargs):
            self.buttons.append((str(label), pygame.Rect(rect), kwargs))
            return original(rect, label, callback, *args, **kwargs)
        self.patches.enter_context(patch.object(self.app.ui, 'button', side_effect=capture))

    def render(self, view=None, empty=False):
        if view:
            select_view(self.app, view, empty=empty)
        self.buttons.clear()
        self.app.draw()

    def control(self, label, index=0):
        controls = [(rect, options) for name, rect, options in self.buttons if name == label]
        self.assertTrue(controls, f'Missing {label}; saw {[name for name, _, _ in self.buttons]}')
        return controls[index]

    def click_rect(self, rect):
        self.assertTrue(self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                        pos=self.app.screen.to_physical_point(rect.center))))

    def click(self, label, index=0):
        rect, options = self.control(label, index)
        self.assertFalse(options.get('disabled'), f'{label} disabled')
        self.click_rect(rect)

    def fill(self, key, value):
        field = next(rect for rect, name in self.app.ui.fields if name == key)
        self.click_rect(field)
        self.app.ui.event(pygame.event.Event(pygame.TEXTINPUT, text=value))

    def test_all_integrated_views_and_empty_states_fit_minimum_to_native_4k(self):
        for physical in ((1180, 800), (1280, 800), (2048, 1152), (3840, 2160)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(physical), effective_ui_scale(physical))
            self.app.ui.screen = self.app.screen
            for empty in (False, True):
                for view in UI2_VIEWS:
                    with self.subTest(size=physical, view=view, empty=empty):
                        self.render(view, empty)
                        bounds = self.app.screen.get_rect()
                        self.assertTrue(self.app.ui.actions)
                        for rect, _ in self.app.ui.actions+self.app.ui.fields:
                            self.assertGreater(rect.width, 0)
                            self.assertGreater(rect.height, 0)
                            self.assertTrue(bounds.contains(rect), (view, rect, bounds))
                        if view not in ('world', 'battle'):
                            self.assertNotIn('chat', [name for _, name in self.app.ui.fields])
                        if view in ('settings', 'settings_auth'):
                            self.assertEqual(self.app.ui.fields, [])
                        if view in ('tamerpicker', 'starterpicker'):
                            self.assertEqual([name for _, name in self.app.ui.fields], ['search'])
        self.assertFalse(self.app.assets.errors, self.app.assets.errors)

    def test_lab_routes_scan_and_partner_modes_through_actual_app(self):
        self.render('lab')
        self.click('Scan & materialize')
        self.assertEqual(self.app.menu, 'scan')
        self.render()
        self.assertIn('search', [name for _, name in self.app.ui.fields])
        for label, mode in (('Digivolution', 'evolution'), ('DigiBank', 'storage'), ('Active team', 'roster')):
            self.render('lab')
            self.click(label)
            self.assertEqual((self.app.menu, self.app.partner_screen.mode), ('party', mode))
            self.render()
            self.assertNotIn('chat', [name for _, name in self.app.ui.fields])

    def test_scan_and_evolution_clicks_send_exact_rules_engine_choices_without_completion(self):
        send = self.patches.enter_context(patch.object(self.app, 'send'))
        cue = self.patches.enter_context(patch.object(self.app.audio, 'cue'))
        self.render('scan')
        first = self.app.scan_screen.entries()[0]
        before = copy.deepcopy(self.app.state)
        self.click('Materialize')
        send.assert_called_with('materialize', species_id=first['id'])
        self.assertEqual(self.app.state, before)
        self.assertIsNone(self.app.presentation_notice)
        self.assertNotIn('scan_complete', [call.args[0] for call in cue.call_args_list])
        self.render('evolution')
        expected = next(route for route in self.app.state['evolution_options'][0] if not route.get('devolve'))
        self.assertTrue(expected['eligible'], 'Fixture eligibility must be generated by the rules engine')
        before = copy.deepcopy(self.app.state)
        self.click('Digivolve', index=-1)
        send.assert_called_with('evolve', party_index=0, to=expected['to'])
        self.assertEqual(self.app.state, before)
        self.assertIsNone(self.app.presentation_notice)
        self.assertNotIn('evolution_complete', [call.args[0] for call in cue.call_args_list])
        self.app.state['in_lab'] = False
        self.render()
        self.assertTrue(self.control('Digivolve', index=-1)[1]['disabled'])

    def test_filtered_digibank_withdraw_uses_original_server_index(self):
        send = self.patches.enter_context(patch.object(self.app, 'send'))
        self.render('storage_space')
        wanted = self.app.state['storage'][1]
        self.fill('bank_search', wanted['name'])
        self.render()
        before = copy.deepcopy(self.app.state)
        self.click('Withdraw')
        send.assert_called_with('party', action='withdraw', index=1)
        self.assertEqual(self.app.state, before)
        self.app.state['party'] += copy.deepcopy(self.app.state['party'])
        self.render()
        self.assertFalse(self.control('Swap into slot 1')[1]['disabled'])
        send.reset_mock()
        self.click('Swap into slot 1')
        send.assert_not_called()
        self.render()
        self.click('Confirm swap')
        send.assert_called_once_with('party', action='exchange', party_index=0, uid=wanted['uid'])

    def test_battle_item_full_party_recipient_and_skills_keep_correct_payload(self):
        send = self.patches.enter_context(patch.object(self.app, 'send'))
        self.render('skills')
        actor = self.app.state['battle']['actor']
        self.app.target = 1
        self.render()
        self.click('Use skill')
        send.assert_called_with('battle', action='skill', target=1, party_index=actor, skill_index=0)
        self.assertIsNone(self.app.menu)
        self.render('battleitems')
        recipient_actions = []
        original = self.app.combat_menu.recipients
        def record_recipients(*args):
            start = len(self.app.ui.actions)
            original(*args)
            recipient_actions[:] = self.app.ui.actions[start:]
        self.patches.enter_context(patch.object(self.app.combat_menu, 'recipients', side_effect=record_recipients))
        self.render()
        self.assertEqual(len(recipient_actions), 6)
        self.click_rect(recipient_actions[5][0])
        self.assertEqual(self.app.selected_party, 5)
        self.render()
        self.click('Use capsule')
        send.assert_called_with('battle', action='item', target=0, party_index=5, item='hp_s')
        self.assertIsNone(self.app.menu)

    def test_auth_picker_and_settings_block_previous_fields_then_restore_route(self):
        self.render('register')
        self.fill('username', 'QA_Tamer')
        self.fill('password', 'preview-password')
        self.app.open_picker('tamer')
        self.render()
        self.assertEqual([key for _, key in self.app.ui.fields], ['search'])
        self.fill('search', 'Dawn')
        self.app.key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertIsNone(self.app.auth_picker)
        self.assertIsNone(self.app.ui.focus)
        self.render()
        self.assertEqual(self.app.ui.values['username'], 'QA_Tamer')
        self.assertEqual(self.app.ui.values['password'], 'preview-password')
        self.app.toggle_settings()
        self.render()
        self.assertEqual(self.app.ui.fields, [])
        self.click('Done')
        self.render()
        self.assertEqual([key for _, key in self.app.ui.fields], ['username', 'password'])

    def deliver_result(self, operation, state=None, *, ok=True, rid=85):
        self.app.connection = SimpleNamespace(connected=True, incoming=queue.Queue())
        self.app.requests[rid] = operation
        packet = {'op': 'result', 'rid': rid, 'ok': ok}
        if state is not None:
            packet['state'] = state
        if not ok:
            packet['error'] = 'The server rejected this request.'
        self.app.connection.incoming.put(packet)
        self.app.poll()

    def test_successful_materialization_ack_cues_and_displays_real_banked_partner(self):
        self.render('scan')
        before = copy.deepcopy(self.app.state)
        after = copy.deepcopy(before)
        sid = self.app.scan_screen.entries()[0]['id']
        self.app._qa_engine.handle(after, 'materialize', {'species_id': sid})
        self.assertEqual(len(after['party']), 6)
        self.assertEqual(len(after['storage']), len(before['storage'])+1)
        cue = self.patches.enter_context(patch.object(self.app.audio, 'cue'))
        effect = self.patches.enter_context(patch.object(self.app.audio, 'effect'))
        self.deliver_result('materialize', after)
        self.assertIs(self.app.state, after)
        self.assertEqual(self.app.presentation_notice['species_id'], after['storage'][-1]['species_id'])
        self.assertEqual(self.app.presentation_notice['theme'], 'scan')
        cue.assert_called_once_with('scan_complete', now=self.app.now)
        effect.assert_not_called()
        self.assertEqual(self.app.state['scan'][sid], 0)

    def test_successful_evolution_ack_preserves_identity_and_uses_completion_cue(self):
        self.render('evolution')
        before = copy.deepcopy(self.app.state)
        after = copy.deepcopy(before)
        target = next(route['to'] for route in after['evolution_options'][0] if route['eligible'] and not route.get('devolve'))
        self.app._qa_engine.handle(after, 'evolve', {'party_index': 0, 'to': target})
        cue = self.patches.enter_context(patch.object(self.app.audio, 'cue'))
        self.deliver_result('evolve', after)
        self.assertEqual(self.app.state['party'][0]['uid'], before['party'][0]['uid'])
        self.assertEqual(self.app.state['party'][0]['level'], 1)
        self.assertEqual(self.app.presentation_notice['species_id'], target)
        self.assertEqual(self.app.presentation_notice['theme'], 'evolution')
        cue.assert_called_once_with('evolution_complete', now=self.app.now)

    def test_failed_or_stateless_results_do_not_invent_partner_completion(self):
        self.render('scan')
        before = copy.deepcopy(self.app.state)
        cue = self.patches.enter_context(patch.object(self.app.audio, 'cue'))
        self.deliver_result('materialize', {'party': []}, ok=False)
        self.assertEqual(self.app.state, before)
        self.assertIsNone(self.app.presentation_notice)
        cue.assert_called_once_with('error', now=self.app.now)
        cue.reset_mock()
        self.deliver_result('evolve')
        self.assertEqual(self.app.state, before)
        self.assertIsNone(self.app.presentation_notice)
        cue.assert_not_called()

    def test_success_notice_suppresses_covered_actions_until_it_expires(self):
        self.render('scan')
        initial_actions = list(self.app.ui.actions)
        self.app.presentation_notice = {'theme': 'scan', 'label': 'MATERIALIZATION COMPLETE',
                                        'name': 'Agumon', 'species_id': self.app.state['party'][0]['species_id'],
                                        'until': self.app.now+3.5}
        regions = []
        original = self.app.presentation.card
        def capture_notice(rect, *args, **kwargs):
            regions.append(pygame.Rect(rect))
            return original(rect, *args, **kwargs)
        with patch.object(self.app.presentation, 'card', side_effect=capture_notice):
            self.app.hud.result()
        self.assertEqual(len(regions), 1)
        covered = regions[0]
        self.assertTrue(any(covered.colliderect(rect) for rect, _ in initial_actions))
        self.assertFalse(any(covered.colliderect(rect) for rect, _ in self.app.ui.actions+self.app.ui.fields))
        self.app.now = self.app.presentation_notice['until']+1
        self.render()
        self.assertTrue(any(covered.colliderect(rect) for rect, _ in self.app.ui.actions))


if __name__ == '__main__':
    unittest.main()
