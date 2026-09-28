"""Render the real native client with isolated, synthetic server responses.

No server is contacted and no account, save, configuration, or production demo
data is changed. Every exported image is labelled as a synthetic QA preview.
Run: python tools/preview_ui_screens.py --output ui-review --empty --native4k
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

from venom.client.app import App
from venom.client.community import MatchReplay
from venom.client.display import effective_ui_scale, parse_size
from venom.client.render import NativeCanvas
from venom.common.game import GameEngine


VIEWS = (
    ('shop', None, None),
    ('shop_field', None, None),
    ('ranked', 'ranked', 'overview'),
    ('ranked_ladder', 'ranked', 'ladder'),
    ('ranked_seasons', 'ranked', 'seasons'),
    ('ranked_replay', 'ranked', 'overview'),
    ('ranked_result', 'ranked', 'overview'),
    ('rivals', 'rivals', 'invites'),
    ('rivals_directory', 'rivals', 'directory'),
    ('rivals_history', 'rivals', 'history'),
    ('rival_profile', 'rivals', 'profile'),
    ('activity', 'activity', 'feed'),
    ('activity_maps', 'activity', 'maps'),
)

# Kept separate so existing UI1 regression tests retain their original scope.
UI2_VIEWS = ('lab', 'dex', 'scan', 'roster', 'evolution', 'storage', 'storage_space',
             'maps', 'skills', 'battleitems', 'signin', 'register', 'tamerpicker',
             'starterpicker', 'settings', 'settings_auth', 'battle', 'world',
             'materialize_result', 'evolution_result')


def game_fixture(app):
    """Use the real rules engine for monsters, skills and route eligibility.

    This is an isolated in-memory QA account. Its progression is deliberately
    staged to exercise populated screens; it is never saved or sent online.
    """
    if not hasattr(app, '_qa_game_state'):
        engine = app._qa_engine = GameEngine(ROOT, seed=147)
        species = {entry['name'].lower(): entry for entry in engine.species.values()}
        starter = species.get('agumon', engine.species[engine.starters[0]])['id']
        state = engine.new_player('TamerPreview', app.tamer, starter)
        # Historical screen fixtures begin in the field; v0.6.0 accounts begin at home.
        state['in_farm'] = False
        preferred = ('Agumon', 'Gabumon', 'Patamon', 'Greymon', 'Garurumon', 'Angemon')
        chosen = [species[name.lower()]['id'] for name in preferred if name.lower() in species]
        chosen += [sid for sid in engine.starters if sid not in chosen]
        state['party'] = [engine._monster(sid, level=50 if index == 0 else 24+index*2,
                                           abi=100 if index == 0 else 24, cam=100 if index == 0 else 48)
                          for index, sid in enumerate(chosen[:6])]
        candidates = list(engine.species)
        state['storage'] = [engine._monster(candidates[(index*7+13) % len(candidates)],
                                             level=12+index % 20, abi=16, cam=35)
                            for index in range(28)]
        for category in ('party', 'storage'):
            for index, mon in enumerate(state[category]):
                mon['uid'] = f'qa-{category}-{index:03}'
        state['credits'] = 12450
        state['inventory'] = {'hp_s': 12, 'hp_m': 4, 'hp_l': 2, 'sp_s': 8, 'sp_m': 3, 'sp_l': 1}
        state['scan'] = {sid: (200, 125, 100, 80, 60, 45, 20, 0)[index % 8]
                         for index, sid in enumerate(chosen[:12]+candidates[20:42])}
        state['events'] = []
        engine._refresh(state)
        app._qa_game_state = copy.deepcopy(state)
    return copy.deepcopy(app._qa_game_state)


def select_ui2_view(app, name, *, empty=False):
    app.state = game_fixture(app)
    app.menu = None
    app.scroll = app.selected_party = app.target = 0
    app.settings_open = app.auth_pending = app.action_pending = False
    app.auth_picker = None
    app.presentation_notice = None
    app.animations, app.toasts, app.players, app.player_render = [], [], {}, {}
    app.ui.focus = None
    app.ui.values.update(search='', world_search='', bank_search='', username='', password='')
    app.state['in_lab'] = name in ('lab', 'scan', 'evolution', 'storage', 'storage_space',
                                  'materialize_result', 'evolution_result')
    app.position.update(app.state['x'], app.state['y'])
    app.follower.update(app.position+pygame.Vector2(-34, 26))
    app.logs = [('Offline UI preview. All account data shown here is synthetic.', (99, 203, 221))]
    if hasattr(app, 'scan_screen'):
        app.scan_screen.ready_only, app.scan_screen.stage, app.scan_screen.variant = False, 'all', 'all'
    if hasattr(app, 'partner_screen'):
        app.partner_screen.route_filter = 'all'
    if name in ('lab', 'dex', 'scan', 'maps'):
        app.menu = name
    elif name in ('roster', 'evolution', 'storage', 'storage_space'):
        app.menu = 'party'
        app.partner_screen.mode = 'storage' if name == 'storage_space' else name
        if name == 'storage_space':
            app.state['party'] = app.state['party'][:3]
            app._qa_engine._refresh(app.state)
    elif name in ('skills', 'battleitems', 'battle'):
        # Keep the same genuine three-enemy encounter regardless of CLI order.
        app._qa_engine.rng.seed(2)
        app._qa_engine.handle(app.state, 'encounter', {})
        app.menu = {'skills': 'skills', 'battleitems': 'battle_items', 'battle': None}[name]
        app.state['party'][0]['hp'] = max(1, app.state['party'][0]['max_hp']-180)
        app.state['party'][-1]['hp'] = max(1, app.state['party'][-1]['max_hp']-130)
    elif name in ('signin', 'register', 'tamerpicker', 'starterpicker', 'settings_auth'):
        app.state = None
        app.auth_tab = 'login' if name in ('signin', 'settings_auth') else 'register'
        app.status = 'OFFLINE UI PREVIEW / Connect to your dedicated server to play.'
        if name in ('tamerpicker', 'starterpicker'):
            app.auth_picker = 'tamer' if name == 'tamerpicker' else 'starter'
        if name == 'settings_auth':
            app.settings_open = True
    elif name == 'settings':
        app.menu = 'maps'
        app.settings_open = True
    elif name in ('materialize_result', 'evolution_result'):
        before = copy.deepcopy(app.state)
        if name == 'materialize_result':
            species_id = next(sid for sid, scan in app.state['scan'].items() if scan >= 100)
            app._qa_engine.handle(app.state, 'materialize', {'species_id': species_id})
            app.menu, operation = 'scan', 'materialize'
        else:
            route = next(route for route in app.state['evolution_options'][0] if route['eligible'])
            app._qa_engine.handle(app.state, 'evolve', {'party_index': 0, 'to': route['to']})
            app.menu, app.partner_screen.mode, operation = 'party', 'evolution', 'evolve'
        app.confirmed_partner_change(operation, before, app.state)
    if empty:
        if name in ('skills', 'battleitems', 'battle'):
            app.state['inventory'] = {}
            for mon in app.state['party']:
                mon['sp'] = 0
        elif app.state and name not in ('materialize_result', 'evolution_result', 'settings', 'world'):
            app.state.update(party=[], storage=[], scan={}, evolution_options=[])
        if name in ('dex', 'scan', 'tamerpicker', 'starterpicker'):
            app.ui.values['search'] = 'no matching QA entry'
        if name == 'maps':
            app.ui.values['world_search'] = 'no matching QA sector'


def server_fixture(app):
    """Representative field names from the server's community response schema."""
    party = copy.deepcopy(app.state['party'])
    species = {entry['name'].lower(): entry for entry in app.assets.species.values()}
    for name in ('Greymon', 'Garurumon', 'Angemon'):
        entry = species.get(name.lower())
        if entry and party:
            mon = dict(party[0], uid='qa-'+entry['id'], species_id=entry['id'], name=entry['name'], level=24)
            party.append(mon)
    party = party[:6]
    names = ('Kira', 'RiftScout', 'NovaByte', 'AzureFox', 'NeonWarden', 'Sora', 'DataDrifter', 'PulseRunner')
    maps = ('Dawn Sector 004', 'Proxy Island', 'Chrome Mine', 'Digital Ruins', 'Access Glacier', 'Sunshine City')
    actions = ('Training partners', 'Exploring', 'Restocking items', 'Scanning Digimon', 'Recovering', 'Changing sector')
    tamers = list(app.assets.tamers) or [app.state['tamer']]
    stats = {key: (index+1)*126 for index, (key, _) in enumerate(app.community.COUNTERS)}
    rows = []
    for index in range(100):
        rows.append({
            'id': f'bot:{index+1:05}', 'name': names[index % len(names)]+f'_{index+1:04}',
            'username': names[index % len(names)]+f'_{index+1:04}', 'kind': 'bot', 'is_bot': True,
            'tamer': tamers[index % len(tamers)], 'points': 1862-index*7,
            'career_rating': 1975-index*5, 'grade': 'B', 'rank': index+1,
            'wins': 38-index % 19, 'losses': 5+index % 9, 'party': copy.deepcopy(party),
            'map_id': app.state['map_id'], 'map_name': maps[index % len(maps)],
            'activity': actions[index % len(actions)], 'level': 24, 'stats': dict(stats),
            'storage_count': 32, 'scan_ready': 7, 'next_activity': 'explore',
            'training_round': 4, 'training_partners': 6, 'training_goal': 30,
        })
    season = {'id': '2026-39', 'label': 'Season 39 · Digital Dawn', 'seconds_remaining': 230512, 'status': 'active'}
    own = dict(rows[0], id='player:tamerpreview', name=app.state['username'], kind='player', is_bot=False,
               points=1648, rank=127, wins=24, losses=8, career_wins=453, career_losses=219,
               digirubies=2300, next_grade={'name': 'A', 'points': 2000},
               energy={'current': 4, 'capacity': 5, 'next_in': 431})
    kinds = (
        ('wild_win', 'Defeated wild Digimon · gained 312 XP and scan data'),
        ('level_up', 'Greymon reached level 24 · attack and defense increased'),
        ('travel', 'Entered Dawn Sector 004 to explore a new training area'),
        ('ranked_win', 'Won an arena match · season rating increased by 21'),
        ('materialized', 'Materialized a new partner using completed scan data'),
        ('heals', 'Recovered the full team at DigiLab'),
    )
    events = [
        {'id': index, 'bot_id': rows[index]['id'], 'name': rows[index]['name'],
         'kind': kinds[index % len(kinds)][0], 'text': kinds[index % len(kinds)][1],
         'at': 1790247720-index*13}
        for index in range(100)
    ]
    challenges = [dict(rows[index], id=f'qa-invite-{index}', challenge_id=f'qa-invite-{index}',
                       bot_id=rows[index]['id'], ranked=False) for index in range(2)]
    history = [dict(row, bot_id=row['id'], last_at=1790247420-index*711) for index, row in enumerate(rows[:12])]
    return {
        'ranked': {'season': season, 'own': own, 'opponents': rows[:15],
                   'rewards': [{'rank_max': 10, 'digirubies': 600}, {'rank_max': 100, 'digirubies': 300},
                               {'rank_max': 1000, 'digirubies': 100}]},
        'ladder': {'scope': 'current', 'season': season, 'entries': rows, 'total': 5038},
        'seasons': [dict(season, id=f'2026-{week}', label=f'Season {week} · Digital Dawn',
                         status='completed', competitors=5038) for week in range(38, 30, -1)],
        'profile': rows[0],
        'rivals': {'challenges': challenges, 'nearby': rows[:6], 'history': history,
                   'directory': rows[:50], 'total': 3000, 'offset': 0},
        'activity': {'population': 3000, 'active': 2946, 'occupied_maps': 254, 'total_maps': 254,
                     'window_seconds': 43200, 'window_start': 1790204520, 'as_of': 1790247720,
                     'tracking_since': 1790161320,
                     'counters': stats, 'events': events,
                     'maps': [{'id': f'qa-map-{index}', 'name': maps[index % len(maps)]+f' / {index+1:03}',
                               'count': max(1, 84-index//3), 'level': 12+index % 54} for index in range(254)]},
    }


def make_app(size='1280x800'):
    args = SimpleNamespace(dev=False, demo=True, demo_battle=False, config=None, frames=0,
                           screenshot=None, size=size, ui_scale='auto', show_fps=False)
    app = App(ROOT, args)
    physical = parse_size(size)
    app.display.surface = pygame.display.set_mode(physical)
    app.screen = NativeCanvas(app.display.surface, effective_ui_scale(physical, 'auto'))
    app.ui.screen = app.screen
    app.now = 8.5
    app.community.data = server_fixture(app)
    app.community.received_at = {key: app.now for key in app.community.data}
    return app


def select_view(app, name, *, empty=False):
    if name in UI2_VIEWS:
        return select_ui2_view(app, name, empty=empty)
    if app.state is None:
        app.state = game_fixture(app)
    app.settings_open = False
    app.auth_picker = None
    app.presentation_notice = None
    app.state['battle'] = None
    _, tab, mode = next(view for view in VIEWS if view[0] == name)
    app.menu = 'shop' if name.startswith('shop') else 'community'
    app.state['in_lab'] = name == 'shop'
    app.scroll = 0
    app.ui.focus = None
    app.community.error = ''
    app.community.replay = None
    app.community.stats_page = 0
    app.community.activity_filter = 'All'
    app.community.data = server_fixture(app)
    app.community.profile_id = 'bot:00001'
    if tab:
        app.community.tab, app.community.mode = tab, mode
    if empty:
        app.community.data = {'ranked': {'season': app.community.data['ranked']['season'],
                                        'own': app.community.data['ranked']['own'], 'opponents': [], 'rewards': []},
                              'ladder': {'entries': [], 'total': 0}, 'seasons': [], 'profile': {},
                              'rivals': {'challenges': [], 'nearby': [], 'history': [], 'directory': [], 'total': 0},
                              'activity': {'population': 0, 'active': 0, 'occupied_maps': 0, 'total_maps': 254,
                                           'counters': {}, 'events': [], 'maps': []}}
        if name.startswith('shop'):
            app.state['inventory'] = {}
    else:
        app.state['inventory'] = {'hp_s': 5, 'hp_m': 2, 'hp_l': 1, 'sp_s': 3, 'sp_m': 1, 'sp_l': 1}
    if name in ('ranked_replay', 'ranked_result'):
        party = copy.deepcopy(app.state['party'])
        result = {'ranked': True, 'attacker_name': app.state['username'], 'defender_name': 'Kira_0001',
                  'attacker_won': True, 'points': {'attacker': {'delta': 21}},
                  'replay': {'party': party, 'enemies': copy.deepcopy(party),
                             'active': [0, 1, 2], 'enemy_active': [0, 1, 2],
                             'events': [{'kind': 'damage', 'side': 'enemy', 'index': 0,
                                         'attacker_side': 'player', 'attacker_index': 0,
                                         'amount': 68, 'hp_after': max(0, party[0]['hp']-68),
                                         'effectiveness': 2, 'attribute': 'fire', 'text': 'Agumon used Pepper Breath!'}]}}
        app.community.replay = MatchReplay(app, result)
        app.community.replay.age = .18
        if name == 'ranked_result':
            app.community.replay.skip()


def capture(app, path):
    app.draw()
    bounds = app.screen.get_rect()
    invalid = [list(rect) for rect, _ in app.ui.actions if not bounds.contains(rect)]
    # Kept outside the content frame; this makes fabricated QA records explicit.
    label = 'OFFLINE UI QA / SYNTHETIC SERVER DATA'
    font = pygame.font.Font(None, max(12, round(13*app.screen.scale)))
    stamp = font.render(label, True, (169, 193, 209), (7, 14, 24))
    app.screen.surface.blit(stamp, (round(20*app.screen.scale), app.screen.surface.get_height()-stamp.get_height()-2))
    pygame.image.save(app.screen.surface, str(path))
    return {'file': path.name, 'pixels': list(app.screen.surface.get_size()), 'ui_scale': app.screen.scale,
            'actions': len(app.ui.actions), 'fields': [key for _, key in app.ui.fields],
            'actions_outside_display': invalid}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'ui-review')
    parser.add_argument('--sizes', nargs='+', default=['1280x800', '2048x1152'])
    parser.add_argument('--suite', choices=('ui1', 'ui2', 'all'), default='ui1')
    parser.add_argument('--views', nargs='+', choices=[view[0] for view in VIEWS]+list(UI2_VIEWS))
    parser.add_argument('--empty', action='store_true', help='Also capture empty responses / inventory.')
    parser.add_argument('--native4k', action='store_true', help='Also render directly into 3840x2160 pixels.')
    parser.add_argument('--party-six', action='store_true', help='Exercise all six shop recipient slots using QA partners.')
    parser.add_argument('--game-fixture', action='store_true', help='Use the rules-engine QA account for legacy screens too.')
    args = parser.parse_args(argv)
    if args.views is None:
        args.views = ([view[0] for view in VIEWS] if args.suite in ('ui1', 'all') else []) + (list(UI2_VIEWS) if args.suite in ('ui2', 'all') else [])
    args.output.mkdir(parents=True, exist_ok=True)
    sizes = list(dict.fromkeys(args.sizes+(['3840x2160'] if args.native4k else [])))
    report = {'fixture': 'Synthetic server data for isolated native-App QA; no real account progress.', 'captures': []}
    try:
        for size in sizes:
            app = make_app(size)
            if args.game_fixture:
                app.state = game_fixture(app)
            if args.party_six:
                app.state['party'] = copy.deepcopy(app.community.data['profile']['party'])
            for empty in ((False, True) if args.empty else (False,)):
                for view in args.views:
                    select_view(app, view, empty=empty)
                    path = args.output/f'{view}_{size}{"_empty" if empty else ""}.png'
                    report['captures'].append(capture(app, path))
            if app.assets.errors:
                raise RuntimeError(f'Asset errors: {app.assets.errors}')
            pygame.quit()
    finally:
        pygame.quit()
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    invalid = [item for item in report['captures'] if item['actions_outside_display']]
    print(f'Rendered {len(report["captures"])} native App previews to {args.output}')
    if invalid:
        raise SystemExit(f'Out-of-bounds actions in {len(invalid)} screenshots; inspect report.json')


if __name__ == '__main__':
    main()
