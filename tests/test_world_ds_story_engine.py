"""Server-side campaign boundaries, quest capabilities and durable reward tests.

Settlement is invoked directly only to isolate reward/idempotency boundaries;
test_world_ds_story_acceptance exercises the same campaign with real battle turns.
"""
import copy
import json
from pathlib import Path

import pytest

from venom.common import story
from venom.common.game import GameEngine, GameError


ROOT = Path(__file__).resolve().parents[1]
DS = "world_ds_paradox"
DAWN = "dawn_relay"


@pytest.fixture
def game():
    engine = GameEngine(ROOT, seed=62)
    state = engine.new_player("ParadoxTester", next(iter(engine.tamers)), "agumon")
    return engine, state


def command(engine, state, action, **fields):
    return engine.handle(state, "story", {"action": action, **fields})


def enter(engine, state, campaign=DS):
    command(engine, state, "enter", campaign_id=campaign)
    return state["story"]


def meet(engine, state, npc):
    data = story.content(engine, state["story"]["campaign_id"])
    region = next(row for row in data["regions"] if npc["map_id"] in row["maps"])
    command(engine, state, "travel", chapter=region["index"], map_id=npc["map_id"])
    state.update(x=npc["x"], y=npc["y"])
    command(engine, state, "talk", npc_id=npc["id"])
    while "next" in choices(state):
        choose(engine, state, "next")
    return state["story"]["view"]["dialogue"]


def choices(state):
    return {row["id"] for row in state["story"]["view"]["dialogue"]["choices"]}


def choose(engine, state, choice):
    command(engine, state, "dialogue", token=state["story"]["view"]["dialogue"]["token"], choice=choice)


def first_field(engine):
    data = story.content(engine, DS)
    npcs = [data["npcs"][ident] for ident in data["regions"][1]["npc_ids"]]
    return {row["role"]: row for row in npcs}


def test_legacy_dawn_and_ds_have_independent_saved_itineraries(game):
    engine, state = game
    original_world = copy.deepcopy({key: state.get(key) for key in story.LOCATION_FIELDS})
    dawn = enter(engine, state, DAWN)
    dawn.pop("campaign_id")  # A v0.10 save has no campaign discriminator.
    dawn["badges"].append("lumen")
    dawn["completed"].append("lumen_warden")
    command(engine, state, "return")
    ds = enter(engine, state)
    assert ds["badges"] == [] and ds["completed"] == []
    assert ds["id"] != dawn["id"]
    assert state["story_campaigns"][DAWN]["id"] == dawn["id"]
    command(engine, state, "travel", chapter=1)
    ds_location = {key: state[key] for key in ("map_id", "x", "y")}
    command(engine, state, "return")
    restored = enter(engine, state, DAWN)
    assert restored["id"] == dawn["id"] and restored["badges"] == ["lumen"]
    command(engine, state, "return")
    # Serialization must not depend on aliasing between active and parked profiles.
    state = json.loads(json.dumps(state))
    engine._refresh(state)
    assert enter(engine, state)["id"] == ds["id"]
    assert {key: state[key] for key in ds_location} == ds_location
    command(engine, state, "return")
    assert {key: state.get(key) for key in story.LOCATION_FIELDS} == original_world


def test_hub_is_peaceful_and_services_share_real_character_state(game):
    engine, state = game
    party = copy.deepcopy(state["party"])
    enter(engine, state)
    assert state["party"] == party
    view = state["story"]["view"]
    assert view["hub"] and not view["training_available"]
    assert view["badge_total"] == 17 and view["badge_count"] == 0
    assert view["chapters"][1]["unlocked"] and not view["chapters"][2]["unlocked"]
    assert not any(row["level"] for row in view["npcs"])
    with pytest.raises(GameError, match="peaceful"):
        command(engine, state, "train")
    with pytest.raises(GameError):
        engine.handle(state, "encounter", {})
    home = {key: state[key] for key in ("map_id", "x", "y")}
    command(engine, state, "camp")
    money, capsules = state["credits"], state["inventory"].get("hp_s", 0)
    engine.handle(state, "shop", {"item": "hp_s", "quantity": 1})
    assert state["credits"] < money and state["inventory"]["hp_s"] == capsules + 1
    command(engine, state, "field")
    engine.handle(state, "digifarm", {"action": "enter"})
    assert state["in_farm"] and state["in_story"]
    command(engine, state, "field")
    assert {key: state[key] for key in home} == home and not state["in_farm"]
    command(engine, state, "travel", chapter=1)
    assert state["story"]["view"]["training_available"]
    for _ in range(3):
        command(engine, state, "train")
        story.settle(engine, state, True)
        engine._refresh(state)
    assert state["party"][0]["level"] >= 10


def test_campaign_switch_rejects_active_story_and_foreign_requests(game):
    engine, state = game
    enter(engine, state)
    profile = copy.deepcopy(state["story"])
    for campaign in (DAWN, "unknown", True, None):
        with pytest.raises(GameError):
            command(engine, state, "enter", campaign_id=campaign)
    assert state["story"] == profile
    with pytest.raises(GameError, match="different Story campaign"):
        command(engine, state, "heal", campaign_id=DAWN)
    command(engine, state, "travel", chapter=1)
    command(engine, state, "train")
    with pytest.raises(GameError):
        command(engine, state, "return")
    with pytest.raises(GameError):
        command(engine, state, "enter", campaign_id=DAWN)


def test_exact_crest_prefix_opens_fields_not_duplicate_badge_counts(game):
    engine, state = game
    profile = enter(engine, state)
    data = story.content(engine, DS)
    profile["badges"] = [data["regions"][17]["badge"]["id"]] * 17
    with pytest.raises(GameError, match="preceding Paradox Crests"):
        command(engine, state, "travel", chapter=2)
    profile["badges"] = [data["regions"][1]["badge"]["id"]]
    command(engine, state, "travel", chapter=2)
    with pytest.raises(GameError):
        command(engine, state, "travel", chapter=3)


def test_quest_accept_battle_return_and_guardian_requires_all_steps(game):
    engine, state = game
    state["party"] = [engine._monster("wargreymon", 99, abi=150, cam=100)]
    profile = enter(engine, state)
    npcs = first_field(engine)
    quest, trainer, boss = (npcs[role] for role in ("quest", "trainer", "warden"))
    meet(engine, state, trainer)
    assert "challenge" not in choices(state)
    meet(engine, state, quest)
    assert "accept_quest" in choices(state) and "complete_quest" not in choices(state)
    stale = profile["view"]["dialogue"]["token"]
    choose(engine, state, "accept_quest")
    assert quest["id"] in profile["quest_accepted"] and quest["id"] not in profile["completed"]
    with pytest.raises(GameError):
        command(engine, state, "dialogue", token=stale, choice="accept_quest")
    meet(engine, state, quest)
    assert "complete_quest" not in choices(state)
    meet(engine, state, trainer)
    choose(engine, state, "challenge")
    assert state["battle"]["story_campaign_id"] == DS and not state["battle"]["story_training"]
    story.settle(engine, state, True)
    engine._refresh(state)
    meet(engine, state, boss)
    assert "challenge" not in choices(state)
    meet(engine, state, quest)
    assert "complete_quest" in choices(state)
    stale = profile["view"]["dialogue"]["token"]
    choose(engine, state, "complete_quest")
    assert quest["id"] in profile["completed"]
    wallet = state["credits"]
    with pytest.raises(GameError):
        command(engine, state, "dialogue", token=stale, choice="complete_quest")
    assert state["credits"] == wallet
    meet(engine, state, quest)
    assert "complete_quest" not in choices(state) and "accept_quest" not in choices(state)
    meet(engine, state, boss)
    choose(engine, state, "challenge")
    assert all(monster["paradox"] for monster in state["battle"]["enemies"])
    story.settle(engine, state, True)
    engine._refresh(state)
    assert profile["badges"] == [boss["badge"]]
    command(engine, state, "travel", chapter=2)


def test_final_requires_all_unique_crests_and_reward_is_permanent_once(game):
    engine, state = game
    state["party"] = [engine._monster(ident, 99, abi=150, cam=100)
                      for ident in ("omnimon", "wargreymon", "metalgarurumon")]
    profile = enter(engine, state)
    data = story.content(engine, DS)
    final = data["npcs"][data["champion_id"]]
    profile["completed"].extend(final["requires"])
    required = [row["badge"]["id"] for row in data["regions"] if row.get("badge")]
    profile["badges"] = required[:-1] + [required[0]]
    state.update(map_id=final["map_id"], x=final["x"], y=final["y"])
    with pytest.raises(story.StoryError, match="17 different"):
        story._begin(engine, state, final)
    profile["badges"] = required
    story._begin(engine, state, final)
    assert len(state["battle"]["enemies"]) == 3
    assert all(monster["level"] == 100 and monster["paradox"] for monster in state["battle"]["enemies"])
    story.settle(engine, state, False)
    assert not profile["champion"]["first_victory"]
    assert not state.get("permanent_rewards", {}).get("paradox_scan_mastery")
    story._begin(engine, state, final)
    story.settle(engine, state, True)
    assert state["permanent_rewards"]["paradox_scan_mastery"] is True
    assert profile["champion"]["status"] == "completed"
    wallet, inventory = state["credits"], copy.deepcopy(state["inventory"])
    with pytest.raises(story.StoryError):
        story.settle(engine, state, True)
    story._begin(engine, state, final)
    story.settle(engine, state, True)
    assert state["credits"] == wallet and state["inventory"] == inventory
    assert profile["recent"][0]["replay"] and not profile["recent"][0]["scan_mastery_unlocked"]
    command(engine, state, "return")
    enter(engine, state, DAWN)
    assert state["permanent_rewards"]["paradox_scan_mastery"] is True
    assert state["story"]["view"]["scan_bonus"] == 20


def test_battle_binding_cannot_be_transferred_between_campaign_profiles(game):
    engine, state = game
    enter(engine, state)
    command(engine, state, "travel", chapter=1)
    command(engine, state, "train")
    saved = json.loads(json.dumps(state))
    engine._refresh(saved)
    assert saved["battle"] == state["battle"]
    for field, value in (("story_campaign_id", DAWN), ("story_profile_id", "another-character")):
        changed = copy.deepcopy(saved)
        changed["battle"][field] = value
        before = (changed["credits"], copy.deepcopy(changed["story"]["stats"]))
        with pytest.raises(story.StoryError):
            story.settle(engine, changed, True)
        assert (changed["credits"], changed["story"]["stats"]) == before
