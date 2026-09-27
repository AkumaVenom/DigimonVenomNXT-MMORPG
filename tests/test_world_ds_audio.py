"""Real recording validation and scene-priority regressions for the DS region."""
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

import numpy as np
import pygame
import soundfile as sf

from venom.client.assets import Audio

ROOT = Path(__file__).resolve().parents[1]


class WorldDSRecordingTests(unittest.TestCase):
    def test_recordings_decode_have_safe_peaks_and_match_provenance(self):
        data = json.loads((ROOT/'data/world_ds_audio.json').read_text())
        pygame.mixer.init()
        self.addCleanup(pygame.mixer.quit)
        self.assertEqual(len(data['music']), 28)
        self.assertEqual(len(data['skipped']), 7)
        self.assertEqual(len(data['source']['archives']), 6)
        seen = set()
        for track in data['music']:
            with self.subTest(track=track['id']):
                self.assertNotIn(track['id'], seen)
                seen.add(track['id'])
                path = ROOT/track['path']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), track['sha256'])
                recording, rate = sf.read(path, dtype='float32', always_2d=True)
                self.assertEqual(rate, 32000)
                self.assertEqual(recording.shape[1], 2)
                self.assertEqual(len(recording), track['quality']['frames'])
                self.assertTrue(np.isfinite(recording).all())
                self.assertGreater(float(np.sqrt(np.mean(recording**2))), .02)
                self.assertLess(float(np.abs(recording).max()), .98)
                self.assertEqual(track['quality']['missing_instruments'], [])
                source = track['source']
                self.assertEqual(len(source['preview_sha256']), 64)
                self.assertEqual(len(source['sequence_sha256']), 64)
                self.assertAlmostEqual(len(recording)/rate,
                                       source['loop_end_seconds']-source['loop_start_seconds'], delta=1/rate)
                # Pygame/SDL's actual streaming decoder must accept every file.
                pygame.mixer.music.load(str(path))
        pygame.mixer.music.unload()
        self.assertTrue(set(data['scene_tracks'].values()) <= seen)
        self.assertTrue(all(item['reason'] in ('Duplicate source sequence', 'Incomplete supplied preview')
                            for item in data['skipped']))


class WorldDSAudioRoutingTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        self.region = json.loads((ROOT/'data/world_ds_audio.json').read_text())
        self.ui = json.loads((ROOT/'data/ui_audio.json').read_text())
        catalog = json.loads((ROOT/'data/catalog.json').read_text())
        self.legacy = [track for track in catalog['audio']['music']
                       if not track.get('id', '').startswith('ds_')]
        # Simulate the merged catalog even when tested before an asset rebuild.
        catalog['audio']['music'] = self.legacy + self.region['music']
        maps = {f'dawn_{i}': {} for i in range(64)}
        maps.update({'ds_green': {'region_id': 'world_ds', 'music_id': 'ds_bgm10', 'battle_music_id': 'ds_bgm03'},
                     'ds_void': {'region_id': 'world_ds', 'music_id': 'ds_bgm23', 'battle_music_id': 'ds_bgm17'}})
        self.load = self.enterContext(patch.object(pygame.mixer.music, 'load'))
        self.play = self.enterContext(patch.object(pygame.mixer.music, 'play'))
        self.audio = Audio(SimpleNamespace(root=ROOT, maps=maps, catalog=catalog))
        self.now = 1.

    def scene(self, map_id='ds_green', **context):
        self.now += 1.
        self.audio.music(map_id=map_id, now=self.now, **context)
        self.now += .2
        self.audio.music(map_id=map_id, now=self.now, **context)

    def path(self, identifier):
        return f'assets/audio/world_ds/{identifier}.ogg'

    def test_explicit_exploration_tracks_restore_after_battle_and_travel(self):
        self.scene()
        self.assertEqual(self.audio.track, self.path('ds_bgm10'))
        self.scene(battle=True)
        self.assertEqual(self.audio.track, self.path('ds_bgm03'))
        self.scene()
        self.assertEqual(self.audio.track, self.path('ds_bgm10'))
        self.scene('ds_void')
        self.assertEqual(self.audio.track, self.path('ds_bgm23'))
        self.scene('ds_void', battle=True)
        self.assertEqual(self.audio.track, self.path('ds_bgm17'))
        for _ in range(20):
            self.scene('ds_void', battle=True)
        self.assertEqual(self.load.call_count, 5)

    def test_legacy_dawn_playlist_is_unchanged_after_catalog_append(self):
        for index in (0, 1, 45, 46, 63):
            self.scene('dawn_'+str(index))
            self.assertEqual(self.audio.track, self.legacy[index % len(self.legacy)]['path'])
        self.assertEqual(len(self.audio._world_tracks), len(self.legacy))

    def test_farm_lab_menus_story_season_replays_keep_priority(self):
        self.scene()
        for scene in ('settings', 'maps', 'shop', 'ranked', 'rivals'):
            self.scene(screen=scene)
            self.assertEqual(self.audio.track, self.ui['screen_tracks'][scene])
            self.scene()
            self.assertEqual(self.audio.track, self.path('ds_bgm10'))
        self.scene(in_farm=True)
        self.assertEqual(self.audio.track, self.ui['screen_tracks']['farm'])
        self.scene(in_lab=True)
        self.assertEqual(self.audio.track, self.ui['screen_tracks']['digilab'])
        self.scene(in_story=True, story_region=2)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm14.ogg')
        self.scene(in_story=True, battle=True, story_battle={'story_role': 'champion'})
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm51.ogg')
        self.scene(in_season=True, screen='season')
        self.assertEqual(self.audio.track, self.ui['screen_tracks']['season'])
        self.scene(in_season=True, screen='season', battle=True)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm40.ogg')
        self.scene(screen='ranked', replay=True, battle=True)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm40.ogg')

    def test_victory_fanfare_plays_once_then_returns_to_region(self):
        self.scene(battle=True)
        self.audio.world_ds_victory('ds_green', now=self.now)
        self.scene()
        self.assertEqual(self.audio.track, self.path('ds_bgm30'))
        self.play.assert_called_with(0, fade_ms=25)
        for _ in range(5):
            self.scene()
        self.assertEqual(self.audio.track, self.path('ds_bgm10'))
        self.play.assert_called_with(-1, fade_ms=self.audio.FADE_IN_MS)
        self.assertEqual(sum(call.args[0].endswith('ds_bgm30.ogg') for call in self.load.call_args_list), 1)

    def test_paradox_story_uses_ds_music_and_preserves_service_priority(self):
        context = {'in_story': True, 'story_campaign': 'world_ds_paradox'}
        self.scene(**context)
        self.assertEqual(self.audio.track, self.path('ds_bgm10'))
        self.scene(**context, battle=True, story_battle={'story_role': 'trainer'})
        self.assertEqual(self.audio.track, self.path('ds_bgm03'))
        self.scene(**context, battle=True, story_battle={'story_role': 'final'})
        self.assertEqual(self.audio.track, self.path('ds_bgm17'))
        self.scene(**context, in_lab=True)
        self.assertEqual(self.audio.track, self.ui['screen_tracks']['digilab'])
        self.scene(**context, in_farm=True)
        self.assertEqual(self.audio.track, self.ui['screen_tracks']['farm'])
        self.scene(**context, screen='settings')
        self.assertEqual(self.audio.track, self.ui['screen_tracks']['settings'])
        self.scene(**context)
        self.assertEqual(self.audio.track, self.path('ds_bgm10'))

    def test_travel_and_new_battle_cancel_victory_and_dawn_ignores_it(self):
        self.scene()
        self.audio.world_ds_victory('ds_green', now=self.now)
        self.scene('ds_void')
        self.assertIsNone(self.audio._world_ds_result)
        self.assertEqual(self.audio.track, self.path('ds_bgm23'))
        self.audio.world_ds_victory('ds_void', now=self.now)
        self.scene('ds_void', battle=True)
        self.assertIsNone(self.audio._world_ds_result)
        self.assertEqual(self.audio.track, self.path('ds_bgm17'))
        self.audio.world_ds_victory('dawn_0', now=self.now)
        self.assertIsNone(self.audio._world_ds_result)

    def test_region_transition_preserves_mute_volume_and_nonblocking_fade(self):
        self.audio.set_volumes(.62, .28)
        self.scene()
        self.audio.toggle()
        self.scene('ds_void')
        self.assertEqual(self.audio.track, self.path('ds_bgm23'))
        self.assertEqual(pygame.mixer.music.get_volume(), 0.)
        self.audio.toggle()
        self.assertAlmostEqual(pygame.mixer.music.get_volume(), .62, delta=.01)
        self.assertEqual(self.audio.effects_volume, .28)
        with patch.object(pygame.mixer.music, 'fadeout', side_effect=AssertionError('blocking fade')):
            self.scene(battle=True)
            self.scene()

    def test_missing_optional_region_music_uses_safe_legacy_fallback(self):
        self.audio._world_ds_tracks = {}
        self.scene()
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm10.ogg')
        self.scene(battle=True)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm40.ogg')


if __name__ == '__main__':
    unittest.main()
