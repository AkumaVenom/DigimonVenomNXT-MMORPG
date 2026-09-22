"""Display guarantees: native pixels, full-screen restoration, and safe persistence."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch, PropertyMock
import xml.etree.ElementTree as ET

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import pygame
from venom.client.display import DisplayManager, effective_ui_scale, validate_settings


class NativeDisplayTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / 'display.json'

    def tearDown(self):
        pygame.quit()
        self.directory.cleanup()

    def display(self, **options):
        args = dict(demo=True, frames=0, settings=str(self.path))
        args.update(options)
        return DisplayManager(Path(self.directory.name), SimpleNamespace(**args))

    def test_4k_is_a_native_framebuffer_and_ui_scale_does_not_resize_it(self):
        display = self.display(size=(3840, 2160))
        self.assertEqual(display.surface.get_size(), (3840, 2160))
        self.assertFalse(display.surface.get_flags() & pygame.SCALED)
        self.assertEqual(display.ui_scale, 2.5)
        display.apply(ui_scale=2)
        self.assertEqual(display.ui_scale, 2)
        self.assertEqual(display.surface.get_size(), (3840, 2160))
        self.assertEqual(effective_ui_scale((1920, 1080)), 1.25)
        self.assertLessEqual(effective_ui_scale((960, 600), 3), 0.75)

    def test_borderless_fullscreen_restores_windowed_geometry(self):
        display = self.display(size=(1440, 900))
        desktop = pygame.display.get_desktop_sizes()[0]
        display.toggle_fullscreen()
        self.assertTrue(display.fullscreen)
        self.assertEqual(display.surface.get_size(), desktop)
        self.assertEqual(display.window_size, (1440, 900))
        # Fullscreen resize notifications must not overwrite remembered geometry.
        display.resize(desktop)
        display.toggle_fullscreen()
        self.assertFalse(display.fullscreen)
        self.assertEqual(display.surface.get_size(), (1440, 900))
        display.resize((1920, 1080))
        display.toggle_fullscreen()
        display.toggle_fullscreen()
        self.assertEqual(display.surface.get_size(), (1920, 1080))

    def test_explicit_preview_settings_persist_and_ignore_non_settings(self):
        display = self.display()
        display.apply(ui_scale=1.25, zoom=8, fps=144, show_fps=True,
                      music_volume=0, effects_volume=.5, password='do-not-write')
        self.assertTrue(display.save())
        saved = json.loads(self.path.read_text())
        self.assertNotIn('password', saved)
        again = self.display()
        self.assertEqual(again.settings['zoom'], 8)
        self.assertEqual(again.settings['fps'], 144)
        self.assertTrue(again.settings['show_fps'])
        self.assertEqual(again.settings['music_volume'], 0)
        self.assertEqual(again.settings['effects_volume'], .5)
        self.assertFalse(list(self.path.parent.glob('.display-*.tmp')))

    def test_corrupt_settings_recover_and_nonexplicit_preview_never_saves(self):
        self.path.write_text('{partial')
        display = self.display()
        self.assertEqual(display.window_size, (1280, 800))
        self.assertTrue(display.warning)
        preview = self.display(settings=None)
        preview.settings_path = self.path
        self.assertFalse(preview.save())
        self.assertEqual(self.path.read_text(), '{partial')
        checked = validate_settings({'window_size': [float('nan'), 800], 'ui_scale': float('inf'),
                                     'fps': 999999, 'zoom': float('nan'), 'fullscreen': 'yes',
                                     'music_volume': -1, 'effects_volume': 7})
        self.assertEqual(checked['window_size'], [1280, 800])
        self.assertEqual(checked['ui_scale'], 'auto')
        self.assertEqual(checked['fps'], 120)
        self.assertEqual(checked['zoom'], 1)
        self.assertFalse(checked['fullscreen'])
        self.assertEqual(checked['music_volume'], 0)
        self.assertEqual(checked['effects_volume'], 1)

    def test_saved_and_interactive_sizes_fit_monitor_but_explicit_qa_size_wins(self):
        self.path.write_text(json.dumps({'window_size': [3840, 2160]}))
        with patch('pygame.display.get_driver', return_value='windows'), \
             patch('pygame.display.get_desktop_sizes', return_value=[(1920, 1080)]), \
             patch.object(DisplayManager, 'maximum_window_size', new_callable=PropertyMock, return_value=(1872, 1000)):
            restored = self.display()
            self.assertEqual(restored.surface.get_size(), (1872, 1000))
            explicit = self.display(size=(3840, 2160))
            self.assertEqual(explicit.surface.get_size(), (3840, 2160))
            explicit.apply(window_size=(3840, 2160))
            self.assertEqual(explicit.surface.get_size(), (1872, 1000))
            self.assertEqual(explicit.window_size, (1872, 1000))

    def test_windows_manifest_disables_bitmap_virtualization_without_elevation(self):
        root = Path(__file__).resolve().parents[1]
        manifest = ET.parse(root / 'tools/windows_client.manifest').getroot()
        awareness = manifest.find('.//{http://schemas.microsoft.com/SMI/2016/WindowsSettings}dpiAwareness')
        execution = manifest.find('.//{urn:schemas-microsoft-com:asm.v3}requestedExecutionLevel')
        self.assertIn('PerMonitorV2', awareness.text)
        self.assertEqual(execution.attrib['level'], 'asInvoker')


if __name__ == '__main__':
    unittest.main()
