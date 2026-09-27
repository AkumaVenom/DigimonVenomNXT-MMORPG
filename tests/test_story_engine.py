"""Campaign boundaries exercised with production content and real battle turns."""
import copy
import json
from pathlib import Path

import pytest

from venom.common.game import GameEngine, GameError
from venom.common import story

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def game():
    engine = GameEngine(ROOT, seed=19)
    return engine, engine.new_player("RelayTester", next(iter(engine.tamers)), "agumon")


def enter(engine, state):
    engine.handle(state, "story", {"action": "enter"})
    return state["story"]


def meet(engine, state, npc):
    region = next(row for row in story.content(engine)["regions"] if npc["map_id"] in row["maps"])
    engine.handle(state, "story", {"action": "travel", "chapter": region["index"], "map_id": npc["map_id"]})
    state.update(x=npc["x"], y=npc["y"])
    engine.handle(state, "story", {"action": "talk", "npc_id": npc["id"]})
    while any(row["id"] == "next" for row in state["story"]["view"]["dialogue"]["choices"]):
        engine.handle(state, "story", {"action": "dialogue", "token": state["story"]["view"]["dialogue"]["token"], "choice": "next"})


def start(engine, state, npc):
    meet(engine, state, npc)
    engine.handle(state, "story", {"action": "challenge", "npc_id": npc["id"], "token": state["story"]["view"]["dialogue"]["token"]})


def fight(engine, state):
    for _ in range(1000):
        battle = state.get("battle")
        if not battle:
            return
        target = next(index for index, monster in enumerate(battle["enemies"]) if monster["hp"] > 0)
        actor = state["party"][battle["actor"]]
        action = "skill" if actor["sp"] >= actor["skills"][0]["sp"] else "attack"
        engine.handle(state, "battle", {"action": action, "target": target, "skill_index": 0,
                                        "battle_id": battle["id"], "expected_turn": battle["turn"]})
    raise AssertionError("The interactive battle did not finish")


def strong_team(engine, state):
    state["party"] = [engine._monster(ident, 99, abi=150, cam=100) for ident in ("omnimon", "wargreymon", "metalgarurumon")]


def test_entry_shared_partners_wallet_and_nested_world_return(game):
    engine, state = game
    location = {key: copy.deepcopy(state.get(key)) for key in story.LOCATION_FIELDS}
    party, inventory = copy.deepcopy(state["party"]), copy.deepcopy(state["inventory"])
    enter(engine, state)
    assert state["party"] == party and state["inventory"] == inventory and state["credits"] == 650
    assert not any(key in state["story_return_state"] for key in ("party", "storage", "credits", "inventory"))
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "shop", {"item": "hp_s", "quantity": 1})
    state["party"][0]["cam"] += 1
    engine.handle(state, "story", {"action": "return"})
    assert {key: state.get(key) for key in story.LOCATION_FIELDS} == location
    assert state["credits"] == 590 and state["inventory"]["hp_s"] == inventory["hp_s"] + 1
    assert state["party"][0]["cam"] == party[0]["cam"] + 1
    old = copy.deepcopy(state["story"])
    enter(engine, state)
    assert state["story"]["id"] == old["id"] and state["story"]["badges"] == old["badges"]


def test_two_private_campaigns_never_share_progress(game):
    engine, state = game
    first = enter(engine, state)
    other = engine.new_player("AnotherTamer", next(iter(engine.tamers)), "palmon")
    second = enter(engine, other)
    before = copy.deepcopy(other)
    state["story"]["badges"].append("lumen")
    assert other == before and first["id"] != second["id"]


def test_progression_guards_proximity_tokens_and_chapter_gates(game):
    engine, state = game
    enter(engine, state)
    data = story.content(engine)
    for index in (True, -1, 1, 8, 9, "1"):
        with pytest.raises(GameError):
            engine.handle(state, "story", {"action": "travel", "chapter": index})
    with pytest.raises(GameError):
        engine.handle(state, "story", {"action": "travel", "chapter": 0, "map_id": "map_051_a"})
    with pytest.raises(GameError):
        engine.handle(state, "story", {"action": "talk", "npc_id": "lumen_trial_1"})
    boss = data["npcs"]["lumen_warden"]
    meet(engine, state, boss)
    assert not any(row["id"] == "challenge" for row in state["story"]["view"]["dialogue"]["choices"])
    with pytest.raises(GameError):
        engine.handle(state, "story", {"action": "challenge", "npc_id": boss["id"], "token": state["story"]["view"]["dialogue"]["token"]})
    mentor = data["npcs"]["lumen_mentor"]
    engine.handle(state, "story", {"action": "travel", "chapter": 0})
    state.update(x=mentor["x"], y=mentor["y"])
    engine.handle(state, "story", {"action": "talk", "npc_id": mentor["id"]})
    stale = state["story"]["view"]["dialogue"]["token"]
    engine.handle(state, "story", {"action": "dialogue", "token": stale, "choice": "next"})
    with pytest.raises(GameError):
        engine.handle(state, "story", {"action": "dialogue", "token": stale, "choice": "next"})


def test_native_training_input_save_and_flee(game):
    engine, state = game
    enter(engine, state)
    engine.handle(state, "story", {"action": "train"})
    battle = state["battle"]
    assert battle["kind"] == "story" and battle["story_training"]
    snapshot = json.loads(json.dumps(state))
    engine._refresh(snapshot)
    assert snapshot["battle"] == state["battle"]
    assert snapshot["story"]["active_battle"] == state["story"]["active_battle"]
    with pytest.raises(GameError):
        engine.handle(state, "battle", {"action": "attack"})
    with pytest.raises(GameError):
        engine.handle(state, "story", {"action": "return"})
    engine.handle(state, "battle", {"action": "flee", "battle_id": battle["id"], "expected_turn": battle["turn"]})
    assert state["battle"] is None and state["story"]["active_battle"] is None
    assert state["story"]["stats"]["battles"] == 0


def test_npc_battle_manual_no_flee_no_scan_and_once_only_first_reward(game):
    engine, state = game
    strong_team(engine, state)
    enter(engine, state)
    npc = story.content(engine)["npcs"]["lumen_trial_1"]
    start(engine, state, npc)
    assert state["battle"]
    with pytest.raises(GameError):
        engine.handle(state, "battle", {"action": "flee", "battle_id": state["battle"]["id"], "expected_turn": state["battle"]["turn"]})
    fight(engine, state)
    assert npc["id"] in state["story"]["completed"] and state["scan"] == {}
    assert sum(monster["species_id"] == "terriermon" for monster in state["party"]) == 1
    dialogue = state["story"]["view"]["dialogue"]
    assert dialogue["result_only"] and dialogue["result"]["won"]
    assert all(row["id"] in ("next", "leave") for row in dialogue["choices"])
    wallet = state["credits"]
    with pytest.raises(GameError):
        engine.handle(state, "story", {"action": "challenge", "npc_id": npc["id"], "token": dialogue["token"]})
    with pytest.raises(story.StoryError):
        story.settle(engine, state, True)
    assert state["credits"] == wallet
    partner = state["party"][0]
    assert partner["level"] == 99
    actual = engine.stats_for(engine.species[partner["species_id"]], 99, partner["abi"], partner["farm_bonuses"])
    assert partner["max_hp"] == actual["hp"] and partner["atk"] == actual["atk"]
    start(engine, state, npc)
    fight(engine, state)
    assert state["credits"] - wallet == npc["reward"]["credits"] // 5
    assert sum(monster["species_id"] == "terriermon" for monster in state["party"]) == 1


def test_shared_farm_lab_and_evolution_remain_available(game):
    engine, state = game
    enter(engine, state)
    location = {key: state[key] for key in ("map_id", "x", "y")}
    engine.handle(state, "digifarm", {"action": "enter"})
    assert state["in_story"] and state["in_farm"]
    engine.handle(state, "digifarm", {"action": "return"})
    assert {key: state[key] for key in location} == location
    engine.handle(state, "digilab", {"action": "enter"})
    monster = engine._monster("agumon", 30, abi=30, cam=100)
    state["party"][0] = monster
    engine._refresh(state)
    option = next(row for row in state["evolution_options"][0] if row["eligible"] and not row["devolve"])
    engine.handle(state, "evolve", {"party_index": 0, "to": option["to"]})
    assert state["party"][0]["uid"] == monster["uid"] and state["party"][0]["level"] == 1
    engine.handle(state, "digilab", {"action": "return"})
    assert state["in_story"] and not state["in_lab"]
    for op, payload in (("season", {"action": "enter"}), ("encounter", {}), ("travel", {"map_id": "map_001_a"})):
        with pytest.raises(GameError):
            engine.handle(state, op, payload)


def test_eight_badges_champion_defend_loss_reclaim_without_reset(game):
    engine, state = game
    strong_team(engine, state)
    enter(engine, state)
    data = story.content(engine)
    for region in data["regions"]:
        for ident in (*region["trial_ids"], region["warden_id"]):
            start(engine, state, data["npcs"][ident])
            fight(engine, state)
            assert state["story"]["recent"][0]["won"], ident
        if region["index"] < 8:
            assert len(state["story"]["badges"]) == region["index"] + 1
    champion = state["story"]["champion"]
    assert champion["first_victory"] and champion["status"] == "defending"
    assert champion["reigns"] == 1 and champion["holder"] == state["username"]
    opponent = story._champion_npc(state["story"], data)
    start(engine, state, opponent)
    fight(engine, state)
    assert champion["defenses"] == 1 and champion["streak"] == 1
    opponent = story._champion_npc(state["story"], data)
    for monster in state["party"]:
        monster["hp"] = 1
    start(engine, state, opponent)
    fight(engine, state)
    assert champion["status"] == "reclaim" and champion["holder_id"] == opponent["id"]
    assert champion["reigns"] == 1 and champion["defenses"] == 1
    assert len(state["story"]["badges"]) == 8
    assert story._champion_npc(state["story"], data)["id"] == opponent["id"]
    dialogue = state["story"]["view"]["dialogue"]
    assert dialogue["result_only"]
    engine.handle(state, "story", {"action": "dialogue", "token": dialogue["token"], "choice": "leave"})
    start(engine, state, opponent)
    fight(engine, state)
    assert champion["status"] == "defending" and champion["reigns"] == 2
    assert state["story"]["stats"]["battles"] == 30
    start(engine, state, data["npcs"]["lumen_trial_1"])
    fight(engine, state)
    assert state["story"]["stats"]["battles"] == 31
    assert len(state["story"]["recent"]) == story.HISTORY_LIMIT
    assert state["story"]["recent"][-1]["number"] == 2
    assert all(monster["level"] <= 99 for monster in state["party"])
    assert any(partner["level"] == 100 for npc in data["challengers"] for partner in npc["team"])


def test_corrupt_battle_binding_cannot_pay_out(game):
    engine, state = game
    enter(engine, state)
    engine.handle(state, "story", {"action": "train"})
    state["story"]["active_battle"]["id"] = "another-challenge"
    before = (state["credits"], copy.deepcopy(state["story"]["stats"]))
    with pytest.raises(story.StoryError):
        story.settle(engine, state, True)
    assert (state["credits"], state["story"]["stats"]) == before


def test_reward_caps_and_full_roster_partner_data_preserved(game):
    engine, state = game
    enter(engine, state)
    state["credits"] = story.MAX_CREDITS - 3
    state["inventory"]["hp_s"] = 998
    state["party"] = [engine._monster("agumon", 5) for _ in range(6)]
    state["storage"] = [engine._monster("palmon", 1) for _ in range(100)]
    actual = story._grant_reward(engine, state, {"credits": 50, "items": {"hp_s": 10}, "partner": "terriermon"}, True)
    assert actual == 3 and state["credits"] == story.MAX_CREDITS
    assert state["inventory"]["hp_s"] == 999 and state["scan"]["terriermon"] == 200
    assert len(state["party"]) == 6 and len(state["storage"]) == 100


def test_native_story_gate_proximity_and_badge_requirement(game):
    engine, state = game
    enter(engine, state)
    gate = state["story"]["view"]["exits"][0]
    assert gate["unlocked"]
    with pytest.raises(GameError):
        engine.handle(state, "story", {"action": "exit", "exit_id": gate["id"]})
    state.update(x=gate["x"], y=gate["y"])
    engine.handle(state, "story", {"action": "exit", "exit_id": gate["id"]})
    assert state["map_id"] == gate["to_map"]
    locked = next(row for row in state["story"]["view"]["exits"] if not row["unlocked"])
    state.update(x=locked["x"], y=locked["y"])
    with pytest.raises(GameError):
        engine.handle(state, "story", {"action": "exit", "exit_id": locked["id"]})
    assert state["map_id"] == gate["to_map"]


def test_champion_requires_all_badges_even_if_qualifier_flags_exist(game):
    engine, state = game
    enter(engine, state)
    data = story.content(engine)
    champion = data["npcs"][data["champion_id"]]
    state["story"]["completed"].extend(champion["requires"])
    state["story"]["badges"].extend(region["id"] for region in data["regions"][:7])
    with pytest.raises(story.StoryError, match="eight"):
        story._begin(engine, state, champion)
    assert state["battle"] is None and state["story"]["champion"]["first_victory"] is False


def test_stale_manual_turn_cannot_execute_twice(game):
    engine, state = game
    enter(engine, state)
    engine.handle(state, "story", {"action": "train"})
    battle = state["battle"]
    request = {"action": "guard", "battle_id": battle["id"], "expected_turn": battle["turn"]}
    engine.handle(state, "battle", request)
    after = copy.deepcopy(state["battle"])
    with pytest.raises(GameError):
        engine.handle(state, "battle", request)
    assert state["battle"] == after
