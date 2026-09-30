"""Native account and settings contracts: real input, modal ownership and bounds."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch
import unittest

import pygame

from venom.client.app import App
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class EntrySettingsDesignTests(unittest.TestCase):
    def setUp(self):
        self.app = App(ROOT, SimpleNamespace(demo=True, demo_battle=False, dev=False,
                                             config=None, frames=0, screenshot=None,
                                             size=(1180, 800)))
        self.addCleanup(pygame.quit)
        self.app.state = None
        self.app.connection = SimpleNamespace(connected=True)
        self.app.status = 'Server connected. Sign in or create your tamer.'
        self.buttons = []
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        original = self.app.ui.button
        def capture(rect, label, callback, **kwargs):
            self.buttons.append((str(label), pygame.Rect(rect), callback, kwargs))
            return original(rect, label, callback, **kwargs)
        self.patches.enter_context(patch.object(self.app.ui, 'button', side_effect=capture))

    def render(self, settings=False):
        self.buttons.clear()
        self.app.ui.begin()
        self.app.draw_background()
        self.app.entry_screen.draw()
        if settings:
            self.app.settings_panel.draw()

    def control(self, label, index=0):
        found = [entry for entry in self.buttons if entry[0] == label]
        self.assertGreater(len(found), index, (label, [entry[0] for entry in self.buttons]))
        return found[index]

    def click(self, label, index=0):
        _, rect, _, options = self.control(label, index)
        self.assertFalse(options.get('disabled'), label)
        self.assertTrue(self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
            button=1, pos=self.app.screen.to_physical_point(rect.center))))

    def test_auth_payload_validation_and_pending_controls_preserved(self):
        send = self.patches.enter_context(patch.object(self.app, 'send'))
        self.app.ui.values.update(username=' UI_Tamer ', password='EightChars!')
        self.render()
        self.click('Enter the Digital World')
        send.assert_called_once_with('login', username='UI_Tamer', password='EightChars!')
        self.click('Create account')
        self.render()
        self.click('Begin your adventure')
        send.assert_called_with('register', username='UI_Tamer', password='EightChars!',
                                tamer=self.app.tamer, starter=self.app.starter)
        count = send.call_count
        self.app.ui.values['username'] = 'invalid user'
        self.click('Begin your adventure')
        self.assertEqual(count, send.call_count)
        self.assertIn('3–24', self.app.status)
        self.app.auth_pending = True
        self.render()
        for label in ('Connecting…', 'Reconnect', 'Sign in', 'Create account'):
            self.assertTrue(self.control(label)[3]['disabled'])
        self.app.auth_pending = False
        self.app.connection.connected = False
        self.render()
        self.assertTrue(self.control('Begin your adventure')[3]['disabled'])
        self.assertEqual([key for _, key in self.app.ui.fields], ['username', 'password'])

    def test_picker_owns_input_selects_real_identifier_and_clears_focus(self):
        self.app.auth_tab = 'register'
        self.app.open_picker('starter')
        expected = next(s for s in self.app.assets.species.values()
                        if s.get('stage') == 'rookie' and not s.get('paradox') and not s.get('shiny')
                        and s['id'] != self.app.starter)
        self.app.ui.values['search'] = expected['name']
        self.render()
        self.assertEqual([key for _, key in self.app.ui.fields], ['search'])
        # The one large partner card owns the same physical click path as buttons.
        card = next(rect for rect, _ in self.app.ui.actions if rect.height > 100)
        self.app.ui.focus = 'search'
        self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                           pos=self.app.screen.to_physical_point(card.center)))
        self.assertEqual(self.app.starter, expected['id'])
        self.assertIsNone(self.app.auth_picker)
        self.assertIsNone(self.app.ui.focus)
        self.assertFalse(self.app.ui.fields)
        self.app.open_picker('tamer')
        self.app.ui.values['search'] = '__no_such_tamer__'
        self.render()
        self.assertFalse(any(rect.height > 100 for rect, _ in self.app.ui.actions))
        self.click('Close')
        self.assertIsNone(self.app.auth_picker)

    def test_every_front_end_view_keeps_targets_in_native_bounds(self):
        for size in ((1180, 800), (2048, 1152), (3840, 2160)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(size), effective_ui_scale(size))
            self.app.ui.screen = self.app.screen
            for mode in ('login', 'register', 'tamer', 'starter', 'settings'):
                with self.subTest(size=size, mode=mode):
                    self.app.auth_tab = 'login' if mode == 'login' else 'register'
                    self.app.auth_picker = mode if mode in ('tamer', 'starter') else None
                    self.render(settings=mode == 'settings')
                    bounds = self.app.screen.get_rect()
                    for rect, _ in self.app.ui.actions+self.app.ui.fields:
                        self.assertTrue(bounds.contains(rect), (rect, bounds))
                        self.assertGreater(rect.width, 0)
                        self.assertGreater(rect.height, 0)
        self.assertFalse(self.app.assets.errors, self.app.assets.errors)

    def test_settings_modal_blocks_form_and_retains_all_display_controls(self):
        apply = self.patches.enter_context(patch.object(self.app, 'apply_display'))
        self.app.settings_open = True
        self.render(settings=True)
        self.assertFalse(self.app.ui.fields)
        form_field = pygame.Rect(self.app.screen.get_width()-486-36+28, 246, 430, 44)
        self.assertFalse(any(rect == form_field for rect, _ in self.app.ui.actions))
        for label, key, value in (('Windowed', 'fullscreen', False),
                                  ('Fullscreen · F11', 'fullscreen', True),
                                  ('2560 × 1440', 'window_size', [2560,1440]),
                                  ('175%', 'ui_scale', 1.75), ('Auto', 'ui_scale', 'auto'),
                                  ('240', 'fps', 240), ('FPS counter: Off', 'show_fps', True)):
            self.click(label)
            apply.assert_called_with(**{key: value})
        self.app.display.settings['music_volume'] = .98
        self.click('+', 0)
        apply.assert_called_with(music_volume=1.)
        self.app.display.settings['effects_volume'] = .01
        self.click('−', 1)
        apply.assert_called_with(effects_volume=0.)
        self.app.world.set_zoom(1)
        self.render(settings=True)
        self.assertTrue(self.control('−', 2)[3]['disabled'])
        self.app.world.set_zoom(8)
        self.render(settings=True)
        self.assertTrue(self.control('+', 2)[3]['disabled'])
        save = self.patches.enter_context(patch.object(self.app.display, 'save'))
        self.click('Done')
        self.assertFalse(self.app.settings_open)
        save.assert_called_once_with()
        self.assertFalse(self.app.ui.actions)

    def test_settings_window_sizes_disabled_in_fullscreen_and_warnings_render(self):
        self.patches.enter_context(patch.object(type(self.app.display), 'fullscreen',
                                               new_callable=PropertyMock, return_value=True))
        self.app.display.warning = 'Saved preferences could not be read. Defaults restored.'
        self.render(settings=True)
        for label in ('1280 × 800', '1920 × 1080', '2560 × 1440', '3840 × 2160'):
            self.assertTrue(self.control(label)[3]['disabled'])
        first = self.app.settings_panel._overlay
        self.render(settings=True)
        self.assertIs(first, self.app.settings_panel._overlay)


if __name__ == '__main__':
    unittest.main()
