"""Visible-screen music routing must stay responsive and retain audio settings."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from venom.client.assets import Audio


class ScreenAudioTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'data').mkdir()
        self.screen_tracks = {name: f'ui/{name}.ogg' for name in
                              ('shop', 'ranked', 'rivals', 'activity', 'digilab')}
        (self.root/'data/ui_audio.json').write_text(json.dumps({
            'screen_tracks': self.screen_tracks,
            'cues': {'confirm': 'confirm.ogg', 'back': 'back.ogg'},
        }))
        assets = SimpleNamespace(root=self.root, maps={'first': {}, 'second': {}}, catalog={
            'audio': {'music': [{'id': 'title', 'path': 'world-one.ogg'},
                                {'id': 'world', 'path': 'world-two.ogg'},
                                {'id': 'battle', 'path': 'battle.ogg'}],
                      'scene_tracks': {'title': 'title', 'battle': 'battle'},
                      'effects': {'confirm': 'confirm.ogg', 'cancel': 'back.ogg'}}})
        self.load = self.enterContext(patch.object(pygame.mixer.music, 'load'))
        self.play = self.enterContext(patch.object(pygame.mixer.music, 'play'))
        self.fadeout = self.enterContext(patch.object(pygame.mixer.music, 'fadeout'))
        self.sound = self.enterContext(patch.object(pygame.mixer, 'Sound', side_effect=lambda _: Mock()))
        self.audio = Audio(assets)
        self.now = 1.

    def tearDown(self):
        pygame.quit()
        self.temp.cleanup()

    def enter_scene(self, **context):
        self.now += 1.
        self.audio.music(map_id='second', now=self.now, **context)
        self.now += .2
        self.audio.music(map_id='second', now=self.now, **context)

    def test_screen_loops_are_distinct_and_world_is_restored(self):
        self.enter_scene()
        self.assertEqual(self.audio.track, 'world-two.ogg')
        for name in ('shop', 'ranked', 'rivals', 'activity'):
            self.enter_scene(screen=name)
            self.assertEqual(self.audio.track, self.screen_tracks[name])
        self.enter_scene()
        self.assertEqual(self.audio.track, 'world-two.ogg')
        self.assertEqual(self.load.call_count, 6)
        for call in self.play.call_args_list:
            self.assertEqual(call.args, (-1,))
            self.assertGreater(call.kwargs['fade_ms'], 0)
        self.fadeout.assert_not_called()

    def test_steady_screen_does_no_repeated_io_or_stream_loading(self):
        self.enter_scene(screen='rivals')
        with patch.object(Path, 'read_text', side_effect=AssertionError('frame-time disk read')):
            for frame in range(1000):
                self.audio.music(map_id='second', screen='rivals', now=self.now+frame/144.)
        self.assertEqual(self.load.call_count, 1)
        self.assertEqual(self.play.call_count, 1)

    def test_transition_fades_without_waiting_and_can_be_cancelled(self):
        self.enter_scene()
        self.audio.music(map_id='second', screen='shop', now=10.)
        self.audio.music(map_id='second', screen='shop', now=10.07)
        self.assertEqual(self.load.call_count, 1)
        self.assertAlmostEqual(pygame.mixer.music.get_volume(), .35/2, delta=.012)
        self.audio.music(map_id='second', now=10.08)
        self.audio.music(map_id='second', now=11.)
        self.assertEqual(self.load.call_count, 1)
        self.assertEqual(self.audio.track, 'world-two.ogg')
        self.assertAlmostEqual(pygame.mixer.music.get_volume(), .35, delta=.01)
        self.fadeout.assert_not_called()

    def test_rapid_screen_switch_loads_only_the_latest_target(self):
        self.enter_scene()
        self.audio.music(map_id='second', screen='shop', now=10.)
        self.audio.music(map_id='second', screen='rivals', now=10.02)
        self.audio.music(map_id='second', screen='rivals', now=10.3)
        self.assertEqual(self.audio.track, self.screen_tracks['rivals'])
        self.assertEqual(self.load.call_count, 2)
        self.assertNotIn(str(self.root/self.screen_tracks['shop']),
                         [call.args[0] for call in self.load.call_args_list])

    def test_battle_or_replay_has_priority_then_returns_to_screen(self):
        self.enter_scene(screen='ranked', in_lab=True)
        self.assertEqual(self.audio.track, self.screen_tracks['ranked'])
        self.enter_scene(screen='ranked', in_lab=True, battle=True)
        self.assertEqual(self.audio.track, 'battle.ogg')
        self.enter_scene(screen='ranked', in_lab=True, battle=False)
        self.assertEqual(self.audio.track, self.screen_tracks['ranked'])
        self.enter_scene(in_lab=True)
        self.assertEqual(self.audio.track, self.screen_tracks['digilab'])

    def test_mute_changes_context_silently_and_restores_saved_volume(self):
        self.enter_scene()
        self.audio.set_volumes(.65, .25)
        with patch.object(pygame.mixer, 'stop') as stop:
            self.audio.toggle()
            stop.assert_called_once()
        self.audio.music(map_id='second', screen='activity', now=10.)
        self.assertEqual(self.audio.track, self.screen_tracks['activity'])
        self.assertEqual(pygame.mixer.music.get_volume(), 0.)
        self.audio.cue('confirm', now=10.)
        self.sound.assert_not_called()
        self.audio.toggle()
        self.assertAlmostEqual(pygame.mixer.music.get_volume(), .65, delta=.01)
        self.audio.music(map_id='second', screen='activity', now=11.)
        self.assertEqual(self.load.call_count, 2)
        self.assertEqual(self.audio.effects_volume, .25)

    def test_zero_music_volume_does_not_disable_ui_effects(self):
        self.audio.set_volumes(0., .45)
        self.enter_scene(screen='shop')
        self.audio.cue('confirm', now=1.)
        self.assertEqual(pygame.mixer.music.get_volume(), 0.)
        self.sound.assert_called_once_with(str(self.root/'confirm.ogg'))
        self.audio.sounds['confirm.ogg'].set_volume.assert_called_with(.45)
        self.audio.sounds['confirm.ogg'].play.assert_called_once()

    def test_cues_are_cached_and_nested_callbacks_do_not_stack_sounds(self):
        self.audio.cue('confirm', now=1.)
        self.audio.cue('back', now=1.01)
        self.audio.cue('confirm', now=1.2)
        self.audio.cue('back', now=1.4)
        self.assertEqual(self.sound.call_count, 2)
        self.assertEqual(self.audio.sounds['confirm.ogg'].play.call_count, 2)
        self.assertEqual(self.audio.sounds['back.ogg'].play.call_count, 1)

    def test_bad_optional_track_is_not_retried_each_frame(self):
        self.load.side_effect = pygame.error('Corrupt optional music')
        self.enter_scene(screen='shop')
        for frame in range(120):
            self.audio.music(map_id='second', screen='shop', now=10.+frame/60.)
        self.assertEqual(self.load.call_count, 1)
        self.assertIn(self.screen_tracks['shop'], self.audio._failed_tracks)


class SuppliedInterfaceAudioTests(unittest.TestCase):
    def test_shipped_audio_is_present_distinct_and_unchanged(self):
        import soundfile as sf
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root/'data/ui_audio.json').read_text())
        requested = [data['screen_tracks'][scene] for scene in ('shop', 'ranked', 'rivals', 'activity')]
        self.assertEqual(len(set(requested)), 4)
        for info in data['source_assets'].values():
            path = root/info['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), info['sha256'])
            decoded = sf.info(path)
            self.assertEqual(decoded.channels, 2)
            self.assertEqual(decoded.samplerate, 32768)
            self.assertAlmostEqual(decoded.duration, info['duration'], delta=.001)
            if path.as_posix().endswith(tuple(Path(p).name for p in requested)):
                self.assertGreater(decoded.duration, 30.)


if __name__ == '__main__':
    unittest.main()
