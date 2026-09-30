"""Supplied soundtrack integrity, sample-accurate loops and region routing."""
import hashlib
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import numpy as np
import pygame
import soundfile as sf

from tools.import_xros_audio import SCENES, WORLD_TRACKS, soundtrack_for_map, wav_loop
from venom.client.assets import Audio

ROOT = Path(__file__).resolve().parents[1]


class XrosRecordingTests(unittest.TestCase):
    def test_all_supplied_music_decodes_and_retains_intro_and_loop_frames(self):
        data = json.loads((ROOT/'data/xros_audio.json').read_text())
        self.assertEqual(len(data['music']), 20)
        self.assertEqual(len(data['skipped']), 77)
        self.assertEqual(len(data['source']['manifest_recordings_not_supplied']), 54)
        self.assertEqual(sum(t['source']['manifest_verified'] for t in data['music']), 8)
        seen = set()
        pygame.mixer.init()
        self.addCleanup(pygame.mixer.quit)
        for track in data['music']:
            with self.subTest(track=track['id']):
                self.assertNotIn(track['id'], seen)
                seen.add(track['id'])
                source = track['source']
                self.assertEqual(len(source['sha256']), 64)
                for part in ('loop', 'intro') if track.get('intro_path') else ('loop',):
                    path = ROOT/track['intro_path' if part == 'intro' else 'path']
                    digest = track['intro_sha256' if part == 'intro' else 'sha256']
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
                    recording, rate = sf.read(path, dtype='float32', always_2d=True)
                    quality = track['quality']['segments'][part]
                    self.assertEqual(rate, 44100)
                    self.assertEqual(recording.shape[1], 2)
                    self.assertEqual(len(recording), quality['frames'])
                    self.assertTrue(np.isfinite(recording).all())
                    self.assertGreater(float(np.sqrt(np.mean(recording**2))), .001)
                    self.assertLessEqual(float(np.abs(recording).max()), .98)
                    expected = (source['loop_start_frame'] if part == 'intro' else
                                source['loop_end_frame_exclusive'] - source['loop_start_frame']
                                if track['looped'] else source['frames'])
                    self.assertEqual(len(recording), expected)
                    pygame.mixer.music.load(str(path))
                # Exercise SDL's real intro -> infinitely queued stream support.
                if track.get('intro_path'):
                    pygame.mixer.music.load(str(ROOT/track['intro_path']))
                    pygame.mixer.music.play(0)
                    pygame.mixer.music.queue(str(ROOT/track['path']), loops=-1)
                    pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        self.assertEqual(seen, set(WORLD_TRACKS) | set(SCENES.values()))
        self.assertEqual(sum(bool(t.get('intro_path')) for t in data['music']), 19)
        arrival = next(t for t in data['music'] if t['id'] == 'xros_bm009')
        self.assertFalse(arrival['looped'])
        self.assertEqual(arrival['continuation_id'], SCENES['world'])

    def test_level_assignments_use_every_music_recording_and_combat_tier(self):
        assigned = [soundtrack_for_map({'level': level}) for level in range(1, 100)]
        self.assertEqual({m['music_id'] for m in assigned}, set(WORLD_TRACKS))
        self.assertEqual({m['battle_music_id'] for m in assigned},
                         {SCENES['battle'], SCENES['advanced_battle'], SCENES['endgame_battle']})
        self.assertEqual(assigned[33]['battle_music_id'], SCENES['battle'])
        self.assertEqual(assigned[34]['battle_music_id'], SCENES['advanced_battle'])
        self.assertEqual(assigned[74]['battle_music_id'], SCENES['endgame_battle'])

    def test_riff_loop_reader_preserves_inclusive_end_and_rejects_unsupported_loops(self):
        import tempfile
        header = struct.pack('<9I', 0, 0, 22675, 60, 0, 0, 0, 1, 0)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'loop.wav'
            def fixture(kind=0):
                smpl = header + struct.pack('<6I', 0, kind, 21, 97, 0, 0)
                body = b'WAVE' + b'JUNK' + struct.pack('<I', 1) + b'x\0'
                body += b'smpl' + struct.pack('<I', len(smpl)) + smpl
                path.write_bytes(b'RIFF' + struct.pack('<I', len(body)) + body)
            fixture()
            self.assertEqual(wav_loop(path), (21, 98))
            fixture(kind=1)
            with self.assertRaisesRegex(ValueError, 'non-forward'):
                wav_loop(path)


class XrosMusicRoutingTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        self.region = json.loads((ROOT/'data/xros_audio.json').read_text())
        self.tracks = {t['id']: t for t in self.region['music']}
        self.ui = json.loads((ROOT/'data/ui_audio.json').read_text())
        catalog = json.loads((ROOT/'data/catalog.json').read_text())
        self.legacy = [t for t in catalog['audio']['music']
                       if t.get('region_id') not in ('world_ds', 'xros_wars')
                       and not t.get('id', '').startswith(('ds_', 'xros_'))]
        # Independent of whether the map/catalog merge has run yet.
        catalog['audio']['music'] = self.legacy + self.region['music']
        maps = {f'dawn_{i}': {} for i in range(64)}
        maps.update({'xros_begin': {'region_id': 'xros_wars', 'music_id': 'xros_002_seq_n_01',
                                   'battle_music_id': 'xros_bm300'},
                     'xros_end': {'region_id': 'xros_wars', 'music_id': 'xros_013_seq_n_13',
                                 'battle_music_id': 'xros_bm608'},
                     'xros_arrival': {'region_id': 'xros_wars', 'music_id': 'xros_bm009',
                                     'battle_music_id': 'xros_bm300'},
                     'ds_green': {'region_id': 'world_ds', 'music_id': 'ds_bgm10',
                                  'battle_music_id': 'ds_bgm03'}})
        self.load = self.enterContext(patch.object(pygame.mixer.music, 'load'))
        self.play = self.enterContext(patch.object(pygame.mixer.music, 'play'))
        self.queue = self.enterContext(patch.object(pygame.mixer.music, 'queue'))
        self.audio = Audio(SimpleNamespace(root=ROOT, maps=maps, catalog=catalog))
        self.now = 1.

    def scene(self, map_id='xros_begin', **context):
        self.now += 1.
        self.audio.music(map_id=map_id, now=self.now, **context)
        self.now += .2
        self.audio.music(map_id=map_id, now=self.now, **context)

    def assert_xros(self, identifier):
        track = self.tracks[identifier]
        self.assertEqual(self.audio.track, track['path'])
        self.load.assert_called_with(str(ROOT/track.get('intro_path', track['path'])))
        if track.get('intro_path'):
            self.play.assert_called_with(0, fade_ms=self.audio.FADE_IN_MS)
            self.queue.assert_called_with(str(ROOT/track['path']), loops=-1)

    def test_exploration_battle_and_cross_region_travel_restore_correct_tracks(self):
        self.scene()
        self.assert_xros('xros_002_seq_n_01')
        self.scene(battle=True)
        self.assert_xros('xros_bm300')
        self.scene()
        self.assert_xros('xros_002_seq_n_01')
        self.scene('xros_end')
        self.assert_xros('xros_013_seq_n_13')
        self.scene('xros_end', battle=True)
        self.assert_xros('xros_bm608')
        for _ in range(15):
            self.scene('xros_end', battle=True)
        self.assertEqual(self.load.call_count, 5)
        self.scene('ds_green')
        self.assertEqual(self.audio.track, 'assets/audio/world_ds/ds_bgm10.ogg')
        self.scene('dawn_0')
        self.assertEqual(self.audio.track, self.legacy[0]['path'])
        self.assertEqual(self.audio._world_tracks, self.legacy)

    def test_arrival_composition_plays_once_then_queues_exploration_without_silence(self):
        self.scene('xros_arrival')
        self.assert_xros('xros_bm009')
        self.play.assert_called_with(0, fade_ms=25)
        self.queue.assert_called_with(str(ROOT/self.tracks[SCENES['world']]['path']), loops=-1)
        self.scene('xros_arrival')
        self.assertEqual(self.load.call_count, 1)
        self.scene('xros_arrival', battle=True)
        self.assert_xros('xros_bm300')

    def test_settings_services_private_modes_and_replays_preserve_existing_priority(self):
        for screen in ('settings', 'maps', 'shop', 'ranked', 'rivals'):
            self.scene(screen=screen)
            self.assertEqual(self.audio.track, self.ui['screen_tracks'][screen])
            self.scene()
            self.assert_xros('xros_002_seq_n_01')
        for flag, screen in (('in_farm', 'farm'), ('in_lab', 'digilab')):
            self.scene(**{flag: True})
            self.assertEqual(self.audio.track, self.ui['screen_tracks'][screen])
        self.scene(in_story=True, story_region=2)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm14.ogg')
        self.scene(in_story=True, battle=True, story_battle={'story_role': 'champion'})
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm51.ogg')
        self.scene(in_season=True, screen='season', battle=True)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm40.ogg')
        self.scene(screen='ranked', replay=True, battle=True)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm40.ogg')

    def test_muting_and_nonblocking_fades_apply_to_current_intro_and_queued_loop(self):
        self.audio.set_volumes(.57, .23)
        self.scene()
        self.audio.toggle()
        self.scene('xros_end')
        self.assert_xros('xros_013_seq_n_13')
        self.assertEqual(pygame.mixer.music.get_volume(), 0.)
        self.audio.toggle()
        self.assertAlmostEqual(pygame.mixer.music.get_volume(), .57, delta=.01)
        self.assertEqual(self.audio.effects_volume, .23)
        with patch.object(pygame.mixer.music, 'fadeout', side_effect=AssertionError('blocking fade')):
            self.scene(battle=True)
            self.scene()

    def test_missing_optional_manifest_falls_back_to_existing_world_and_battle_tracks(self):
        self.audio._xros_tracks = {}
        self.scene()
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm10.ogg')
        self.scene(battle=True)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm40.ogg')


if __name__ == '__main__':
    unittest.main()
