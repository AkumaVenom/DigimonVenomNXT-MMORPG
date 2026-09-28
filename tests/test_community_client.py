"""Native community screens, authoritative replay and coordinate hit testing."""
import copy
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import queue
from types import SimpleNamespace
import unittest

import pygame

from venom.client.app import App
from venom.client.community import MatchReplay
from venom.client.render import NativeCanvas
from venom.common.paths import root_path


def fixture(app):
    party = copy.deepcopy(app.state['party'])
    tamer = app.state['tamer']
    rival = {'id': 'bot:00001', 'name': 'Kira_00001', 'username': 'Kira_00001', 'kind': 'bot',
             'is_bot': True, 'tamer': tamer, 'points': 1450, 'wins': 15, 'losses': 3, 'rank': 4,
             'career_rating': 1450, 'grade': 'B', 'party': party, 'map_id': app.state['map_id'],
             'map_name': 'Training Sector', 'activity': 'Exploring', 'level': 12,
             'stats': {key: i*126 for i, (key, _) in enumerate(app.community.COUNTERS)}}
    season = {'id': '2026-39', 'label': 'Season 39 · Digital Dawn', 'seconds_remaining': 230512, 'status': 'active'}
    own = dict(rival, id='player:tamerpreview', name='TamerPreview', kind='player', is_bot=False,
               career_wins=453, career_losses=219, digirubies=2300, energy={'current': 4, 'capacity': 5})
    rows = [dict(rival, id=f'bot:{i:05}', name=f'Rival_{i:05}', rank=i+1) for i in range(100)]
    events = [{'id': i, 'bot_id': 'bot:00001', 'name': 'Kira_00001', 'kind': 'wild_win',
               'text': 'Defeated three wild Digimon · gained 312 XP and scan data', 'at': 1790070120+i} for i in range(100)]
    return {'ranked': {'season': season, 'own': own, 'opponents': rows[:15], 'rewards': [{'rank_max': 10, 'digirubies': 600}]},
            'ladder': {'scope': 'current', 'season': season, 'entries': rows, 'total': 5038},
            'seasons': [dict(season, status='completed', competitors=5038)],
            'profile': rival,
            'rivals': {'challenges': [dict(rival, id='invite1', challenge_id='invite1', bot_id=rival['id'])],
                       'nearby': rows[:6], 'history': [dict(rival, last_at=1790070120)],
                       'directory': rows[:50], 'total': 5000, 'offset': 0},
            'activity': {'population': 5000, 'active': 5000, 'occupied_maps': 254, 'total_maps': 254,
                         'window_seconds': 43200, 'window_start': 1790027020, 'as_of': 1790070220,
                         'tracking_since': 1789983820,
                         'counters': rival['stats'], 'events': events,
                         'maps': [{'id': f'map{i}', 'name': f'Sector {i}', 'count': 20, 'level': 12} for i in range(254)]}}


@unittest.skipUnless((root_path()/'data/catalog.json').exists(), 'Imported assets required')
class CommunityViewsTests(unittest.TestCase):
    def setUp(self):
        args = SimpleNamespace(dev=False, demo=True, demo_battle=False, config=None, frames=0, screenshot=None, size='1280x800')
        self.app = App(root_path(), args)
        self.app.community.data = fixture(self.app)
        self.app.menu = 'community'

    def tearDown(self):
        pygame.quit()

    def test_all_screens_fit_minimum_and_native_4k_with_no_hidden_gameplay_actions(self):
        for size, scale in (((1180, 800), 1), ((3840, 2160), 2.5)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(size), scale)
            self.app.ui.screen = self.app.screen
            for tab, modes in (('ranked', ('overview', 'ladder', 'seasons')), ('rivals', ('invites', 'directory', 'history', 'profile')), ('activity', ('feed', 'maps'))):
                self.app.community.tab = tab
                for mode in modes:
                    with self.subTest(size=size, tab=tab, mode=mode):
                        self.app.community.mode = mode
                        self.app.community.profile_id = 'bot:00001'
                        self.app.draw()
                        self.assertTrue(self.app.ui.actions)
                        bounds = self.app.screen.get_rect()
                        for area, callback in self.app.ui.actions:
                            self.assertTrue(bounds.contains(area), (mode, area, bounds))
                        self.assertNotIn('chat', [key for _, key in self.app.ui.fields])
        self.assertFalse(self.app.assets.errors, self.app.assets.errors)

    def test_native_bot_target_uses_interpolated_position_and_is_covered_by_hub(self):
        self.app.menu = None
        self.app.world.set_zoom(4)
        rival = self.app.community.data['profile']
        pos = self.app.position+pygame.Vector2(65, 40)
        actor = dict(rival, x=pos.x+70, y=pos.y+70, dx=1., dy=0., lead=self.app.state['party'][0]['species_id'])
        self.app.players = {rival['name']: actor}
        self.app.player_render = {rival['name']: pos}
        self.app.draw()
        expected = self.app.world.camera.world_to_screen(pos)
        logical = self.app.screen.to_logical_point(expected)
        hits = [(rect, callback) for rect, callback in self.app.ui.actions if rect.collidepoint((logical[0], logical[1]-10))]
        self.assertTrue(hits, 'Bot target must follow the rendered interpolation, not the latest raw packet')
        hits[0][1]()
        self.assertEqual(self.app.community.profile_id, rival['id'])
        self.assertEqual(self.app.menu, 'community')
        self.app.draw()
        self.assertNotIn('chat', [key for _, key in self.app.ui.fields])

    def test_poll_community_response_does_not_clear_gameplay_pending_or_replace_party(self):
        self.app.connection = SimpleNamespace(incoming=queue.Queue(), connected=True)
        self.app.requests[12] = 'community'
        self.app.community.pending['ranked'] = (12, 0)
        self.app.community.request_ids[12] = 'ranked'
        self.app.action_pending = True
        party = self.app.state['party']
        self.app.connection.incoming.put({'op': 'result', 'rid': 12, 'ok': True,
                                         'community': {'action': 'ranked', 'data': self.app.community.data['ranked']}})
        self.app.poll()
        self.assertTrue(self.app.action_pending)
        self.assertIs(party, self.app.state['party'])
        self.assertFalse(self.app.community.pending)

    def test_remote_rival_keeps_last_walking_facing_when_stopping(self):
        rival = self.app.community.data['profile']
        self.app.players = {rival['name']: dict(rival, x=self.app.position.x, y=self.app.position.y, dx=-1., dy=0.)}
        actors = self.app.world._actors()
        self.assertEqual(next(actor[5] for actor in actors if actor[-1]=='bot:00001'), 'left')
        self.app.players[rival['name']]['dx'] = 0.
        actors = self.app.world._actors()
        self.assertEqual(next(actor[5] for actor in actors if actor[-1]=='bot:00001'), 'left')

    def test_queries_are_coalesced_and_match_not_automatically_retried(self):
        self.app.args.demo = False
        sent = []
        self.app.connection = SimpleNamespace(connected=True, send=lambda op, **data: sent.append((op, data)) or len(sent))
        self.app.community.refresh()
        self.app.community.refresh()
        self.assertEqual(len(sent), 1)
        self.app.community.request('match', opponent_id='bot:00001')
        self.app.now = 40
        self.app.community.update(.016)
        self.assertIn('match', self.app.community.pending)
        self.assertEqual(sum(data['action']=='match' for _, data in sent), 1)

    def test_authoritative_replay_reserves_damage_skip_and_real_party_immutable(self):
        party = copy.deepcopy(self.app.state['party'])
        party.append(copy.deepcopy(party[0]))
        before = copy.deepcopy(self.app.state)
        first_hp = party[0]['hp']
        result = {'ranked': True, 'attacker_name': 'TamerPreview', 'defender_name': 'Kira', 'attacker_won': True,
                  'points': {'attacker': {'delta': 21}}, 'replay': {'party': party, 'enemies': copy.deepcopy(party),
                  'active': [0, 1, 2], 'enemy_active': [0, 1, 2], 'events': [
                      {'kind': 'damage', 'side': 'enemy', 'index': 0, 'attacker_side': 'player', 'attacker_index': 0,
                       'amount': 20, 'effectiveness': 2, 'attribute': 'fire', 'hp_after': first_hp-20},
                      {'kind': 'reserve', 'side': 'enemy', 'index': 3, 'retired_index': 0},
                      {'kind': 'damage', 'side': 'player', 'index': 1, 'attacker_side': 'enemy', 'attacker_index': 3,
                       'amount': 13, 'effectiveness': 1, 'attribute': 'neutral'}]}}
        replay = MatchReplay(self.app, result)
        self.app.community.replay = replay
        replay.update(.3)
        self.app.draw()
        self.assertEqual(replay.teams['enemy'][0]['hp'], first_hp-20)
        replay.skip()
        self.app.draw()
        self.assertEqual(replay.active['enemy'][0], 3)
        self.assertEqual(replay.teams['enemy'][0]['hp'], first_hp-20, 'Skip must not apply the current hit twice')
        self.assertEqual(self.app.state, before)
        self.assertEqual(result['replay']['enemies'][0]['hp'], first_hp)

    def test_settings_modal_removes_hub_actions(self):
        self.app.community.tab, self.app.community.mode = 'rivals', 'directory'
        self.app.settings_open = True
        self.app.draw()
        self.assertNotIn('rival_search', [key for _, key in self.app.ui.fields])

    def test_real_ranked_replay_reaches_the_authoritative_final_hp_totals(self):
        from venom.common.game import GameEngine
        from venom.server.database import Database
        from venom.server.community_store import CommunityStore
        from venom.server.ranked import RankedService
        engine = GameEngine(root_path(), seed=56)
        database = Database({'driver': 'sqlite', 'path': ':memory:'}, dev=True)
        database.initialize()
        store = CommunityStore(database)
        store.initialize()
        service = RankedService(engine, store, {'match_cooldown': 0})
        try:
            profiles = [{'id': f'bot:{index:05}', 'kind': 'bot', 'name': f'ReplayRival{index}', 'tamer': self.app.tamer,
                         'party': [engine._monster(engine.starters[0], level=12+index) for _ in range(6)]} for index in (1, 2)]
            service.register_many(profiles)
            result = service.start_match(profiles[0]['id'], profiles[1]['id'], match_id='native-contract-replay')
            self.app.community.receive({'action': 'match', 'data': result})
            replay = self.app.community.replay
            replay.update(.3)
            self.app.draw()
            while not replay.done:
                replay.update(.35)
            self.app.draw()
            for side, name in (('player', 'attacker'), ('enemy', 'defender')):
                party = replay.teams[side]
                fraction = sum(mon['hp']/max(1, mon['max_hp']) for mon in party)/len(party)
                self.assertAlmostEqual(round(fraction, 4), result['remaining_hp'][name])
        finally:
            database.close()


if __name__ == '__main__':
    unittest.main()
