"""Rendering cost must stay bounded without reducing pixels or rival population."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pygame

from venom.client.world import WorldRenderer


class WorldPerformanceTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((32, 32))
        self.screen = pygame.Surface((800, 600))
        self.app = SimpleNamespace(screen=self.screen, position=pygame.Vector2(768, 384))
        self.renderer = WorldRenderer(self.app)
        self.viewport = pygame.Rect(70, 80, 640, 400)
        self.renderer.camera.zoom = 3.25
        self.renderer.camera.configure((1536, 768), self.viewport, self.app.position)
        self.screen.set_clip(self.viewport)

    def tearDown(self):
        pygame.quit()

    def test_scrolling_reuses_native_resolution_layer_instead_of_resampling_each_frame(self):
        source = pygame.Surface((1536, 768))
        source.fill('red')
        with patch.object(pygame.transform, 'scale', wraps=pygame.transform.scale) as scale:
            for _ in range(90):
                self.renderer.camera.center.x += .5
                self.renderer._draw_layer(source, 'background')
            self.assertEqual(scale.call_count, 1)
        cached = self.renderer._layers['background'][2]
        self.assertGreaterEqual(cached.get_width(), self.viewport.width)
        self.assertGreaterEqual(cached.get_height(), self.viewport.height)

    def test_fractional_scale_scroll_translates_pixels_exactly_within_cached_patch(self):
        source = pygame.Surface((1536, 768))
        source.fill((240, 20, 30))
        for x in range(0, 1536, 11):
            pygame.draw.line(source, (15, 220, 50), (x, 0), (x, 767), 4)
        for y in range(0, 768, 13):
            pygame.draw.line(source, (30, 40, 230), (0, y), (1535, y), 3)
        self.screen.fill((1, 2, 3))
        self.renderer._draw_layer(source, 'background')
        before, origin = self.screen.copy(), self.renderer.camera.origin
        self.renderer.camera.center += (7.25, 3.5)
        delta = self.renderer.camera.origin - origin
        self.screen.fill((1, 2, 3))
        self.renderer._draw_layer(source, 'background')
        overlap = self.viewport.clip(self.viewport.move(round(delta.x), round(delta.y)))
        previous = overlap.move(-round(delta.x), -round(delta.y))
        self.assertEqual(pygame.image.tobytes(self.screen.subsurface(overlap), 'RGB'),
                         pygame.image.tobytes(before.subsurface(previous), 'RGB'))
        self.assertEqual(self.screen.get_at((20, 20))[:3], (0, 0, 0))

    def test_zoom_resize_source_and_scroll_outside_margin_rebuild_layers(self):
        source = pygame.Surface((1536, 768))
        with patch.object(pygame.transform, 'scale', wraps=pygame.transform.scale) as scale:
            self.renderer._draw_layer(source, 'background')
            self.renderer.camera.center.x += 200
            self.renderer._draw_layer(source, 'background')
            self.renderer.camera.zoom = 4
            self.renderer._draw_layer(source, 'background')
            self.renderer.camera.viewport.width -= 20
            self.renderer._draw_layer(source, 'background')
            self.renderer._draw_layer(source.copy(), 'background')
            self.assertEqual(scale.call_count, 5)

    def test_maximum_zoom_cache_remains_view_sized_and_nearest_filtered(self):
        source = pygame.Surface((1536, 768))
        source.fill('red')
        pygame.draw.rect(source, 'blue', (768, 0, 768, 768))
        self.renderer.camera.zoom = 8
        self.renderer._draw_layer(source, 'background')
        _, crop, cached = self.renderer._layers['background']
        self.assertLess(crop.width, source.get_width() // 2)
        for axis, length in enumerate(cached.get_size()):
            self.assertLessEqual(length, self.viewport.size[axis]
                                 + 2 * self.renderer.LAYER_SCROLL_MARGIN
                                 + 4 * self.renderer.camera.scale + 2)
        palette = {(255, 0, 0), (0, 0, 255)}
        self.assertTrue(all(self.screen.get_at((x, self.viewport.centery))[:3] in palette
                            for x in range(self.viewport.left, self.viewport.right)))

    def test_foreground_alpha_and_layer_order_are_preserved(self):
        background = pygame.Surface((1536, 768))
        background.fill('red')
        foreground = pygame.Surface((1536, 768), pygame.SRCALPHA)
        foreground.fill((0, 0, 0, 0))
        pygame.draw.rect(foreground, (0, 0, 255, 128), (768, 0, 768, 768))
        self.renderer._draw_layer(background, 'background')
        self.renderer._draw_layer(foreground, 'foreground')
        self.assertEqual(self.screen.get_at((self.viewport.left + 20, self.viewport.centery))[:3], (255, 0, 0))
        self.assertEqual(self.screen.get_at((self.viewport.right - 20, self.viewport.centery))[:3], (127, 0, 128))

    def test_panning_to_all_map_edges_leaves_no_holes_or_draws_outside_clip(self):
        source = pygame.Surface((1536, 768))
        source.fill('red')
        for zoom in (1.5, 3.25, 8):
            self.renderer.camera.zoom = zoom
            for target in ((0, 0), (1536, 0), (0, 768), (1536, 768), (768, 384)):
                self.renderer.camera.center.update(target)
                self.renderer.camera._clamp()
                self.screen.fill('black')
                self.renderer._draw_layer(source, 'background')
                expected = pygame.Surface(self.viewport.size)
                expected.fill('red')
                self.assertEqual(pygame.image.tobytes(self.screen.subsurface(self.viewport), 'RGB'),
                                 pygame.image.tobytes(expected, 'RGB'))
                self.assertEqual(self.screen.get_at((self.viewport.left - 1, self.viewport.centery))[:3], (0, 0, 0))

    def test_hundreds_of_small_actor_sprites_do_not_thrash_the_byte_bounded_cache(self):
        sources = [pygame.Surface((8, 8), pygame.SRCALPHA) for _ in range(400)]
        with patch.object(pygame.transform, 'scale', wraps=pygame.transform.scale) as scale:
            for source in sources:
                self.renderer._scale_sprite(source, 2)
            for source in sources:
                self.renderer._scale_sprite(source, 2)
            self.assertEqual(scale.call_count, len(sources))
        self.assertLessEqual(self.renderer._sprite_bytes, self.renderer.SPRITE_CACHE_BYTES)
        self.assertEqual(len(self.renderer._sprites), len(sources))
        self.renderer.SPRITE_CACHE_BYTES = 5000
        self.renderer._scale_sprite(pygame.Surface((9, 9)), 2)
        self.assertLessEqual(self.renderer._sprite_bytes, 5000)

    def test_native_size_sprites_need_no_extra_surface(self):
        source = pygame.Surface((8, 8), pygame.SRCALPHA)
        with patch.object(pygame.transform, 'scale', wraps=pygame.transform.scale) as scale:
            self.assertIs(self.renderer._scale_sprite(source, 1), source)
            scale.assert_not_called()

    def test_all_rivals_and_companions_remain_in_depth_sorted_actor_list(self):
        self.app.state = {'map_id': 'map', 'username': 'Player', 'party': []}
        self.app.tamer, self.app.direction, self.app.moving = 'tamer', 'down', False
        self.app.players = {
            f'Rival {i}': {'id': f'bot:{i}', 'is_bot': True, 'map_id': 'map',
                          'tamer': 'tamer', 'lead': 'agumon', 'x': i * 10, 'y': i * 5}
            for i in range(400)
        }
        self.app.player_render = {}
        actors = self.renderer._actors()
        self.assertEqual(len(actors), 801)
        self.assertEqual(len([row for row in actors if row[-1] is not None]), 400)
        self.assertEqual([row[0] for row in actors], sorted(row[0] for row in actors))


if __name__ == '__main__':
    unittest.main()
