"""The replacement Fanglongmon art keeps the two established playable identities.

These checks use the shipped catalog and ordinary engine commands. Encounter
randomness is pinned to a legal roll so a rare Paradox does not make QA flaky;
opponents, levels, combat settlement and recruitment remain production rules.
"""
from __future__ import annotations

import copy
from pathlib import Path
from unittest.mock import patch

import pytest

from venom.common.game import GameEngine, GameError
from venom.server.database import Database


ROOT = Path(__file__).resolve().parents[1]
FORMS = ("fanglongmon", "fanglongmon_paradox")


@pytest.fixture
def game():
    engine = GameEngine(ROOT, seed=100)
    state = engine.new_player("FanglongKeeper", next(iter(engine.tamers)), "agumon")
    return engine, state


def encounter_form(engine, state, species_id, region):
    """Select an existing habitat and force only valid random encounter choices."""
    rare = int(engine.species[species_id]["paradox"])
    habitats = [area for area in engine.maps.values()
                if area.get("region_id", "dawn") == region
                and species_id in engine._pools[area["id"]][rare]]
    assert habitats, f"{species_id} must remain discoverable in {region}"
    area = min(habitats, key=lambda row: (row["level"], row["id"]))
    engine.handle(state, "travel", {"map_id": area["id"]})
    original_choice = engine.rng.choice

    def choose(values):
        return species_id if species_id in values else original_choice(values)

    with patch.object(engine.rng, "choices", return_value=[1]), \
            patch.object(engine.rng, "choice", side_effect=choose), \
            patch.object(engine.rng, "random", return_value=0.0 if rare else 1.0):
        engine.handle(state, "encounter", {})
    enemies = state["battle"]["enemies"]
    assert len(enemies) == 1 and enemies[0]["species_id"] == species_id
    assert enemies[0]["paradox"] is bool(rare)
    low, high = engine.wild_level_range(area)
    assert low <= enemies[0]["level"] <= high
    return enemies[0]


@pytest.mark.parametrize("species_id", FORMS)
@pytest.mark.parametrize("region", ("dawn", "world_ds"))
@pytest.mark.parametrize("mastery", (False, True))
def test_both_forms_are_real_wild_encounters_with_once_only_scan_rewards(game, species_id, region, mastery):
    engine, state = game
    engine.handle(state, "digifarm", {"action": "return"})
    # A veteran owned team surveys existing endgame habitats; no enemy stats,
    # battle outcomes, XP, currency or scan results are injected.
    state["party"] = [engine._monster("omnimon", 99, abi=50, cam=80) for _ in range(3)]
    state["permanent_rewards"] = {"paradox_scan_mastery": mastery}
    encounter_form(engine, state, species_id, region)
    before_credits = state["credits"]
    for _ in range(100):
        if state["battle"] is None:
            break
        engine.handle(state, "battle", {"action": "attack", "target": 0})
    assert state["battle"] is None, "Ordinary battle controls must finish the encounter"
    assert state["wins"] == 1 and state["losses"] == 0
    assert state["credits"] > before_credits
    expected = (6 if mastery else 5) if species_id.endswith("_paradox") else 20
    assert state["scan"] == {species_id: expected}
    for _ in range(2):
        assert engine._check_end(state)
    assert state["scan"] == {species_id: expected}
    assert state["wins"] == 1


@pytest.mark.parametrize("species_id", FORMS)
@pytest.mark.parametrize("scan,expected_abi", ((100, 0), (200, 5)))
@pytest.mark.parametrize("full_party", (False, True))
def test_materialization_preserves_variant_and_uses_existing_party_or_farm(game, species_id, scan,
                                                                         expected_abi, full_party):
    engine, state = game
    if full_party:
        state["party"] = [engine._monster("agumon") for _ in range(6)]
    existing_ids = {mon["uid"] for mon in state["party"]}
    state["scan"][species_id] = scan
    engine.handle(state, "materialize", {"species_id": species_id})
    partner = (state["storage"] if full_party else state["party"])[-1]
    assert partner["species_id"] == species_id
    assert partner["paradox"] is species_id.endswith("_paradox")
    assert partner["uid"] not in existing_ids
    assert (partner["level"], partner["abi"]) == (1, expected_abi)
    assert partner["skills"] and all(move["sp"] > 0 for move in partner["skills"])
    assert state["scan"][species_id] == 0
    assert len(state["party"]) == (6 if full_party else 2)
    assert len(state["storage"]) == (1 if full_party else 0)
    with pytest.raises(GameError, match="100% scan"):
        engine.handle(state, "materialize", {"species_id": species_id})


@pytest.mark.parametrize("species_id", FORMS)
def test_existing_examon_route_and_reverse_preserve_owned_partner(game, species_id):
    engine, state = game
    target = "examon_paradox" if species_id.endswith("_paradox") else "examon"
    # Fanglongmon already had this data-splice route. Replacement art must not
    # create another species or silently change its earned evolution family.
    assert len([row for row in engine.catalog["species"] if row["id"] == species_id]) == 1
    assert engine.species[species_id]["base_id"] == "fanglongmon"
    assert [route["to"] for route in engine.species[species_id]["evolutions"]] == [target]
    assert not engine.devolutions.get(species_id)
    bonuses = {"hp": 11, "atk": 7, "int": 5}
    partner = engine._monster(species_id, 60, abi=50, cam=77, farm_bonuses=bonuses)
    uid = partner["uid"]
    state["party"] = [partner]
    route = next(row for row in engine.evolution_options(partner) if row["to"] == target)
    assert route["eligible"] and not route["devolve"]
    engine.handle(state, "evolve", {"party_index": 0, "to": target})
    evolved = state["party"][0]
    assert evolved["species_id"] == target
    assert (evolved["uid"], evolved["cam"], evolved["farm_bonuses"]) == (uid, 77, bonuses)
    assert evolved["paradox"] is species_id.endswith("_paradox")
    assert evolved["level"] == 1 and evolved["abi"] > 50
    assert species_id in evolved["history"]
    with pytest.raises(GameError, match="LEVEL 5"):
        engine.handle(state, "evolve", {"party_index": 0, "to": species_id})
    evolved["level"] = 5
    before_abi = evolved["abi"]
    engine.handle(state, "evolve", {"party_index": 0, "to": species_id})
    restored = state["party"][0]
    assert restored["species_id"] == species_id and restored["level"] == 1
    assert (restored["uid"], restored["cam"], restored["farm_bonuses"]) == (uid, 77, bonuses)
    assert restored["paradox"] is species_id.endswith("_paradox")
    assert restored["abi"] > before_abi and target in restored["history"]
    stats = engine.stats_for(engine.species[species_id], 1, restored["abi"], bonuses)
    assert restored["max_hp"] == stats["hp"]
    assert restored["atk"] == stats["atk"] and restored["int"] == stats["int"]


@pytest.mark.parametrize("species_id", FORMS)
def test_owned_fanglongmon_can_use_paid_skills_and_free_attack(game, species_id):
    engine, state = game
    engine.handle(state, "digifarm", {"action": "return"})
    state["party"] = [engine._monster(species_id, 60, abi=50)]
    enemy = encounter_form(engine, state, "fanglongmon", "world_ds")
    partner = state["party"][0]
    for index in range(len(partner["skills"])):
        skill = partner["skills"][index]
        before_sp, before_hp = partner["sp"], enemy["hp"]
        engine.handle(state, "battle", {"action": "skill", "skill_index": index, "target": 0})
        assert partner["sp"] == before_sp - skill["sp"]
        assert enemy["hp"] < before_hp
        assert any(event.get("attacker_side") == "player" and event.get("move") == skill["name"]
                   for event in state["events"])
    assert state["battle"], "The encounter fixture must survive long enough to check both skills"
    partner["sp"] = 0
    before_hp = enemy["hp"]
    engine.handle(state, "battle", {"action": "attack", "target": 0})
    assert partner["sp"] == 0 and enemy["hp"] < before_hp


def test_existing_normal_and_paradox_saves_survive_database_and_engine_refresh(game, tmp_path):
    engine, state = game
    state["party"] = [engine._monster("fanglongmon", 73, abi=63, cam=82,
                                     farm_bonuses={"atk": 8, "hp": 17})]
    state["storage"] = [engine._monster("fanglongmon_paradox", 52, abi=39, cam=69,
                                       farm_bonuses={"spd": 4})]
    state["scan"] = {"fanglongmon": 120, "fanglongmon_paradox": 85}
    state["permanent_rewards"] = {"paradox_scan_mastery": True}
    engine._refresh(state)
    owned = copy.deepcopy({key: state[key] for key in ("party", "storage", "scan", "permanent_rewards")})
    database = Database({"driver": "sqlite", "path": str(tmp_path / "fanglongmon.sqlite")}, dev=True)
    try:
        database.initialize()
        key = database.register(state["username"], "fanglongmon-save-test", state)
        resumed, revision = database.load(key)
        fresh_engine = GameEngine(ROOT, seed=101)
        fresh_engine._refresh(resumed)
        assert {key: resumed[key] for key in owned} == owned
        database.save(key, resumed, revision)
        reloaded, next_revision = database.load(key)
        assert next_revision == revision + 1
        fresh_engine._refresh(reloaded)
        assert {key: reloaded[key] for key in owned} == owned
        assert all(mon["species_id"] in fresh_engine.species for mon in reloaded["party"] + reloaded["storage"])
    finally:
        database.close()
