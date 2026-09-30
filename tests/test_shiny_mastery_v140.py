"""Independent scan masteries use the normal, server-owned combat controls.

The small catalog fixture also exercises stale variety flags, fractional server
rates and restored pre-v1.4.0 Paradox battles without importing release art.
"""
import copy
import json
from pathlib import Path

import pytest

from venom.common.game import GameEngine, GameError
from test_shiny_gameplay_v120 import EventRng, game


def start(engine, state, species_ids):
    engine.rng = EventRng(.5, len(species_ids))
    engine.handle(state, "encounter", {})
    battle = state["battle"]
    battle["enemies"] = [engine._monster(sid, 1) for sid in species_ids]
    for enemy in battle["enemies"]:
        enemy["hp"] = enemy["max_hp"] = 20
    return battle


def attack(engine, state, index=0):
    battle = state["battle"]
    command = {"action": "attack", "target": index}
    if battle.get("kind") == "story":
        command.update(battle_id=battle["id"], expected_turn=battle["turn"])
    engine.handle(state, "battle", command)


@pytest.mark.parametrize("shiny,paradox", [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize("variety,base", [("normal", 20), ("shiny", 5), ("paradox", 5)])
@pytest.mark.parametrize("count", [1, 3])
def test_actual_wins_pay_only_the_matching_mastery(game, shiny, paradox, variety, base, count):
    engine, state = game
    state["permanent_rewards"] = {"shiny_scan_mastery": shiny, "paradox_scan_mastery": paradox}
    sid = "alpha" if variety == "normal" else f"alpha_{variety}"
    start(engine, state, [sid] * count)
    for index in range(count):
        attack(engine, state, index)
        if index < count - 1:
            assert state["scan"][sid] == base * (index + 1)
    bonus = 1 if variety != "normal" and state["permanent_rewards"][f"{variety}_scan_mastery"] else 0
    assert state["battle"] is None
    assert state["scan"] == {sid: count * (base + bonus)}
    assert engine._check_end(state)
    assert state["scan"][sid] == count * (base + bonus)


@pytest.mark.parametrize("outcome", ["flee", "loss"])
def test_partial_shiny_battle_keeps_base_scans_without_victory_bonus(game, outcome):
    engine, state = game
    state["permanent_rewards"] = {"shiny_scan_mastery": True, "paradox_scan_mastery": True}
    start(engine, state, ["alpha_shiny", "alpha"])
    attack(engine, state)
    assert state["scan"]["alpha_shiny"] == 5
    assert state["battle"]["shiny_mastery_pending"] == {"alpha_shiny": 1}
    state = json.loads(json.dumps(state))
    engine._refresh(state)
    if outcome == "flee":
        engine.handle(state, "battle", {"action": "flee"})
    else:
        # The living opponent now wins through its real next combat turn.
        state["party"][0]["hp"] = 1
        state["party"][0]["spd"] = 1
        state["battle"]["enemies"][1]["atk"] = 100000
        engine.handle(state, "battle", {"action": "guard"})
    assert state["battle"] is None
    assert state["scan"] == {"alpha_shiny": 5}
    assert state["permanent_rewards"]["shiny_scan_mastery"] is True


def test_mixed_multikill_reconnect_and_settlement_are_independent_and_once_only(game):
    engine, state = game
    state["permanent_rewards"] = {"shiny_scan_mastery": True, "paradox_scan_mastery": True}
    start(engine, state, ["alpha_shiny", "alpha_paradox", "alpha"])
    attack(engine, state, 0)
    attack(engine, state, 1)
    assert state["scan"] == {"alpha_shiny": 5, "alpha_paradox": 5}
    restored = json.loads(json.dumps(state))
    engine._refresh(restored)
    engine._scan_defeat(restored, 0)  # Restoring an already-scanned enemy is harmless.
    assert restored["scan"] == state["scan"]
    attack(engine, restored, 2)
    assert restored["scan"] == {"alpha_shiny": 6, "alpha_paradox": 6, "alpha": 20}
    before = copy.deepcopy(restored["scan"])
    engine._award_scan_mastery(restored)
    engine._check_end(restored)
    assert restored["scan"] == before


def test_legacy_pending_paradox_rewards_survive_new_release(game):
    engine, state = game
    state["permanent_rewards"] = {"paradox_scan_mastery": True}
    battle = start(engine, state, ["alpha_paradox", "alpha"])
    battle["enemies"][0]["hp"] = 0
    battle["scanned"] = [0]
    battle["paradox_mastery_pending"] = {"alpha_paradox": 1}
    state["scan"]["alpha_paradox"] = 5
    state = json.loads(json.dumps(state))
    engine._refresh(state)
    attack(engine, state, 1)
    assert state["scan"]["alpha_paradox"] == 6
    assert "alpha_shiny" not in state["scan"]


@pytest.mark.parametrize("rate,expected", [(7, 8.4), (.125, .15)])
def test_custom_scan_rates_keep_fractional_twenty_percent_and_cap(game, rate, expected):
    engine, state = game
    state["permanent_rewards"] = {"shiny_scan_mastery": True}
    engine.rules["shiny_scan_gain"] = rate
    start(engine, state, ["alpha_shiny"])
    attack(engine, state)
    assert state["scan"]["alpha_shiny"] == expected
    state["scan"]["alpha_shiny"] = 199.99
    start(engine, state, ["alpha_shiny"])
    attack(engine, state)
    assert state["scan"]["alpha_shiny"] == 200


def test_mastery_survives_materialization_and_cannot_be_claimed_during_battle(game):
    engine, state = game
    state["permanent_rewards"] = {"shiny_scan_mastery": True}
    state["scan"]["alpha_shiny"] = 94
    start(engine, state, ["alpha_shiny", "alpha"])
    attack(engine, state)
    assert state["scan"]["alpha_shiny"] == 99
    with pytest.raises(GameError, match="current battle"):
        engine.handle(state, "materialize", {"species_id": "alpha_shiny"})
    attack(engine, state, 1)
    assert state["scan"]["alpha_shiny"] == 100
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "materialize", {"species_id": "alpha_shiny"})
    assert state["scan"]["alpha_shiny"] == 0
    engine._refresh(state)
    assert state["scan"]["alpha_shiny"] == 0
    assert state["permanent_rewards"]["shiny_scan_mastery"] is True
    assert state["party"][-1]["species_id"] == "alpha_shiny"


@pytest.mark.parametrize("kind", ["story", "season", "ranked", "npc", "quest"])
@pytest.mark.parametrize("sid", ["alpha", "alpha_paradox", "alpha_shiny"])
def test_owned_opponents_never_give_base_or_mastery_scan(game, kind, sid):
    engine, state = game
    state["permanent_rewards"] = {"shiny_scan_mastery": True, "paradox_scan_mastery": True}
    battle = start(engine, state, [sid])
    battle.update(kind=kind, story_training=False)
    battle["enemies"][0]["hp"] = 0
    engine._scan_defeat(state, 0)
    engine._award_scan_mastery(state)
    assert state["scan"] == {}
    assert not battle.get("shiny_mastery_pending")
    assert not battle.get("paradox_mastery_pending")


@pytest.mark.parametrize("campaign", ["dawn_relay", "world_ds_paradox", "xros_ghostline"])
def test_real_private_field_training_receives_the_same_shiny_bonus(campaign):
    engine = GameEngine(Path(__file__).resolve().parents[1], seed=140)
    state = engine.new_player("ShinyGraduate", next(iter(engine.tamers)), "agumon")
    state["party"] = [engine._monster("agumon", 99, abi=200, cam=100)]
    state["permanent_rewards"] = {"shiny_scan_mastery": True, "paradox_scan_mastery": True}
    engine.handle(state, "story", {"action": "enter", "campaign_id": campaign})
    if campaign != "dawn_relay":
        engine.handle(state, "story", {"action": "travel", "chapter": 1})
    engine.rng = EventRng(0)
    engine.handle(state, "story", {"action": "train"})
    assert state["battle"]["story_training"]
    shiny = next(enemy["species_id"] for enemy in state["battle"]["enemies"] if enemy["shiny"])
    for _ in range(100):
        if not state["battle"]:
            break
        target = next(i for i, enemy in enumerate(state["battle"]["enemies"]) if enemy["hp"] > 0)
        attack(engine, state, target)
    assert state["battle"] is None
    assert state["scan"][shiny] == 6
    assert state["permanent_rewards"] == {"shiny_scan_mastery": True, "paradox_scan_mastery": True}


@pytest.mark.parametrize("parked", [False, True])
@pytest.mark.parametrize("completed", [False, True])
def test_completed_active_or_parked_profile_repairs_only_permanent_flag(game, parked, completed):
    engine, state = game
    profile = {"campaign_id": "xros_ghostline", "champion": {"first_victory": completed}}
    state["story"] = None if parked else profile
    state["story_campaigns"] = {"xros_ghostline": profile} if parked else {}
    state["permanent_rewards"] = {"paradox_scan_mastery": True}
    # A materialized scan stays consumed when a completion is re-imported.
    state["scan"] = {"alpha_shiny": 0, "alpha_paradox": 42}
    before = copy.deepcopy({k: state[k] for k in ("scan", "credits", "party", "storage", "inventory")})
    for _ in range(3):
        engine._refresh(state)
        assert bool(state["permanent_rewards"].get("shiny_scan_mastery")) is completed
        assert state["permanent_rewards"]["paradox_scan_mastery"] is True
        assert {k: state[k] for k in before} == before
