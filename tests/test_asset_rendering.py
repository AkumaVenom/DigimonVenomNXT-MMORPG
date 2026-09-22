"""Pixel-art integrity and memory/audio behavior under changing display sizes."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pygame

from venom.client.assets import Assets, Audio


class AssetRenderingTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((32, 32))
        self.temp = tempfile.TemporaryDirectory()
        self.assets = Assets(Path(self.temp.name))

    def tearDown(self):
        pygame.quit()
        self.temp.cleanup()

    def test_small_pixel_art_previews_do_not_invent_blended_colors(self):
        source = pygame.Surface((8, 8), pygame.SRCALPHA)
        colors = [(255, 0, 0, 255), (0, 0, 255, 255)]
        for y in range(8):
            for x in range(8):
                source.set_at((x, y), colors[(x + y) % 2])
        preview = self.assets.fit(source, (3, 3))
        self.assertEqual(preview.get_size(), (3, 3))
        self.assertTrue(all(tuple(preview.get_at((x, y))) in colors for y in range(3) for x in range(3)))

    def test_resize_variants_obey_memory_budget_and_preserve_recent_entries(self):
        source = pygame.Surface((10, 10), pygame.SRCALPHA)
        self.assets.SCALED_CACHE_BYTES = 5000
        first = self.assets.fit(source, (20, 20), key='first')
        self.assets.fit(source, (20, 20), key='second')
        self.assets.fit(source, (20, 20), key='third')
        self.assertIs(self.assets.fit(source, (20, 20), key='first'), first)
        self.assets.fit(source, (20, 20), key='fourth')
        self.assertNotIn('second', self.assets.scaled)
        self.assertIn('first', self.assets.scaled)
        self.assertLessEqual(self.assets.scaled_bytes, self.assets.SCALED_CACHE_BYTES)
        self.assets.fit(source, (100, 100), key='oversized')
        self.assertNotIn('oversized', self.assets.scaled)
        self.assertIn('first', self.assets.scaled)
        self.assets.clear_scaled()
        self.assertEqual(self.assets.scaled_bytes, 0)
        self.assertFalse(self.assets.scaled)

    def test_original_image_cache_is_also_bounded_by_bytes(self):
        self.assets.IMAGE_CACHE_BYTES = 2000
        for index in range(5):
            path = f'{index}.png'
            pygame.image.save(pygame.Surface((20, 20), pygame.SRCALPHA), Path(self.temp.name) / path)
            self.assertIsNotNone(self.assets.image(path))
            self.assertLessEqual(self.assets.cache_bytes, 2000)
        self.assertEqual(list(self.assets.cache), ['4.png'])


class AudioSettingsTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.assets = SimpleNamespace(root=Path('.'), maps={'first': {}, 'second': {}}, catalog={'audio': {
            'music': [{'id': 'title', 'path': 'title.wav'}, {'id': 'world', 'path': 'world.wav'}],
            'scene_tracks': {'title': 'title'}, 'effects': []}})

    def tearDown(self):
        pygame.quit()

    def test_muting_restores_configured_gain_without_replacing_world_music(self):
        with patch.object(pygame.mixer.music, 'load') as load, patch.object(pygame.mixer.music, 'play'):
            audio = Audio(self.assets)
            audio.set_volumes(.7, .6)
            for _ in range(100):
                audio.music(map_id='second')
            self.assertEqual(load.call_count, 1)
            self.assertEqual(audio.track, 'world.wav')
            audio.toggle()
            self.assertFalse(audio.enabled)
            self.assertEqual(pygame.mixer.music.get_volume(), 0.)
            audio.toggle()
            audio.music(map_id='second')
            self.assertEqual(load.call_count, 1)
            self.assertAlmostEqual(pygame.mixer.music.get_volume(), .7, delta=.01)
            self.assertEqual(audio.effects_volume, .6)

    def test_volumes_are_clamped_and_missing_audio_device_is_safe(self):
        with patch.object(pygame.mixer, 'get_init', return_value=None), patch.object(pygame.mixer, 'init', side_effect=pygame.error('No device')):
            audio = Audio(self.assets)
            audio.set_volumes(2, -1)
            self.assertEqual((audio.music_volume, audio.effects_volume), (1., 0.))
            audio.set_volumes(float('nan'), None)
            self.assertEqual((audio.music_volume, audio.effects_volume), (1., 0.))
            audio.toggle()
            audio.music(map_id='second')
            audio.effect()
            self.assertFalse(audio.available)
            self.assertFalse(audio.enabled)
