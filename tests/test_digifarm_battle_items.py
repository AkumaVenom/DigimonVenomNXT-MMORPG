"""The expanded shop must never offer farm-only food as a battle capsule."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from venom.client.combat_menu import CombatMenu
from venom.common.game import SHOP


class DigiFarmBattleItemsTests(unittest.TestCase):
    def test_scrolling_expanded_catalog_still_offers_only_recovery_items(self):
        colors = {'muted': (120, 120, 120), 'accent': (0, 200, 255)}
        app = SimpleNamespace(
            presentation=Mock(colors=Mock(return_value=colors)),
            shop_data=lambda: SHOP, scroll=100, screen=Mock(), assets=Mock(),
            state={'inventory': {key: 1 for key in SHOP}, 'party': [{}]},
            action_pending=False, animations=[], ui=Mock(),
        )
        menu = CombatMenu(app)
        with patch('venom.client.combat_menu.text') as text, patch.object(menu, 'use') as use:
            menu.items(pygame.Rect(0, 0, 900, 600))
            # A scroll offset left by another screen must not expose the meats.
            self.assertEqual(app.scroll, 0)
            buttons = app.ui.button.call_args_list
            self.assertEqual(len(buttons), 6)
            for button in buttons:
                self.assertEqual(button.args[1], 'Use capsule')
                button.args[2]()
            self.assertEqual([call.args[0] for call in use.call_args_list],
                             ['hp_s', 'hp_m', 'hp_l', 'sp_s', 'sp_m', 'sp_l'])
            captions = [str(call.args[2]) for call in text.call_args_list]
            self.assertFalse(any('DigiMeat' in caption for caption in captions))


if __name__ == '__main__':
    unittest.main()
