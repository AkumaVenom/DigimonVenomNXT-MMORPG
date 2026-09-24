"""DigiFarm training survives arena snapshots; private homes have no field rivals."""
import copy
from pathlib import Path
from unittest.mock import Mock

import pytest

from venom.common.game import GameEngine
from venom.server.community import Community
from venom.server.community_store import CommunityStore
from venom.server.database import Database
from venom.server.ranked import RankedService


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def arena():
    engine = GameEngine(ROOT, seed=87)
    db = Database({'driver': 'sqlite', 'path': ':memory:'}, dev=True)
    db.initialize()
    store = CommunityStore(db)
    store.initialize()
    ranked = RankedService(engine, store, {'match_cooldown': 0, 'opponent_cooldown': 0},
                           clock=lambda: 1_800_000_000.0)
    try:
        yield engine, ranked, store
    finally:
        db.close()


def profile(engine, ident):
    monster = engine._monster(engine.starters[0], level=12)
    monster['skills'] = []  # Isolate a physical strike from skill-selection effects.
    return {'id': ident, 'name': ident, 'kind': 'player',
            'tamer': next(iter(engine.tamers)), 'party': [monster]}


def train(monster):
    bonuses = {'hp': 5, 'sp': 5, 'atk': 5, 'def': 5, 'int': 5, 'spd': 5}
    monster['farm_bonuses'] = bonuses
    for stat, amount in bonuses.items():
        monster[stat] += amount
    monster['max_hp'] += bonuses['hp']
    monster['max_sp'] += bonuses['sp']


def test_permanent_training_is_durable_in_defender_snapshot_and_replay(arena):
    engine, ranked, store = arena
    trained, opponent = profile(engine, 'player:trained'), profile(engine, 'player:rival')
    train(trained['party'][0])
    trained['party'][0]['hp'] = 1
    trained['party'][0]['sp'] = 0
    original = copy.deepcopy(trained)
    ranked.register_many([trained, opponent])

    restarted = RankedService(engine, store, ranked.config, clock=ranked.clock)
    assert restarted.profiles[trained['id']]['party'] == trained['party']
    result = restarted.start_match(trained['id'], opponent['id'], 'farm-training-replay')
    snapshot = result['replay']['party'][0]
    assert snapshot['farm_bonuses'] == trained['party'][0]['farm_bonuses']
    for stat in ('max_hp', 'max_sp', 'atk', 'def', 'int', 'spd'):
        assert snapshot[stat] == trained['party'][0][stat]
    assert snapshot['hp'] == snapshot['max_hp']
    assert snapshot['sp'] == snapshot['max_sp']
    assert trained == original
    assert restarted.profiles[trained['id']]['party'] == original['party']
    persisted = next(row for row in store.profiles() if row['id'] == trained['id'])
    assert persisted['party'] == original['party']


def test_permanent_attack_training_changes_actual_arena_damage(arena):
    engine, ranked, _ = arena
    untrained = profile(engine, 'player:attacker')
    defender = profile(engine, 'player:defender')
    trained = copy.deepcopy(untrained)
    trained['party'][0]['farm_bonuses'] = {'atk': 5}
    trained['party'][0]['atk'] += 5

    def first_hit(attacker):
        battle = ranked._fight(attacker, defender, 'identical-rng-for-training')
        return next(event['amount'] for event in battle['replay']['events']
                    if event['kind'] == 'damage' and event['attacker_side'] == 'player')

    assert first_hit(trained) > first_hit(untrained)


def test_home_has_no_nearby_rivals_or_invitations_and_rejects_old_field_challenge():
    community = Community.__new__(Community)
    community.bots = Mock()
    community.challenges = {}
    community.next_invite = {}
    state = {'username': 'Farmer', 'in_farm': True, 'in_lab': False, 'battle': None,
             'map_id': 'field', 'x': 10, 'y': 10}
    assert community._nearby(state, 10) == []
    community._offer(state, 10)
    assert community.challenges == {}
    assert community.next_invite == {}
    community.bots.snapshot.assert_not_called()
    with pytest.raises(ValueError, match='Return to the field'):
        community._challenge_bot(state, 'bot:00001', require_nearby=False)
    community.bots.profile.assert_not_called()


def test_battle_park_remains_available_from_private_home():
    # Arena combat uses private snapshots, so entering the home must not disable
    # its top-level navigation like local field rival challenges.
    Community._peace({'in_farm': True, 'in_lab': False, 'battle': None})
