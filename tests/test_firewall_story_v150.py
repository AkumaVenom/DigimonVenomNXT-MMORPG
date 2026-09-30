"""Dawn's permanent reward survives its living championship and old saves.

The final-battle prerequisite fixture isolates reward boundaries. The existing
fresh-rookie story acceptance tests separately earn every preceding badge/trial
through real combat, and also verify the first-win reward.
"""
import copy
import json
from pathlib import Path

import pytest

from venom.common import story
from venom.common.game import GameEngine, GameError, variety_of
from venom.server.database import Database
from test_story_engine import fight, start, strong_team
from test_shiny_gameplay_v120 import EventRng

ROOT = Path(__file__).resolve().parents[1]
FLAG = "firewall_scan_mastery"


@pytest.fixture
def game():
    engine = GameEngine(ROOT, seed=19)
    return engine, engine.new_player("FireWallRelay", next(iter(engine.tamers)), "agumon")


def prepare_final(engine, state):
    engine.handle(state, "story", {"action": "enter", "campaign_id": story.DAWN_CAMPAIGN})
    data = story.content(engine)
    profile = state["story"]
    profile["badges"] = story._badges(data)
    profile["completed"] = [row["id"] for row in data["npcs"].values()
                            if row["role"] in ("trainer", "warden")]
    strong_team(engine, state)
    return data, data["npcs"][data["champion_id"]]


def mastery(state):
    return bool(state.get("permanent_rewards", {}).get(FLAG))


def test_first_final_loss_retry_defence_loss_reclaim_unlocks_only_once(game):
    engine, state = game
    data, final = prepare_final(engine, state)
    for partner in state["party"]:
        partner["hp"] = 1
    start(engine, state, final)
    fight(engine, state)
    profile = state["story"]
    assert not profile["recent"][0]["won"]
    assert not mastery(state) and not profile["champion"]["first_victory"]
    assert profile["recent"][0]["scan_mastery_variety"] == "firewall"
    assert not profile["recent"][0]["scan_mastery_unlocked"]

    start(engine, state, final)
    battle_id = state["battle"]["id"]
    fight(engine, state)
    assert profile["champion"]["first_victory"] and mastery(state)
    assert profile["recent"][0]["scan_mastery_unlocked"]
    assert profile["view"]["scan_bonus"] == profile["view"]["firewall_scan_bonus"] == 20
    assert profile["view"]["paradox_scan_bonus"] == profile["view"]["shiny_scan_bonus"] == 0
    assert len([event for event in state["events"] if event["kind"] == "story_mastery"]) == 1
    assert "5% to 6%" in profile["dialogue"]["lines"][0]
    wallet = state["credits"]
    with pytest.raises(story.StoryError):
        story.settle(engine, state, True)
    with pytest.raises(GameError):
        engine.handle(state, "battle", {"action": "attack", "battle_id": battle_id, "expected_turn": 0})
    assert state["credits"] == wallet

    for win in (True, False, True):
        opponent = story._champion_npc(profile, data)
        if not win:
            for partner in state["party"]:
                partner["hp"] = 1
        start(engine, state, opponent)
        fight(engine, state)
        assert profile["recent"][0]["won"] is win
        assert not profile["recent"][0]["scan_mastery_unlocked"]
        assert not any(event["kind"] == "story_mastery" for event in state["events"])
        assert mastery(state) and profile["view"]["firewall_scan_bonus"] == 20
    assert profile["champion"]["reigns"] == 2
    assert profile["champion"]["defenses"] == 1
    assert profile["champion"]["status"] == "defending"
    assert state["scan"] == {}  # Every opponent above was an owned NPC team.


@pytest.mark.parametrize("parked", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("status,completed", [("challenger", False), ("defending", True), ("reclaim", True)])
def test_legacy_active_and_parked_champions_repair_only_entitlement(game, parked, legacy, status, completed):
    engine, state = game
    profile = {"champion": {"first_victory": completed, "status": status}}
    if not legacy:
        profile["campaign_id"] = story.DAWN_CAMPAIGN
    state["story"] = None if parked else profile
    state["story_campaigns"] = {story.DAWN_CAMPAIGN: profile} if parked else {}
    state["permanent_rewards"] = {"paradox_scan_mastery": True, "shiny_scan_mastery": True}
    state["scan"] = {"agumon_firewall": 0, "agumon_shiny": 42, "agumon_paradox": 6}
    before = copy.deepcopy({key: state[key] for key in ("scan", "credits", "party", "storage", "inventory")})
    for _ in range(3):
        engine._refresh(state)
        assert mastery(state) is completed
        assert state["permanent_rewards"]["paradox_scan_mastery"]
        assert state["permanent_rewards"]["shiny_scan_mastery"]
        assert {key: state[key] for key in before} == before
        assert profile["champion"]["status"] == status


@pytest.mark.parametrize("campaign,flag", [(story.DS_CAMPAIGN, "paradox_scan_mastery"),
                                         (story.XROS_CAMPAIGN, "shiny_scan_mastery")])
def test_other_campaign_completions_never_grant_dawn_mastery(game, campaign, flag):
    engine, state = game
    state["story_campaigns"] = {campaign: {"campaign_id": campaign, "champion": {"first_victory": True}}}
    state["permanent_rewards"] = {flag: True}
    engine._refresh(state)
    assert not mastery(state)


def test_real_win_three_campaign_switch_and_sqlite_restart_repair(game, tmp_path):
    engine, state = game
    _, final = prepare_final(engine, state)
    start(engine, state, final)
    fight(engine, state)
    original_id = state["story"]["id"]
    assert mastery(state)
    for campaign in (story.DS_CAMPAIGN, story.XROS_CAMPAIGN):
        engine.handle(state, "story", {"action": "return"})
        engine.handle(state, "story", {"action": "enter", "campaign_id": campaign})
        assert state["story"]["view"]["firewall_scan_bonus"] == 20
        assert state["story"]["view"]["scan_bonus"] == 0
        assert not state["story"]["champion"]["first_victory"]
    legacy = state["story_campaigns"][story.DAWN_CAMPAIGN]
    legacy.pop("campaign_id")
    legacy["champion"].update(status="reclaim", holder="Nox", holder_id="citadel_challenger_1")
    state["permanent_rewards"].pop(FLAG)
    state["scan"]["agumon_firewall"] = 0
    before = copy.deepcopy({key: state[key] for key in ("party", "storage", "inventory", "credits", "scan")})
    config = {"driver": "sqlite", "path": str(tmp_path / "legacy-firewall.sqlite3")}
    database = Database(config, dev=True)
    database.initialize()
    key = database.register(state["username"], "test-password-123", state)
    database.close()
    database = Database(config, dev=True)
    try:
        restored, revision = database.load(key)
        new_engine = GameEngine(ROOT, seed=151)
        new_engine._refresh(restored)
        assert mastery(restored)
        assert restored["story"]["campaign_id"] == story.XROS_CAMPAIGN
        assert restored["story"]["view"]["firewall_scan_bonus"] == 20
        assert {key: restored[key] for key in before} == before
        database.save(key, restored, revision)
        new_engine.handle(restored, "story", {"action": "return"})
        new_engine.handle(restored, "story", {"action": "enter", "campaign_id": story.DAWN_CAMPAIGN})
        assert restored["story"]["id"] == original_id
        assert restored["story"]["champion"]["status"] == "reclaim"
        assert restored["story"]["view"]["scan_bonus"] == 20
        other = new_engine.new_player("OtherRelay", next(iter(new_engine.tamers)), "agumon")
        new_engine.handle(other, "story", {"action": "enter"})
        assert not mastery(other) and other["story"]["view"]["scan_bonus"] == 0
    finally:
        database.close()


@pytest.mark.parametrize("campaign", story.CAMPAIGN_IDS)
def test_private_training_firewall_roll_and_mastery_uses_actual_wild_combat(game, campaign):
    engine, state = game
    state["party"] = [engine._monster("agumon", 99, abi=200, cam=100)]
    state["permanent_rewards"] = {FLAG: True}
    engine.handle(state, "story", {"action": "enter", "campaign_id": campaign})
    if campaign != story.DAWN_CAMPAIGN:
        engine.handle(state, "story", {"action": "travel", "chapter": 1})
    engine.rng = EventRng(.012)
    engine.handle(state, "story", {"action": "train"})
    assert state["battle"]["story_training"]
    enemy = state["battle"]["enemies"][0]
    assert variety_of(enemy) == "firewall"
    sid = enemy["species_id"]
    # Preserve a live FireWall training turn through ordinary JSON serialization.
    restored = json.loads(json.dumps(state))
    engine._refresh(restored)
    fight(engine, restored)
    assert restored["story"]["recent"][0]["won"]
    assert restored["scan"][sid] == 6


@pytest.mark.parametrize("owned_variety", ["shiny", "firewall"])
def test_owned_rare_partner_never_guarantees_that_variety_in_opening_practice(game, owned_variety):
    engine, state = game
    state["party"] = [engine._monster(f"agumon_{owned_variety}", 5)]
    engine.handle(state, "story", {"action": "enter"})
    engine.rng = EventRng(.5)
    engine.handle(state, "story", {"action": "train"})
    enemy = state["battle"]["enemies"][0]
    assert enemy["species_id"] == "agumon"
    assert variety_of(enemy) == "normal"
    assert state["party"][0]["species_id"] == f"agumon_{owned_variety}"


def test_authored_dawn_reward_is_readable_and_does_not_replace_story_teams(game):
    engine, _ = game
    data = story.content(engine)
    assert data["completion_reward"] == {"flag": FLAG, "variety": "firewall", "scan_bonus_percent": 20}
    assert "FireWall" in data["introduction"] and "5% to 6%" in data["introduction"]
    for npc in (*data["npcs"].values(), *data["challengers"]):
        assert all(variety_of(engine.species[partner["species"]]) == "normal" for partner in npc["team"])
