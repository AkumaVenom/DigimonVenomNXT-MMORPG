"""Pixel geometry, native text, input mapping and bounded scaling checks."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import unittest
import pygame
from venom.client.render import NativeCanvas, draw
from venom.client.widgets import UI, text, outlined_text


class Fonts:
    def __init__(self):
        self.fonts = {}
        self.requested = []

    def font(self, size=18, bold=False):
        self.requested.append((size, bold))
        if (size, bold) not in self.fonts:
            font = pygame.font.Font(None, size)
            font.set_bold(bold)
            self.fonts[size, bold] = font
        return self.fonts[size, bold]


class NativeRenderingTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((64, 64))
        self.assets = Fonts()

    def tearDown(self):
        pygame.quit()

    def test_native_font_pixels_match_rendering_at_actual_output_resolution(self):
        surface = pygame.Surface((900, 300), pygame.SRCALPHA)
        canvas = NativeCanvas(surface, 2.5)
        rect = text(canvas, self.assets, 'Digimon Venom NXT', (12, 16), size=24, bold=True)
        expected = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        glyphs = self.assets.font(60, True).render('Digimon Venom NXT', True, (231, 241, 249))
        expected.blit(glyphs, (30, 40))
        self.assertEqual(pygame.image.tobytes(surface, 'RGBA'), pygame.image.tobytes(expected, 'RGBA'))
        self.assertEqual(rect.topleft, (12, 16))
        self.assertIn((60, True), self.assets.requested)

    def test_logical_geometry_clip_and_fractional_scale_do_not_leave_seams(self):
        actual = pygame.Surface((500, 300))
        actual.fill('black')
        canvas = NativeCanvas(actual, 1.25)
        self.assertEqual(canvas.get_size(), (400, 240))
        self.assertEqual(canvas.to_physical_rect((7, 9, 13, 11)), pygame.Rect(9, 11, 16, 14))
        canvas.set_clip((4, 4, 20, 20))
        draw.rect(canvas, 'red', (0, 0, 100, 100))
        self.assertEqual(actual.get_at((5, 5)), pygame.Color('red'))
        self.assertEqual(actual.get_at((4, 5)), pygame.Color('black'))
        self.assertEqual(canvas.get_clip(), pygame.Rect(4, 4, 20, 20))
        canvas.set_clip(None)
        draw.rect(canvas, 'blue', (0, 30, 7, 5))
        draw.rect(canvas, 'green', (7, 30, 7, 5))
        for x in range(17):
            self.assertNotEqual(actual.get_at((x, 39)), pygame.Color('black'))

    def test_mouse_clicks_use_logical_coordinates_at_high_dpi(self):
        canvas = NativeCanvas(pygame.Surface((1200, 800)), 2.0)
        ui = UI(canvas, self.assets)
        ui.begin()
        clicked = []
        ui.button((20, 30, 100, 40), 'Apply', lambda: clicked.append(True))
        ui.field((20, 90, 150, 36), 'name')
        self.assertTrue(ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))))
        self.assertEqual(clicked, [True])
        self.assertTrue(ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 200))))
        self.assertEqual(ui.focus, 'name')
        self.assertFalse(ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(400, 200))))

    def test_pixel_art_nearest_scaling_and_native_blit(self):
        source = pygame.Surface((2, 2))
        source.fill('red')
        source.set_at((1, 0), 'blue')
        canvas = NativeCanvas(pygame.Surface((40, 40)), 3)
        canvas.blit(source, (2, 3))
        for x in range(6, 9):
            self.assertEqual(canvas.surface.get_at((x, 9)), pygame.Color('red'))
        for x in range(9, 12):
            self.assertEqual(canvas.surface.get_at((x, 9)), pygame.Color('blue'))
        canvas.blit_native(source, (5, 5))
        self.assertEqual(canvas.surface.get_at((15, 15)), pygame.Color('red'))
        self.assertEqual(canvas.surface.get_at((16, 15)), pygame.Color('blue'))

    def test_scaled_cache_is_bounded_and_mutable_sources_can_bypass_it(self):
        canvas = NativeCanvas(pygame.Surface((100, 100)), 2, cache_bytes=12000)
        for i in range(100):
            source = pygame.Surface((16, 16), pygame.SRCALPHA)
            source.fill((i, 0, 0))
            canvas.blit(source, (0, 0))
        self.assertLessEqual(canvas._cache_bytes, 12000)
        self.assertLessEqual(len(canvas._scaled), 2)
        source.fill('blue')
        canvas.blit(source, (0, 0), cache=False)
        self.assertEqual(canvas.surface.get_at((0, 0)), pygame.Color('blue'))
        canvas.invalidate(source)
        self.assertFalse(any(key[0] is source for key in canvas._scaled))
        canvas.set_surface(pygame.Surface((200, 200)), 2.5)
        self.assertEqual(canvas._cache_bytes, 0)

    def test_outlined_fading_text_keeps_cached_glyphs_immutable(self):
        canvas = NativeCanvas(pygame.Surface((800, 400), pygame.SRCALPHA), 2)
        outlined_text(canvas, self.assets, '148', (100, 50), size=34, alpha=80)
        faded = max(pygame.image.tobytes(canvas.surface, 'RGBA')[3::4])
        self.assertGreater(faded, 0)
        canvas.surface.fill((0, 0, 0, 0))
        outlined_text(canvas, self.assets, '148', (100, 50), size=34, alpha=255)
        self.assertEqual(max(pygame.image.tobytes(canvas.surface, 'RGBA')[3::4]), 255)


if __name__ == '__main__':
    unittest.main()
