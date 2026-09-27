"""Existing rivals expand into an additive region through normal game actions.

The small maps deliberately reuse verified Dawn collision assets; imported World
DS geometry and the complete 5,000-rival migration have separate acceptance
checks. Mature teams in upgrade cases are explicit persisted-save fixtures.
"""
from __future__ import annotations

import copy
from pathlib import Path

from venom.common.game import GameEngine
from venom.server.bots import BotManager


ROOT = Path(__file__).resolve().parents[1]


class MemoryStore:
    def __init__(self):
        self.rows = {}

    def bot_load_all(self):
        return copy.deepcopy(list(self.rows.values()))

    def bot_save_batch(self, rows):
        self.rows.update({row['id']: copy.deepcopy(row) for row in rows})


def engine_for(levels=(1, 1), include_ds=True):
    engine = GameEngine(ROOT, seed=518)
    originals = [copy.deepcopy(area) for area in engine.maps.values()
                 if not area['id'].startswith('world_ds_')][:2]
    maps = {}
    for index, level in enumerate(levels):
        if index >= 2 and not include_ds:
            break
        area = copy.deepcopy(originals[index % len(originals)])
        area['id'] = originals[index]['id'] if index < 2 else f'world_ds_{index - 1:03}'
        area['name'] = f'Test field {index + 1}'
        area['level'] = level
        area['region_id'] = 'dawn' if index < 2 else 'world_ds'
        maps[area['id']] = area
    engine.maps = maps
    engine.starters = ['agumon']
    engine._pools = {mid: (['agumon'], []) for mid in maps}
    return engine


def manager_for(engine, count=6, store=None, now=0):
    manager = BotManager(engine, store or MemoryStore(), config={
        'count': count, 'seed': 525, 'action_interval': .1,
        'explore_seconds': 2, 'min_dwell': 30, 'max_dwell': 30,
        'save_interval': 10000, 'tick_budget_ms': 100,
    })
    manager.initialize(now)
    return manager


def owned(bot):
    return {m['uid']: copy.deepcopy(m) for m in bot['state']['party'] + bot['state']['storage']}


def test_upgrade_preserves_roster_and_live_battles_until_safe_travel():
    levels = (1, 1, 1, 1, 1, 1)
    old = manager_for(engine_for(levels, include_ds=False), count=12)
    first = old.bots['bot:00001']
    old._execute(first, 'encounter', {})
    assert first['state']['battle']
    old.flush(force=True, now=5)
    before = copy.deepcopy(old.store.rows)
    upgraded = manager_for(engine_for(levels), count=12, store=old.store, now=1000)
    assert set(upgraded.bots) == set(before)
    assert all(not upgraded.by_map[mid] for mid in upgraded.by_map if mid.startswith('world_ds_'))
    for ident, bot in upgraded.bots.items():
        assert bot['state'] == before[ident]['state']
        assert bot['stats'] == before[ident]['stats']
    # Resumed live combat stays on its original field and keeps the exact ID.
    first = upgraded.bots[first['id']]
    assert first['runtime']['phase'] == 'battle'
    original_map = first['state']['map_id']
    upgraded._step(first, 1001)
    assert first['state']['map_id'] == original_map
    assert first['stats']['travels'] == 0
    after_live_turn = owned(first)
    # The normal exploration boundary is what introduces the new maps.
    for bot in list(upgraded.bots.values())[1:]:
        bot['runtime']['leave_at'] = 1002
        upgraded._explore(bot, 1002)
    assert all(upgraded.by_map[mid] for mid in upgraded.by_map if mid.startswith('world_ds_'))
    assert sum(len(ids) for ids in upgraded.by_map.values()) == 12
    for bot in upgraded.bots.values():
        expected = after_live_turn if bot['id'] == first['id'] else {
            m['uid']: m for m in before[bot['id']]['state']['party']}
        assert owned(bot) == expected
        assert upgraded.navigation.walkable(bot['state']['map_id'], bot['state']['x'], bot['state']['y'])
    upgraded.flush(force=True, now=1003)
    restored = manager_for(engine_for(levels), count=12, store=old.store, now=5000)
    assert restored.by_map == upgraded.by_map
    assert {key: bot['stats'] for key, bot in restored.bots.items()} == {
        key: bot['stats'] for key, bot in upgraded.bots.items()}


def test_one_rival_fairly_visits_every_accessible_map_across_restarts():
    levels = (1,) * 9 + (99,)
    engine = engine_for(levels)
    manager = manager_for(engine, count=1)
    bot = manager.bots['bot:00001']
    initial_owned = owned(bot)
    visited = {bot['state']['map_id']}
    for step in range(1, 10):
        manager._relocate(bot, step * 30)
        visited.add(bot['state']['map_id'])
        manager.flush(force=True, now=step * 30)
        manager = manager_for(engine, count=1, store=manager.store, now=step * 1000)
        bot = manager.bots['bot:00001']
    assert visited == {mid for mid, area in engine.maps.items() if area['level'] == 1}
    assert owned(bot) == initial_owned
    assert bot['stats']['travels'] == 9
    assert bot['stats']['wild_wins'] == 0
    assert len(manager.bots) == 1


def test_travel_honors_capability_and_other_rivals_pending_reservations():
    manager = manager_for(engine_for((1, 1, 1, 1, 99)), count=2)
    first, second = manager.bots.values()
    maps = list(manager.engine.maps)
    manager._reserve_coverage(second, maps[2])
    manager._relocate(first, 40)
    assert first['state']['map_id'] == maps[3]
    assert manager.coverage_reservations[maps[2]] == {second['id']}
    assert first['state']['party'][0]['level'] == 3
    assert not manager.by_map[maps[4]]


def test_added_fields_use_normal_walk_battle_scan_capture_and_lab_loop():
    manager = manager_for(engine_for((1, 1, 1, 1)), count=8)
    initial_ds = {ident for mid, ids in manager.by_map.items() if mid.startswith('world_ds_') for ident in ids}
    source_by_id = {ident: owned(bot) for ident, bot in manager.bots.items()}
    for tick in range(1, 3001):
        manager.tick(tick / 10, .1, budget=1000)
    for ident in initial_ds:
        bot = manager.bots[ident]
        assert set(source_by_id[ident]) <= set(owned(bot))
        for key in ('wild_started', 'wild_wins', 'scans', 'scan_data', 'materialized',
                    'level_ups', 'heals', 'travels', 'exploration_steps'):
            assert bot['stats'][key] > 0, (ident, key)
        assert bot['stats']['errors'] == 0
        assert bot['stats']['wild_wins'] == bot['state']['wins']
    assert set().union(*manager.by_map.values()) == set(manager.bots)
    assert len(manager.bots) == 8
    assert not any(bot['state'].get('in_story') or bot['state'].get('in_season')
                   for bot in manager.bots.values())


def test_future_training_goals_reach_new_frontier_without_changing_saved_goals():
    engine = engine_for((1, 1, 99))
    manager = manager_for(engine, count=2)
    bot = manager.bots['bot:00001']
    assert set(manager._training_goal(bot, round_number) for round_number in range(1, 85)) == set(range(16, 100))
    before = owned(bot)
    bot['runtime'].update(training_goal=40, training_round=1,
                          training_uids=list(before), training_peak=3)
    manager._execute(bot, 'digilab', {'action': 'enter'})
    manager._manage_party(bot)
    assert bot['runtime']['training_goal'] == 40
    assert owned(bot) == before
    manager.flush(force=True, now=1)
    restored = manager_for(engine, count=2, store=manager.store, now=1000)
    assert restored.bots[bot['id']]['runtime']['training_goal'] == 40
    assert owned(restored.bots[bot['id']]) == before


def test_frontier_cohort_is_not_reset_or_rotated_before_earned_goal():
    manager = manager_for(engine_for((1, 1, 99)), count=1)
    bot = manager.bots['bot:00001']
    # Mature save fixture: a real high-level partner training towards99, with a
    # younger owned reserve waiting. No awarded levels occur in the operations.
    veteran = manager.engine._monster('agumon', level=80, abi=100, cam=100)
    recruit = manager.engine._monster('agumon', level=1)
    bot['state']['party'] = [veteran]
    bot['state']['storage'] = [recruit]
    manager._execute(bot, 'digilab', {'action': 'enter'})
    bot['runtime'].update(training_goal=99, training_round=3, training_peak=80,
                          training_uids=[veteran['uid']], training_start_wins=0)
    bot['stats']['wild_wins'] = 100
    before = owned(bot)
    assert any(route['eligible'] for route in manager.engine.evolution_options(veteran))
    manager._manage_party(bot)
    manager._evolve(bot)
    assert bot['runtime']['training_uids'] == [veteran['uid']]
    assert owned(bot) == before
    assert bot['stats']['training_rotations'] == 0
    assert bot['stats']['evolutions'] == 0


def test_frontier_partner_reaches_level99_through_real_wild_battle_xp():
    manager = manager_for(engine_for((1, 1, 99)), count=1)
    bot = manager.bots['bot:00001']
    # An explicit near-cap saved team; every subsequent XP point and level is
    # produced by the ordinary encounter/turn/reward path, never a test setter.
    veteran = manager.engine._monster('agumon', level=98, abi=100, cam=100)
    recruit = manager.engine._monster('agumon', level=1)
    bot['state']['party'] = [veteran]
    bot['state']['storage'] = [recruit]
    bot['runtime'].update(training_goal=99, training_round=3, training_peak=98,
                          training_uids=[veteran['uid']], training_start_wins=0)
    high_map = next(mid for mid, area in manager.engine.maps.items() if area['level'] == 99)
    old_map = bot['state']['map_id']
    manager._execute(bot, 'travel', {'map_id': high_map})
    manager.by_map[old_map].remove(bot['id'])
    manager.by_map[high_map].add(bot['id'])
    for _ in range(40):
        manager._execute(bot, 'encounter', {})
        for _turn in range(500):
            if not bot['state'].get('battle'):
                break
            manager._execute(bot, 'battle', manager._battle_action(bot))
        assert not bot['state'].get('battle')
        manager._execute(bot, 'digilab', {'action': 'enter'})
        manager._manage_party(bot)
        manager._evolve(bot)
        if owned(bot)[veteran['uid']]['level'] == 99:
            break
        manager._execute(bot, 'digilab', {'action': 'return'})
    assert owned(bot)[veteran['uid']]['level'] == 99
    assert owned(bot)[veteran['uid']]['xp'] == 0
    assert owned(bot)[veteran['uid']]['species_id'] == 'agumon'
    assert bot['stats']['wild_wins'] > 0 and bot['stats']['xp_earned'] > 0
    assert bot['stats']['level_ups'] == 1
    assert bot['stats']['training_rotations'] == 1
    assert veteran['uid'] in {m['uid'] for m in bot['state']['storage']}
    assert bot['state']['party'][0]['uid'] == recruit['uid']
