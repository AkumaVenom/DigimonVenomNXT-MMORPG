"""Authored-case invariants: chronology, identities, consent and navigable scope."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from venom.common.game import GameEngine
from venom.common import xros_story_content as content
from venom.common.xros_story_layout import CAMPAIGN_MAPS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def game():
    return GameEngine(ROOT, seed=914)


@pytest.fixture(scope="module")
def campaign(game):
    return content.build_content(game)


def test_campaign_is_thirty_one_distinct_existing_xros_maps_without_world_mutation(game, campaign):
    before = copy.deepcopy(game.maps)
    assert len(campaign["regions"]) == len(campaign["maps"]) == 31
    assert tuple(campaign["maps"]) == CAMPAIGN_MAPS
    assert len(set(CAMPAIGN_MAPS)) == 31
    assert campaign["start_map"] == CAMPAIGN_MAPS[0]
    assert all(game.maps[mid]["region_id"] == "xros_wars" for mid in campaign["maps"])
    assert content.build_content(game) is campaign
    assert game.maps == before
    hub = campaign["regions"][0]
    assert hub["peaceful"] and not hub["quest_ids"] and hub["badge"] is None
    assert not campaign["maps"][hub["maps"][0]]["allow_wild_battles"]
    assert {campaign["npcs"][i]["role"] for i in hub["npc_ids"]} >= {
        "mentor", "intel", "healer", "shop", "lab", "farm"}
    assert not any(campaign["npcs"][i]["team"] for i in hub["npc_ids"])


def test_every_field_has_an_ordered_case_proof_and_forward_portal(campaign):
    for index, region in enumerate(campaign["regions"][1:], 1):
        qid = region["quest_ids"][0]
        quest = campaign["npcs"][qid]
        assert quest["role"] == "quest" and quest["badge"] == region["badge"]["id"]
        assert quest["requires"] == ([f"ghost_{index - 1:02d}_quest"] if index > 1 else [])
        exits = campaign["maps"][region["maps"][0]]["exits"]
        assert any(row["to_map"] == CAMPAIGN_MAPS[index - 1] and not row["requires_badge"] for row in exits)
        if index < 30:
            assert quest["quest_requires"] == [f"ghost_{index:02d}_trainer"]
            trainer = campaign["npcs"][quest["quest_requires"][0]]
            assert trainer["requires_accepted"] == [qid]
            assert trainer["team"] and not trainer["repeatable"]
            forward = next(row for row in exits if row["to_map"] == CAMPAIGN_MAPS[index + 1])
            assert forward["requires_badge"] == region["badge"]["id"]
        else:
            assert quest["quest_requires"] == []
            uplink = next(row for row in exits if row["to_map"] == CAMPAIGN_MAPS[0])
            assert uplink["requires_campaign_complete"] is True
    levels = [row["level_min"] for row in campaign["regions"]]
    assert levels == sorted(levels) and levels[0] == 1 and levels[-1] == 99


def test_exactly_thirty_real_battles_no_scripted_shiny_scans_or_party_boosts(game, campaign):
    battlers = [npc for npc in campaign["npcs"].values() if npc["team"]]
    assert len(battlers) == 30
    for npc in campaign["npcs"].values():
        assert not any(key in npc["reward"] for key in ("training_level", "level_floor", "partner", "scan"))
        for partner in npc["team"]:
            species = game.species[partner["species"]]
            assert not species.get("shiny") and not species.get("paradox") and not species.get("firewall")
            assert 1 <= partner["level"] <= 99
    final = campaign["npcs"][content.FINAL_NPC_ID]
    assert [row["level"] for row in final["team"]] == [99, 99, 99]
    assert final["map_id"] == CAMPAIGN_MAPS[-1]
    assert not final["repeatable"]
    assert final["requires"] == [f"ghost_{i:02d}_quest" for i in range(1, 31)]
    assert final["requires_badges"] == [f"ghost_{i:02d}" for i in range(1, 31)]
    assert campaign["completion_reward"] == {"shiny_scan_bonus": 20}


def test_every_recurring_character_keeps_their_face_and_no_duplicate_people_per_map(campaign):
    identities = {}
    for npc in campaign["npcs"].values():
        identity = npc["character_id"]
        identities.setdefault(identity, set()).add(npc["tamer"])
    assert all(len(portraits) == 1 for portraits in identities.values())
    for area in campaign["maps"].values():
        people = [campaign["npcs"][i]["character_id"] for i in area["npc_ids"]]
        assert len(people) == len(set(people)), area["id"]
    mara = [npc for npc in campaign["npcs"].values() if npc["character_id"] == content.MARA_CHARACTER_ID]
    assert len(mara) == 17
    assert len({npc["map_id"] for npc in mara}) == 17
    assert all(npc["hide_on_campaign_complete"] for npc in mara)
    assert all(npc["tamer"] == "tamer_031" for npc in mara)
    assert all(npc["character_id"] == content.MARA_CHARACTER_ID for npc in campaign["npcs"].values() if npc["tamer"] == "tamer_031")
    assert all(npc["hide_on_reveal"] for npc in mara if npc.get("role") == "intel" and not npc.get("show_requires_reveal"))


def test_reveal_is_earned_on_map_twenty_seven_not_announced_by_earlier_case(campaign):
    revealing = [npc for npc in campaign["npcs"].values() if npc.get("reveal_on_complete")]
    assert [npc["id"] for npc in revealing] == [content.REVEAL_QUEST_ID]
    reveal = revealing[0]
    assert reveal["map_id"] == CAMPAIGN_MAPS[26]
    assert "Mara Vale is the Null Regent" in " ".join(reveal["dialogue"]["won"])
    for branch in ("intro", "quest_start", "quest_complete"):
        text = " ".join(reveal["dialogue"][branch])
        assert "Mara Vale is the Null Regent" not in text
        assert "Mara answered" not in text
    confession = campaign["npcs"]["ghost_26_mara"]
    assert confession["show_requires_reveal"]
    assert "I am the Null Regent" in " ".join(confession["dialogue"]["intro"])
    assert campaign["npcs"][content.FINAL_NPC_ID]["requires_reveal"]


def test_clean_recorder_changes_actual_witness_hacking_flags(campaign):
    hacked = [npc for npc in campaign["npcs"].values() if npc.get("hacked_after_victory")]
    assert len(hacked) == 23
    assert all(npc["role"] == "trainer" for npc in hacked)
    assert all(npc["dialogue"]["hacked_repeat"] for npc in hacked)
    assert "account stayed under her control" in " ".join(campaign["npcs"]["ghost_24_quest"]["dialogue"]["won"])
    for index in range(24, 30):
        assert not campaign["npcs"][f"ghost_{index:02d}_trainer"]["hacked_after_victory"]


def test_new_intel_only_uses_completed_evidence_and_never_previews_the_twist(campaign):
    hub = campaign["npcs"]["ghost_hub_mara"]
    indices = [int(row["requires_completed"][0].split("_")[1]) for row in hub["dialogue_variants"]]
    assert indices == sorted(indices, reverse=True)
    assert len(indices) == len(set(indices))
    for variant in hub["dialogue_variants"]:
        assert all(i in campaign["npcs"] for i in variant["requires_completed"])
        assert "I am the Null Regent" not in " ".join(variant["lines"])
    for index in content.MARA_FIELDS:
        if index >= 26:
            continue
        npc = campaign["npcs"][f"ghost_{index:02d}_mara"]
        assert npc["dialogue"]["ready"] != npc["dialogue_variants"][0]["lines"]
        assert npc["dialogue_variants"][0]["requires_completed"] == [f"ghost_{index:02d}_quest"]


def test_authored_dialogue_is_readable_unique_and_has_recovery_followup(campaign):
    for key in ("quest", "brief", "report", "challenge", "victory", "loss", "recovery", "after"):
        assert len({chapter[key] for chapter in content.CHAPTERS}) == 30
    for npc in campaign["npcs"].values():
        assert npc["role_label"]
        for lines in npc["dialogue"].values():
            assert isinstance(lines, list) and lines
            assert all(isinstance(line, str) and line.strip() for line in lines)
            assert all(len(line.split()) <= 75 for line in lines)
        if npc["character_id"] != content.MARA_CHARACTER_ID:
            assert npc["dialogue"]["campaign_complete"]
    epilogue = campaign["epilogue"]
    narrator = campaign["npcs"][epilogue["npc_id"]]
    assert narrator["character_id"] == "ghost_iona" and narrator["role"] == "quest"
    assert narrator["map_id"] == CAMPAIGN_MAPS[-1]
    assert "6% scan instead of 5%" in " ".join(epilogue["lines"])
    assert "will not return" in " ".join(epilogue["lines"])


@pytest.mark.parametrize("mutation", ["missing_map", "wrong_region", "missing_species", "missing_portrait", "changed_spawn"])
def test_builder_rejects_broken_catalog_references(game, mutation):
    # Shallow engine shell with isolated source tables avoids corrupting the
    # session's catalog while proving authoring failures are explicit.
    class Fixture:
        pass
    broken = Fixture()
    broken.maps = copy.deepcopy(game.maps)
    broken.species = copy.deepcopy(game.species)
    broken.tamers = copy.deepcopy(game.tamers)
    if mutation == "missing_map":
        del broken.maps[CAMPAIGN_MAPS[4]]
    elif mutation == "wrong_region":
        broken.maps[CAMPAIGN_MAPS[0]]["region_id"] = "dawn"
    elif mutation == "missing_species":
        del broken.species["diaboromon"]
    elif mutation == "missing_portrait":
        del broken.tamers["tamer_031"]
    else:
        broken.maps[CAMPAIGN_MAPS[1]]["spawn"][0] += 2
    with pytest.raises(ValueError, match="Ghostline|portrait|opponent|Digimon"):
        content.build_content(broken)


@pytest.mark.parametrize("variety", ["paradox", "shiny", "firewall"])
def test_authoring_rejects_an_existing_rare_form_in_a_scripted_normal_team(game, campaign, variety):
    altered = copy.deepcopy(campaign)
    opponent = altered["npcs"][content.FINAL_NPC_ID]["team"][0]
    rare_id = f"{opponent['species']}_{variety}"
    assert rare_id in game.species
    opponent["species"] = rare_id
    with pytest.raises(ValueError, match="authored teams require normal existing Digimon"):
        content._validate(game, altered)
