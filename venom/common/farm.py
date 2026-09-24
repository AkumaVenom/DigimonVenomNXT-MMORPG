"""Shared DigiFarm coordinates and movement for prediction and authority.

Positions use the supplied island artwork's native pixel coordinates. The inset
shore follows the grass, keeping feet away from the cliffs and digital water.
This is independent of a tamer's saved field location and needs no image loader.
"""
from __future__ import annotations

import math


FARM_WIDTH = 1672
FARM_HEIGHT = 941
FARM_SPAWN = (836.0, 470.0)
FARM_ENTRY = {"id": "digifarm", "width": FARM_WIDTH, "height": FARM_HEIGHT}
FARM_DIRECTIONS = frozenset(("up", "down", "left", "right", "up_left", "up_right",
                             "down_left", "down_right"))

# Clockwise, just inside the grass lip. Keep this in image/world coordinates so
# resize, letterboxing and the tamer's camera never change authoritative bounds.
FARM_SHORE = (
    (117, 282), (135, 247), (180, 207), (205, 185), (236, 167),
    (287, 155), (323, 145), (365, 151), (409, 147), (456, 124),
    (516, 121), (558, 112), (603, 123), (651, 114), (682, 109),
    (728, 127), (775, 138), (832, 146), (887, 150), (933, 139),
    (975, 116), (1025, 125), (1084, 130), (1138, 148), (1201, 151),
    (1262, 160), (1318, 173), (1377, 197), (1417, 212), (1449, 244),
    (1480, 255), (1500, 277), (1534, 292), (1524, 310), (1501, 327),
    (1498, 356), (1495, 379), (1511, 397), (1549, 415), (1585, 438),
    (1608, 466), (1594, 480), (1554, 493), (1537, 518), (1524, 556),
    (1492, 589), (1463, 626), (1439, 653), (1404, 676), (1367, 699),
    (1329, 709), (1277, 699), (1244, 706), (1197, 727), (1162, 747),
    (1126, 753), (1088, 743), (1051, 720), (1013, 709), (968, 698),
    (918, 680), (866, 672), (810, 679), (756, 687), (699, 683),
    (637, 681), (589, 689), (538, 691), (496, 707), (462, 737),
    (423, 754), (389, 756), (354, 737), (330, 711), (308, 696),
    (279, 672), (247, 651), (213, 632), (181, 609), (143, 602),
    (101, 584), (79, 564), (69, 545), (92, 513), (119, 489),
    (147, 464), (166, 437), (180, 405), (190, 382), (175, 359),
    (166, 337), (131, 308),
)


def _finite_number(value):
    try:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        return False


def farm_walkable(x, y):
    """Whether a character's feet are on safe grass, never the water or cliff."""
    if not (_finite_number(x) and _finite_number(y)):
        return False
    if not (0 <= x < FARM_WIDTH and 0 <= y < FARM_HEIGHT):
        return False
    inside = False
    ax, ay = FARM_SHORE[-1]
    for bx, by in FARM_SHORE:
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
        ax, ay = bx, by
    return inside


def normalize_farm_position(state):
    """Add/migrate home coordinates without touching the saved field or return."""
    saved = state.get("farm_position")
    if not isinstance(saved, dict) or not farm_walkable(saved.get("x"), saved.get("y")):
        position = {"x": FARM_SPAWN[0], "y": FARM_SPAWN[1], "direction": "down"}
    else:
        direction = saved.get("direction")
        position = {"x": float(saved["x"]), "y": float(saved["y"]),
                    "direction": direction if isinstance(direction, str) and direction in FARM_DIRECTIONS else "down"}
    state["farm_position"] = position
    return position


def move_farm_position(position, dx, dy, dt, speed=180.0):
    """Match normal map speed, diagonal normalization and per-pixel wall sliding."""
    if not all(_finite_number(value) for value in (dx, dy, dt, speed)):
        raise ValueError("Movement must contain finite numbers.")
    if abs(dx) > 1 or abs(dy) > 1 or not 0 <= dt <= .1 or not 0 <= speed <= 1000:
        raise ValueError("Movement input is out of bounds.")
    x, y = position
    if not farm_walkable(x, y):
        raise ValueError("DigiFarm movement must start on safe grass.")
    x, y = float(x), float(y)
    length = math.hypot(dx, dy)
    if length > 1:
        dx, dy = dx / length, dy / length
    distance_x, distance_y = dx * speed * dt, dy * speed * dt
    steps = max(1, math.ceil(max(abs(distance_x), abs(distance_y))))
    step_x, step_y = distance_x / steps, distance_y / steps
    for _ in range(steps):
        if step_x and farm_walkable(x + step_x, y):
            x += step_x
        if step_y and farm_walkable(x, y + step_y):
            y += step_y
    return x, y
