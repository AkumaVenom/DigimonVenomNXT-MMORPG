"""Independent Xros habitats, all-world collection, and save-safe shared play."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from venom.common.game import GameEngine, GameError, STAGE_RANK, variety_of
from venom.version import VERSION


ROOT = Path(__file__).resolve().parents[1]
BASELINE_HABITATS = {
    "dawn": (254, "d0a16339bfb3be241617060d420d71bac5e432a83f75e8bf83f469f127247f29",
             "f7c7e923518ed9c4e3eaf7c6b6ea705bc26f763b224e3f801946daa985339844"),
    "world_ds": (150, "2ba65987dfb76d17597b9f43e6d4ceae7e32648a769e4e21dfd050ba3d2b0106",
                 "b552c060fcd86a0148a9f783025a77746cdf7ad931fea166e2c0346fd4206ae8"),
}
STAGE_BANDS = {0: (1, 10), 1: (1, 14), 2: (1, 24), 3: (12, 40),
               4: (28, 59), 5: (45, 99), 6: (75, 99)}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.fixture(scope="module")
def expansion_root(tmp_path_factory):
    """Exercise every level boundary independently of the authored map layout."""
    root = tmp_path_factory.mktemp("xros_gameplay")
    catalog = json.loads((ROOT / "data/catalog.json").read_text())
    catalog["maps"] = [m for m in catalog["maps"] if m.get("region_id") != "xros_wars"]
    catalog["maps"].extend({
        "id": f"xros_test_{level:03d}", "region_id": "xros_wars", "name": f"Xros Test {level}",
        "level": level, "level_min": max(1, level - 2), "level_max": min(99, level + 2),
        "width": 512, "height": 512, "spawn": [128, 256],
    } for level in range(1, 100))
    (root / "catalog.json").write_text(json.dumps(catalog))
    (root / "mechanics.json").write_text((ROOT / "data/mechanics.json").read_text())
    return root


@pytest.fixture
def game(expansion_root):
    engine = GameEngine(expansion_root, seed=130)
    state = engine.new_player("XrosTester", next(iter(engine.tamers)), "agumon")
    return engine, state


class EventRng:
    """One forced rarity roll; enemy count, habitat selection and levels stay explicit."""
    def __init__(self, roll, count=1):
        self.roll, self.count, self.rolls = roll, count, 0

    def random(self):
        self.rolls += 1
        return self.roll

    def choices(self, *args, **kwargs):
        return [self.count]

    def choice(self, values):
        return values[0]

    def randint(self, low, high):
        return low

    def randrange(self, stop):
        return stop - 1

    def uniform(self, low, high):
        return (low + high) / 2


def strongest_party(engine, state):
    state["party"] = [engine._monster("omnimon", 99, abi=200, cam=100)]
    state["party"][0]["spd"] = 1000000


def assert_region_habitats(engine, areas):
    assert areas
    collected = {"normal": set(), "paradox": set(), "shiny": set(), "firewall": set()}
    for area in areas:
        normal, paradox = engine._pools[area["id"]]
        shiny = engine._shiny_pools[area["id"]]
        firewall = engine._firewall_pools[area["id"]]
        assert len(normal) >= 12, area["id"]
        assert len(normal) == len(set(normal)), area["id"]
        assert normal == area["encounters"]
        assert paradox == area["paradox_encounters"]
        assert shiny == area["shiny_encounters"]
        assert firewall == area["firewall_encounters"]
        assert set(paradox) == {engine._variants["paradox"][sid]["id"] for sid in normal}
        assert set(shiny) == {engine._variants["shiny"][sid]["id"] for sid in normal}
        for variety, pool in (("normal", normal), ("paradox", paradox), ("shiny", shiny), ("firewall", firewall)):
            collected[variety].update(pool)
            for sid in pool:
                species = engine.species[sid]
                assert variety_of(species) == variety
                low, high = STAGE_BANDS[STAGE_RANK[species["stage"]]]
                assert low <= area["level"] <= high, (area["id"], sid, area["level"])
        ranks = {STAGE_RANK[engine.species[sid]["stage"]] for sid in normal}
        if area["level"] <= 10:
            assert ranks == {0, 1, 2}, area["id"]
        if area["level"] >= 75:
            assert ranks == {5, 6}, area["id"]
    for variety, found in collected.items():
        expected = {sid for sid, species in engine.species.items() if variety_of(species) == variety}
        assert len(expected) == 502
        assert found == expected, (variety, sorted(expected - found))


def test_xros_preserves_all_v120_habitats_and_original_home(game):
    engine, state = game
    for region, (count, habitat_hash, shiny_hash) in BASELINE_HABITATS.items():
        maps = {key: pool for key, pool in engine._pools.items()
                if (engine.maps[key].get("region_id") or "dawn") == region}
        assert len(maps) == count
        assert fingerprint(maps) == habitat_hash
        assert fingerprint({key: engine._shiny_pools[key] for key in maps}) == shiny_hash
    assert state["map_id"] == "map_001_a" and state["in_farm"]
    assert state["catalog_version"] == VERSION
    engine.maps["000_xros"] = {**engine.maps["xros_test_001"], "id": "000_xros"}
    assert engine.new_player("Second", next(iter(engine.tamers)), "agumon")["map_id"] == "map_001_a"


def test_xros_every_level_has_appropriate_stages_and_every_variety_has_a_home(game):
    engine, _ = game
    areas = [m for m in engine.maps.values() if m.get("region_id") == "xros_wars"]
    assert_region_habitats(engine, areas)
    # The endgame is a varied route, rather than one repeated fallback roster.
    endgame = [tuple(engine._pools[m["id"]][0]) for m in areas if m["level"] >= 75]
    assert len(set(endgame)) == len(endgame)


def test_independent_regions_do_not_consume_rng_or_depend_on_map_enumeration(game):
    engine, _ = game
    before = copy.deepcopy(engine._pools), copy.deepcopy(engine._shiny_pools)
    rng_before = engine.rng.getstate()
    engine.maps = dict(reversed(list(engine.maps.items())))
    engine._prepare_encounter_pools()
    assert engine.rng.getstate() == rng_before
    assert (engine._pools, engine._shiny_pools) == before
    engine.maps["future_region_001"] = {**engine.maps["xros_test_001"],
                                          "id": "future_region_001", "region_id": "future_region"}
    engine._prepare_encounter_pools()
    assert {key: engine._pools[key] for key in before[0]} == before[0]
    assert {key: engine._shiny_pools[key] for key in before[1]} == before[1]
    assert engine.new_player("Third", next(iter(engine.tamers)), "agumon")["map_id"] == "map_001_a"


@pytest.mark.parametrize("level", [1, 35, 99])
@pytest.mark.parametrize("count", [1, 2, 3])
@pytest.mark.parametrize("roll,expected", [(0, "paradox"), (.024999999, "paradox"),
                                           (.025, "shiny"), (.034999999, "shiny"),
                                           (.035, "firewall"), (.042, "normal"), (.99999, "normal")])
def test_xros_wild_battles_use_exact_existing_rarity_intervals(game, level, count, roll, expected):
    engine, state = game
    strongest_party(engine, state)
    engine.rng = EventRng(roll, count)
    engine.handle(state, "travel", {"map_id": f"xros_test_{level:03d}"})
    engine.handle(state, "encounter", {"shiny": True, "paradox": True, "species_id": "forged", "level": 999})
    enemies = state["battle"]["enemies"]
    assert len(enemies) == count
    assert engine.rng.rolls == 1
    assert sum(enemy["shiny"] for enemy in enemies) == int(expected == "shiny")
    assert sum(enemy["paradox"] for enemy in enemies) == int(expected == "paradox")
    assert sum(enemy["firewall"] for enemy in enemies) == int(expected == "firewall")
    area = engine.maps[state["map_id"]]
    low, high = engine.wild_level_range(area)
    for enemy in enemies:
        assert low <= enemy["level"] <= high
        key = "encounters" if enemy["variety"] == "normal" else f"{enemy['variety']}_encounters"
        assert enemy["species_id"] in area[key]


def test_twenty_xros_shiny_wins_earn_separate_scan_and_a_persistent_partner(game, expansion_root):
    engine, state = game
    strongest_party(engine, state)
    engine.rng = EventRng(.03)
    engine.handle(state, "travel", {"map_id": "xros_test_001"})
    normal_id = engine._pools[state["map_id"]][0][0]
    shiny_id = engine._shiny_pools[state["map_id"]][0]
    paradox_id = engine._variants["paradox"][normal_id]["id"]
    state["scan"].update({normal_id: 60, paradox_id: 35})
    state["permanent_rewards"] = {"paradox_scan_mastery": True}
    for victory in range(20):
        engine.handle(state, "encounter", {})
        assert state["battle"]["enemies"][0]["species_id"] == shiny_id
        for _ in range(20):
            if not state["battle"]:
                break
            engine.handle(state, "battle", {"action": "attack", "target": 0})
        assert state["battle"] is None
        assert state["scan"][shiny_id] == (victory + 1) * 5
    assert state["scan"][normal_id] == 60 and state["scan"][paradox_id] == 35
    assert state["wins"] == 20
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "materialize", {"species_id": shiny_id})
    assert state["scan"][shiny_id] == 0
    partner = next(mon for mon in state["party"] if mon["species_id"] == shiny_id)
    assert partner["shiny"] and partner["variety"] == "shiny"
    engine.handle(state, "digilab", {"action": "return"})
    saved = json.loads(json.dumps(state))
    GameEngine(expansion_root)._refresh(saved)
    assert saved["party"] == state["party"]
    assert saved["scan"] == state["scan"]
    assert saved["map_id"] == "xros_test_001"


def test_shared_travel_hubs_and_saved_progress_do_not_require_story_unlocks(game, expansion_root):
    engine, state = game
    owned = copy.deepcopy(state["party"])
    state["scan"] = {"agumon": 85, "agumon_shiny": 15, "agumon_paradox": 20}
    initial_scan = dict(state["scan"])
    credits, inventory = state["credits"], copy.deepcopy(state["inventory"])
    assert not state.get("story")
    ds_map = min((m for m in engine.maps.values() if m.get("region_id") == "world_ds"),
                 key=lambda m: (m["level"], m["id"]))["id"]
    for map_id in ("xros_test_001", "xros_test_099", "map_001_a", ds_map, "xros_test_035"):
        engine.handle(state, "travel", {"map_id": map_id, "x": -1000, "y": 999999})
        assert [state["x"], state["y"]] == engine.maps[map_id]["spawn"]
        for hub in ("digilab", "digifarm"):
            engine.handle(state, hub, {"action": "enter"})
            engine.handle(state, hub, {"action": "return"})
            assert state["map_id"] == map_id
    saved = json.loads(json.dumps(state))
    saved["catalog_version"] = "1.2.0"
    GameEngine(expansion_root)._refresh(saved)
    assert saved["map_id"] == "xros_test_035" and saved["catalog_version"] == VERSION
    assert saved["party"] == owned
    assert saved["scan"] == initial_scan
    assert (saved["credits"], saved["inventory"]) == (credits, inventory)
    assert not saved.get("story")
    for flag in ("in_story", "in_season"):
        saved[flag] = True
        with pytest.raises(GameError):
            engine.handle(saved, "travel", {"map_id": "xros_test_001"})
        saved[flag] = False


def test_shipped_xros_region_covers_full_roster_and_every_map_supports_shiny_encounters():
    engine = GameEngine(ROOT, seed=130)
    areas = [m for m in engine.maps.values() if m.get("region_id") == "xros_wars"]
    assert_region_habitats(engine, areas)
    assert min(engine.wild_level_range(area)[0] for area in areas) == 1
    assert max(engine.wild_level_range(area)[1] for area in areas) == 99
    state = engine.new_player("EveryMap", next(iter(engine.tamers)), "agumon")
    for area in areas:
        strongest_party(engine, state)
        engine.handle(state, "travel", {"map_id": area["id"]})
        engine.rng = EventRng(.03)
        engine.handle(state, "encounter", {})
        enemies = state["battle"]["enemies"]
        assert len(enemies) == 1 and enemies[0]["shiny"], area["id"]
        assert enemies[0]["species_id"] in area["shiny_encounters"]
        engine.handle(state, "battle", {"action": "flee"})
