"""Actual client coverage for private-farm navigation, care, and crowded scenes."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame

from tools.preview_ui_screens import ROOT, game_fixture, make_app, select_view
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas
from venom.common.game import SHOP


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class DigiFarmClientTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app('1180x800')
        self.addCleanup(pygame.quit)
        self.app.state = game_fixture(self.app)
        self.app.state.update(in_lab=False, in_farm=True, shop=copy.deepcopy(SHOP))
        self.app.menu = None
        self.app.state['inventory'].update(digimeat_cam=4, digimeat_atk_5=2)
        self.farm = self.app.farm_screen
        self.controls = []
        original = self.app.ui.button

        def capture(rect, label, callback, *args, **kwargs):
            self.controls.append((str(label), pygame.Rect(rect), kwargs))
            return original(rect, label, callback, *args, **kwargs)

        capture_patch = patch.object(self.app.ui, 'button', side_effect=capture)
        capture_patch.start()
        self.addCleanup(capture_patch.stop)

    def render(self):
        self.controls.clear()
        self.app.draw()

    def control(self, label, index=0):
        return [entry for entry in self.controls if entry[0] == label][index]

    def click_rect(self, rect):
        point = self.app.screen.to_physical_point(pygame.Rect(rect).center)
        return self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))

    def click(self, label, index=0):
        _, rect, options = self.control(label, index)
        self.assertFalse(options.get('disabled'), label)
        self.assertTrue(self.click_rect(rect))

    def fill_capacity(self):
        sources = self.app.state['storage']
        self.app.state['storage'] = [copy.deepcopy(sources[i % len(sources)]) for i in range(100)]
        for index, mon in enumerate(self.app.state['storage']):
            mon.update(uid=f'farm-resident-{index:03}', name=f'Resident {index:03}')

    def test_all_hundred_residents_and_controls_fit_minimum_to_4k(self):
        self.fill_capacity()
        for physical in ((1180, 800), (1920, 1080), (3840, 2160)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(physical), effective_ui_scale(physical))
            self.app.ui.screen = self.app.screen
            for age in (0., 8., 30., 300.):
                with self.subTest(size=physical, age=age):
                    self.farm.age = age
                    self.render()
                    self.assertEqual(set(self.farm.resident_rects),
                                     {mon['uid'] for mon in self.app.state['storage']})
                    bounds = self.app.screen.get_rect()
                    stage = pygame.Rect(34, 189, bounds.width-354, bounds.height-269)
                    for rect in self.farm.resident_rects.values():
                        self.assertTrue(stage.contains(rect), (physical, stage, rect))
                    for rect, _ in self.app.ui.actions + self.app.ui.fields:
                        self.assertTrue(bounds.contains(rect), (physical, rect))
                    self.farm.select('farm-resident-099')
                    self.render()
                    for rect, _ in self.app.ui.actions + self.app.ui.fields:
                        self.assertTrue(bounds.contains(rect), (physical, 'manager', rect))
                    self.farm.close_manager()
        self.assertFalse(self.app.assets.errors, self.app.assets.errors)

    def test_resident_search_and_paging_reach_last_owned_digimon(self):
        self.fill_capacity()
        with patch.object(self.farm, 'select', wraps=self.farm.select) as selected:
            self.render()
            self.click('Next')
            self.render()
            self.assertEqual(self.farm.page, 1)
            field = next(rect for rect, name in self.app.ui.fields if name == 'farm_search')
            self.assertTrue(self.click_rect(field))
            self.app.ui.event(pygame.event.Event(pygame.TEXTINPUT, text='Resident 099'))
            self.render()
            self.assertEqual(self.farm.page, 0)
            self.assertTrue(self.control('Next')[2]['disabled'])
            # The filtered resident row is the only care target in the right pane.
            right = self.app.screen.get_width()-312
            row = next(rect for rect, callback in self.app.ui.actions
                       if rect.x >= right and rect.height == 44)
            self.assertTrue(self.click_rect(row))
            selected.assert_called_once_with('farm-resident-099')
            self.assertEqual(self.farm.selected_uid, 'farm-resident-099')

    def test_feed_sends_selected_uid_and_waits_for_authoritative_state(self):
        mon = self.app.state['storage'][-1]
        self.farm.select(mon['uid'])
        self.farm.item = 'digimeat_atk_5'
        before = copy.deepcopy(self.app.state)
        with patch.object(self.app, 'send') as send:
            self.render()
            self.click('Feed one treat')
            send.assert_called_once_with('digifarm', action='feed', uid=mon['uid'],
                                         item='digimeat_atk_5', quantity=1)
            self.assertEqual(self.app.state, before)
            self.assertEqual(self.farm.last_feedback, '')
            self.app.action_pending = True
            self.render()
            self.assertTrue(self.control('Feeding…')[2]['disabled'])
            self.farm.feed()
            self.assertEqual(send.call_count, 1)

    def test_care_modal_removes_behind_it_resident_search_and_travel_actions(self):
        self.render()
        travel = self.control('Return to field')[1]
        uid = self.app.state['storage'][0]['uid']
        self.farm.select(uid)
        self.render()
        self.assertFalse(self.app.ui.fields)
        with patch.object(self.app, 'send') as send, patch.object(self.farm, 'select') as select:
            # Its centre lies under the modal's Feed button. Click the visible
            # right-hand edge outside the modal to isolate click-through.
            self.click_rect(pygame.Rect(travel.right-3, travel.y, 2, travel.height))
            send.assert_not_called()
            select.assert_not_called()
            self.assertEqual(self.farm.selected_uid, uid)
        self.click('Close  Esc')
        self.assertFalse(self.farm.manager_open)

    def test_stat_meat_requires_full_bonus_space_but_cam_can_top_up(self):
        mon = self.app.state['storage'][0]
        mon['farm_bonuses']['atk'] = 98
        self.farm.select(mon['uid'])
        self.farm.item = 'digimeat_atk_5'
        self.render()
        self.assertTrue(self.control('Feed one treat')[2]['disabled'])
        with patch.object(self.app, 'send') as send:
            self.farm.feed()
            send.assert_not_called()
        mon['cam'] = 98
        self.farm.item = 'digimeat_cam'
        self.render()
        self.assertFalse(self.control('Feed one treat')[2]['disabled'])

    def test_shop_feed_waits_for_home_arrival_and_preserves_requested_treat(self):
        self.app.state['in_farm'] = False
        self.app.menu = 'shop'
        with patch.object(self.app, 'send') as send:
            self.farm.open_manager(item='digimeat_spd_5')
            send.assert_called_once_with('digifarm', action='enter')
            self.assertFalse(self.farm.manager_open)
            self.assertTrue(self.farm.request_manager)
            # The server travel response arrives in a later frame.
            self.app.state = copy.deepcopy(self.app.state)
            self.app.state['in_farm'] = True
            self.farm.update(.016)
            self.assertTrue(self.farm.manager_open)
            self.assertFalse(self.farm.request_manager)
            self.assertIsNone(self.app.menu)
            self.assertEqual(self.farm.item, 'digimeat_spd_5')
            self.assertEqual(self.farm.food_page, 2)
            self.assertEqual(self.farm.selected_uid, self.app.state['storage'][0]['uid'])
            self.assertEqual(send.call_count, 1)

    def test_home_shortcut_works_from_settings_and_focused_farm_search(self):
        for settings in (False, True):
            with self.subTest(settings=settings), patch.object(self.app, 'send') as send, patch.object(self.app.display, 'save'):
                self.app.state['in_farm'] = False
                self.app.settings_open = settings
                self.app.ui.focus = 'farm_search'
                self.app.key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2, mod=0))
                send.assert_called_once_with('digifarm', action='enter')
                self.assertFalse(self.app.settings_open)
                self.assertIsNone(self.app.ui.focus)

    def test_enter_on_farm_never_focuses_invisible_chat(self):
        for mode in ('farm', 'search', 'care'):
            with self.subTest(mode=mode):
                self.app.ui.focus = None
                self.farm.manager_open = False
                if mode == 'search':
                    self.app.ui.focus = 'farm_search'
                    self.app.ui.values['farm_search'] = 'Greymon'
                elif mode == 'care':
                    self.farm.select(self.app.state['storage'][0]['uid'])
                self.render()
                with patch.object(self.app, 'send') as send:
                    self.app.key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0))
                    self.assertIsNone(self.app.ui.focus)
                    send.assert_not_called()
                if mode == 'search':
                    self.assertEqual(self.app.ui.values['farm_search'], 'Greymon')
                if mode == 'care':
                    self.assertTrue(self.farm.manager_open)

    def test_home_button_routes_all_signed_in_screens_and_requires_battle_forfeit(self):
        views = ('world', 'lab', 'dex', 'scan', 'roster', 'evolution', 'storage',
                 'maps', 'shop', 'ranked', 'rivals', 'activity', 'settings', 'battle', 'skills', 'battleitems')
        for view in views:
            with self.subTest(view=view), patch.object(self.app, 'send') as send, patch.object(self.app.display, 'save'):
                self.farm.home_confirmation = self.farm.manager_open = False
                select_view(self.app, view)
                self.app.state['in_farm'] = False
                before = copy.deepcopy(self.app.state)
                self.render()
                self.click('Home · DigiFarm')
                self.assertFalse(self.app.settings_open)
                if before.get('battle'):
                    send.assert_not_called()
                    self.assertTrue(self.farm.home_confirmation)
                    self.render()
                    self.assertEqual(len(self.app.ui.actions), 2)
                    self.click('Forfeit & return home')
                    send.assert_called_once_with('digifarm', action='enter', forfeit=True)
                else:
                    send.assert_called_once_with('digifarm', action='enter')
                self.assertEqual(self.app.state, before)

    def test_home_and_escape_cancel_full_party_swap_without_mutating(self):
        self.app.menu = 'party'
        self.app.partner_screen.mode = 'storage'
        pair = (self.app.state['party'][0]['uid'], self.app.state['storage'][0]['uid'])
        before = copy.deepcopy(self.app.state)
        self.app.partner_screen.pending_exchange = pair
        self.render()
        with patch.object(self.app, 'send') as send:
            self.click('Home · DigiFarm')
            self.assertIsNone(self.app.partner_screen.pending_exchange)
            self.assertIsNone(self.app.menu)
            send.assert_not_called()
        self.app.menu = 'party'
        self.app.partner_screen.pending_exchange = pair
        self.app.key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
        self.assertIsNone(self.app.partner_screen.pending_exchange)
        self.assertEqual(self.app.menu, 'party')
        self.assertEqual(before, self.app.state)

    def test_battle_home_confirmation_blocks_keyboard_attacks(self):
        select_view(self.app, 'battle')
        self.app.state['in_farm'] = False
        self.app.enter_farm()
        self.render()
        with patch.object(self.app, 'send') as send:
            self.app.key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0))
            send.assert_not_called()
        self.app.key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
        self.assertFalse(self.farm.home_confirmation)

    def test_roaming_is_bounded_infrequent_and_pauses_for_care(self):
        self.fill_capacity()
        moving = samples = 0
        for index, mon in enumerate(self.app.state['storage']):
            positions = []
            for step in range(600):
                x, y, walking, _ = self.farm.resident_position(mon['uid'], index, 100, age=step*.2)
                self.assertTrue(.16 <= x <= .84, x)
                self.assertTrue(.23 <= y <= .66, y)
                positions.append((x, y))
                moving += walking
                samples += 1
            self.assertGreater(len(set(positions)), 10)
            self.assertLess(max(x for x, _ in positions)-min(x for x, _ in positions), .04)
            self.assertLess(max(y for _, y in positions)-min(y for _, y in positions), .04)
        self.assertGreater(moving/samples, .12)
        self.assertLess(moving/samples, .30)
        self.farm.paused = True
        age = self.farm.age
        self.farm.update(.1)
        self.assertEqual(self.farm.age, age)
        self.farm.paused = False
        self.farm.select('farm-resident-000')
        self.farm.update(.1)
        self.assertEqual(self.farm.age, age)


if __name__ == '__main__':
    unittest.main()
