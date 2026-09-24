"""Exercise native display changes through the actual app event routing."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import pygame
from venom.client.app import App
from venom.common.paths import root_path


@unittest.skipUnless((root_path() / 'data/catalog.json').exists(), 'Imported game assets required')
class NativeDisplayIntegrationTests(unittest.TestCase):
    def setUp(self):
        args = SimpleNamespace(dev=False, demo=True, demo_battle=False, config=None,
                               frames=0, screenshot=None, size=(3840, 2160))
        self.app = App(root_path(), args)

    def tearDown(self):
        pygame.quit()

    def click(self, position):
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)
        consumed = self.app.ui.event(event)
        if not consumed:
            self.app.key(event)
        return consumed

    def test_4k_settings_clicks_change_zoom_and_frame_cap_at_displayed_positions(self):
        controls = []
        original_button = self.app.ui.button

        def capture(rect, label, callback, *args, **kwargs):
            controls.append((str(label), pygame.Rect(rect), callback))
            return original_button(rect, label, callback, *args, **kwargs)

        def render():
            controls.clear()
            with patch.object(self.app.ui, 'button', side_effect=capture):
                self.app.draw()

        def click_control(label, index=0):
            # Covered and disabled controls are excluded by the real action list.
            active = [rect for name, rect, callback in controls if name == label
                      and any(action is callback for _, action in self.app.ui.actions)]
            self.assertGreater(len(active), index, f'Missing displayed control: {label}')
            physical = self.app.screen.to_physical_point(active[index].center)
            self.assertTrue(self.click(physical))

        render()
        click_control('Settings')
        self.assertTrue(self.app.settings_open)
        render()
        click_control('+', 2)  # Music, effects, then world zoom in the modal.
        self.assertEqual(self.app.world.zoom, 1.5)
        render()
        click_control('144')
        self.assertEqual(self.app.display.settings['fps'], 144)
        self.assertEqual(self.app.display.surface.get_size(), (3840, 2160))

    def test_settings_modal_blocks_world_clicks_and_gameplay_shortcuts(self):
        self.app.ui.focus = 'chat'
        self.app.toggle_settings()
        self.app.draw()
        self.assertIsNone(self.app.ui.focus)
        send = Mock()
        with patch.object(self.app, 'send', send):
            # The visible, dimmed DigiLab button must not remain clickable.
            self.assertFalse(self.click((2850, 95)))
            for key in (pygame.K_F1, pygame.K_e, pygame.K_b, pygame.K_m, pygame.K_PLUS):
                self.app.key(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
        send.assert_not_called()
        self.assertIsNone(self.app.menu)
        self.assertEqual(self.app.world.zoom, 1)
        self.app.key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
        self.assertFalse(self.app.settings_open)

    def test_global_fullscreen_and_settings_keys_work_while_typing(self):
        self.app.ui.focus = 'chat'
        self.app.args.frames = 1
        pygame.event.clear()
        for key, mod in ((pygame.K_F11, 0), (pygame.K_RETURN, pygame.KMOD_ALT), (pygame.K_F10, 0)):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))
        final = {}
        original_draw = self.app.draw

        def capture_draw():
            original_draw()
            final.update(size=self.app.display.surface.get_size(),
                         ui_surface=self.app.ui.screen.surface,
                         display_surface=self.app.display.surface)

        with patch.object(self.app, 'draw', capture_draw):
            self.app.run()
        self.assertFalse(self.app.display.fullscreen)
        self.assertEqual(self.app.display.window_size, (3840, 2160))
        self.assertEqual(final['size'], (3840, 2160))
        self.assertIs(final['ui_surface'], final['display_surface'])
        self.assertTrue(self.app.settings_open)
        self.assertIsNone(self.app.ui.focus)


if __name__ == '__main__':
    unittest.main()
