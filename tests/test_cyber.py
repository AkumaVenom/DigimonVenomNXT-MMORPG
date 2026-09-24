"""Native circuit cache, bounded numeric animation and clipping regressions."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from venom.client.assets import Assets
from venom.client.cyber import CyberBackdrop
from venom.client.render import NativeCanvas


class CyberBackdropTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((32, 32))
        self.app = SimpleNamespace(now=4.5, assets=Assets(Path('/nonexistent')),
                                   screen=NativeCanvas(pygame.Surface((960, 600)).convert(), 1.))
        self.cyber = CyberBackdrop(self.app)

    def tearDown(self):
        pygame.quit()

    def test_native_static_cache_is_reused_until_display_or_dpi_changes(self):
        self.cyber.draw()
        first = self.cyber._background_surface
        self.assertEqual(first.get_size(), (960, 600))
        expected = pygame.image.tobytes(self.app.screen.surface, 'RGB')
        with patch.object(self.cyber, '_paint_static', side_effect=AssertionError('per-frame rebuild')):
            self.app.screen.fill('red')
            self.cyber.draw()
        self.assertIs(self.cyber._background_surface, first)
        self.assertEqual(pygame.image.tobytes(self.app.screen.surface, 'RGB'), expected)
        self.app.screen = NativeCanvas(pygame.Surface((1920, 1080)).convert(), 1.25)
        self.cyber.draw()
        second = self.cyber._background_surface
        self.assertIsNot(first, second)
        self.assertEqual(second.get_size(), (1920, 1080))
        self.app.screen.scale = 1.5
        self.cyber.draw()
        self.assertIsNot(second, self.cyber._background_surface)
        self.assertLessEqual(self.cyber.cache_bytes, self.cyber.CACHE_BYTES)

    def test_4k_art_and_glyphs_are_drawn_at_native_resolution(self):
        self.app.screen = NativeCanvas(pygame.Surface((3840, 2160)).convert(), 2.5)
        self.cyber.draw()
        self.assertEqual(self.cyber._background_surface.get_size(), (3840, 2160))
        glyph = self.cyber._glyph('8', (88, 183, 211), 91)
        expected = self.app.assets.font(round(9*2.5)).render('8', True, (88, 183, 211))
        self.assertEqual(glyph.get_size(), expected.get_size())
        self.assertLessEqual(self.cyber.cache_bytes, 64*1024*1024)

    def test_rain_preserves_exact_physical_clip_at_fractional_dpi(self):
        target = pygame.Surface((1000, 700)).convert()
        target.fill((9, 17, 24))
        self.app.screen = NativeCanvas(target, 1.25)
        clip = pygame.Rect(101, 91, 803, 511)
        target.set_clip(clip)
        self.cyber.rain((40, 40, 720, 480), 'rivals')
        self.assertEqual(target.get_clip(), clip)
        self.assertEqual(target.get_at((50, 80)), (9, 17, 24, 255))
        with patch.object(self.cyber, '_glyph', side_effect=RuntimeError('render error')):
            # Place a visible stream inside the existing clip.
            self.app.now = 20.
            with self.assertRaises(RuntimeError):
                self.cyber.rain((80, 60, 600, 420), 'rivals')
        self.assertEqual(target.get_clip(), clip)

    def test_themed_code_does_not_touch_content_or_pixels_outside_shell(self):
        target = self.app.screen.surface
        target.fill((15, 23, 37))
        rect = pygame.Rect(80, 40, 700, 480)
        before = pygame.image.tobytes(target.subsurface(rect.inflate(-36, 0)), 'RGB')
        for seconds in (1., 3., 5., 7., 9.):
            self.app.now = seconds
            self.cyber.rain(rect, 'activity')
        self.assertEqual(pygame.image.tobytes(target.subsurface(rect.inflate(-36, 0)), 'RGB'), before)
        self.assertEqual(target.get_at((10, 10)), (15, 23, 37, 255))
        self.assertEqual(target.get_at((rect.left-1, rect.centery)), (15, 23, 37, 255))

    def test_numeric_animation_depends_on_elapsed_time_not_frame_count(self):
        target = self.app.screen.surface
        target.fill((9, 17, 24))
        rect = pygame.Rect(0, 0, 960, 600)
        self.app.now = 3.
        self.cyber.rain(rect)
        first = pygame.image.tobytes(target, 'RGB')
        target.fill((9, 17, 24))
        self.cyber.rain(rect)
        self.assertEqual(pygame.image.tobytes(target, 'RGB'), first)
        target.fill((9, 17, 24))
        self.app.now = 4.
        self.cyber.rain(rect)
        self.assertNotEqual(pygame.image.tobytes(target, 'RGB'), first)
        self.assertTrue(self.cyber._glyphs)
        self.assertTrue(all(key[1] in '0123456789' for key in self.cyber._glyphs))

    def test_cache_budget_survives_themes_scales_and_oversized_output(self):
        self.cyber.GLYPH_CACHE_BYTES = 4096
        self.cyber.GLYPH_CACHE_ITEMS = 20
        for scale in (1., 1.25, 2., 2.5):
            self.app.screen.scale = scale
            for theme in (None, 'shop', 'rivals', 'ranked', 'activity'):
                for seconds in (1., 4., 9., 14.):
                    self.app.now = seconds
                    self.cyber.rain(self.app.screen.get_rect(), theme)
        self.assertLessEqual(self.cyber._glyph_bytes, 4096)
        self.assertLessEqual(len(self.cyber._glyphs), 20)
        self.cyber.CACHE_BYTES = 16384
        self.cyber.draw()
        self.assertIsNone(self.cyber._background_surface)
        self.assertLessEqual(self.cyber.cache_bytes, self.cyber.CACHE_BYTES)

    def test_empty_or_fully_clipped_rain_does_no_rendering(self):
        with patch.object(self.cyber, '_glyph') as glyph:
            self.cyber.rain((0, 0, 0, 10))
            self.cyber.rain((2000, 2000, 10, 10))
            glyph.assert_not_called()


if __name__ == '__main__':
    unittest.main()
