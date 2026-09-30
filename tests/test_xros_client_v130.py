"""Exercise Xros atlas controls, regional travel and field discovery at native sizes."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame

from tools.preview_ui_screens import ROOT, game_fixture, make_app
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas
from venom.client.varieties import paradox_map_available, shiny_map_available


class XrosClientTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app('1280x800')
        self.addCleanup(pygame.quit)
        self.app.state = game_fixture(self.app)
        self.app.animations, self.app.toasts = [], []
        self.world = self.app.world_screen
        self.xros = self.world.region_entries('xros_wars')
        if not self.xros:
            self.skipTest('Super Xros Wars map import required')
        self.controls = []
        original = self.app.ui.button
        def capture(rect, label, callback, *args, **kwargs):
            self.controls.append((str(label), pygame.Rect(rect), callback, kwargs))
            return original(rect, label, callback, *args, **kwargs)
        self.enterContext(patch.object(self.app.ui, 'button', side_effect=capture))

    def render(self):
        self.controls.clear()
        self.app.menu = 'maps'
        self.app.draw()

    def tab(self, region):
        return f'{dict(self.world.REGIONS)[region]}  ·  {len(self.world.region_entries(region))}'

    def click(self, label):
        rect = next(rect for text, rect, _, options in self.controls
                    if text == label and not options.get('disabled'))
        self.assertTrue(self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
            button=1, pos=self.app.screen.to_physical_point(rect.center))))

    def test_three_regions_partition_maps_and_keep_authored_progression(self):
        self.assertEqual([region for region, _ in self.world.available_regions()],
                         ['dawn', 'world_ds', 'xros_wars'])
        self.assertEqual(len(self.world.region_entries('dawn')), 254)
        self.assertEqual(len(self.world.region_entries('world_ds')), 150)
        self.assertEqual(len(self.xros), 96)
        self.assertEqual([area['level'] for area in self.xros], sorted(area['level'] for area in self.xros))
        self.assertTrue(all(area['id'].startswith('xros_') for area in self.xros))
        self.assertEqual(min(self.world.levels(area)[0] for area in self.xros), 1)
        self.assertEqual(max(self.world.levels(area)[1] for area in self.xros), 99)
        all_maps = [area['id'] for region, _ in self.world.available_regions()
                    for area in self.world.region_entries(region)]
        self.assertEqual(len(set(all_maps)), len(all_maps))
        self.assertEqual(set(all_maps), set(self.app.assets.maps))

    def test_native_tabs_filters_and_search_retain_independent_xros_browsing(self):
        self.render(); self.click(self.tab('xros_wars')); self.render()
        self.click('Next'); self.render()
        offset = self.app.scroll
        self.assertGreater(offset, 0)
        for region in ('dawn', 'world_ds'):
            self.click(self.tab(region)); self.render()
            self.assertEqual(self.app.scroll, 0)
        self.click(self.tab('xros_wars')); self.render()
        self.assertEqual(self.app.scroll, offset)
        self.click('Lv. 76–99'); self.render()
        self.assertTrue(all(76 <= area['level'] <= 99 for area in self.world.entries()))
        target = self.world.entries()[-1]
        self.app.ui.values['world_search'] = target['id']; self.render()
        self.assertEqual([area['id'] for area in self.world.entries()], [target['id']])
        self.click(self.tab('world_ds')); self.render()
        self.assertEqual(self.app.ui.values['world_search'], '')
        self.click(self.tab('xros_wars')); self.render()
        self.assertEqual(self.app.ui.values['world_search'], target['id'])
        self.assertEqual(self.world._browsing['xros_wars']['band'], (76, 99))

    def test_current_xros_map_focus_and_exact_travel_preserve_server_authority(self):
        target = self.xros[-1]
        self.app.state.update(map_id=target['id'], x=target['spawn'][0], y=target['spawn'][1])
        before = copy.deepcopy(self.app.state)
        self.app.menu = None; self.app.set_menu('maps'); self.render()
        self.assertEqual(self.world.region, 'xros_wars')
        self.assertIn(target, self.world.entries()[self.app.scroll:self.app.scroll+self.world._page_size])
        for region in ('dawn', 'world_ds', 'xros_wars'):
            self.click(self.tab(region)); self.render()
            candidate = next(area for area in self.world.entries()[self.app.scroll:self.app.scroll+self.world._page_size]
                             if area['id'] != target['id'])
            with patch.object(self.app, 'send') as send:
                self.click('Transfer')
                send.assert_called_once_with('travel', map_id=candidate['id'])
        self.assertEqual(self.app.state, before)
        self.click('Show this map in atlas'); self.render()
        self.assertEqual(self.world.region, 'xros_wars')
        self.assertIn(target, self.world.entries()[self.app.scroll:self.app.scroll+self.world._page_size])

    def test_every_xros_destination_keeps_travel_activity_guards(self):
        with patch.object(self.app, 'send') as send:
            for key in ('in_story', 'in_season', 'in_lab', 'battle', 'admin_jail'):
                self.app.state[key] = True
                for area in self.xros:
                    self.world.transfer(area['id'])
                send.assert_not_called()
                self.app.state[key] = False
            self.app.action_pending = True
            self.world.transfer(self.xros[0]['id']); send.assert_not_called()
            self.app.action_pending = False
            self.world.transfer('xros_missing'); send.assert_not_called()
            self.app.state['in_farm'] = True
            self.world.transfer(self.xros[0]['id'])
            send.assert_called_once_with('travel', map_id=self.xros[0]['id'])

    def test_all_regions_fit_native_controls_and_third_tab_without_overlap(self):
        for physical in ((960, 600), (1280, 800), (1920, 1080), (3840, 2160)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(physical), effective_ui_scale(physical, 'auto'))
            self.app.ui.screen = self.app.screen
            for region, _ in self.world.available_regions():
                self.world.select_region(region); self.render()
                bounds = self.app.screen.get_rect()
                for rect, _ in self.app.ui.actions+self.app.ui.fields:
                    self.assertTrue(bounds.contains(rect), (physical, region, bounds, rect))
                tabs = [rect for label, rect, _, _ in self.controls
                        if label in {self.tab(key) for key, _ in self.world.available_regions()}]
                self.assertEqual(len(tabs), 3)
                self.assertTrue(all(not a.colliderect(b) for i, a in enumerate(tabs) for b in tabs[i+1:]))
                self.assertLessEqual(self.world._thumbnail_bytes, self.world.THUMBNAIL_BYTES)
        self.assertFalse(self.app.assets.errors)

    def test_every_xros_map_has_real_art_exact_levels_and_both_rare_varieties(self):
        for area in self.xros:
            self.assertTrue((ROOT/area['path']).is_file())
            self.assertEqual(self.world.levels(area), self.app._qa_engine.wild_level_range(area))
            self.assertTrue(shiny_map_available(area, self.app.assets.species), area['id'])
            self.assertTrue(paradox_map_available(area, self.app.assets.species), area['id'])
            self.assertEqual(self.world.rare_label(area), 'FIREWALL 0.7%  ·  SHINY 1%  ·  PARADOX 2.5%')
            self.world.thumbnail(area, pygame.Rect(0, 0, 190, 90))
        self.assertFalse(self.app.assets.errors)
        self.assertLessEqual(self.world._thumbnail_bytes, self.world.THUMBNAIL_BYTES)
        self.assertLessEqual(len(self.world._thumbnails), self.world.THUMBNAIL_ITEMS)

    def test_population_uses_fresh_server_counts_including_zero_without_inventing_missing_counts(self):
        first, second = self.xros[:2]
        self.app.community.data['activity'] = {'maps': [{'id': first['id'], 'count': 6},
                                                       {'id': second['id'], 'count': 0}]}
        self.app.community.received_at['activity'] = self.app.now
        self.assertEqual(self.world.population(first), 6)
        self.assertEqual(self.world.population(second), 0)
        self.assertIsNone(self.world.population(self.xros[-1]))
        self.app.now += 31
        self.assertIsNone(self.world.population(first))
        self.app.args.demo = False
        with patch.object(self.app.community, 'request') as request:
            self.world.on_open()
            request.assert_called_once_with('activity')
        self.app.community.received_at['activity'] = self.app.now
        with patch.object(self.app.community, 'request') as request:
            self.world.on_open()
            request.assert_not_called()

    def test_field_hud_identifies_region_and_levels_without_private_story_claims(self):
        import venom.client.world as world_module
        area = self.xros[0]
        self.app.state.update(map_id=area['id'], in_story=False, in_farm=False, in_lab=False)
        with patch.object(world_module, 'text', wraps=world_module.text) as labels:
            self.app.world._draw_hud(area, pygame.Rect(20, 100, 850, 470))
        values = [str(call.args[2]) for call in labels.call_args_list]
        self.assertIn(f'SUPER XROS WARS  ·  {self.world.level_label(area)}', values)
        self.assertIn('SHINY  1% chance · +5% scan per defeat', values)
        self.assertFalse(any('CRESTS' in value or 'STORY MODE' in value for value in values))


if __name__ == '__main__':
    unittest.main()
