"""Played Super Xros Wars release acceptance with production assets and rules.

Existing habitats are frozen against the delivered v1.2.0 baseline. New-region
combat, scans and recruits below are earned through ordinary engine commands.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from venom.common.game import GameEngine
from venom.server.navigation import Navigation
from test_world_ds_acceptance import fight

ROOT = Path(__file__).resolve().parents[1]
LEGACY = {
    "dawn": (254, "d0a16339bfb3be241617060d420d71bac5e432a83f75e8bf83f469f127247f29",
             "06f30b24109c9f0f7bf8f8912a8a644d5a4cba84565903d1dd8fd649820030e8"),
    "world_ds": (150, "2ba65987dfb76d17597b9f43e6d4ceae7e32648a769e4e21dfd050ba3d2b0106",
                 "583221d38fd8fe503363b92ad0334e869504a44e3b2b387178d08eed7658684b"),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def xros_maps(engine):
    maps = sorted((area for area in engine.maps.values() if area.get("region_id") == "xros_wars"),
                  key=lambda area: (area["level"], area["id"]))
    assert len(maps) == 96, "The shipped catalog must contain all 96 Super Xros Wars maps"
    return maps


def test_v120_dawn_and_world_ds_maps_and_habitats_are_preserved_exactly():
    engine = GameEngine(ROOT, seed=431)
    catalog = json.loads((ROOT / "data/catalog.json").read_text())
    for region, (count, pool_digest, map_digest) in LEGACY.items():
        pools = {mid: pool for mid, pool in engine._pools.items()
                 if engine.maps[mid].get("region_id", "dawn") == region}
        maps = [area for area in catalog["maps"] if area.get("region_id", "dawn") == region]
        assert len(maps) == len(pools) == count
        assert digest(pools) == pool_digest, f"{region}: an existing species habitat changed"
        # v1.2.0 computed Shiny habitats at engine load. v1.3.0 also publishes
        # the same derived field in the catalog so clients can inspect it.
        for area in maps:
            assert area["shiny_encounters"] == engine._shiny_pools[area["id"]]
        original_fields = [{key: value for key, value in area.items() if key not in ("shiny_encounters", "firewall_encounters")}
                           for area in maps]
        assert digest(original_fields) == map_digest, f"{region}: existing map metadata or assets changed"
    assert len(engine.tamers) == 64
    assert len(engine.species) == 2008
    assert sum(s["variety"] != "firewall" for s in engine.species.values()) == 1506
    assert len(engine.maps) == 500
    assert len(xros_maps(engine)) == 96


def test_every_xros_map_enters_real_level_bounded_wild_battle_and_returns_from_hubs():
    engine = GameEngine(ROOT, seed=3901)
    state = engine.new_player("XrosFieldSurvey", next(iter(engine.tamers)), "agumon")
    state["party"] = [engine._monster("omnimon", level=99, abi=80, cam=100) for _ in range(3)]
    navigation = Navigation(ROOT, engine.maps)
    for area in xros_maps(engine):
        engine.handle(state, "travel", {"map_id": area["id"]})
        assert navigation.walkable(area["id"], state["x"], state["y"]), area["id"]
        engine.handle(state, "encounter", {})
        battle = state["battle"]
        assert battle and battle.get("kind") not in ("story", "season"), area["id"]
        assert 1 <= len(battle["enemies"]) <= 3
        available = set().union(*map(set, engine._pools[area["id"]])) | set(engine._shiny_pools[area["id"]]) | set(engine._firewall_pools[area["id"]])
        for enemy in battle["enemies"]:
            assert enemy["species_id"] in available
            assert area["level_min"] <= enemy["level"] <= area["level_max"]
        engine.handle(state, "battle", {"action": "flee"})
        engine.handle(state, "digilab", {"action": "enter"})
        engine.handle(state, "digilab", {"action": "return"})
        assert state["map_id"] == area["id"]


def test_fresh_rookie_earns_first_xros_recruit_without_replacing_owned_partner():
    engine = GameEngine(ROOT, seed=7709)
    state = engine.new_player("XrosRookie", next(iter(engine.tamers)), "agumon")
    original_uid = state["party"][0]["uid"]
    area = xros_maps(engine)[0]
    assert area["level_min"] == 1
    engine.handle(state, "travel", {"map_id": area["id"]})
    controls = 0
    for _ in range(150):
        engine.handle(state, "encounter", {})
        controls += fight(engine, state)
        engine.handle(state, "digilab", {"action": "enter"})
        capturable = next((sid for sid, total in state["scan"].items() if total >= 100), None)
        if capturable:
            engine.handle(state, "materialize", {"species_id": capturable})
            assert state["scan"][capturable] == 0
            assert state["party"][1]["species_id"] == capturable
            assert state["party"][1]["level"] == 1
            break
        engine.handle(state, "digilab", {"action": "return"})
    else:
        pytest.fail("A new tamer could not earn a Super Xros Wars recruit within 150 ordinary encounters")
    assert controls > 0 and state["wins"] >= 5
    assert state["party"][0]["uid"] == original_uid
    assert state["party"][0]["level"] > 1
    assert state["credits"] > 650
    engine.handle(state, "digilab", {"action": "return"})
    assert state["map_id"] == area["id"]


@pytest.mark.parametrize("variety,roll,gain,defeats", [
    ("normal", .5, 20, 5), ("paradox", .01, 5, 20), ("shiny", .03, 5, 20),
])
def test_each_variety_is_caught_from_real_xros_combat_with_its_own_scan_family(variety, roll, gain, defeats):
    engine = GameEngine(ROOT, seed=209)
    state = engine.new_player("XrosCollector", next(iter(engine.tamers)), "agumon")
    area = xros_maps(engine)[0]
    base = engine._pools[area["id"]][0][0]
    species_id = base if variety == "normal" else f"{base}_{variety}"
    owned = engine._monster("omnimon", 99, abi=100, cam=100)
    state["party"] = [owned]
    engine.handle(state, "travel", {"map_id": area["id"]})
    original_choice = engine.rng.choice

    def choose(values):
        return species_id if species_id in values else original_choice(values)

    for win in range(defeats):
        # Select only valid RNG outcomes. The habitat, levels, opponents,
        # combat turns, scan settlement and materialization stay authoritative.
        with patch.object(engine.rng, "random", return_value=roll), \
                patch.object(engine.rng, "choices", return_value=[1]), \
                patch.object(engine.rng, "choice", side_effect=choose):
            engine.handle(state, "encounter", {})
        assert [enemy["species_id"] for enemy in state["battle"]["enemies"]] == [species_id]
        fight(engine, state)
        assert state["scan"] == {species_id: (win + 1) * gain}
    assert state["wins"] == defeats and state["losses"] == 0
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "materialize", {"species_id": species_id})
    assert state["scan"] == {species_id: 0}
    assert state["party"][0]["uid"] == owned["uid"]
    assert state["party"][-1]["species_id"] == species_id
    assert state["party"][-1]["level"] == 1
    engine.handle(state, "digilab", {"action": "return"})
    assert state["map_id"] == area["id"]


def test_xros_location_owned_progress_and_private_modes_roundtrip_across_all_regions():
    engine = GameEngine(ROOT, seed=628)
    state = engine.new_player("XrosReturn", next(iter(engine.tamers)), "agumon")
    area = xros_maps(engine)[len(xros_maps(engine)) // 2]
    engine.handle(state, "travel", {"map_id": area["id"]})
    navigation = Navigation(ROOT, engine.maps)
    state["x"], state["y"] = navigation.spawn(area["id"], 7)
    location = {key: state[key] for key in ("map_id", "x", "y")}
    possessions = copy.deepcopy({key: state[key] for key in ("party", "storage", "inventory", "credits", "scan")})
    for mode in ("digilab", "digifarm", "story", "season"):
        engine.handle(state, mode, {"action": "enter"})
        engine.handle(state, mode, {"action": "return"})
        assert {key: state[key] for key in location} == location, mode
        assert {key: state[key] for key in possessions} == possessions, mode
    progress = copy.deepcopy({key: state[key] for key in ("story", "season")})
    for region in ("dawn", "world_ds", "xros_wars"):
        destination = next(m for m in engine.maps.values() if m.get("region_id", "dawn") == region)
        engine.handle(state, "travel", {"map_id": destination["id"]})
        assert state["map_id"] == destination["id"]
        assert {key: state[key] for key in progress} == progress
    restored = json.loads(json.dumps(state))
    GameEngine(ROOT, seed=1023)._refresh(restored)
    assert restored == state
