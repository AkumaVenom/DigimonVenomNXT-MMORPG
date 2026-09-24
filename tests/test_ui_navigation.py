"""Native input and server-action contracts for the redesigned menu screens."""
import copy
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from contextlib import ExitStack
import unittest
from unittest.mock import patch

import pygame

from tools.preview_ui_screens import ROOT, VIEWS, make_app, select_view
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class NativeMenuNavigationTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.buttons = []
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.addCleanup(pygame.quit)
        for owner in (self.app.ui, self.app.community):
            if hasattr(owner, 'button'):
                original = owner.button
                def capture(rect, label, callback, *args, _original=original, **kwargs):
                    self.buttons.append((str(label), pygame.Rect(rect), dict(kwargs)))
                    return _original(rect, label, callback, *args, **kwargs)
                self.patches.enter_context(patch.object(owner, 'button', side_effect=capture))

    def render(self, view=None, empty=False):
        if view:
            select_view(self.app, view, empty=empty)
        self.buttons.clear()
        self.app.draw()

    def control(self, *labels, index=0):
        found = [(rect, options) for name, rect, options in self.buttons if name in labels]
        self.assertGreater(len(found), index, f'Missing controls {labels}; saw {[b[0] for b in self.buttons]}')
        return found[index]

    def click(self, *labels, index=0):
        rect, options = self.control(*labels, index=index)
        self.assertFalse(options.get('disabled'), f'{labels} is disabled')
        position = self.app.screen.to_physical_point(rect.center)
        self.assertTrue(self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)))

    def test_all_views_and_empty_states_keep_controls_on_native_display(self):
        for physical in ((1280, 800), (2048, 1152), (3840, 2160)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(physical), effective_ui_scale(physical))
            self.app.ui.screen = self.app.screen
            for empty in (False, True):
                for view, _, _ in VIEWS:
                    with self.subTest(physical=physical, view=view, empty=empty):
                        self.render(view, empty=empty)
                        bounds = self.app.screen.get_rect()
                        self.assertTrue(self.app.ui.actions)
                        for rect, _ in self.app.ui.actions:
                            self.assertGreater(rect.width, 0)
                            self.assertGreater(rect.height, 0)
                            self.assertTrue(bounds.contains(rect), (view, rect, bounds))
                        self.assertNotIn('chat', [key for _, key in self.app.ui.fields])
        self.assertFalse(self.app.assets.errors, self.app.assets.errors)

    def test_ranked_buttons_preserve_authoritative_action_and_energy_gates(self):
        request = self.patches.enter_context(patch.object(self.app.community, 'request'))
        before = copy.deepcopy(self.app.state)
        self.render('ranked')
        self.click('Find ranked match', 'Find match')
        request.assert_called_with('match')
        self.click('Battle')
        request.assert_called_with('match', opponent_id='bot:00001')
        self.assertEqual(self.app.state, before, 'Presentation must not award results or alter the real party')
        self.app.community.data['ranked']['own']['energy']['current'] = 0
        self.render()
        self.assertTrue(self.control('Find ranked match', 'Find match')[1]['disabled'])
        self.assertTrue(self.control('Battle')[1]['disabled'])
        self.app.community.data['ranked']['own']['energy']['current'] = 4
        self.app.community.pending['match'] = (99, self.app.now)
        self.render()
        self.assertTrue(self.control('Battle')[1]['disabled'])

    def test_ladder_scopes_archives_and_profile_links_remain_accessible(self):
        request = self.patches.enter_context(patch.object(self.app.community, 'request'))
        self.render('ranked')
        self.click('Top 100')
        self.assertEqual(self.app.community.mode, 'ladder')
        request.assert_called_with('ladder', scope='current')
        self.render()
        self.click('Overall career')
        request.assert_called_with('ladder', scope='career')
        self.render()
        self.click('Past seasons')
        self.assertEqual(self.app.community.mode, 'seasons')
        self.render()
        self.click('View final top 100', 'Final standings')
        request.assert_called_with('ladder', scope='history', season_id='2026-38')

    def test_rivals_accept_decline_and_profile_challenge_use_correct_identifiers(self):
        request = self.patches.enter_context(patch.object(self.app.community, 'request'))
        self.render('rivals')
        self.click('Accept')
        request.assert_called_with('accept', challenge_id='qa-invite-0')
        self.click('Decline')
        request.assert_called_with('decline', challenge_id='qa-invite-0')
        self.render('rival_profile')
        self.click('Challenge rival')
        request.assert_called_with('challenge', bot_id='bot:00001')
        self.app.community.data['profile']['map_id'] = 'qa-other-map'
        self.render()
        self.assertTrue(self.control('Challenge rival')[1]['disabled'])
        self.app.community.data['profile']['map_id'] = self.app.state['map_id']
        self.app.community.data['profile']['battle'] = True
        self.render()
        self.assertTrue(self.control('Challenge rival')[1]['disabled'])

    def test_directory_text_input_pagination_and_profile_work_at_native_4k(self):
        self.app.screen = NativeCanvas(pygame.display.set_mode((3840, 2160)), 2.5)
        self.app.ui.screen = self.app.screen
        request = self.patches.enter_context(patch.object(self.app.community, 'request'))
        self.render('rivals_directory')
        field = next(rect for rect, name in self.app.ui.fields if name == 'rival_search')
        self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                            pos=self.app.screen.to_physical_point(field.center)))
        self.app.ui.event(pygame.event.Event(pygame.TEXTINPUT, text='Kira'))
        self.click('Find rival')
        request.assert_called_with('rivals', query='Kira', offset=0, limit=50)
        self.click('Next')
        request.assert_called_with('rivals', query='Kira', offset=50, limit=50)
        self.render()
        self.click('Previous')
        request.assert_called_with('rivals', query='Kira', offset=0, limit=50)
        self.render()
        self.click('Profile')
        self.assertEqual(self.app.community.mode, 'profile')
        self.assertEqual(self.app.community.profile_id, 'bot:00001')
        request.assert_called_with('profile', bot_id='bot:00001')

    def test_activity_filters_counters_and_map_navigation_preserve_controls(self):
        self.render('activity')
        for label in ('Wild', 'Ranked', 'Progress', 'Travel', 'All'):
            self.click(label)
            self.assertEqual(self.app.community.activity_filter, label)
            self.render()
        self.click('More counters')
        self.assertEqual(self.app.community.stats_page, 1)
        self.render()
        self.click('Main counters')
        self.assertEqual(self.app.community.stats_page, 0)
        self.click('Map population')
        self.assertEqual(self.app.community.mode, 'maps')

    def test_replay_controls_only_change_playback_and_return_to_hub(self):
        self.render('ranked_replay')
        before = copy.deepcopy(self.app.state)
        self.click('1× playback')
        self.assertEqual(self.app.community.replay.speed, 2.)
        self.render()
        self.click('Show result')
        self.assertTrue(self.app.community.replay.done)
        self.render()
        self.click('Return to hub')
        self.assertIsNone(self.app.community.replay)
        self.assertEqual(self.app.menu, 'community')
        self.assertEqual(self.app.state, before)

    def test_settings_hide_underlying_search_and_close_returns_to_field(self):
        self.render('rivals_directory')
        self.assertIn('rival_search', [name for _, name in self.app.ui.fields])
        self.app.toggle_settings()
        self.render()
        self.assertNotIn('rival_search', [name for _, name in self.app.ui.fields])
        self.app.toggle_settings()
        self.render()
        self.click('Field  Esc', 'Field Esc')
        self.assertIsNone(self.app.menu)
        self.assertIsNone(self.app.ui.focus)
        self.assertFalse(self.app.ui.actions)
        self.assertFalse(self.app.ui.fields)

    def test_shop_purchase_and_use_keep_server_prices_inventory_and_party_authoritative(self):
        self.app.state['in_lab'] = True
        send = self.patches.enter_context(patch.object(self.app, 'send'))
        self.render('shop')
        before = copy.deepcopy(self.app.state)
        self.click('Buy', 'Buy 1')
        send.assert_called_with('shop', item='hp_s', quantity=1)
        self.click('Use')
        send.assert_called_with('item', item='hp_s', party_index=0)
        self.assertEqual(self.app.state, before)
        self.app.action_pending = True
        self.render()
        self.assertTrue(self.control('Buy', 'Buy 1')[1]['disabled'])
        self.assertTrue(self.control('Use')[1]['disabled'])

    def test_shop_quantities_filters_and_purchase_limits_are_clickable(self):
        send = self.patches.enter_context(patch.object(self.app, 'send'))
        self.render('shop')
        self.click('+')
        self.render()
        self.click('Buy')
        send.assert_called_with('shop', item='hp_s', quantity=2)
        self.click('−')
        self.render()
        self.click('Buy')
        send.assert_called_with('shop', item='hp_s', quantity=1)
        self.click('SP recovery')
        self.render()
        self.click('Buy')
        send.assert_called_with('shop', item='sp_s', quantity=1)
        self.click('HP recovery')
        self.render()
        self.click('Buy')
        send.assert_called_with('shop', item='hp_s', quantity=1)
        self.app.state['inventory']['hp_s'] = 999
        self.render()
        self.assertTrue(self.control('Buy')[1]['disabled'])
        self.assertTrue(self.control('+')[1]['disabled'])
        self.render('shop_field')
        self.assertTrue(self.control('Buy')[1]['disabled'])
        self.app.state['inventory'] = {}
        self.render()
        self.assertTrue(self.control('Use')[1]['disabled'])
        enter_lab = self.patches.enter_context(patch.object(self.app, 'enter_lab'))
        self.render()
        self.click('Visit DigiLab to buy')
        enter_lab.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
