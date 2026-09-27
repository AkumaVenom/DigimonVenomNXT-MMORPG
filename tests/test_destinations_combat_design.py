"""Actual native input contracts for atlas transfers and battle command decks."""
import copy
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import unittest
from unittest.mock import patch
import pygame

from tools.preview_ui_screens import ROOT, make_app
from venom.client.destinations import WorldScreen
from venom.client.combat_menu import CombatMenu
from venom.client.render import NativeCanvas
from venom.common.game import GameEngine


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class DestinationsCombatTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app('1180x800')
        self.addCleanup(pygame.quit)
        if not hasattr(self.app, 'close_menu'):
            self.app.close_menu = lambda:setattr(self.app, 'menu', None)
        self.world = WorldScreen(self.app)
        self.combat = CombatMenu(self.app)
        self.buttons = []
        original = self.app.ui.button
        def capture(rect, label, callback, *args, **kwargs):
            self.buttons.append((label, pygame.Rect(rect), kwargs))
            return original(rect, label, callback, *args, **kwargs)
        wrapped = patch.object(self.app.ui, 'button', side_effect=capture)
        wrapped.start()
        self.addCleanup(wrapped.stop)

    def render(self, kind='maps'):
        self.app.ui.begin()
        self.buttons.clear()
        self.app.menu = kind
        w, h = self.app.screen.get_size()
        rect = pygame.Rect(20, 98, w-40, h-118)
        if kind == 'maps':
            self.world.draw(rect)
        else:
            self.combat.draw(rect, kind)
        return rect

    def click(self, label, index=0):
        matches = [(rect, options) for name, rect, options in self.buttons if name == label]
        self.assertGreater(len(matches), index, f'Missing {label}')
        rect, options = matches[index]
        self.assertFalse(options.get('disabled'))
        point = self.app.screen.to_physical_point(rect.center)
        self.assertTrue(self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point)))

    def battle(self):
        party = self.app.state['party']
        self.app.state['party'] = [copy.deepcopy(party[i % len(party)]) for i in range(6)]
        for index, mon in enumerate(self.app.state['party']):
            mon.update(name=f'Partner {index+1}', skills=GameEngine._skills(mon), sp=30, max_sp=42)
        self.app.state['battle'] = {'actor':2, 'active':[0,1,2], 'turn':9,
                                    'enemies':copy.deepcopy(self.app.state['party'][:3])}
        self.app.target = 1

    def test_transfer_search_paging_and_lab_gates_preserve_server_contract(self):
        with patch.object(self.app, 'send') as send:
            self.render()
            self.click('Transfer')
            destination = list(self.app.assets.maps.values())[1]['id']
            send.assert_called_once_with('travel', map_id=destination)
            self.click('Next')
            self.assertGreater(self.app.scroll, 0)
            self.render()
            self.click('Previous')
            self.assertEqual(self.app.scroll, 0)
            self.app.ui.values['world_search'] = destination
            self.render()
            self.assertEqual(len([name for name, _, _ in self.buttons if name == 'Transfer']), 1)
            self.app.state['in_lab'] = True
            self.render()
            self.assertTrue(next(options['disabled'] for name, _, options in self.buttons if name == 'Transfer'))
            self.world.transfer(destination)
            send.assert_called_once()
            self.click('Return from DigiLab')
            send.assert_called_with('digilab', action='return')
            self.app.state['in_lab'] = False
            self.app.action_pending = True
            self.world.transfer(destination)
            self.assertEqual(send.call_count, 2)

    def test_native_thumbnail_cache_preserves_aspect_and_avoids_reloading(self):
        self.render()
        with patch.object(self.app.assets, 'image', wraps=self.app.assets.image) as image:
            self.render()
            paths = [call.args[0] for call in image.call_args_list]
            self.assertFalse(any(str(path).startswith('assets/maps/') for path in paths))
        for (path, size), surface in self.world._thumbnails.items():
            entry = next(entry for entry in self.app.assets.maps.values() if entry['path'] == path)
            self.assertLessEqual(surface.get_width(), size[0])
            self.assertLessEqual(surface.get_height(), size[1])
            self.assertAlmostEqual(surface.get_width()/surface.get_height(), entry['width']/entry['height'], delta=.06)
        self.assertLessEqual(self.world._thumbnail_bytes, self.world.THUMBNAIL_BYTES)
        self.assertLessEqual(len(self.world._thumbnails), self.world.THUMBNAIL_ITEMS)

    def test_skill_command_uses_current_actor_target_and_authoritative_index(self):
        self.battle()
        before = copy.deepcopy(self.app.state)
        with patch.object(self.app, 'send') as send:
            self.render('skills')
            self.click('Use skill', 1)
            send.assert_called_once_with('battle', action='skill', target=1, party_index=2, skill_index=1)
            self.assertIsNone(self.app.menu)
            self.assertEqual(self.app.state, before)
            self.app.state['party'][2]['sp'] = 0
            self.render('skills')
            for label, _, options in self.buttons:
                if label == 'Not enough SP':
                    self.assertTrue(options['disabled'])
            self.combat.cast(0)
            self.assertEqual(send.call_count, 1)
            self.app.state['party'][2]['sp'] = 42
            self.app.animations = [{}]
            self.render('skills')
            self.combat.cast(0)
            self.assertEqual(send.call_count, 1)

    def test_enemy_selection_and_all_six_item_recipients_accept_native_clicks(self):
        self.battle()
        self.render('skills')
        targets = [rect for rect, callback in self.app.ui.actions if getattr(callback, '__name__', '') == '<lambda>']
        # The three target cards are appended after the skill and navigation buttons.
        target_card = targets[-1]
        self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                            pos=self.app.screen.to_physical_point(target_card.center)))
        self.assertEqual(self.app.target, 2)
        self.render('battle_items')
        self.assertEqual(len([label for label, _, _ in self.buttons if label == 'Use capsule']), 6)
        recipient = self.app.ui.actions[-1][0]
        self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                            pos=self.app.screen.to_physical_point(recipient.center)))
        self.assertEqual(self.app.selected_party, 5)
        with patch.object(self.app, 'send') as send:
            self.click('Use capsule')
            send.assert_called_once_with('battle', action='item', target=2, party_index=5, item='hp_s')
            self.assertIsNone(self.app.menu)

    def test_commands_and_fields_fit_minimum_and_native_4k_display(self):
        self.battle()
        for physical, scale in (((1180,800), 1.), ((3840,2160), 2.5)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(physical), scale)
            self.app.ui.screen = self.app.screen
            for kind in ('maps', 'skills', 'battle_items'):
                with self.subTest(physical=physical, kind=kind):
                    bounds = self.render(kind)
                    for rect, _ in self.app.ui.actions+self.app.ui.fields:
                        self.assertTrue(bounds.contains(rect), (bounds, rect))
                        self.assertGreater(min(rect.size), 0)
        self.assertFalse(self.app.assets.errors)

    def test_zero_sp_attack_bar_fills_available_space_without_an_extra_command(self):
        self.battle()
        self.app.state['party'][2]['sp'] = 0
        self.app.animations = []
        self.app.action_pending = False
        for physical, scale in (((960,600), 1.), ((1280,800), 1.), ((3840,2160), 2.5)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(physical), scale)
            self.app.ui.screen = self.app.screen
            w, h = self.app.screen.get_size()
            self.app.viewport = pygame.Rect(20, 94, w-352, h-262)
            for kind in ('wild', 'story', 'season'):
                with self.subTest(physical=physical, kind=kind):
                    self.app.state['battle']['kind'] = kind
                    self.app.ui.begin()
                    self.buttons.clear()
                    self.app.draw_battle()
                    expected = ['Attack', 'Skill · SP', 'Items'] + (['Flee'] if kind == 'wild' else [])
                    self.assertEqual([label for label, _, _ in self.buttons], expected)
                    rects = [rect for _, rect, _ in self.buttons]
                    self.assertTrue(all(self.app.viewport.contains(rect) for rect in rects))
                    self.assertTrue(all(not options.get('disabled') for _, _, options in self.buttons))
                    self.assertTrue(all(rect.width == rects[0].width for rect in rects))
                    self.assertTrue(all(right.left - left.right == 8 for left, right in zip(rects, rects[1:])))
                    self.assertLessEqual(abs((rects[0].left - self.app.viewport.left)
                                             - (self.app.viewport.right - rects[-1].right)), len(rects)-1)
                    with patch.object(self.app, 'send') as send:
                        self.click('Attack')
                        send.assert_called_once_with('battle', action='attack', target=1, party_index=2)

    def test_close_works_during_battle_and_busy_commands_do_not_send(self):
        self.battle()
        self.app.action_pending = True
        with patch.object(self.app, 'send') as send:
            self.render('battle_items')
            self.combat.use('hp_s')
            self.combat.cast(0)
            send.assert_not_called()
            self.click('Battle  Esc')
            self.assertIsNone(self.app.menu)


if __name__ == '__main__':
    unittest.main()
