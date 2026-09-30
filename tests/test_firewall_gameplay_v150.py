"""FireWall stays a separately collectible, habitat-safe cosmetic family."""
import copy
import json
from pathlib import Path

import pytest

from venom.common.game import GameEngine, GameError, variety_of
from test_shiny_gameplay_v120 import EventRng, _species


@pytest.fixture
def game(tmp_path):
    bases = [_species("alpha", evolutions=[{"to": "beta", "level": 5},
                                           {"to": "alpha_firewall", "level": 1}]),
             _species("beta", "champion"), _species("gamma")]
    species = copy.deepcopy(bases)
    for variety in ("paradox", "shiny", "firewall"):
        for base in bases:
            species.append({**copy.deepcopy(base), "id": f"{base['id']}_{variety}",
                            "name": f"{base['name']} ({'FireWall' if variety == 'firewall' else variety.title()})",
                            "base_id": base["id"], "variety": variety,
                            **{key: key == variety for key in ("paradox", "shiny", "firewall")}})
    catalog = {"species": species, "tamers": [{"id": "tamer", "name": "Tamer", "frames": {}}],
               "maps": [{"id": ident, "name": ident, "level": level, "region_id": region,
                         "width": 500, "height": 500, "spawn": [100, 100]}
                        for ident, level, region in (("forest", 1, "dawn"), ("mountain", 20, "dawn"),
                                                      ("ds_forest", 1, "world_ds"),
                                                      ("xros_forest", 1, "super_xros"))]}
    (tmp_path / "catalog.json").write_text(json.dumps(catalog))
    (tmp_path / "mechanics.json").write_text(json.dumps({"firewall_encounter_chance": .007,
        "firewall_scan_gain": 5, "shiny_encounter_chance": .01, "paradox_encounter_chance": .025,
        "species_overrides": {"Alpha": {"type": "virus", "attribute": "water"}}}))
    engine = GameEngine(tmp_path, seed=150)
    state = engine.new_player("FireWallTamer", "tamer", "alpha")
    state.update(in_farm=False)
    state["party"][0] = engine._monster("alpha", 99, abi=200, cam=100)
    state["party"][0]["spd"] = 1000000
    return engine, state


def test_firewall_is_separate_from_starters_and_every_evolution_family(game):
    engine, state = game
    assert set(engine.starters) == {"alpha", "gamma"}
    with pytest.raises(GameError, match="regular Rookie"):
        engine.new_player("NoFreeRare", "tamer", "alpha_firewall")
    for variety in ("normal", "paradox", "shiny", "firewall"):
        suffix = "" if variety == "normal" else "_" + variety
        for base in ("alpha", "gamma"):
            routes = engine.species[base + suffix]["evolutions"]
            assert "beta" + suffix in {r["to"] for r in routes}
    for source in engine.species.values():
        for route in source["evolutions"]:
            assert variety_of(source) == variety_of(engine.species[route["to"]])
        for option in engine.evolution_options(engine._monster(source["id"], 99, abi=200, cam=100)):
            assert variety_of(source) == variety_of(engine.species[option["to"]])
    state["in_farm"] = True
    with pytest.raises(GameError, match="not available"):
        engine.handle(state, "evolve", {"party_index": 0, "to": "alpha_firewall"})
    assert engine.species["alpha_firewall"]["type"] == "virus"
    assert engine.species["alpha_firewall"]["attribute"] == "water"
    for level, abi in ((1, 0), (50, 100), (99, 200)):
        assert engine.stats_for(engine.species["alpha_firewall"], level, abi) == engine.stats_for(
            engine.species["alpha"], level, abi)


@pytest.mark.parametrize("count", [1, 2, 3])
@pytest.mark.parametrize("roll,expected", [(0, "paradox"), (.0249999999, "paradox"),
    (.025, "shiny"), (.0349999999, "shiny"), (.035, "firewall"), (.0419999999, "firewall"),
    (.042, "normal"), (.9999999, "normal")])
def test_exact_interval_boundaries_are_per_battle_and_ignore_client_rarity_requests(game, count, roll, expected):
    engine, state = game
    for map_id in engine.maps:
        engine.rng = EventRng(roll, count)
        engine.handle(state, "travel", {"map_id": map_id})
        engine.handle(state, "encounter", {"firewall": True, "firewall_chance": 1,
                                            "species_id": "alpha_firewall", "scan_gain": 200})
        enemies = state["battle"]["enemies"]
        assert len(enemies) == count
        assert engine.rng.rolls == 1
        rare = [e for e in enemies if e["variety"] != "normal"]
        assert len(rare) == int(expected != "normal")
        if rare:
            assert rare[0]["variety"] == expected
            assert rare[0]["species_id"] in engine.maps[map_id][f"{expected}_encounters"]
        engine.handle(state, "battle", {"action": "flee"})


@pytest.mark.parametrize("count", [1, 3])
def test_exact_distribution_preserves_existing_marginal_odds_and_adds_seven_per_thousand(game, count):
    engine, _ = game
    totals = dict.fromkeys(("normal", "paradox", "shiny", "firewall"), 0)
    for sample in range(10000):
        engine.rng = EventRng((sample + .5) / 10000)
        enemies = [engine._monster("alpha") for _ in range(count)]
        engine._roll_wild_variety(enemies, ["alpha_paradox"], ["alpha_shiny"], ["alpha_firewall"])
        totals[next((e["variety"] for e in enemies if e["variety"] != "normal"), "normal")] += 1
    assert totals == {"normal": 9580, "paradox": 250, "shiny": 100, "firewall": 70}
    # Pre-v1.5.0 callers are valid and keep exactly their original roll space.
    engine.rng = EventRng(.04)
    enemies = [engine._monster("alpha")]
    engine._roll_wild_variety(enemies, ["alpha_paradox"], ["alpha_shiny"])
    assert enemies[0]["variety"] == "normal"


def test_twenty_real_victories_unlock_only_firewall_materialization(game):
    engine, state = game
    engine.rng = EventRng(.04)
    engine._pools[state["map_id"]] = (["alpha"], ["alpha_paradox"])
    engine._firewall_pools[state["map_id"]] = ["alpha_firewall"]
    state["permanent_rewards"] = {"shiny_scan_mastery": True, "paradox_scan_mastery": True}
    state["scan"] = {"alpha": 100, "alpha_shiny": 45, "alpha_paradox": 35}
    for victory in range(20):
        engine.handle(state, "encounter", {})
        engine.handle(state, "battle", {"action": "attack", "target": 0})
        assert state["battle"] is None
        assert state["scan"]["alpha_firewall"] == (victory + 1) * 5
        if victory == 18:
            engine.handle(state, "digilab", {"action": "enter"})
            with pytest.raises(GameError, match="at least 100%"):
                engine.handle(state, "materialize", {"species_id": "alpha_firewall"})
            engine.handle(state, "digilab", {"action": "return"})
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "materialize", {"species_id": "alpha_firewall"})
    assert state["scan"] == {"alpha": 100, "alpha_shiny": 45, "alpha_paradox": 35, "alpha_firewall": 0}
    assert state["party"][-1]["firewall"] and not state["party"][-1]["shiny"]
    assert not state["party"][-1]["paradox"]


def test_firewall_farm_food_evolution_devolution_identity_and_saved_damage_are_retained(game):
    engine, state = game
    state["in_farm"] = True
    state["party"] = [engine._monster("alpha") for _ in range(6)]
    state["scan"]["alpha_firewall"] = 200
    engine.handle(state, "materialize", {"species_id": "alpha_firewall"})
    partner = state["storage"][0]
    uid = partner["uid"]
    assert partner["abi"] == 5 and partner["firewall"]
    state["inventory"]["digimeat_atk_5"] = 1
    engine.handle(state, "digifarm", {"action": "feed", "uid": uid, "item": "digimeat_atk_5"})
    engine.handle(state, "party", {"action": "deposit", "index": 5})
    engine.handle(state, "party", {"action": "withdraw", "index": 0})
    state["party"][-1].update(level=50, abi=100, cam=100)
    engine.handle(state, "evolve", {"party_index": 5, "to": "beta_firewall"})
    state["party"][5]["level"] = 5
    engine.handle(state, "evolve", {"party_index": 5, "to": "alpha_firewall"})
    partner = state["party"][5]
    partner["hp"] -= 10
    partner["sp"] -= 5
    assert partner["history"] == ["alpha_firewall", "beta_firewall"]
    assert partner["uid"] == uid and partner["cam"] == 100
    assert partner["farm_bonuses"] == {"atk": 5}
    restored = json.loads(json.dumps(state))
    # Saved cached display flags are repaired from authoritative species IDs.
    for partner in restored["party"] + restored["storage"]:
        partner.update(firewall=False, shiny=True, paradox=True, variety="shiny", base_id="forged")
    engine._refresh(restored)
    assert restored["party"] == state["party"]
    assert restored["storage"] == state["storage"]


def test_all_500_public_maps_and_all_502_firewall_forms_are_actually_encounterable():
    engine = GameEngine(Path(__file__).resolve().parents[1], seed=150)
    state = engine.new_player("EveryHabitat", next(iter(engine.tamers)), "agumon")
    state["party"] = [engine._monster("agumon", 99, abi=200)]
    state["party"][0]["spd"] = 1000000
    assert len(engine.maps) == 500
    assert engine.catalog["rules"]["firewall_encounter_chance"] == .007
    assert engine.catalog["rules"]["firewall_scan_gain"] == 5
    normal_ids = {s["id"] for s in engine.species.values() if variety_of(s) == "normal"}
    firewall_ids = {s["id"] for s in engine.species.values() if variety_of(s) == "firewall"}
    assert len(normal_ids) == len(firewall_ids) == 502
    assert firewall_ids == {sid + "_firewall" for sid in normal_ids}
    habitats, encountered = {}, set()

    def encounter(area, sid=None):
        engine.rng = EventRng(.04, species_id=sid)
        engine.handle(state, "travel", {"map_id": area["id"]})
        engine.handle(state, "encounter", {})
        enemy, = state["battle"]["enemies"]
        assert enemy["firewall"] and not enemy["shiny"] and not enemy["paradox"]
        assert enemy["species_id"] in area["firewall_encounters"]
        low, high = engine.wild_level_range(area)
        assert low <= enemy["level"] <= high
        encountered.add(enemy["species_id"])
        engine.handle(state, "battle", {"action": "flee"})

    for area in engine.maps.values():
        normal, paradox = engine._pools[area["id"]]
        assert area["firewall_encounters"] == [sid + "_firewall" for sid in normal]
        assert all(variety_of(engine.species[sid]) == "normal" for sid in normal)
        assert all(variety_of(engine.species[sid]) == "paradox" for sid in paradox)
        assert area["firewall_encounters"]
        habitats.update({sid: area for sid in area["firewall_encounters"]})
        encounter(area)
    assert set(habitats) == firewall_ids
    for sid in sorted(firewall_ids - encountered):
        encounter(habitats[sid], sid)
    assert encountered == firewall_ids
    for sid in firewall_ids:
        species = engine.species[sid]
        base = engine.species[species["base_id"]]
        assert species["stage"] == base["stage"]
        for level, abi in ((1, 0), (50, 100), (99, 200)):
            assert engine.stats_for(species, level, abi) == engine.stats_for(base, level, abi)
        assert all(variety_of(engine.species[r["to"]]) == "firewall" for r in species["evolutions"])
