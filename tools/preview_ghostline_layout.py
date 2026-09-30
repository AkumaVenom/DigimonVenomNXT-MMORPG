"""Validate and render the Ghostline campaign against shipped Xros artwork.

This never changes map art, masks, catalog metadata, or runtime placements.
Run from the repository root: python tools/preview_ghostline_layout.py
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from venom.common.xros_story_layout import CAMPAIGN_MAPS, PLACEMENTS
from venom.server.navigation import Navigation

SLOTS = ("Arrival", "Quest / guide", "Medic", "Shop", "Tamer / lab",
         "Boss / farm", "Return portal", "Intel / archive", "Forward portal")
COLORS = ("#ffffff", "#ffd874", "#6ee7b7", "#ffb67c", "#ff7798",
          "#ce96ff", "#74b8ff", "#81edfa", "#63ffbf")
LETTERS = "AQMSTBRIF"


def connected_routes(navigation, map_id, points):
    """Return exact collision-checked paths from arrival to every authored slot.

    White destination pixels alone cannot establish reachability: each edge
    uses the same supercover trace as authoritative player movement.
    """
    start = tuple(points[0])
    if not navigation.walkable(map_id, *start):
        raise ValueError(f"Blocked Ghostline arrival: {map_id}: {start}")
    required = set(map(tuple, points))
    queue = deque([start])
    parents = {start: None}
    missing = required - {start}
    while queue and missing:
        origin = queue.popleft()
        for dx, dy in ((16, 0), (-16, 0), (0, 16), (0, -16)):
            target = origin[0] + dx, origin[1] + dy
            if target in parents or not navigation.walkable(map_id, *target):
                continue
            if math.dist(navigation.trace(map_id, origin, target), target) > 1e-7:
                continue
            parents[target] = origin
            queue.append(target)
            missing.discard(target)
    if missing:
        raise ValueError(f"Unreachable Ghostline positions: {map_id}: {sorted(missing)}")
    routes = []
    for target in points:
        route, current = [], tuple(target)
        while current is not None:
            route.append(current)
            current = parents[current]
        routes.append(list(reversed(route)))
    return routes


def validate_layout(root=ROOT):
    catalog = json.loads((root / "data/catalog.json").read_text(encoding="utf-8"))
    maps = {row["id"]: row for row in catalog["maps"]}
    navigation = Navigation(root, maps)
    report = {"campaign": "Ghostline", "maps": [], "map_count": len(CAMPAIGN_MAPS),
              "slot_count": 0, "collision_method": "Navigation.trace on 16-unit cardinal lattice",
              "geometry_modified": False}
    routes_by_map = {}
    for index, map_id in enumerate(CAMPAIGN_MAPS, 1):
        area, points = maps[map_id], PLACEMENTS[map_id]
        if area["region_id"] != "xros_wars":
            raise ValueError(f"Ghostline map is outside Super Xros Wars: {map_id}")
        if tuple(area["spawn"]) != points[0]:
            raise ValueError(f"Public spawn changed for Ghostline map: {map_id}")
        routes = connected_routes(navigation, map_id, points)
        routes_by_map[map_id] = routes
        minimum = min(math.dist(a, b) for i, a in enumerate(points) for b in points[i + 1:])
        if minimum < 96:
            raise ValueError(f"Crowded Ghostline actors in {map_id}: {minimum}")
        # A foot-sized clear area keeps markers off ledges and ornaments.
        for point in points[1:]:
            for dx, dy in ((12, 0), (-12, 0), (0, 12), (0, -12),
                           (8, 8), (8, -8), (-8, 8), (-8, -8)):
                if not navigation.walkable(map_id, point[0] + dx, point[1] + dy):
                    raise ValueError(f"Insufficient clear floor in {map_id}: {point}")
        report["maps"].append({
            "chapter": index, "map_id": map_id, "public_name": area["name"],
            "art_sha256": hashlib.sha256((root / area["path"]).read_bytes()).hexdigest(),
            "mask_sha256": hashlib.sha256((root / area["walkable"]).read_bytes()).hexdigest(),
            "arrival": list(points[0]), "minimum_spacing": round(minimum, 3),
            "slots": [{"index": slot, "name": SLOTS[slot], "point": list(point),
                       "route_length": 16 * (len(routes[slot]) - 1)}
                      for slot, point in enumerate(points)],
        })
        report["slot_count"] += len(points)
    if len({row["art_sha256"] for row in report["maps"]}) != len(CAMPAIGN_MAPS):
        raise ValueError("Ghostline contains duplicate source map art")
    return maps, routes_by_map, report


def render(root=ROOT, output=None):
    output = output or root / "docs/validation/release_v140/layout"
    output.mkdir(parents=True, exist_ok=True)
    maps, routes, report = validate_layout(root)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
        small = ImageFont.truetype("DejaVuSans.ttf", 14)
    except OSError:
        font = small = ImageFont.load_default()
    panels = []
    for chapter, map_id in enumerate(CAMPAIGN_MAPS, 1):
        area = maps[map_id]
        source = Image.open(root / area["path"]).convert("RGB")
        scale = min(1024 / source.width, 640 / source.height)
        source = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.NEAREST)
        frame = Image.new("RGB", (1080, 760), "#101823")
        x0, y0 = (1080 - source.width) // 2, 68 + (640 - source.height) // 2
        frame.paste(source, (x0, y0))
        draw = ImageDraw.Draw(frame)
        draw.text((24, 12), f"MAP {chapter:02d}  |  {map_id}  |  {area['name']}", fill="#e7f4ff", font=font)
        draw.text((24, 38), "Reachable from unchanged arrival; supplied collision and art preserved", fill="#91a9be", font=small)
        # Show the actual collision route to the next chapter's gate.
        route = [(x0 + x * scale, y0 + y * scale) for x, y in routes[map_id][8]]
        draw.line(route, fill="#63ffbf", width=2)
        for slot, (x, y) in enumerate(PLACEMENTS[map_id]):
            xx, yy = round(x0 + x * scale), round(y0 + y * scale)
            draw.ellipse((xx - 12, yy - 12, xx + 12, yy + 12), fill="#071018", outline=COLORS[slot], width=3)
            draw.text((xx, yy), LETTERS[slot], anchor="mm", fill=COLORS[slot], font=small)
        draw.text((24, 724), "A arrival  Q quest  M medic  S shop  T tamer/lab  B boss/farm  R back  I intel  F onward", fill="#e7f4ff", font=small)
        frame.save(output / f"{chapter:02d}_{map_id}.png")
        panels.append(frame.resize((540, 380), Image.Resampling.LANCZOS))
    for offset in range(0, len(panels), 8):
        sheet = Image.new("RGB", (1080, 1520), "#101823")
        for index, panel in enumerate(panels[offset:offset + 8]):
            sheet.paste(panel, ((index % 2) * 540, (index // 2) * 380))
        sheet.save(output / f"contact_{offset + 1:02d}_{min(offset + 8, len(panels)):02d}.jpg", quality=94)
    (output / "collision_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Validated {report['map_count']} maps and {report['slot_count']} collision-connected slots; previews: {output}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    render(output=args.output)


if __name__ == "__main__":
    main()
