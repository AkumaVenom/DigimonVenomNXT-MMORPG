"""Exhausted partners retain the normal Attack in human and rival battles."""
import copy
import json
import random

import pytest

from venom.common.game import GameEngine, GameError
from venom.server.bots import BotManager


@pytest.fixture
def battle(tmp_path):
    (tmp_path / 'data').mkdir()
    species = {'id': 'partner', 'name': 'Partner', 'stage': 'rookie',
               'type': 'free', 'attribute': 'neutral', 'paradox': False,
               'base_id': 'partner', 'sprites': {}, 'evolutions': [],
               'base_stats': {'hp': 240, 'sp': 50, 'atk': 40, 'def': 25, 'int': 36, 'spd': 30}}
    catalog = {'species': [species], 'tamers': [{'id': 'tamer', 'name': 'Tamer', 'frames': {}}],
               'maps': [{'id': 'field', 'name': 'Field', 'level': 1, 'width': 500,
                         'height': 500, 'spawn': [250, 250]}]}
    (tmp_path / 'data/catalog.json').write_text(json.dumps(catalog))
    engine = GameEngine(tmp_path, seed=17)
    state = engine.new_player('test', 'tamer', 'partner')
    engine.handle(state, 'digifarm', {'action': 'return'})
    enemy = engine._monster('partner', level=20)
    state['battle'] = {'id': 'free-attack', 'enemies': [enemy], 'active': [0], 'actor': 0,
                       'turn': 1, 'clock': 0.0, 'scanned': [],
                       'queue': [{'side': 'enemy', 'index': 0, 'at': 1000000.0}]}
    state['events'] = []
    return engine, state


def test_attack_power_cost_and_turn_are_identical_at_zero_and_positive_sp(battle):
    engine, initial = battle
    damage = []
    for sp in (0, 1, 30):
        state = copy.deepcopy(initial)
        state['party'][0]['sp'] = sp
        before_hp = state['party'][0]['hp']
        engine.rng = random.Random(12345)
        engine.handle(state, 'battle', {'action': 'attack', 'target': 0})
        hit = next(event for event in state['events'] if event['kind'] == 'damage')
        assert hit['move'] == 'Attack'
        assert hit['amount'] > 0
        damage.append(hit['amount'])
        assert state['party'][0]['sp'] == sp
        assert state['party'][0]['hp'] == before_hp  # No recoil or enemy turn.
        assert state['battle']['turn'] == 2
    assert len(set(damage)) == 1


def test_retired_command_cannot_change_resources_damage_or_turn(battle):
    engine, state = battle
    state['party'][0]['sp'] = 0
    before = copy.deepcopy(state)
    with pytest.raises(GameError, match='Unknown battle action'):
        engine.handle(state, 'battle', {'action': 'struggle', 'target': 0})
    assert state == before


def test_unaffordable_skill_guides_back_to_free_attack_without_spending_turn(battle):
    engine, state = battle
    state['party'][0]['sp'] = 0
    before = copy.deepcopy(state)
    with pytest.raises(GameError, match='Not enough SP.*Attack') as exc:
        engine.handle(state, 'battle', {'action': 'skill', 'skill_index': 0, 'target': 0})
    assert 'struggle' not in str(exc.value).lower()
    assert state == before
    engine.handle(state, 'battle', {'action': 'attack', 'target': 0})
    assert state['battle']['turn'] == before['battle']['turn'] + 1


@pytest.mark.parametrize('sp', [0, 1])
def test_wild_rival_without_affordable_skill_uses_normal_attack(battle, sp):
    engine, state = battle
    state['party'][0]['sp'] = sp
    state['inventory'] = {}
    manager = BotManager(engine, object(), config={'enabled': False})
    command = manager._battle_action({'state': state})
    assert command == {'action': 'attack', 'target': 0}
    engine.handle(state, 'battle', command)
    assert state['party'][0]['sp'] == sp
    assert any(event.get('move') == 'Attack' for event in state['events'])
