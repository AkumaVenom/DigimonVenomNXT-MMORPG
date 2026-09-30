"""FireWall victory scans, pending bonuses and other masteries stay independent."""
import copy
import itertools
import json
from pathlib import Path

import pytest

from venom.common.game import GameEngine, GameError
from test_firewall_gameplay_v150 import game
from test_shiny_gameplay_v120 import EventRng
from test_shiny_mastery_v140 import attack, start


@pytest.mark.parametrize("variety,base", [("normal", 20), ("paradox", 5), ("shiny", 5), ("firewall", 5)])
@pytest.mark.parametrize("count", [1, 3])
def test_wild_victories_apply_only_each_owned_matching_mastery(game, variety, base, count):
    engine, initial = game
    sid = "alpha" if variety == "normal" else f"alpha_{variety}"
    for flags in itertools.product((False, True), repeat=3):
        state = copy.deepcopy(initial)
        state["permanent_rewards"] = {f"{key}_scan_mastery": flag
            for key, flag in zip(("paradox", "shiny", "firewall"), flags)}
        start(engine, state, [sid] * count)
        for index in range(count):
            attack(engine, state, index)
            if index < count - 1:
                assert state["scan"][sid] == base * (index + 1)
        bonus = int(variety != "normal" and state["permanent_rewards"][f"{variety}_scan_mastery"])
        assert state["battle"] is None
        assert state["scan"] == {sid: count * (base + bonus)}
        engine._award_scan_mastery(state)
        assert engine._check_end(state)
        assert state["scan"][sid] == count * (base + bonus)
        if variety == "firewall" and bonus:
            assert any("FireWall Scan Mastery" in event["text"] for event in state["events"])


@pytest.mark.parametrize("outcome", ["flee", "loss"])
def test_partial_firewall_encounter_retains_base_but_never_victory_bonus(game, outcome):
    engine, state = game
    state["permanent_rewards"] = {"firewall_scan_mastery": True}
    start(engine, state, ["alpha_firewall", "alpha"])
    attack(engine, state)
    assert state["scan"]["alpha_firewall"] == 5
    assert state["battle"]["firewall_mastery_pending"] == {"alpha_firewall": 1}
    state = json.loads(json.dumps(state))
    engine._refresh(state)
    if outcome == "flee":
        engine.handle(state, "battle", {"action": "flee"})
    else:
        state["party"][0]["hp"] = 1
        state["party"][0]["spd"] = 1
        state["battle"]["enemies"][1]["atk"] = 100000
        engine.handle(state, "battle", {"action": "guard"})
    assert state["battle"] is None
    assert state["scan"] == {"alpha_firewall": 5}
    assert state["permanent_rewards"]["firewall_scan_mastery"]


def test_all_three_pending_masteries_survive_reconnect_and_pay_once(game):
    engine, state = game
    state["permanent_rewards"] = {f"{variety}_scan_mastery": True for variety in ("paradox", "shiny", "firewall")}
    start(engine, state, ["alpha_firewall", "alpha_shiny", "alpha_paradox"])
    attack(engine, state, 0)
    attack(engine, state, 1)
    assert state["scan"] == {"alpha_firewall": 5, "alpha_shiny": 5}
    restored = json.loads(json.dumps(state))
    # Stale cached labels never change the authoritative scan family.
    restored["battle"]["enemies"][0].update(firewall=False, shiny=True, variety="shiny")
    engine._refresh(restored)
    engine._scan_defeat(restored, 0)
    assert restored["scan"] == state["scan"]
    attack(engine, restored, 2)
    assert restored["scan"] == {"alpha_firewall": 6, "alpha_shiny": 6, "alpha_paradox": 6}
    assert restored["battle"] is None
    engine._award_scan_mastery(restored)
    engine._check_end(restored)
    assert restored["scan"] == {"alpha_firewall": 6, "alpha_shiny": 6, "alpha_paradox": 6}


@pytest.mark.parametrize("old_variety", ["paradox", "shiny"])
def test_pre_firewall_saved_pending_mastery_is_not_lost_or_duplicated(game, old_variety):
    engine, state = game
    sid = f"alpha_{old_variety}"
    state["permanent_rewards"] = {f"{old_variety}_scan_mastery": True, "firewall_scan_mastery": True}
    battle = start(engine, state, [sid, "alpha"])
    battle["enemies"][0]["hp"] = 0
    battle["scanned"] = [0]
    battle[f"{old_variety}_mastery_pending"] = {sid: 1}
    state["scan"][sid] = 5
    state = json.loads(json.dumps(state))
    engine._refresh(state)
    attack(engine, state, 1)
    assert state["scan"] == {sid: 6, "alpha": 20}


@pytest.mark.parametrize("rate,expected", [(5, 6), (7, 8.4), (.125, .15)])
def test_firewall_fractional_custom_rates_and_scan_cap(game, rate, expected):
    engine, state = game
    state["permanent_rewards"] = {"firewall_scan_mastery": True}
    engine.rules["firewall_scan_gain"] = rate
    start(engine, state, ["alpha_firewall"])
    attack(engine, state)
    assert state["scan"]["alpha_firewall"] == expected
    state["scan"]["alpha_firewall"] = 199.99
    start(engine, state, ["alpha_firewall"])
    attack(engine, state)
    assert state["scan"]["alpha_firewall"] == 200


def test_mastery_allows_materialization_only_after_final_victory_and_is_not_consumed(game):
    engine, state = game
    state["permanent_rewards"] = {"firewall_scan_mastery": True}
    state["scan"]["alpha_firewall"] = 94
    start(engine, state, ["alpha_firewall", "alpha"])
    attack(engine, state)
    assert state["scan"]["alpha_firewall"] == 99
    with pytest.raises(GameError, match="current battle"):
        engine.handle(state, "materialize", {"species_id": "alpha_firewall"})
    attack(engine, state, 1)
    assert state["scan"]["alpha_firewall"] == 100
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "materialize", {"species_id": "alpha_firewall"})
    engine._refresh(state)
    assert state["scan"]["alpha_firewall"] == 0
    assert state["permanent_rewards"]["firewall_scan_mastery"]
    assert state["party"][-1]["species_id"] == "alpha_firewall"


@pytest.mark.parametrize("kind", ["story", "season", "ranked", "npc", "quest"])
def test_owned_battle_partners_never_give_firewall_scan_or_mastery(game, kind):
    engine, state = game
    state["permanent_rewards"] = {"firewall_scan_mastery": True}
    battle = start(engine, state, ["alpha_firewall"])
    battle.update(kind=kind, story_training=False)
    battle["enemies"][0]["hp"] = 0
    engine._scan_defeat(state, 0)
    # Even an unrelated obsolete pending record cannot leak into tamer scans.
    battle["firewall_mastery_pending"] = {"alpha_firewall": 1}
    engine._award_scan_mastery(state)
    assert state["scan"] == {}
    assert "firewall_mastery_pending" not in battle


def test_nonmatching_mastery_pending_records_never_pay(game):
    engine, state = game
    state["permanent_rewards"] = {"firewall_scan_mastery": True}
    battle = start(engine, state, ["alpha"])
    battle["firewall_mastery_pending"] = {"alpha_shiny": 1, "unknown_firewall": 1, "alpha": 1}
    attack(engine, state)
    assert state["scan"] == {"alpha": 20}


@pytest.mark.parametrize("campaign", ["dawn_relay", "world_ds_paradox", "xros_ghostline"])
def test_all_three_private_field_training_modes_award_firewall_mastery(campaign):
    engine = GameEngine(Path(__file__).resolve().parents[1], seed=150)
    state = engine.new_player("FireWallPractice", next(iter(engine.tamers)), "agumon")
    state["party"] = [engine._monster("agumon_firewall", 99, abi=200, cam=100)]
    state["permanent_rewards"] = {"firewall_scan_mastery": True}
    engine.handle(state, "story", {"action": "enter", "campaign_id": campaign})
    if campaign != "dawn_relay":
        engine.handle(state, "story", {"action": "travel", "chapter": 1})
    # Existing private practice has no Paradox roll; FireWall follows Shiny's 1%.
    engine.rng = EventRng(.014)
    engine.handle(state, "story", {"action": "train"})
    assert state["battle"]["story_training"]
    firewall = next(e["species_id"] for e in state["battle"]["enemies"] if e["firewall"])
    for _ in range(100):
        if not state["battle"]:
            break
        target = next(i for i, e in enumerate(state["battle"]["enemies"]) if e["hp"] > 0)
        attack(engine, state, target)
    assert state["battle"] is None
    assert state["scan"][firewall] == 6
    assert state["permanent_rewards"]["firewall_scan_mastery"]
