"""Rarity is server-owned, collectible only as its own persistent scan family."""
import copy
import json
import random
from pathlib import Path

import pytest

from venom.common.game import GameEngine, GameError, variety_of
from venom.common import season, story


def _species(sid, stage="rookie", **extra):
    return {"id": sid, "name": sid.title(), "stage": stage, "type": "free", "attribute": "neutral",
            "base_id": sid, "base_stats": {"hp": 240, "sp": 40, "atk": 40, "def": 25, "int": 36, "spd": 30},
            "sprites": {}, "evolutions": [], **extra}


@pytest.fixture
def game(tmp_path):
    bases = [_species("alpha", evolutions=[{"to": "beta", "level": 5},
                                           {"to": "alpha_shiny", "level": 1},
                                           {"to": "alpha_paradox", "level": 1}]),
             _species("beta", "champion"), _species("gamma")]
    species = copy.deepcopy(bases)
    for variety in ("paradox", "shiny"):
        for base in bases:
            species.append({**copy.deepcopy(base), "id": f"{base['id']}_{variety}",
                            "name": f"{base['name']} ({variety.title()})", "base_id": base["id"],
                            "paradox": variety == "paradox", "shiny": variety == "shiny", "variety": variety})
    catalog = {"species": species, "tamers": [{"id": "tamer", "name": "Tamer", "frames": {}}],
               "maps": [{"id": ident, "name": ident, "level": level, "region_id": region,
                         "width": 500, "height": 500, "spawn": [100, 100]}
                        for ident, level, region in (("forest", 1, "dawn"), ("mountain", 20, "dawn"),
                                                      ("ds_forest", 1, "world_ds"), ("ds_mountain", 20, "world_ds"))]}
    (tmp_path / "catalog.json").write_text(json.dumps(catalog))
    (tmp_path / "mechanics.json").write_text(json.dumps({"shiny_encounter_chance": .01,
                                                         "shiny_scan_gain": 5,
                                                         "paradox_encounter_chance": .025,
                                                         "species_overrides": {"Alpha": {"type": "virus", "attribute": "water"}}}))
    engine = GameEngine(tmp_path, seed=12)
    state = engine.new_player("ShinyTamer", "tamer", "alpha")
    state.update(in_farm=False)
    state["party"][0] = engine._monster("alpha", 99, abi=200, cam=100)
    state["party"][0]["spd"] = 1000000
    return engine, state


class EventRng:
    """Control the event roll without conflating enemy count/level/species draws."""
    def __init__(self, roll, count=1, species_id=None):
        self.roll, self.count, self.rolls, self.species_id = roll, count, 0, species_id

    def random(self):
        self.rolls += 1
        return self.roll

    def choices(self, *args, **kwargs):
        return [self.count]

    def choice(self, sequence):
        return self.species_id if self.species_id in sequence else sequence[0]

    def randint(self, low, high):
        return low

    def uniform(self, low, high):
        return (low + high) / 2

    def randrange(self, stop):
        return stop - 1


def test_regular_pools_starters_and_all_evolution_routes_keep_varieties_separate(game):
    engine, state = game
    assert set(engine.starters) == {"alpha", "gamma"}
    for sid in ("alpha_shiny", "alpha_paradox"):
        with pytest.raises(GameError, match="regular Rookie"):
            engine.new_player("Tamer", "tamer", sid)
    for area in engine.maps.values():
        normal, paradox = engine._pools[area["id"]]
        assert all(variety_of(engine.species[sid]) == "normal" for sid in normal)
        assert all(variety_of(engine.species[sid]) == "paradox" for sid in paradox)
        assert set(area["shiny_encounters"]) == {f"{sid}_shiny" for sid in normal}
    for source in engine.species.values():
        for route in source["evolutions"]:
            assert variety_of(source) == variety_of(engine.species[route["to"]])
        for option in engine.evolution_options(engine._monster(source["id"], 99, abi=200, cam=100)):
            assert variety_of(source) == variety_of(engine.species[option["to"]])
    for variety in ("normal", "paradox", "shiny"):
        suffix = "" if variety == "normal" else f"_{variety}"
        assert f"beta{suffix}" in {r["to"] for r in engine.species[f"alpha{suffix}"]["evolutions"]}
        assert f"beta{suffix}" in {r["to"] for r in engine.species[f"gamma{suffix}"]["evolutions"]}
    assert engine.stats_for(engine.species["alpha"], 40, 90) == engine.stats_for(engine.species["alpha_shiny"], 40, 90)
    assert engine.species["alpha_shiny"]["type"] == "virus"
    assert engine.species["alpha_shiny"]["attribute"] == "water"
    state.update(in_farm=True)
    with pytest.raises(GameError, match="not available"):
        engine.handle(state, "evolve", {"party_index": 0, "to": "alpha_shiny"})


@pytest.mark.parametrize("map_id", ["forest", "mountain", "ds_forest", "ds_mountain"])
@pytest.mark.parametrize("count", [1, 2, 3])
@pytest.mark.parametrize("roll,expected", [(0.0, "paradox"), (.0249999999, "paradox"),
                                           (.025, "shiny"), (.0349999999, "shiny"),
                                           (.035, "normal"), (.999, "normal")])
def test_real_world_encounters_apply_one_exact_rarity_roll(game, map_id, count, roll, expected):
    engine, state = game
    engine.rng = EventRng(roll, count)
    engine.handle(state, "travel", {"map_id": map_id})
    engine.handle(state, "encounter", {"shiny": True, "shiny_chance": 1, "species_id": "alpha_shiny"})
    enemies = state["battle"]["enemies"]
    assert len(enemies) == count
    assert engine.rng.rolls == 1
    assert sum(enemy["shiny"] for enemy in enemies) == int(expected == "shiny")
    assert sum(enemy["paradox"] for enemy in enemies) == int(expected == "paradox")
    if expected == "shiny":
        assert enemies[-1]["species_id"] in engine.maps[map_id]["shiny_encounters"]


@pytest.mark.parametrize("count", [1, 3])
def test_exact_probability_distribution_does_not_grow_with_enemy_count(game, count):
    engine, _ = game
    tallies = {"normal": 0, "paradox": 0, "shiny": 0}
    for i in range(10000):
        engine.rng = EventRng((i + .5) / 10000, count)
        enemies = [engine._monster("alpha") for _ in range(count)]
        engine._roll_wild_variety(enemies, ["alpha_paradox"], ["alpha_shiny"])
        variety = next((m["variety"] for m in enemies if m["variety"] != "normal"), "normal")
        tallies[variety] += 1
    assert tallies == {"normal": 9650, "paradox": 250, "shiny": 100}


def test_twenty_actual_wins_materialize_only_shiny_scan_and_keep_mastery_separate(game):
    engine, state = game
    engine.rng = EventRng(.03)
    engine._pools[state["map_id"]] = (["alpha"], ["alpha_paradox"])
    engine._shiny_pools[state["map_id"]] = ["alpha_shiny"]
    state["permanent_rewards"] = {"paradox_scan_mastery": True}
    state["scan"] = {"alpha": 100, "alpha_paradox": 35}
    for victory in range(20):
        engine.handle(state, "encounter", {})
        engine.handle(state, "battle", {"action": "attack", "target": 0})
        assert state["battle"] is None
        assert state["scan"]["alpha_shiny"] == (victory + 1) * 5
        if victory == 18:
            engine.handle(state, "digilab", {"action": "enter"})
            with pytest.raises(GameError, match="at least 100%"):
                engine.handle(state, "materialize", {"species_id": "alpha_shiny"})
            engine.handle(state, "digilab", {"action": "return"})
    assert state["scan"]["alpha"] == 100 and state["scan"]["alpha_paradox"] == 35
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "materialize", {"species_id": "alpha_shiny"})
    assert state["scan"]["alpha_shiny"] == 0
    monster = state["party"][-1]
    assert monster["shiny"] and not monster["paradox"] and monster["variety"] == "shiny"
    assert state["permanent_rewards"]["paradox_scan_mastery"] is True


@pytest.mark.parametrize("kind,training,expected", [(None, False, 5), ("story", True, 5),
                                                    ("story", False, 0), ("season", False, 0)])
def test_scan_uses_catalog_identity_and_never_scans_npc_owned_partners(game, kind, training, expected):
    engine, state = game
    enemy = engine._monster("alpha_shiny")
    enemy.update(hp=0, shiny=False, paradox=True)  # Stale display flags cannot alter rewards.
    state["permanent_rewards"] = {"paradox_scan_mastery": True}
    state["battle"] = {"enemies": [enemy], "scanned": [], "kind": kind, "story_training": training}
    engine._scan_defeat(state, 0)
    restored = json.loads(json.dumps(state))
    engine._scan_defeat(restored, 0)
    assert restored["scan"].get("alpha_shiny", 0) == expected
    assert "paradox_mastery_pending" not in restored["battle"]


def test_shiny_scan_cap_flee_and_reload_are_lossless(game):
    engine, state = game
    engine.rng = EventRng(.03, 2)
    engine._shiny_pools[state["map_id"]] = ["alpha_shiny"]
    engine.handle(state, "encounter", {})
    state["scan"]["alpha_shiny"] = 198
    state["battle"]["enemies"][1]["hp"] = 0
    engine._scan_defeat(state, 1)
    state = json.loads(json.dumps(state))
    engine._refresh(state)
    engine._scan_defeat(state, 1)
    assert state["scan"]["alpha_shiny"] == 200
    engine.handle(state, "battle", {"action": "flee"})
    assert state["scan"]["alpha_shiny"] == 200 and state["battle"] is None


def test_materialize_to_farm_withdraw_evolve_devolve_and_save_preserve_identity(game):
    engine, state = game
    state.update(in_farm=True)
    state["party"] = [engine._monster("alpha") for _ in range(6)]
    state["scan"]["alpha_shiny"] = 200
    engine.handle(state, "materialize", {"species_id": "alpha_shiny"})
    shiny = state["storage"][0]
    uid = shiny["uid"]
    assert shiny["abi"] == 5 and shiny["shiny"]
    engine.handle(state, "party", {"action": "deposit", "index": 5})
    engine.handle(state, "party", {"action": "withdraw", "index": 0})
    shiny = state["party"][-1]
    shiny.update(level=50, abi=100, cam=100, farm_bonuses={"atk": 5})
    engine.handle(state, "evolve", {"party_index": 5, "to": "beta_shiny"})
    assert state["party"][5]["species_id"] == "beta_shiny"
    state["party"][5]["level"] = 5
    engine.handle(state, "evolve", {"party_index": 5, "to": "alpha_shiny"})
    saved = json.loads(json.dumps(state))
    engine._refresh(saved)
    assert saved["party"][5]["uid"] == uid
    assert saved["party"][5]["shiny"] and saved["party"][5]["cam"] == 100
    assert saved["party"][5]["farm_bonuses"] == {"atk": 5}
    assert saved["party"][5]["history"] == ["alpha_shiny", "beta_shiny"]
    assert saved["party"] == state["party"] and saved["storage"] == state["storage"]
    legacy = copy.deepcopy(saved)
    for monster in legacy["party"] + legacy["storage"]:
        for key in ("shiny", "variety", "base_id"):
            monster.pop(key, None)
    engine._refresh(legacy)
    assert legacy["party"] == saved["party"] and legacy["storage"] == saved["storage"]


def test_season_rivals_cannot_receive_shinies_from_starter_or_evolution_lists(game):
    engine, state = game
    career = season.create_career(state, engine.species, engine.tamers,
                                   engine.starters + ["alpha_shiny", "alpha_paradox"])
    for rival in career["roster"]:
        if rival["is_player"]:
            continue
        assert all(variety_of(engine.species[p["species_id"]]) == "normal" for p in rival["team"])
        rival["development"] = 11
        rival["team"] = [{"species_id": "alpha", "level": 99}]
        engine.species["alpha"]["evolutions"] = [{"to": "beta_shiny", "level": 1},
                                                  {"to": "beta_paradox", "level": 1}]
        season._develop(rival, engine.species, random.Random(0), [])
        assert rival["team"][0]["species_id"] == "alpha"


def test_shipped_catalog_every_scannable_world_habitat_exposes_shiny_candidates():
    engine = GameEngine(Path(__file__).resolve().parents[1], seed=3)
    state = engine.new_player("WorldShinyHunter", next(iter(engine.tamers)), "agumon")
    engine.handle(state, "digifarm", {"action": "return"})
    state["party"][0]["spd"] = 1000000
    assert engine.catalog["rules"]["shiny_encounter_chance"] == .01
    assert engine.catalog["rules"]["shiny_scan_gain"] == 5
    covered = set()
    encountered = set()
    habitat = {}

    def encounter(area, species_id=None):
        engine.rng = EventRng(.03, species_id=species_id)
        engine.handle(state, "travel", {"map_id": area["id"]})
        engine.handle(state, "encounter", {})
        enemies = state["battle"]["enemies"]
        assert len(enemies) == 1 and enemies[0]["shiny"], area["id"]
        enemy = enemies[0]
        assert enemy["species_id"] in area["shiny_encounters"]
        low, high = engine.wild_level_range(area)
        assert low <= enemy["level"] <= high
        encountered.add(enemy["species_id"])
        engine.handle(state, "battle", {"action": "flee"})

    for area in engine.maps.values():
        assert area["shiny_encounters"], area["id"]
        covered.update(area["shiny_encounters"])
        assert all(engine.species[sid]["shiny"] for sid in area["shiny_encounters"])
        for sid in area["shiny_encounters"]:
            habitat[sid] = area
        encounter(area)
    assert covered == {s["id"] for s in engine.species.values() if s["shiny"]}
    for sid in sorted(covered - encountered):
        encounter(habitat[sid], sid)
    assert encountered == covered


@pytest.mark.parametrize("campaign", ["dawn_relay", "world_ds_paradox"])
@pytest.mark.parametrize("roll,expected", [(0, True), (.009999999, True), (.01, False), (.5, False)])
def test_shipped_story_training_rolls_shiny_and_never_guarantees_an_owned_shiny(campaign, roll, expected):
    engine = GameEngine(Path(__file__).resolve().parents[1], seed=5)
    state = engine.new_player("ShinyPractice", next(iter(engine.tamers)), "agumon")
    state["party"] = [engine._monster("agumon_shiny")]
    state["party"][0].update(spd=1000000, atk=1000000)
    engine.handle(state, "story", {"action": "enter", "campaign_id": campaign})
    if campaign == "world_ds_paradox":
        engine.handle(state, "story", {"action": "travel", "chapter": 1})
    engine.rng = EventRng(roll)
    engine.handle(state, "story", {"action": "train"})
    battle = state["battle"]
    enemy = battle["enemies"][0]
    assert battle["story_training"] and engine.rng.rolls == 1
    assert enemy["shiny"] is expected
    expected_id = "agumon_shiny" if expected else "agumon_firewall" if .01 <= roll < .017 else "agumon"
    assert enemy["species_id"] == expected_id
    engine.handle(state, "battle", {"action": "attack", "target": 0,
                                    "battle_id": battle["id"], "expected_turn": battle["turn"]})
    assert state["scan"][enemy["species_id"]] == (20 if expected_id == "agumon" else 5)
