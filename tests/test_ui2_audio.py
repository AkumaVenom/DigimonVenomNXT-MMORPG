"""UI2 soundtracks retain UI1 assignments and use the one streaming channel."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
import soundfile as sf
from venom.client.assets import Audio


ROOT = Path(__file__).resolve().parents[1]
UI1_TRACKS = {
    'shop': 'bgm12', 'ranked': 'bgm30', 'rivals': 'bgm20',
    'activity': 'bgm14', 'dex': 'bgm15', 'party': 'bgm13',
    'maps': 'bgm18', 'digilab': 'bgm11',
}
UI2_TRACKS = {
    'scan': 'bgm16', 'evolution': 'bgm19', 'storage': 'bgm17',
    'skills': 'bgm32', 'auth': 'bgm00', 'settings': 'bgm43',
    'authpicker': 'bgm01',
}


class UI2AudioTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        self.config = json.loads((ROOT/'data/ui_audio.json').read_text())
        catalog = json.loads((ROOT/'data/catalog.json').read_text())
        assets = SimpleNamespace(root=ROOT, maps={'first': {}, 'second': {}}, catalog=catalog)
        self.load = self.enterContext(patch.object(pygame.mixer.music, 'load'))
        self.play = self.enterContext(patch.object(pygame.mixer.music, 'play'))
        self.fadeout = self.enterContext(patch.object(pygame.mixer.music, 'fadeout',
                                                    side_effect=AssertionError('blocking fade')))
        self.sound = self.enterContext(patch.object(pygame.mixer, 'Sound', side_effect=lambda _: Mock()))
        self.audio = Audio(assets)
        self.now = 1.

    def scene(self, screen=None, **kwargs):
        self.now += 1.
        self.audio.music(screen=screen, now=self.now, **kwargs)
        self.now += .2
        self.audio.music(screen=screen, now=self.now, **kwargs)

    def test_approved_tracks_and_cues_are_retained(self):
        for scene, track in UI1_TRACKS.items():
            self.assertEqual(self.config['screen_tracks'][scene], f'assets/audio/interface/{track}.ogg')
        expected_cues = {'confirm': 'se001', 'back': 'se002', 'open': 'se003',
                         'tab': 'se000', 'purchase': 'se009', 'error': 'se004'}
        for cue, name in expected_cues.items():
            self.assertEqual(self.config['cues'][cue], f'assets/audio/interface/{name}.ogg')
        self.scene('scan', battle=True)
        self.assertEqual(self.audio.track, 'assets/audio/music/bgm40.ogg')

    def test_every_screen_streams_a_distinct_loop_without_full_sound_loading(self):
        visited = []
        for scene in (*UI1_TRACKS, *UI2_TRACKS):
            self.scene(scene, map_id='second')
            self.assertEqual(self.audio.track, self.config['screen_tracks'][scene])
            visited.append(self.audio.track)
        self.assertEqual(len(set(visited)), len(visited))
        self.assertEqual(self.load.call_count, len(visited))
        for call in self.play.call_args_list:
            self.assertEqual(call.args, (-1,))
            self.assertEqual(call.kwargs['fade_ms'], self.audio.FADE_IN_MS)
        self.sound.assert_not_called()
        self.fadeout.assert_not_called()

    def test_new_tracks_and_completion_cue_decode_and_match_manifest(self):
        for name in (*UI2_TRACKS.values(), 'se030'):
            info = self.config['source_assets'][name]
            path = ROOT/info['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), info['sha256'])
            with sf.SoundFile(path) as stream:
                self.assertEqual(stream.samplerate, 32768)
                self.assertEqual(stream.channels, 2)
                self.assertAlmostEqual(len(stream)/stream.samplerate, info['duration'], delta=.001)
                self.assertGreater(abs(stream.read()).max(), .001)
                if name.startswith('bgm'):
                    self.assertGreater(len(stream)/stream.samplerate, 30.)

    def test_battle_wins_over_new_screens_and_restore_does_not_restart_steady_music(self):
        for screen in ('scan', 'evolution', 'settings', 'skills'):
            self.scene(screen, in_lab=True)
            self.scene(screen, in_lab=True, battle=True)
            self.assertEqual(self.audio.track, 'assets/audio/music/bgm40.ogg')
            self.scene(screen, in_lab=True)
            self.assertEqual(self.audio.track, self.config['screen_tracks'][screen])
        self.scene('lab')
        self.assertEqual(self.audio.track, self.config['screen_tracks']['digilab'])
        count = self.load.call_count
        with patch.object(Path, 'read_text', side_effect=AssertionError('frame-time disk read')):
            for frame in range(300):
                self.audio.music(screen='lab', now=self.now+frame/120.)
        self.assertEqual(self.load.call_count, count)

    def test_settings_and_auth_switch_while_muted_restore_latest_screen_only(self):
        self.scene('auth')
        self.audio.set_volumes(.61, .27)
        self.audio.toggle()
        for screen in ('settings', 'authpicker', 'storage'):
            self.scene(screen)
            self.assertEqual(self.audio.track, self.config['screen_tracks'][screen])
            self.assertEqual(pygame.mixer.music.get_volume(), 0.)
            self.audio.cue('evolution_complete', now=self.now)
        self.sound.assert_not_called()
        count = self.load.call_count
        self.audio.toggle()
        self.assertAlmostEqual(pygame.mixer.music.get_volume(), .61, delta=.01)
        self.scene('storage')
        self.assertEqual(self.load.call_count, count)
        self.assertEqual(self.audio.effects_volume, .27)

    def test_fast_success_is_audible_once_after_button_acknowledgment(self):
        # Opening a scan/evolution screen must never imply operation success.
        self.scene('scan')
        self.scene('evolution')
        self.sound.assert_not_called()
        self.audio.cue('confirm', now=20.)
        self.audio.cue('scan_complete', now=20.01)
        self.audio.cue('scan_complete', now=20.02)
        scan = self.audio.sounds[self.config['cues']['scan_complete']]
        scan.play.assert_called_once()
        self.audio.cue('confirm', now=21.)
        self.audio.cue('evolution_complete', now=21.01)
        self.audio.cue('evolution_complete', now=21.02)
        evolution = self.audio.sounds[self.config['cues']['evolution_complete']]
        evolution.play.assert_called_once()
        self.assertEqual(self.sound.call_count, 3)


if __name__ == '__main__':
    unittest.main()
