"""Independent release acceptance against the user's confirmed v1.4.0 baseline.

Published legacy fingerprints were taken before this update. These checks catch
accidental changes that a self-generated current manifest cannot detect. The
full existing Dawn played-campaign tests separately prove prerequisite earning
and the first-championship reward through ordinary battle controls.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from venom.common import story
from venom.common.game import GameEngine, GameError, variety_of

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.fixture(scope="module")
def release():
    return GameEngine(ROOT, seed=150)


def test_previous_1506_species_and_all_500_map_assets_are_exactly_preserved():
    catalog = json.loads((ROOT / "data/catalog.json").read_text("utf-8"))
    previous = [row for row in catalog["species"] if row.get("variety") != "firewall"]
    assert len(catalog["species"]) == 2008 and len(previous) == 1506
    assert digest(previous) == "4c270d436304203835d9ce087dec54a53ef81a43a7244508e664d818d20dca14"
    old_maps = [{key: value for key, value in row.items() if key != "firewall_encounters"}
                for row in catalog["maps"]]
    assert len(old_maps) == 500
    assert digest(old_maps) == "5b07d091aec64f9a2e37187bd88fdd39f879da67911c16ab098d8c5d7dfc58b2"
    assert digest(catalog["tamers"]) == "a329f3b7acfc15ef81892c05782b3b467f9c3a42b6a58ad6b335df8903cb8beb"
    assert digest(catalog["audio"]) == "465083983ec6039e96cdab4e6f76b6a28d00472ab669a035701f6e0383e5e839"


def test_old_habitats_are_frozen_and_firewall_pools_match_every_map(release):
    assert digest(release._pools) == "ec5b1a1a0b47f642cd4cafc3d6f5ae6f78919373ccb965de0b0faa80d08ad312"
    assert digest(release._shiny_pools) == "d68b678bdcdabe64b87bc6237e078dd527a78e10f196ed92028dc7e426f89095"
    published = json.loads((ROOT / "data/catalog.json").read_text("utf-8"))
    assert set(release._firewall_pools) == set(release.maps)
    for area in published["maps"]:
        expected = [sid + "_firewall" for sid in release._pools[area["id"]][0]]
        assert area["firewall_encounters"] == expected, area["id"]
        assert release._firewall_pools[area["id"]] == expected, area["id"]
    for prefix, chance in (("paradox", .025), ("shiny", .01), ("firewall", .007)):
        assert release.rules[prefix + "_encounter_chance"] == chance
        assert release.catalog["rules"][prefix + "_encounter_chance"] == chance
        assert release.rules[prefix + "_scan_gain"] == 5
        assert release.catalog["rules"][prefix + "_scan_gain"] == 5


def test_all_502_firewall_families_have_normal_balance_and_closed_evolution_routes(release):
    originals = [row for row in release.species.values() if variety_of(row) == "normal"]
    assert len(originals) == 502
    for base in originals:
        sid = base["id"] + "_firewall"
        firewall = release.species[sid]
        assert firewall["base_id"] == base["id"]
        assert firewall["variety"] == "firewall" and firewall["firewall"] is True
        assert firewall["shiny"] is False and firewall["paradox"] is False
        for key in ("stage", "type", "attribute", "base_stats"):
            assert firewall[key] == base[key], (sid, key)
        for level, abi in ((1, 0), (50, 80), (99, 200)):
            bonuses = {"hp": 31, "sp": 7, "atk": 4, "int": 2}
            assert release.stats_for(firewall, level, abi, bonuses) == release.stats_for(base, level, abi, bonuses), sid
        expected = [{**route, "to": route["to"] + "_firewall"} for route in base["evolutions"]]
        assert firewall["evolutions"] == expected, sid
        monster = release._monster(sid, 99, abi=200, cam=100)
        assert all(variety_of(release.species[row["to"]]) == "firewall"
                   for row in release.evolution_options(monster)), sid
        assert all(variety_of(release.species[row["to"]]) == "firewall"
                   for row in release.devolutions.get(sid, [])), sid
    assert all(variety_of(release.species[sid]) == "normal" for sid in release.starters)
    with pytest.raises(GameError, match="regular Rookie"):
        release.new_player("ForbiddenRareStarter", next(iter(release.tamers)), "agumon_firewall")


@pytest.mark.parametrize("campaign", [story.DAWN_CAMPAIGN, story.DS_CAMPAIGN, story.XROS_CAMPAIGN])
def test_real_firewall_teams_keep_identity_and_stats_through_private_campaign_hubs_and_reload(campaign):
    engine = GameEngine(ROOT, seed=153)
    state = engine.new_player("FireWallTraveller", next(iter(engine.tamers)), "agumon")
    area = next(area for area in engine.maps.values() if area.get("region_id") == "xros_wars")
    engine.handle(state, "travel", {"map_id": area["id"]})
    state["party"] = [engine._monster(sid, level, abi=abi, cam=cam, farm_bonuses={"atk": 7, "hp": 25})
                      for sid, level, abi, cam in (("agumon_firewall", 37, 44, 59),
                                                  ("greymon_firewall", 68, 80, 71),
                                                  ("omnimon_firewall", 91, 135, 96))]
    state["storage"] = [engine._monster("patamon_firewall", 12, abi=10, cam=21)]
    original = copy.deepcopy({key: state[key] for key in ("party", "storage", "scan", "credits", "inventory")})
    location = {key: state[key] for key in ("map_id", "x", "y")}
    engine.handle(state, "story", {"action": "enter", "campaign_id": campaign})
    assert state["in_story"] and state["story"]["campaign_id"] == campaign
    assert {key: state[key] for key in original} == original
    story_location = {key: state[key] for key in ("map_id", "x", "y")}
    for hub in ("digilab", "digifarm"):
        engine.handle(state, hub, {"action": "enter"})
        assert {key: state[key] for key in original} == original
        engine.handle(state, hub, {"action": "return"})
        assert state["in_story"]
        assert {key: state[key] for key in story_location} == story_location
    saved = json.loads(json.dumps(state))
    restored_engine = GameEngine(ROOT, seed=155)
    restored_engine._refresh(saved)
    assert {key: saved[key] for key in original} == original
    assert saved["story"]["id"] == state["story"]["id"]
    assert saved["in_story"] and saved["story"]["campaign_id"] == campaign
    restored_engine.handle(saved, "story", {"action": "return"})
    assert {key: saved[key] for key in original} == original
    assert {key: saved[key] for key in location} == location
