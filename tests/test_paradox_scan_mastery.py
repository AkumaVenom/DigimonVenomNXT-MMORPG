"""Permanent mastery pays only on wild victory, through normal scan settlement."""
import copy
import json
from pathlib import Path

import pytest

from venom.common.game import GameEngine


@pytest.fixture
def game():
    engine = GameEngine(Path(__file__).resolve().parents[1], seed=71)
    state = engine.new_player("ScanMaster", next(iter(engine.tamers)), "agumon")
    engine.handle(state, "digifarm", {"action": "return"})
    state["permanent_rewards"] = {"paradox_scan_mastery": True}
    return engine, state


def encounter(engine, state, *, count=1, paradox=True):
    species = next(s["id"] for s in engine.species.values() if bool(s.get("paradox")) == paradox)
    engine.handle(state, "encounter", {})
    state["battle"].update(enemies=[engine._monster(species, 1) for _ in range(count)],
                          active=[0], actor=0, scanned=[], queue=[], clock=0)
    return species


def defeat(engine, state, index):
    state["battle"]["enemies"][index]["hp"] = 0
    engine._scan_defeat(state, index)


def test_victory_adds_twenty_percent_once_after_reconnect(game):
    engine, state = game
    sid = encounter(engine, state, count=2)
    defeat(engine, state, 0)
    assert state["scan"][sid] == 5  # No victory bonus on a partial battle.
    engine._scan_defeat(state, 0)
    resumed = json.loads(json.dumps(state))
    defeat(engine, resumed, 1)
    assert resumed["scan"][sid] == 10
    assert engine._check_end(resumed)
    assert resumed["scan"][sid] == 12
    engine._check_end(resumed)
    assert resumed["scan"][sid] == 12


@pytest.mark.parametrize("outcome", ["flee", "loss"])
def test_partial_battle_never_pays_victory_bonus(game, outcome):
    engine, state = game
    sid = encounter(engine, state, count=2)
    defeat(engine, state, 0)
    if outcome == "flee":
        engine.handle(state, "battle", {"action": "flee"})
    else:
        state["party"][0]["hp"] = 0
        engine._check_end(state)
    assert state["battle"] is None
    assert state["scan"][sid] == 5


@pytest.mark.parametrize("earned,paradox,expected", [(False, True, 5), (True, False, 20)])
def test_only_unlocked_paradox_wins_receive_bonus(game, earned, paradox, expected):
    engine, state = game
    state["permanent_rewards"]["paradox_scan_mastery"] = earned
    sid = encounter(engine, state, paradox=paradox)
    defeat(engine, state, 0)
    engine._check_end(state)
    assert state["scan"][sid] == expected


@pytest.mark.parametrize("kind", ["story", "season"])
def test_owned_npc_partners_cannot_be_scanned(game, kind):
    engine, state = game
    sid = encounter(engine, state)
    state["battle"].update(kind=kind, story_training=False)
    defeat(engine, state, 0)
    assert sid not in state["scan"]
    assert "paradox_mastery_pending" not in state["battle"]


def test_cap_and_fractional_custom_rate(game):
    engine, state = game
    engine.rules["paradox_scan_gain"] = 7
    sid = encounter(engine, state)
    defeat(engine, state, 0)
    engine._check_end(state)
    assert state["scan"][sid] == 8.4
    sid = encounter(engine, state)
    state["scan"][sid] = 198
    defeat(engine, state, 0)
    engine._check_end(state)
    assert state["scan"][sid] == 200


def test_permanent_reward_not_consumed_by_materialization(game):
    engine, state = game
    sid = encounter(engine, state)
    state["scan"][sid] = 194
    defeat(engine, state, 0)
    engine._check_end(state)
    assert state["scan"][sid] == 200
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "materialize", {"species_id": sid})
    assert state["scan"][sid] == 0
    assert state["permanent_rewards"]["paradox_scan_mastery"] is True
