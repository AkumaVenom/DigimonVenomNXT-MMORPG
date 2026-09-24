"""DigiMeat catalogue reachability and authoritative shop navigation."""
import copy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame

from tools.preview_ui_screens import ROOT, game_fixture, make_app
from venom.common.game import SHOP


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class DigiFarmShopTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app('1180x800')
        self.addCleanup(pygame.quit)
        self.app.state = game_fixture(self.app)
        self.app.state.update(in_lab=False, in_farm=True, credits=100000, shop=copy.deepcopy(SHOP))
        self.app.state['inventory']['digimeat_cam'] = 3
        self.app.menu = 'shop'
        self.controls = []
        original = self.app.ui.button

        def capture(rect, label, callback, *args, **kwargs):
            self.controls.append((label, pygame.Rect(rect), callback, kwargs))
            return original(rect, label, callback, *args, **kwargs)

        capture_patch = patch.object(self.app.ui, 'button', side_effect=capture)
        capture_patch.start()
        self.addCleanup(capture_patch.stop)

    def render(self):
        self.controls.clear()
        self.app.draw()

    def control(self, label):
        return next(control for control in self.controls if control[0] == label)

    def click(self, label):
        _, rect, _, options = self.control(label)
        self.assertFalse(options.get('disabled'), label)
        point = self.app.screen.to_physical_point(rect.center)
        self.assertTrue(self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point)))

    def test_every_catalogue_item_reachable_with_visible_paging_controls(self):
        seen = set()
        original = self.app.shop_screen.product

        def product(rect, key, item):
            seen.add(key)
            return original(rect, key, item)

        with patch.object(self.app.shop_screen, 'product', side_effect=product):
            for _ in range(len(SHOP)):
                self.render()
                for _, rect, _, _ in self.controls:
                    self.assertTrue(self.app.screen.get_rect().contains(rect), rect)
                if self.control('Next')[3].get('disabled'):
                    break
                self.click('Next')
            else:
                self.fail('Shop paging never reached the final item')
        self.assertEqual(seen, set(SHOP))
        self.assertGreater(self.app.scroll, 0)
        self.click('Previous')
        self.assertLess(self.app.scroll, len(SHOP))

    def test_feed_selects_farm_resident_without_sending_capsule_action(self):
        self.app.shop_screen.filter('digimeat')
        self.app.farm_screen = SimpleNamespace(open_manager=Mock(), home_confirmation=False)
        with patch.object(self.app, 'send') as send:
            before = copy.deepcopy(self.app.state)
            self.render()
            self.click('Feed')
            self.app.farm_screen.open_manager.assert_called_once_with(item='digimeat_cam')
            send.assert_not_called()
            self.assertEqual(self.app.state, before)

    def test_farm_purchase_and_recovery_filters_preserve_item_protocol(self):
        with patch.object(self.app, 'send') as send:
            self.app.shop_screen.filter('digimeat')
            self.render()
            self.click('Buy')
            send.assert_called_with('shop', item='digimeat_cam', quantity=1)
            self.click('HP recovery')
            with patch.object(self.app.shop_screen, 'product', wraps=self.app.shop_screen.product) as products:
                self.render()
                self.assertEqual([call.args[1] for call in products.call_args_list], ['hp_s', 'hp_m', 'hp_l'])
            self.click('Use')
            send.assert_called_with('item', item='hp_s', party_index=0)
            self.app.state.update(in_farm=False, in_lab=False)
            self.render()
            self.assertTrue(self.control('Buy')[3]['disabled'])


if __name__ == '__main__':
    unittest.main()
