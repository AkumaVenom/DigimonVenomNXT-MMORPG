"""Exercise visible-screen soundtrack routing through the real App/input path."""
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame

from venom.client.app import App


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT/'data/catalog.json').is_file(), 'Imported assets required')
class ScreenMusicIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(pygame.quit)
        self.load = self.enterContext(patch.object(pygame.mixer.music, 'load'))
        self.play = self.enterContext(patch.object(pygame.mixer.music, 'play'))
        self.fadeout = self.enterContext(patch.object(pygame.mixer.music, 'fadeout'))
        self.sound = self.enterContext(patch.object(pygame.mixer, 'Sound', side_effect=lambda _: Mock()))
        self.milliseconds = 1000
        self.enterContext(patch.object(pygame.time, 'get_ticks', side_effect=lambda: self.milliseconds))
        args = SimpleNamespace(demo=True, demo_battle=False, dev=False, config=None,
                               size='1280x800', frames=0, screenshot=None)
        self.app = App(ROOT, args)
        self.tick()
        self.world_track = self.app.audio.track

    def tick(self, elapsed=.2):
        self.milliseconds += round(elapsed*1000)
        self.app.update(1/60)

    def settle(self):
        self.tick()
        self.tick()
        self.fadeout.assert_not_called()

    def escape(self):
        self.app.key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))

    def test_standard_menu_open_close_restores_world_without_mutating_progress(self):
        before = copy.deepcopy(self.app.state)
        for menu in ('shop', 'dex', 'party', 'maps'):
            with self.subTest(menu=menu):
                self.app.set_menu(menu)
                self.settle()
                self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks[menu])
                self.escape()
                self.settle()
                self.assertEqual(self.app.audio.track, self.world_track)
        self.assertEqual(self.app.state, before)
        self.assertTrue(all(call.args == (-1,) for call in self.play.call_args_list))

    def test_community_shortcuts_route_distinct_tracks_and_closing_restores_digilab(self):
        self.app.state['in_lab'] = True
        for key, tab in ((pygame.K_r, 'ranked'), (pygame.K_v, 'rivals'), (pygame.K_o, 'activity')):
            self.app.key(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
            self.settle()
            self.assertEqual(self.app.menu, 'community')
            self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks[tab])
        self.app.community.close()
        self.settle()
        self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks['digilab'])

    def test_visible_replay_takes_priority_and_hidden_replay_does_not_keep_battle_music(self):
        before = copy.deepcopy(self.app.state)
        party = copy.deepcopy(self.app.state['party'])
        self.app.community.open('ranked')
        self.app.community.receive({'action': 'match', 'data': {'ranked': True, 'replay': {
            'party': party, 'enemies': copy.deepcopy(party),
            'events': [{'kind': 'damage', 'side': 'enemy', 'index': 0, 'amount': 10}],
        }}})
        self.settle()
        battle = self.app.audio._tracks_by_id[self.app.audio._scene_tracks['battle']]['path']
        self.assertEqual(self.app.audio.track, battle)
        replay = self.app.community.replay
        self.escape()
        age = replay.age
        self.settle()
        self.assertEqual(self.app.audio.track, self.world_track)
        self.assertEqual(replay.age, age)
        self.app.community.open('ranked')
        self.settle()
        self.assertEqual(self.app.audio.track, battle)
        self.app.community.finish_replay()
        self.settle()
        self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks['ranked'])
        self.assertEqual(self.app.state, before)

    def test_wild_battle_and_its_item_or_skill_overlay_keep_battle_music(self):
        self.app.state['battle'] = {'turn': 1}
        battle = self.app.audio._tracks_by_id[self.app.audio._scene_tracks['battle']]['path']
        self.settle()
        for overlay in ('skills', 'battle_items'):
            self.app.menu = overlay
            self.settle()
            self.assertEqual(self.app.audio.track, battle)
        self.app.menu = None
        self.app.state['battle'] = None
        self.settle()
        self.assertEqual(self.app.audio.track, self.world_track)

    def test_muted_navigation_updates_actual_scene_and_preserves_settings(self):
        self.app.audio.set_volumes(.62, .27)
        self.app.audio.toggle()
        self.app.set_menu('shop')
        self.settle()
        self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks['shop'])
        self.assertEqual(pygame.mixer.music.get_volume(), 0)
        self.app.community.open('activity')
        self.settle()
        self.assertEqual(self.app.audio.track, self.app.audio._screen_tracks['activity'])
        self.assertEqual(pygame.mixer.music.get_volume(), 0)
        self.sound.assert_not_called()
        self.app.audio.toggle()
        self.assertAlmostEqual(pygame.mixer.music.get_volume(), .62, delta=.01)
        self.assertEqual(self.app.audio.effects_volume, .27)

    def test_mouse_menu_callbacks_do_not_stack_cues_or_load_briefly_closed_music(self):
        self.app.ui.begin()
        self.app.ui.button((10, 10, 110, 35), 'Shop', lambda: self.app.set_menu('shop'))
        self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                           pos=self.app.screen.to_physical_point((30, 25))))
        self.assertEqual(self.app.menu, 'shop')
        self.assertEqual(sum(sound.play.call_count for sound in self.app.audio.sounds.values()), 1)
        self.assertIn(self.app.audio._ui_cues['open'], self.app.audio.sounds,
                      'The specific open cue must win over the generic button confirmation')
        self.tick(.01)
        self.assertIsNotNone(self.app.audio._pending_track)
        self.escape()
        self.settle()
        self.assertEqual(self.load.call_count, 1)
        self.assertEqual(self.app.audio.track, self.world_track)

    def test_mouse_close_callback_uses_back_cue_before_generic_confirmation(self):
        self.app.set_menu('shop')
        self.settle()
        self.app.ui.begin()
        self.app.ui.button((10, 10, 110, 35), 'Field', lambda: self.app.set_menu('shop'))
        before = sum(sound.play.call_count for sound in self.app.audio.sounds.values())
        self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                           pos=self.app.screen.to_physical_point((30, 25))))
        self.assertIsNone(self.app.menu)
        self.assertEqual(sum(sound.play.call_count for sound in self.app.audio.sounds.values()), before+1)
        self.assertIn(self.app.audio._ui_cues['back'], self.app.audio.sounds)
        self.settle()
        self.assertEqual(self.app.audio.track, self.world_track)


if __name__ == '__main__':
    unittest.main()
