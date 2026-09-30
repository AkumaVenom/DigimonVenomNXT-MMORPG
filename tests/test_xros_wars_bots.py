"""Three-region rival expansion uses persisted teams and ordinary game actions.

Small deterministic fixtures reuse a verified collision map. The full-catalog
acceptance case exercises every imported map separately once assets are merged.
"""
from __future__ import annotations

import copy
from pathlib import Path

from venom.common.game import GameEngine
from venom.server.bots import BotManager
from venom.server.community_store import CommunityStore
from venom.server.database import Database
from test_bots import MemoryStore, RankedStub


ROOT = Path(__file__).resolve().parents[1]


def make_engine(levels=(1, 1, 1, 1, 1, 1), *, include_xros=True):
    engine = GameEngine(ROOT, seed=1300)
    template = copy.deepcopy(next(iter(engine.maps.values())))
    maps = {}
    for index, level in enumerate(levels):
        region = ('dawn', 'world_ds', 'xros_wars')[min(2, index // 2)]
        if region == 'xros_wars' and not include_xros:
            continue
        area = {**copy.deepcopy(template), 'id': f'{region}_test_{index:03}',
                'name': f'{region} test field {index + 1}', 'region_id': region,
                'level': level, 'level_min': level, 'level_max': level}
        maps[area['id']] = area
    engine.maps = maps
    engine.starters = ['agumon']
    engine._pools = {mid: (['agumon'], []) for mid in maps}
    engine._shiny_pools = {mid: ['agumon_shiny'] for mid in maps}
    return engine


def make_manager(engine=None, *, count=12, store=None, now=0, ranked=None):
    manager = BotManager(engine or make_engine(), store or MemoryStore(), ranked=ranked,
                         config={'count': count, 'seed': 1300, 'action_interval': .1,
                                 'explore_seconds': 2, 'min_dwell': 30, 'max_dwell': 30,
                                 'save_interval': 10000, 'tick_budget_ms': 100})
    manager.initialize(now)
    return manager


def roster(bot):
    return {member['uid']: copy.deepcopy(member)
            for member in bot['state']['party'] + bot['state']['storage']}


def move(manager, bot, target):
    previous = bot['state']['map_id']
    manager._execute(bot, 'travel', {'map_id': target})
    manager.by_map[previous].discard(bot['id'])
    manager.by_map[target].add(bot['id'])


def test_expansion_restores_active_battles_then_balances_without_roster_reset():
    store = MemoryStore()
    old = make_manager(make_engine(include_xros=False), count=24, store=store)
    first = old.bots['bot:00001']
    old._execute(first, 'encounter', {})
    old.flush(force=True, now=10)
    before = copy.deepcopy(store.rows)
    expanded = make_manager(count=24, store=store, now=1000)
    assert set(expanded.bots) == set(before)
    for ident, bot in expanded.bots.items():
        assert bot['state'] == before[ident]['state']
        assert bot['stats'] == before[ident]['stats']
    first = expanded.bots[first['id']]
    assert first['runtime']['phase'] == 'battle'
    assert first['state']['battle']['id'] == before[first['id']]['state']['battle']['id']
    original_map = first['state']['map_id']
    expanded._step(first, 1001)
    assert first['state']['map_id'] == original_map
    assert first['stats']['travels'] == 0
    # Other explorers finish their old dwell naturally before changing fields.
    for bot in list(expanded.bots.values())[1:]:
        bot['runtime']['leave_at'] = 1002
        expanded._explore(bot, 1002)
    counts = [len(members) for members in expanded.by_map.values()]
    assert min(counts) >= 3 and max(counts) <= 5
    assert all(expanded.by_map[mid] for mid in expanded.by_map if mid.startswith('xros_wars'))
    for ident, bot in expanded.bots.items():
        if ident != first['id']:
            expected = {m['uid']: m for m in before[ident]['state']['party']}
            assert roster(bot) == expected
            assert bot['stats']['wild_wins'] == bot['stats']['xp_earned'] == 0
        assert expanded.navigation.walkable(bot['state']['map_id'], bot['state']['x'], bot['state']['y'])
    expanded.flush(force=True, now=1003)
    restored = make_manager(count=24, store=store, now=5000)
    assert restored.by_map == expanded.by_map
    assert {ident: bot['stats'] for ident, bot in restored.bots.items()} == {
        ident: bot['stats'] for ident, bot in expanded.bots.items()}


def test_banked_veterans_fill_the_fair_share_on_every_region_without_awarded_xp():
    manager = make_manager(make_engine((1, 60, 60, 60, 60, 60)), count=30)
    low = next(mid for mid, area in manager.engine.maps.items() if area['level'] == 1)
    # Mature-save fixture: all teams already own a veteran and a fresh recruit.
    for bot in manager.bots.values():
        move(manager, bot, low)
        recruit = manager.engine._monster('agumon', level=1)
        veteran = manager.engine._monster('agumon', level=99)
        bot['state']['party'], bot['state']['storage'] = [recruit], [veteran]
        bot['runtime'].update(training_uids=[recruit['uid']], training_goal=20,
                              training_peak=1, training_start_wins=0)
        manager._execute(bot, 'digilab', {'action': 'enter'})
    before = {ident: roster(bot) for ident, bot in manager.bots.items()}
    # Reservations spread concurrent Lab decisions over every underfilled map.
    for bot in list(manager.bots.values())[:25]:
        manager._manage_party(bot)
        assert bot['runtime'].get('coverage_target') != low
    assert {mid: manager._map_load(mid) for mid in manager.by_map} == {
        mid: (30 if mid == low else 5) for mid in manager.by_map}
    assert len(manager.by_map[low]) == 30  # No Lab teleport.
    for bot in list(manager.bots.values())[:25]:
        target = bot['runtime']['coverage_target']
        manager._execute(bot, 'digilab', {'action': 'return'})
        manager._relocate(bot, 100, easier=True)
        assert bot['state']['map_id'] == target
        assert manager._field_level(bot['state']['party']) >= 60
        assert not bot['runtime'].get('coverage_target')
    assert {len(members) for members in manager.by_map.values()} == {5}
    assert not any(manager.coverage_reservations.values())
    for ident, bot in manager.bots.items():
        assert roster(bot) == before[ident]
        assert bot['stats']['xp_earned'] == bot['stats']['level_ups'] == 0
    # Checkpointing retains real locations, party identities and counters.
    manager.flush(force=True, now=101)
    restored = make_manager(make_engine((1, 60, 60, 60, 60, 60)), count=30,
                            store=manager.store, now=2000)
    assert restored.by_map == manager.by_map
    assert {ident: roster(bot) for ident, bot in restored.bots.items()} == before


def test_lone_capable_resident_does_not_abandon_a_field_for_a_fuller_destination():
    manager = make_manager(make_engine((1, 1, 1, 1, 1, 1)), count=18)
    sparse, crowded = list(manager.by_map)[:2]
    first = manager.bots[min(manager.by_map[sparse])]
    for ident in list(manager.by_map[sparse] - {first['id']}):
        move(manager, manager.bots[ident], crowded)
    manager._relocate(first, 100)
    assert first['state']['map_id'] == sparse
    assert first['stats']['travels'] == 0
    assert first['runtime']['leave_at'] == 130


def test_single_rival_keeps_switching_between_all_three_regions_after_restarts():
    manager = make_manager(count=1)
    bot = manager.bots['bot:00001']
    before = roster(bot)
    visited = {bot['state']['map_id']}
    for step in range(1, 7):
        manager._relocate(bot, step * 30)
        visited.add(bot['state']['map_id'])
        manager.flush(force=True, now=step * 30)
        manager = make_manager(count=1, store=manager.store, now=step * 1000)
        bot = manager.bots['bot:00001']
    assert visited == set(manager.engine.maps)
    assert bot['stats']['travels'] == 6
    assert roster(bot) == before


def test_xros_rivals_keep_real_battle_scan_lab_shopping_and_ranked_cycles():
    manager = make_manager(count=12, ranked=RankedStub())
    xros_bots = set().union(*(members for mid, members in manager.by_map.items()
                             if manager.engine.maps[mid]['region_id'] == 'xros_wars'))
    initial = {ident: set(roster(manager.bots[ident])) for ident in xros_bots}
    # Depleted-inventory fixture: restocking must spend each rival's own money.
    for ident in xros_bots:
        manager.bots[ident]['state']['inventory'].update(hp_s=0, sp_s=0)
    for tick in range(1, 4001):
        manager.tick(tick / 10, .1, budget=1000)
    for ident in xros_bots:
        bot = manager.bots[ident]
        assert initial[ident] <= set(roster(bot))
        for key in ('wild_started', 'wild_wins', 'scans', 'scan_data', 'materialized',
                    'level_ups', 'heals', 'travels', 'exploration_steps', 'purchases',
                    'ranked_started'):
            assert bot['stats'][key] > 0, (ident, key)
        assert bot['stats']['errors'] == 0
        assert bot['stats']['wild_wins'] == bot['state']['wins']
    assert set().union(*manager.by_map.values()) == set(manager.bots)
    assert manager.counters['ranked_wins'] == manager.counters['ranked_losses'] == len(manager.ranked.matches)


def test_3000_saved_rivals_cover_all_500_maps_and_checkpoint_without_career_reset(tmp_path):
    database = Database({'driver': 'sqlite', 'path': str(tmp_path / 'xros_rival_upgrade.sqlite3')}, dev=True)
    try:
        database.initialize()
        store = CommunityStore(database)
        store.initialize()
        engine = GameEngine(ROOT, seed=1301)
        xros = {mid for mid, area in engine.maps.items() if area.get('region_id') == 'xros_wars'}
        assert len(engine.maps) == 500 and len(xros) == 96
        old_engine = GameEngine(ROOT, seed=1301)
        old_engine.maps = {mid: area for mid, area in old_engine.maps.items() if mid not in xros}
        old = make_manager(old_engine, count=3000, store=store, now=100)
        # Explicit mature-save fixture. Startup and all migration operations
        # below may only use these already-owned levels, XP and identities.
        for bot in old.bots.values():
            member = bot['state']['party'][0]
            member.update(level=99, abi=65, cam=90)
            stats = old_engine.stats_for(old_engine.species[member['species_id']], 99, 65)
            member.update(**stats, max_hp=stats['hp'], max_sp=stats['sp'])
            old_engine._refresh(bot['state'])
            old.dirty.add(bot['id'])
        old.flush(force=True, now=100)
        before = {row['id']: row for row in store.bot_load_all()}
        del old
        upgraded = make_manager(engine, count=3000, store=store, now=1000)
        assert not any(upgraded.by_map[mid] for mid in xros)
        assert upgraded._coverage_quota() == 6
        for ident, bot in upgraded.bots.items():
            assert bot['state'] == before[ident]['state']
            assert bot['stats'] == before[ident]['stats']
        # Real safe exploration boundaries introduce all newly available maps.
        for bot in upgraded.bots.values():
            upgraded._explore(bot, 1100)
        assert all(upgraded.by_map.values())
        assert sum(map(len, upgraded.by_map.values())) == 3000
        assert set().union(*upgraded.by_map.values()) == set(before)
        # Let the remaining crowded-map residents reach their next travel
        # boundary. Deficit-aware ordinary travel reaches exactly six per map
        # when all saved teams can safely reach every difficulty.
        for mid in list(upgraded.by_map):
            while len(upgraded.by_map[mid]) > 6:
                bot = upgraded.bots[min(upgraded.by_map[mid])]
                bot['runtime'].update(leave_at=1200, walk_pending=True)
                upgraded._explore(bot, 1200)
        assert {len(members) for members in upgraded.by_map.values()} == {6}
        for ident, bot in upgraded.bots.items():
            for key in ('party', 'storage', 'inventory', 'credits', 'scan', 'wins', 'losses'):
                assert bot['state'][key] == before[ident]['state'][key], (ident, key)
            assert bot['stats']['level_ups'] == bot['stats']['xp_earned'] == 0
            assert upgraded.navigation.walkable(bot['state']['map_id'], bot['state']['x'], bot['state']['y'])
            assert bot['runtime']['path'], (ident, bot['state']['map_id'])
        upgraded.flush(force=True, now=1200)
        saved = {row['id']: row for row in store.bot_load_all()}
        restored = make_manager(engine, count=3000, store=store, now=9000)
        assert restored.by_map == upgraded.by_map
        for ident, bot in restored.bots.items():
            assert bot['state'] == saved[ident]['state']
            assert bot['stats'] == saved[ident]['stats']
            assert bot['runtime']['route_after_map'] == saved[ident]['runtime']['route_after_map']
    finally:
        database.close()
