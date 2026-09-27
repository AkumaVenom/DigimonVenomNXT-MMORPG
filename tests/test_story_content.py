"""Production campaign references, progression gates and actual Dawn collision."""
from collections import deque
from pathlib import Path

import pytest

from venom.common.game import GameEngine, SHOP
from venom.common.story_content import CHAPTERS, build_content
from venom.server.navigation import Navigation

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def campaign():
    engine = GameEngine(ROOT, seed=41)
    return engine, build_content(engine)


def test_all_production_assets_and_rewards_exist(campaign):
    engine, data = campaign
    assert len(data["regions"]) == 9
    assert len(data["maps"]) == 18
    assert len(data["npcs"]) == 54
    assert len({r["badge"]["id"] for r in data["regions"] if r["badge"]}) == 8
    for map_id, meta in data["maps"].items():
        area = engine.maps[map_id]
        assert (ROOT / area["path"]).is_file()
        assert (ROOT / area["walkable"]).is_file()
        assert meta["arrival"] == area["spawn"]
        assert len(meta["npc_ids"]) > 0
    for npc in [*data["npcs"].values(), *data["challengers"]]:
        tamer = engine.tamers[npc["tamer"]]
        assert npc["tamer"] == npc["tamer_id"]
        for path in tamer["frames"]["down"]:
            assert (ROOT / path).is_file()
        assert npc["map_id"] in data["maps"]
        for monster in npc["team"]:
            species = engine.species[monster["species"]]
            assert (ROOT / species["sprites"]["idle"]).is_file()
            assert not species.get("paradox")
            assert 1 <= monster["level"] <= 100
        for item, count in npc["reward"].get("items", {}).items():
            assert item in SHOP and count > 0
        partner = npc["reward"].get("partner")
        assert partner is None or partner in engine.species


def test_every_npc_and_gate_has_a_collision_connected_route(campaign):
    engine, data = campaign
    nav = Navigation(ROOT, engine.maps)
    for map_id, area in data["maps"].items():
        start = tuple(area["arrival"])
        targets = {(npc["x"], npc["y"]) for npc in data["npcs"].values() if npc["map_id"] == map_id}
        targets.update((gate["x"], gate["y"]) for gate in area["exits"])
        assert all(nav.walkable(map_id, *point) for point in targets)
        assert len(targets) == len(area["npc_ids"]) + len(area["exits"])
        assert all(point != start for point in targets)
        queue, seen = deque([start]), {start}
        missing = targets - seen
        # Every exact supercover lattice edge must connect. White pixels alone
        # would not detect isolated rooms or blocked map decorations.
        while queue and missing:
            origin = queue.popleft()
            for dx, dy in ((16, 0), (-16, 0), (0, 16), (0, -16)):
                target = (origin[0] + dx, origin[1] + dy)
                if target in seen or not nav.walkable(map_id, *target):
                    continue
                actual = nav.trace(map_id, origin, target)
                if abs(actual[0] - target[0]) > 1e-7 or abs(actual[1] - target[1]) > 1e-7:
                    continue
                seen.add(target)
                missing.discard(target)
                queue.append(target)
        assert not missing, f"Unreachable authored positions in {map_id}: {missing}"


def test_badges_unlock_exactly_one_region_at_a_time(campaign):
    _, data = campaign
    for badge_count in range(9):
        held = {region["id"] for region in data["regions"][:badge_count]}
        seen, queue = {data["start_map"]}, deque([data["start_map"]])
        while queue:
            for gate in data["maps"][queue.popleft()]["exits"]:
                destination = gate["to_map"]
                assert destination in data["maps"]
                assert gate["name"] == data["maps"][destination]["name"]
                if gate["requires_badge"] and gate["requires_badge"] not in held:
                    continue
                if destination not in seen:
                    seen.add(destination)
                    queue.append(destination)
        expected = {map_id for region in data["regions"][:min(9, badge_count + 1)] for map_id in region["maps"]}
        assert seen == expected


def test_authored_encounters_have_an_acyclic_increasing_progression(campaign):
    _, data = campaign
    completed, previous = set(), 0
    for index, region in enumerate(data["regions"]):
        fights = [data["npcs"][ident] for ident in (*region["trial_ids"], region["warden_id"])]
        assert [npc["role"] for npc in fights] == ["trainer", "trainer", "champion" if index == 8 else "warden"]
        if index == 0:
            assert [len(fight["team"]) for fight in fights] == [1, 1, 2]
        for fight in fights:
            assert set(fight["requires"]) <= completed
            ceiling = max(partner["level"] for partner in fight["team"])
            assert ceiling > previous
            previous = ceiling
            completed.add(fight["id"])
            for phase in ("intro", "locked", "ready", "won", "lost", "repeat"):
                assert fight["dialogue"][phase] and all(isinstance(line, str) and line.strip() for line in fight["dialogue"][phase])
        if region["badge"]:
            assert fights[-1]["badge"] == region["badge"]["id"]
            assert max(partner["level"] for partner in fights[-1]["team"]) == (index + 1) * 10
    assert previous == 96
    assert data["npcs"]["lumen_trial_1"]["reward"]["partner"] == "terriermon"
    assert data["npcs"]["lumen_trial_2"]["reward"]["partner"] == "patamon"
    assert max(partner["level"] for npc in data["challengers"] for partner in npc["team"]) == 100
    assert len({npc["id"] for npc in data["challengers"]}) == 6
    assert all(npc["repeatable"] for npc in data["challengers"])


def test_chapters_have_specific_original_objectives_and_shared_services(campaign):
    _, data = campaign
    assert len({chapter["synopsis"] for chapter in CHAPTERS}) == 8
    for region in data["regions"]:
        rows = [data["npcs"][ident] for ident in region["npc_ids"]]
        assert len(rows) == 6
        assert {npc["role"] for npc in rows} >= {"mentor", "healer", "shop", "trainer"}
        mentor = next(npc for npc in rows if npc["role"] == "mentor")
        full_briefing = " ".join(mentor["dialogue"]["intro"])
        for npc in rows:
            if npc["team"]:
                assert npc["name"].split()[-1] in full_briefing
        assert data["maps"][region["maps"][0]]["name"] in full_briefing
    first = data["npcs"]["lumen_mentor"]["dialogue"]["intro"]
    assert any("leave them behind" in line for line in first)
    final = " ".join(data["npcs"]["citadel_mentor"]["dialogue"]["intro"])
    assert "lose the title" in final and "win it back" in final


def test_content_is_deterministic_and_cached_without_changing_catalog(campaign):
    engine, content = campaign
    assert build_content(engine) is content
    other = GameEngine(ROOT, seed=9999)
    assert build_content(other) == content
    assert engine.maps["map_001_a"]["name"] == "Dawn Sector 001"
    assert "story" not in engine.catalog
