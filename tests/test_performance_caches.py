"""Crowded-map working sets must stay cached without exceeding byte budgets."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pygame

from venom.client.assets import Assets
from venom.client.render import NativeCanvas


class PerformanceCacheTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((32, 32))
        self.temp = tempfile.TemporaryDirectory()
        self.assets = Assets(Path(self.temp.name))

    def tearDown(self):
        pygame.quit()
        self.temp.cleanup()

    def test_crowded_animated_population_reuses_every_frame_after_warmup(self):
        # Three poses for 180 species exceed both previous entry limits while
        # occupying less than a tenth of the existing cache byte budgets.
        self.assets.species = {
            str(i): {'animations': {'walk': [f'{i}_{frame}.png' for frame in range(3)]}}
            for i in range(180)
        }
        source = pygame.Surface((16, 24), pygame.SRCALPHA)
        source.fill((30, 120, 200, 170))
        with patch.object(pygame.image, 'load', return_value=source) as load, \
                patch.object(pygame.transform, 'scale', wraps=pygame.transform.scale) as scale:
            for cycle in range(3):
                for frame in range(3):
                    for species in self.assets.species:
                        result = self.assets.sprite(species, (58, 64), 'walk', frame / 8)
                        self.assertEqual(result.get_at((0, 0)), source.get_at((0, 0)))
            self.assertEqual(load.call_count, 540)
            self.assertEqual(scale.call_count, 540)
        self.assertLessEqual(self.assets.cache_bytes, self.assets.IMAGE_CACHE_BYTES)
        self.assertLessEqual(self.assets.scaled_bytes, self.assets.SCALED_CACHE_BYTES)

    def test_fitted_frames_do_not_require_evicted_source_pngs(self):
        self.assets.IMAGE_CACHE_BYTES = 0
        self.assets.species = {'mon': {'sprites': {'idle': 'mon.png'}}}
        self.assets.tamers = {'hero': {'frames': {'down': ['hero.png']}, 'display_scale': 2}}
        source = pygame.Surface((8, 16), pygame.SRCALPHA)
        source.fill('red')
        source.set_at((0, 0), 'blue')
        with patch.object(pygame.image, 'load', return_value=source) as load:
            sprite = self.assets.sprite('mon', (32, 32))
            tamer = self.assets.tamer('hero')
            for _ in range(50):
                self.assertIs(self.assets.sprite('mon', [32, 32]), sprite)
                self.assertIs(self.assets.tamer('hero'), tamer)
            self.assertEqual(load.call_count, 2)
            flipped = self.assets.sprite('mon', (32, 32), flip=True)
            self.assertEqual(flipped.get_at((flipped.get_width() - 1, 0)), pygame.Color('blue'))
            self.assets.tamers['hero']['display_scale'] = 1
            smaller = self.assets.tamer('hero')
            self.assertEqual(smaller.get_size(), (8, 16))
            self.assertEqual(load.call_count, 4)
        self.assertEqual(self.assets.cache_bytes, 0)
        self.assertFalse(self.assets.cache)

    def test_native_dpi_cache_retains_small_animation_frames(self):
        canvas = NativeCanvas(pygame.Surface((80, 80)), 2.5)
        sources = [pygame.Surface((12, 20), pygame.SRCALPHA) for _ in range(300)]
        for i, source in enumerate(sources):
            source.fill((i % 256, 90, 180, 255))
        with patch.object(pygame.transform, 'scale', wraps=pygame.transform.scale) as scale:
            for _ in range(3):
                for source in sources:
                    canvas.blit(source, (1, 1))
            self.assertEqual(scale.call_count, len(sources))
        self.assertEqual(canvas.surface.get_at((3, 3)), sources[-1].get_at((0, 0)))
        self.assertLessEqual(canvas._cache_bytes, canvas.cache_limit)
        # Per-surface alpha remains part of the key at native DPI.
        sources[-1].set_alpha(80)
        with patch.object(pygame.transform, 'scale', wraps=pygame.transform.scale) as scale:
            canvas.blit(sources[-1], (1, 1))
            self.assertEqual(scale.call_count, 1)

    def test_entry_safety_limits_and_small_byte_budgets_still_evict(self):
        self.assets.IMAGE_CACHE_ITEMS = 3
        self.assets.SCALED_CACHE_ITEMS = 3
        source = pygame.Surface((8, 16), pygame.SRCALPHA)
        with patch.object(pygame.image, 'load', return_value=source):
            for i in range(20):
                self.assets.image(f'{i}.png')
                self.assets.fit(source, (16, 32), key=str(i))
        self.assertEqual(len(self.assets.cache), 3)
        self.assertEqual(len(self.assets.scaled), 3)
        self.assertEqual(self.assets.cache_bytes, 3 * 8 * 16 * 4)
        self.assertEqual(self.assets.scaled_bytes, 3 * 16 * 32 * 4)
        canvas = NativeCanvas(pygame.Surface((80, 80)), 2, cache_bytes=2600)
        for _ in range(10):
            canvas.blit(pygame.Surface((8, 16), pygame.SRCALPHA), (0, 0))
        self.assertLessEqual(canvas._cache_bytes, 2600)
        self.assertEqual(len(canvas._scaled), 1)


if __name__ == '__main__':
    unittest.main()
