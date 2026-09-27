"""Exercise regional atlas input against the real imported maps and native UI."""
import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import pygame

from tools.preview_ui_screens import ROOT, game_fixture, make_app
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class WorldDSClientTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app('1280x800')
        self.addCleanup(pygame.quit)
        self.app.state = game_fixture(self.app)
        self.app.animations, self.app.toasts = [], []
        self.world = self.app.world_screen
        self.ds = self.world.region_entries('world_ds')
        if not self.ds:
            self.skipTest('World DS asset import required')
        self.dawn = self.world.region_entries('dawn')
        self.controls = []
        original = self.app.ui.button
        def capture(rect, label, callback, *args, **kwargs):
            self.controls.append((label, pygame.Rect(rect), kwargs))
            return original(rect, label, callback, *args, **kwargs)
        self.enterContext(patch.object(self.app.ui, 'button', side_effect=capture))

    def render(self):
        self.controls.clear()
        self.app.menu = 'maps'
        self.app.draw()

    def click(self, label):
        rect = next(rect for text, rect, options in self.controls if text == label and not options.get('disabled'))
        self.assertTrue(self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
            pos=self.app.screen.to_physical_point(rect.center))))

    def tab(self, key):
        return f'{dict(self.world.REGIONS)[key]}  ·  {len(self.world.region_entries(key))}'

    def test_two_regions_keep_original_catalog_and_send_only_authoritative_travel(self):
        before = copy.deepcopy(self.app.state)
        self.render()
        self.assertEqual(len(self.dawn), 254)
        self.assertTrue(all(not entry['id'].startswith('world_ds_') for entry in self.world.entries()))
        self.click(self.tab('world_ds'))
        self.render()
        self.assertTrue(all(entry['id'].startswith('world_ds_') for entry in self.world.entries()))
        with patch.object(self.app, 'send') as send:
            self.click('Transfer')
            send.assert_called_once_with('travel', map_id=self.ds[0]['id'])
        self.assertEqual(self.app.state, before)
        self.assertEqual(len({entry['id'] for entry in self.dawn+self.ds}), len(self.app.assets.maps))

    def test_level_search_page_memory_is_independent_per_region(self):
        self.render(); self.click(self.tab('world_ds')); self.render()
        self.click('Next'); self.render()
        ds_offset = self.app.scroll
        self.assertGreater(ds_offset, 0)
        self.click(self.tab('dawn')); self.render()
        self.assertEqual(self.app.scroll, 0)
        self.click('Next'); self.render()
        dawn_offset = self.app.scroll
        self.click(self.tab('world_ds')); self.render()
        self.assertEqual(self.app.scroll, ds_offset)
        self.click('Lv. 76–99'); self.render()
        self.assertTrue(self.world.entries())
        self.assertTrue(all(76 <= entry['level'] <= 99 for entry in self.world.entries()))
        target = self.world.entries()[-1]
        self.app.ui.values['world_search'] = target['id']; self.render()
        self.assertEqual([entry['id'] for entry in self.world.entries()], [target['id']])
        self.click(self.tab('dawn')); self.render()
        self.assertEqual(self.app.scroll, dawn_offset)
        self.assertEqual(self.app.ui.values['world_search'], '')
        self.click(self.tab('world_ds')); self.render()
        self.assertEqual(self.app.ui.values['world_search'], target['id'])
        self.assertEqual(self.world._browsing['world_ds']['band'], (76, 99))

    def test_opening_after_transfer_finds_current_map_and_story_stays_private(self):
        target = self.ds[-1]
        self.app.state.update(map_id=target['id'], x=target['spawn'][0], y=target['spawn'][1])
        self.app.menu = None; self.app.set_menu('maps'); self.render()
        self.assertEqual(self.world.region, 'world_ds')
        visible = self.world.entries()[self.app.scroll:self.app.scroll+self.world._page_size]
        self.assertIn(target, visible)
        self.click(self.tab('dawn')); self.render()
        self.click('Show this map in atlas'); self.render()
        self.assertEqual(self.world.region, 'world_ds')
        self.assertIn(target, self.world.entries()[self.app.scroll:self.app.scroll+self.world._page_size])
        self.app.close_menu(); self.app.state['in_story'] = True
        self.app.set_menu('maps')
        self.assertEqual((self.app.menu, self.app.story_screen.tab), ('story', 'atlas'))

    def test_gates_and_farm_return_preserve_existing_navigation_rules(self):
        self.render(); self.click(self.tab('world_ds')); self.render()
        target = self.ds[0]['id']
        with patch.object(self.app, 'send') as send:
            for key in ('in_lab', 'in_season', 'in_story', 'admin_jail', 'battle'):
                self.app.state[key] = {'id': 'busy'} if key in ('admin_jail', 'battle') else True
                self.world.transfer(target)
                send.assert_not_called()
                self.app.state[key] = None if key in ('admin_jail', 'battle') else False
            self.app.action_pending = True; self.world.transfer(target); send.assert_not_called()
            self.app.action_pending = False; self.app.state['in_farm'] = True
            self.world.transfer(target); send.assert_called_once_with('travel', map_id=target)
            self.render(); self.click('Return to field position')
            send.assert_called_with('digifarm', action='return')
            self.app.state['in_farm'] = False; self.app.state['in_lab'] = True
            self.render(); self.click('Return from DigiLab')
            send.assert_called_with('digilab', action='return')

    def test_search_empty_pages_and_wheel_never_create_blank_overflow_page(self):
        self.world.select_region('world_ds'); self.render()
        self.app.key(pygame.event.Event(pygame.MOUSEWHEEL, y=-1, x=0))
        self.assertEqual(self.app.scroll, self.world._page_size)
        for _ in range(len(self.ds)):
            self.world.wheel(-1)
        self.render()
        self.assertTrue(self.world.entries()[self.app.scroll:self.app.scroll+self.world._page_size])
        self.assertTrue(next(options['disabled'] for label, _, options in self.controls if label == 'Next'))
        self.app.ui.values['world_search'] = 'No such QA map'; self.render()
        self.assertEqual(self.app.scroll, 0)
        self.assertFalse(self.world.entries())
        self.assertFalse(any(label == 'Transfer' for label, _, _ in self.controls))

    def test_original_assets_readable_bounded_layout_and_exact_wild_ranges(self):
        self.assertEqual(self.world.levels({'level': 1}), (1, 3))
        self.assertEqual(self.world.levels({'level': 99}), (97, 99))
        self.assertEqual(self.world.levels({'level': 1, 'level_min': 1, 'level_max': 1}), (1, 1))
        self.assertEqual(self.world.level_label({'level': 1, 'level_min': 1, 'level_max': 1}), 'WILD Lv. 1')
        for entry in self.app.assets.maps.values():
            self.assertEqual(self.world.levels(entry), self.app._qa_engine.wild_level_range(entry))
        for physical in ((960, 600), (1280, 800), (1920, 1080), (3840, 2160)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(physical), effective_ui_scale(physical, 'auto'))
            self.app.ui.screen = self.app.screen
            for region in ('dawn', 'world_ds'):
                self.world.select_region(region); self.render()
                bounds = self.app.screen.get_rect()
                for rect, _ in self.app.ui.actions+self.app.ui.fields:
                    self.assertTrue(bounds.contains(rect), (physical, region, bounds, rect))
                self.assertLessEqual(self.world._thumbnail_bytes, self.world.THUMBNAIL_BYTES)
        self.assertFalse(self.app.assets.errors)
        self.assertTrue(any(path.startswith('assets/maps/world_ds/') for path, _ in self.world._thumbnails))


if __name__ == '__main__':
    unittest.main()
