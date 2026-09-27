"""World DS uses the shared battle, collection and character progression systems."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from venom.common.game import GameEngine, GameError, STAGE_RANK

ROOT = Path(__file__).resolve().parents[1]
DAWN_POOLS_SHA256 = "d0a16339bfb3be241617060d420d71bac5e432a83f75e8bf83f469f127247f29"


@pytest.fixture(scope="module")
def expansion_root(tmp_path_factory):
    """Production species with a small, independently authored expansion route."""
    root = tmp_path_factory.mktemp("world_ds_engine")
    catalog = json.loads((ROOT / "data/catalog.json").read_text())
    catalog["maps"] = [m for m in catalog["maps"] if m.get("region_id") != "world_ds"]
    for index, level in enumerate((1, 4, 8, 14, 18, 22, 30, 36, 45, 54, 62, 74, 80, 90, 97)):
        for section in (0, 1):
            ident = f"world_ds_{index * 2 + section:03d}"
            catalog["maps"].append({"id": ident, "region_id": "world_ds", "level": level,
                                    "level_min": max(1, level - 2), "level_max": min(99, level + 2),
                                    "name": f"DS Test Route {index + 1}/{section + 1}",
                                    "width": 1536, "height": 768, "spawn": [160, 240]})
    (root / "catalog.json").write_text(json.dumps(catalog))
    (root / "mechanics.json").write_text((ROOT / "data/mechanics.json").read_text())
    return root


@pytest.fixture
def game(expansion_root):
    engine = GameEngine(expansion_root, seed=23)
    state = engine.new_player("ExpansionTester", next(iter(engine.tamers)), "agumon")
    return engine, state


def battle_to_completion(engine, state):
    for _ in range(1000):
        battle = state.get("battle")
        if not battle:
            return
        target = next(i for i, enemy in enumerate(battle["enemies"]) if enemy["hp"] > 0)
        actor = state["party"][battle["actor"]]
        engine.handle(state, "battle", {"action": "skill" if actor["sp"] >= actor["skills"][0]["sp"] else "attack",
                                        "target": target, "skill_index": 0})
    raise AssertionError("Wild battle did not reach a result through normal player inputs")


def test_expansion_preserves_exact_dawn_habitats_and_original_home(game):
    engine, state = game
    old = {ident: pool for ident, pool in engine._pools.items()
           if engine.maps[ident].get("region_id") != "world_ds"}
    encoded = json.dumps(old, sort_keys=True, separators=(",", ":")).encode()
    assert len(old) == 254
    assert hashlib.sha256(encoded).hexdigest() == DAWN_POOLS_SHA256
    assert state["map_id"] == "map_001_a" and state["in_farm"]
    # Even a future expansion map sorting before Dawn must not change home.
    engine.maps["000_expansion"] = {**engine.maps["world_ds_000"], "id": "000_expansion"}
    assert engine.new_player("SecondTamer", next(iter(engine.tamers)), "agumon")["map_id"] == "map_001_a"


def test_ds_pools_are_complete_stage_appropriate_and_varied_at_endgame(game, expansion_root):
    engine, _ = game
    areas = [m for m in engine.maps.values() if m.get("region_id") == "world_ds"]
    available = {sid for m in areas for group in engine._pools[m["id"]] for sid in group}
    assert available == set(engine.species)
    for area in areas:
        normal, rare = engine._pools[area["id"]]
        assert len(normal) >= 12 and rare
        assert not any(engine.species[sid].get("paradox") for sid in normal)
        assert all(engine.species[sid].get("paradox") for sid in rare)
        ranks = {STAGE_RANK[engine.species[sid]["stage"]] for sid in normal}
        if area["level"] < 12:
            assert max(ranks) <= 2
        if area["level"] >= 80:
            assert ranks == {5, 6}
    endgame = [tuple(engine._pools[m["id"]][0]) for m in areas if m["level"] >= 80]
    assert len(set(endgame)) == len(endgame)
    # Map enumeration and gameplay RNG seeds cannot reshuffle habitats.
    reordered = GameEngine(expansion_root, seed=999)
    reordered.maps = dict(reversed(list(reordered.maps.items())))
    reordered._pools = {}
    reordered._prepare_encounter_pools()
    assert reordered._pools == engine._pools


def test_authored_ranges_include_level_one_and_level_99_and_ignore_client_overrides(game):
    engine, state = game
    state["party"] = [engine._monster("omnimon", 99, abi=200, cam=100)]
    found = {"low": set(), "high": set()}
    for ident, label in (("world_ds_000", "low"), ("world_ds_029", "high")):
        engine.handle(state, "travel", {"map_id": ident, "x": -1000, "y": 999999})
        assert [state["x"], state["y"]] == engine.maps[ident]["spawn"]
        low, high = engine.wild_level_range(engine.maps[ident])
        for _ in range(24):
            engine.handle(state, "encounter", {"level": 9999, "species_id": "missing"})
            assert state["battle"] and not state["battle"].get("kind")
            levels = {enemy["level"] for enemy in state["battle"]["enemies"]}
            assert all(low <= level <= high for level in levels)
            found[label].update(levels)
            engine.handle(state, "battle", {"action": "flee"})
    assert 1 in found["low"] and 99 in found["high"]


def test_ds_wild_combat_rewards_scan_and_materialization_share_existing_state(game):
    engine, state = game
    existing_uid = state["party"][0]["uid"]
    # A single-species test habitat makes five ordinary scan victories repeatable.
    engine._pools["world_ds_000"] = (["koromon"], [])
    engine.handle(state, "travel", {"map_id": "world_ds_000"})
    state["party"][0] = {**engine._monster("agumon", 30), "uid": existing_uid}
    credits, wins = state["credits"], state["wins"]
    meat = state["inventory"]["digimeat_cam"]
    experience = state["party"][0]["xp"]
    for _ in range(12):
        engine.handle(state, "encounter", {})
        battle_to_completion(engine, state)
        if state["scan"].get("koromon", 0) >= 100 and state["inventory"]["digimeat_cam"] > meat:
            break
    assert state["scan"]["koromon"] >= 100
    assert state["credits"] > credits and state["wins"] > wins
    assert state["party"][0]["xp"] > experience or state["party"][0]["level"] > 30
    assert state["inventory"]["digimeat_cam"] > meat
    assert state["party"][0]["uid"] == existing_uid
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "materialize", {"species_id": "koromon"})
    assert state["party"][-1]["species_id"] == "koromon"
    assert state["party"][0]["uid"] == existing_uid
    engine.handle(state, "digilab", {"action": "return"})
    assert state["map_id"] == "world_ds_000"
    engine.handle(state, "travel", {"map_id": "map_001_a"})
    assert state["party"][-1]["species_id"] == "koromon" and state["credits"] > credits


def test_world_ds_travel_rejects_forged_maps_and_preserves_activity_guards(game):
    engine, state = game
    for ident in (None, [], {}, True, "world_ds_missing", "../world_ds_000"):
        with pytest.raises(GameError, match="Unknown world area"):
            engine.handle(state, "travel", {"map_id": ident})
    engine.handle(state, "travel", {"map_id": "world_ds_000"})
    engine.handle(state, "encounter", {})
    with pytest.raises(GameError, match="current battle"):
        engine.handle(state, "travel", {"map_id": "map_001_a"})
    engine.handle(state, "battle", {"action": "flee"})
    engine.handle(state, "digilab", {"action": "enter"})
    with pytest.raises(GameError, match="Return to the world"):
        engine.handle(state, "travel", {"map_id": "world_ds_001"})
    engine.handle(state, "digilab", {"action": "return"})
    for flag in ("in_story", "in_season"):
        state[flag] = True
        with pytest.raises(GameError):
            engine.handle(state, "travel", {"map_id": "world_ds_001"})
        state[flag] = False


def test_saved_ds_location_and_owned_roster_survive_reload_and_hub_roundtrips(game, expansion_root):
    engine, state = game
    engine.handle(state, "travel", {"map_id": "world_ds_013"})
    state.update(x=345.5, y=211.25)
    before = copy.deepcopy(state)
    saved = json.loads(json.dumps(state))
    reloaded = GameEngine(expansion_root, seed=4)
    reloaded._refresh(saved)
    assert (saved["map_id"], saved["x"], saved["y"]) == (before["map_id"], before["x"], before["y"])
    assert saved["party"] == before["party"]
    for op in ("digifarm", "digilab"):
        reloaded.handle(saved, op, {"action": "enter"})
        reloaded.handle(saved, op, {"action": "return"})
        assert (saved["map_id"], saved["x"], saved["y"]) == (before["map_id"], before["x"], before["y"])
    assert saved["credits"] == before["credits"] and saved["inventory"] == before["inventory"]
