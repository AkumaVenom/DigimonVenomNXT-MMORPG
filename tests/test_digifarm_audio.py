"""DigiFarm has its own looping score, including overlay and mute restoration."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
import soundfile as sf
from venom.client.assets import Audio


ROOT = Path(__file__).resolve().parents[1]


class DigiFarmAudioTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        self.config = json.loads((ROOT/'data/ui_audio.json').read_text())
        catalog = json.loads((ROOT/'data/catalog.json').read_text())
        self.load = self.enterContext(patch.object(pygame.mixer.music, 'load'))
        self.play = self.enterContext(patch.object(pygame.mixer.music, 'play'))
        self.fadeout = self.enterContext(patch.object(pygame.mixer.music, 'fadeout'))
        self.sound = self.enterContext(patch.object(pygame.mixer, 'Sound'))
        self.audio = Audio(SimpleNamespace(root=ROOT, maps={'meadow': {}}, catalog=catalog))
        self.now = 1.
        self.farm = self.config['screen_tracks']['farm']

    def scene(self, **kwargs):
        self.now += 1.
        self.audio.music(map_id='meadow', now=self.now, **kwargs)
        self.now += .2
        self.audio.music(map_id='meadow', now=self.now, **kwargs)

    def test_farm_streams_once_and_management_does_not_restart_music(self):
        self.scene(in_farm=True)
        self.assertEqual(self.audio.track, self.farm)
        self.scene(in_farm=True, screen='farm')
        self.scene(in_farm=True, screen='digifarm')
        for frame in range(100):
            self.audio.music(in_farm=True, now=self.now + frame / 60)
        self.load.assert_called_once_with(str(ROOT/self.farm))
        self.play.assert_called_once_with(-1, fade_ms=self.audio.FADE_IN_MS)
        self.sound.assert_not_called()
        self.fadeout.assert_not_called()

    def test_overlay_battle_and_world_restore_correct_track(self):
        self.scene()
        world = self.audio.track
        self.scene(in_farm=True)
        self.assertEqual(self.audio.track, self.farm)
        for overlay in ('shop', 'settings', 'storage'):
            self.scene(in_farm=True, screen=overlay)
            self.assertEqual(self.audio.track, self.config['screen_tracks'][overlay])
            self.scene(in_farm=True)
            self.assertEqual(self.audio.track, self.farm)
        self.scene(in_farm=True, screen='farm', battle=True)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm40.ogg')
        self.scene(in_farm=True)
        self.assertEqual(self.audio.track, self.farm)
        self.scene()
        self.assertEqual(self.audio.track, world)

    def test_muted_home_arrival_respects_saved_gain(self):
        self.scene()
        self.audio.set_volumes(.48, .22)
        self.audio.toggle()
        self.scene(in_farm=True)
        self.assertEqual(self.audio.track, self.farm)
        self.assertEqual(pygame.mixer.music.get_volume(), 0)
        self.audio.toggle()
        self.assertAlmostEqual(pygame.mixer.music.get_volume(), .48, delta=.01)
        self.assertEqual(self.audio.effects_volume, .22)

    def test_shipped_original_score_is_healthy_and_distinct(self):
        import numpy as np
        info = self.config['original_assets']['digifarm_home']
        path = ROOT/info['path']
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), info['sha256'])
        self.assertEqual(sum(value == self.farm for value in self.config['screen_tracks'].values()), 1)
        samples, rate = sf.read(path)
        self.assertEqual(rate, info['sample_rate'])
        self.assertEqual(samples.shape[1], 2)
        self.assertAlmostEqual(len(samples)/rate, info['duration'], places=3)
        self.assertGreaterEqual(info['duration'], 45)
        self.assertLessEqual(info['duration'], 90)
        self.assertTrue(np.isfinite(samples).all())
        self.assertGreater(np.sqrt(np.mean(samples*samples)), .03)
        self.assertLess(np.abs(samples).max(), .98)
        # Wrapped note and room tails should make a quiet boundary, with no gap.
        self.assertLess(np.abs(samples[0] - samples[-1]).max(), .025)
        self.assertGreater(np.sqrt(np.mean(samples[-rate//4:]**2)), .01)


if __name__ == '__main__':
    unittest.main()
