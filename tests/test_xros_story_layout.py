"""Real imported geometry checks for the private 31-map Ghostline campaign."""
from collections import deque
import hashlib
import json
import math
from pathlib import Path

import pytest

from venom.common.xros_story_layout import CAMPAIGN_MAPS, PLACEMENTS
from venom.server.navigation import Navigation

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def geometry():
    catalog = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))
    maps = {row["id"]: row for row in catalog["maps"]}
    return maps, Navigation(ROOT, maps)


def test_thirty_one_existing_distinct_super_xros_maps(geometry):
    maps, _ = geometry
    assert len(CAMPAIGN_MAPS) == len(set(CAMPAIGN_MAPS)) == 31
    assert set(PLACEMENTS) == set(CAMPAIGN_MAPS)
    assert CAMPAIGN_MAPS[0] == "xros_175"  # Neon service-counter safe hub.
    assert CAMPAIGN_MAPS[-1] == "xros_176"  # Central control arena finale.
    assert {maps[mid]["region_id"] for mid in CAMPAIGN_MAPS} == {"xros_wars"}
    hashes = {hashlib.sha256((ROOT / maps[mid]["path"]).read_bytes()).hexdigest()
              for mid in CAMPAIGN_MAPS}
    assert len(hashes) == 31, "A differently numbered copy is not a distinct map."


@pytest.mark.parametrize("map_id", CAMPAIGN_MAPS)
def test_every_actor_and_portal_is_reachable_on_actual_map_collision(geometry, map_id):
    maps, nav = geometry
    points = PLACEMENTS[map_id]
    assert len(points) == len(set(points)) == 9
    assert tuple(maps[map_id]["spawn"]) == points[0]
    assert all(nav.walkable(map_id, *point) for point in points)
    # Check real movement paths: nine white pixels can still be nine islands.
    queue, seen, missing = deque([points[0]]), {points[0]}, set(points[1:])
    while queue and missing:
        here = queue.popleft()
        for dx, dy in ((16, 0), (-16, 0), (0, 16), (0, -16)):
            target = here[0] + dx, here[1] + dy
            if target in seen or not nav.walkable(map_id, *target):
                continue
            if math.dist(nav.trace(map_id, here, target), target) > 1e-7:
                continue
            seen.add(target)
            missing.discard(target)
            queue.append(target)
    assert not missing, f"Unreachable authored positions in {map_id}: {missing}"
    assert all(math.dist(a, b) >= 96 for i, a in enumerate(points) for b in points[i + 1:])
    # Portal and NPC footprints require clear ground around the standing point.
    for x, y in points[1:]:
        assert all(nav.walkable(map_id, x + dx, y + dy) for dx, dy in
                   ((12, 0), (-12, 0), (0, 12), (0, -12),
                    (8, 8), (8, -8), (-8, 8), (-8, -8)))


def test_most_campaign_art_is_explicit_cyber_or_machine_environment():
    # Circuit boards, machine pathways, the technological firewall and the
    # three digital rooms are the visual backbone. Other maps are archives
    # and crystal excavation passages used by the original Ghostline story.
    machine_maps = {f"xros_{number:03d}" for number in (
        51, 52, 54, 119, 152, 153, 154, 155, 156, 157, 160, 161,
        163, 164, 165, 175, 176, 177, 180, 182, 188)}
    assert len(set(CAMPAIGN_MAPS) & machine_maps) == 21
    assert len(machine_maps) > len(CAMPAIGN_MAPS) * 2 / 3
