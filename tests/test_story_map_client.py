"""Private authored map actors, native hit areas, exits and soundtrack continuity."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pygame
from venom.client.assets import Assets, Audio
from venom.client.render import NativeCanvas
from venom.client.widgets import UI, CYAN, GOLD, LIME, MUTED
from venom.client.world import WorldRenderer

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class StoryMapClientTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        self.screen = NativeCanvas(pygame.display.set_mode((1280, 800)), 1.25)
        self.assets = Assets(ROOT)
        self.map_id, self.tamer = next(iter(self.assets.maps)), next(iter(self.assets.tamers))
        self.npc = dict(id='story:arden', name='Warden Arden', tamer_id=self.tamer,
                        map_id=self.map_id, x=410, y=360, role='warden', status='available')
        self.gate = dict(id='gate:forest', name='Forest Relay', map_id=self.map_id,
                         to_map='next-map', x=600, y=460, unlocked=True, requires_badge=None)
        self.app = SimpleNamespace(
            screen=self.screen, assets=self.assets, now=1., action_pending=False,
            state={'in_story': True, 'map_id': self.map_id, 'username': 'Player', 'party': [],
                   'story': {'view': {'npcs': [self.npc], 'exits': [self.gate], 'talk_radius': 128,
                                      'map_name': 'Dawn Gate', 'chapter_name': 'A signal in the forest',
                                      'badges': [{'id': 'relay', 'name': 'Relay DigiBadge'}],
                                      'objective': 'Speak with Warden Arden to challenge for the first DigiBadge.'}}},
            position=pygame.Vector2(400, 400), follower=pygame.Vector2(376, 428),
            tamer=self.tamer, moving=False, direction='down', player_render={},
            players={'Ghost': {'username': 'Ghost', 'map_id': self.map_id, 'x': 430, 'y': 370,
                               'tamer': self.tamer},
                     'Bot': {'id': 'bot:1', 'is_bot': True, 'map_id': self.map_id, 'x': 300, 'y': 450,
                             'tamer': self.tamer}},
            story_screen=SimpleNamespace(talk=Mock(), exit=Mock()),
            community=SimpleNamespace(open_profile=Mock()), send=Mock())
        self.app.ui = UI(self.screen, self.assets)
        self.renderer = WorldRenderer(self.app)
        self.renderer.camera.configure((1024, 768), self.screen.to_physical_rect((10, 80, 790, 430)), (400, 400), snap=True)

    def test_story_renders_fixed_authored_tamers_and_filters_stale_multiplayer_snapshot(self):
        actors = self.renderer._actors()
        self.assertEqual([a[1] for a in actors], ['story_npc', 'tamer'])
        self.assertEqual(actors[0][3], self.tamer)
        self.assertEqual(actors[0][6], 'Warden Arden')
        self.assertIs(actors[0][-1], self.npc)
        self.app.state['in_story'] = False
        self.assertEqual({a[6] for a in self.renderer._actors()}, {'Player', 'Ghost', 'AI RIVAL · Bot'})

    def test_story_actors_and_exits_only_in_current_field_not_lab_farm_or_detention(self):
        view = self.app.state['story']['view']
        view['npcs'].append(dict(self.npc, id='other-map', map_id='elsewhere'))
        view['exits'].append(dict(self.gate, id='other-exit', map_id='elsewhere'))
        self.assertEqual(len(self.renderer._story_npcs()), 1)
        self.assertEqual(len(self.renderer._story_exits()), 1)
        for flag in ('in_lab', 'in_farm', 'in_jail', 'admin_jail'):
            self.app.state[flag] = True
            self.assertEqual(self.renderer._story_npcs(), [])
            self.assertEqual(self.renderer._story_exits(), [])
            self.assertEqual(len(self.renderer._actors()), 1)
            self.app.state.pop(flag)

    def test_native_dpi_npc_sprite_and_label_hit_areas_open_dialogue_not_bot_profile(self):
        with patch('venom.client.world.text') as text:
            self.renderer._draw_actor('tamer', (410, 360), self.tamer, False, 'down', 'Warden Arden', story_npc=self.npc)
        self.assertGreaterEqual(len(self.app.ui.actions), 2)
        clip = self.screen.to_logical_rect(self.renderer.camera.viewport)
        for rect, callback in self.app.ui.actions:
            self.assertTrue(clip.contains(rect))
            callback()
        self.assertTrue(any('DIGIBADGE WARDEN' in str(c.args[2]) for c in text.call_args_list))
        self.assertEqual({c.args for c in self.app.story_screen.talk.call_args_list}, {('story:arden',)})
        self.app.community.open_profile.assert_not_called()
        self.app.send.assert_not_called()

    def test_nearby_prompt_selects_nearest_npc_or_gate_using_same_radius(self):
        self.assertEqual(self.renderer.nearest_story_interaction(), ('npc', self.npc))
        self.app.position.update(590, 460)
        self.assertEqual(self.renderer.nearest_story_interaction(), ('exit', self.gate))
        self.app.position.update(900, 700)
        self.assertIsNone(self.renderer.nearest_story_interaction())
        self.app.position.update(720, 460)
        self.assertEqual(self.renderer.nearest_story_interaction()[0], 'exit')
        self.app.state['story']['view']['talk_radius'] = 96
        self.assertIsNone(self.renderer.nearest_story_interaction())

    def test_story_hud_opens_npc_dialogue_and_never_calls_world_encounter(self):
        controls = []
        def button(rect, label, callback, **kwargs):
            controls.append((label, callback, kwargs))
        with patch.object(self.app.ui, 'button', side_effect=button), patch.object(self.renderer, '_draw_minimap'):
            self.renderer._draw_hud({}, pygame.Rect(10, 80, 790, 430))
        _, callback, kwargs = next(row for row in controls if 'Talk nearby' in row[0])
        self.assertFalse(kwargs['disabled'])
        callback()
        self.app.story_screen.talk.assert_called_once_with('story:arden')
        self.app.send.assert_not_called()
        self.assertFalse(any('Search for Digimon' in row[0] for row in controls))

    def test_gate_native_hit_areas_route_only_to_story_exit_and_show_badge_requirement(self):
        self.gate.update(unlocked=False, requires_badge='relay')
        with patch('venom.client.world.text') as text:
            self.renderer._draw_story_exits()
        self.assertEqual(len(self.app.ui.actions), 2)
        clip = self.screen.to_logical_rect(self.renderer.camera.viewport)
        for rect, callback in self.app.ui.actions:
            self.assertTrue(clip.contains(rect))
            callback()
        self.assertTrue(any('Relay DigiBadge' in str(c.args[2]) for c in text.call_args_list))
        self.assertEqual({c.args for c in self.app.story_screen.exit.call_args_list}, {('gate:forest',)})
        self.app.story_screen.talk.assert_not_called()
        self.app.community.open_profile.assert_not_called()
        self.app.send.assert_not_called()

    def test_gate_hud_tracks_authoritative_unlock_status_and_busy_controls(self):
        self.app.position.update(600, 460)
        for unlocked in (False, True):
            self.gate['unlocked'] = unlocked
            with patch.object(self.app.ui, 'button') as button, patch.object(self.renderer, '_draw_minimap'):
                self.renderer._draw_hud({}, pygame.Rect(10, 80, 790, 430))
            call = next(c for c in button.call_args_list if c.args[1] in ('Take path  E', 'Locked path  E'))
            self.assertEqual(call.args[1], 'Take path  E' if unlocked else 'Locked path  E')
            call.args[2]()
            self.app.story_screen.exit.assert_called_with('gate:forest')
        self.app.action_pending = True
        with patch.object(self.app.ui, 'button') as button, patch.object(self.renderer, '_draw_minimap'):
            self.renderer._draw_hud({}, pygame.Rect(10, 80, 790, 430))
        self.assertTrue(button.call_args.kwargs['disabled'])

    def test_crowded_plateau_labels_stay_distinct_bounded_and_clear_of_hud(self):
        self.renderer._reset_story_labels(pygame.Rect(10, 80, 790, 430))
        obstacles = list(self.renderer._story_label_rects)
        labels = [self.renderer._place_story_label(pygame.Rect(390, 245, width, height))
                  for width, height in ((140, 36), (100, 24), (135, 36), (202, 40), (202, 40))]
        bounds = self.screen.to_logical_rect(self.renderer.camera.viewport).inflate(-8, -8)
        for index, label in enumerate(labels):
            self.assertTrue(bounds.contains(label))
            self.assertFalse(any(label.colliderect(other) for other in obstacles+labels[:index]))

    def test_map_marker_colors_distinguish_cleared_locked_and_championship(self):
        for status, role, color in [('locked', 'warden', MUTED), ('defeated', 'trainer', LIME),
                                    ('available', 'champion', GOLD), ('available', 'guide', CYAN)]:
            self.assertEqual(self.renderer._story_color(dict(self.npc, status=status, role=role)), color)
        self.assertIn('CLEARED', self.renderer._story_role(dict(self.npc, status='cleared')))
        self.assertIn('LOCKED', self.renderer._story_role(dict(self.npc, status='locked')))

    def test_story_battle_music_escalates_and_returns_to_same_region_without_blocking(self):
        with patch.object(pygame.mixer.music, 'load') as load, patch.object(pygame.mixer.music, 'play'), \
                patch.object(pygame.mixer.music, 'fadeout') as fadeout:
            audio = Audio(self.assets)
            audio.set_volumes(0, .3)
            audio.music(in_story=True, story_region=2, map_id='first', now=1)
            regional = audio.track
            self.assertEqual(regional, 'assets/audio/music/bgm14.ogg')
            audio.music(in_story=True, story_region=2, map_id='second', now=2)
            self.assertEqual(load.call_count, 1)
            for index, (role, track) in enumerate([('training', 'bgm40'), ('trainer', 'bgm40'), ('warden', 'bgm50'), ('champion', 'bgm51')]):
                audio.music(battle=True, in_story=True, story_battle={'story_role': role}, screen='story', now=3+index)
                self.assertEqual(audio.track, f'assets/audio/music/{track}.ogg')
            audio.music(in_story=True, story_region=2, map_id='second', now=8)
            self.assertEqual(audio.track, regional)
            audio.music(battle=True, screen='season', now=9)
            self.assertEqual(audio.track, 'assets/audio/music/bgm40.ogg')
            audio.music(in_story=True, in_lab=True, story_region=2, now=10)
            self.assertEqual(audio.track, audio._screen_tracks['digilab'])
            audio.music(in_story=True, in_farm=True, story_region=2, now=11)
            self.assertEqual(audio.track, audio._screen_tracks['farm'])
            fadeout.assert_not_called()

    def test_all_regional_and_story_audio_assignments_exist(self):
        audio = Audio(self.assets)
        tracks = set(audio.STORY_REGIONS) | set(audio.STORY_TRACKS.values())
        for track in tracks:
            self.assertIn(track, audio._tracks_by_id)
            self.assertTrue((ROOT/audio._tracks_by_id[track]['path']).is_file())

    def test_story_journal_and_reward_sounds_use_existing_assets_and_debounce_success(self):
        with patch.object(pygame.mixer.music, 'load'), patch.object(pygame.mixer.music, 'play'):
            audio = Audio(self.assets)
            audio.set_volumes(0, .3)
            for screen in ('story', 'story_results'):
                audio.music(screen=screen, now=1)
                self.assertTrue((ROOT/audio.track).is_file())
            with patch.object(audio, '_play_effect') as effect:
                audio.cue('confirm', now=1)
                audio.cue('story_badge', now=1.01)
                audio.cue('story_badge', now=1.02)
                self.assertEqual(effect.call_count, 2)
                self.assertEqual(effect.call_args.args, ('assets/audio/interface/se030.ogg',))


if __name__ == '__main__':
    unittest.main()
