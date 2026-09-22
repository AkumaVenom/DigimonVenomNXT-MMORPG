"""Cheap, deterministic, collision-checked walking for server-controlled tamers.

Only a path's endpoints and start time are retained. A path is checked against
every source collision pixel once, then all spectators sample the same line.
This avoids 5,000 independent physics loops or client-side random movement.
"""
from __future__ import annotations

import math
import random
import bisect
from pathlib import Path


class Navigation:
    SPEED = 180.0  # Same world units / second as a human tamer.

    def __init__(self, root: Path, maps: dict):
        self.root, self.maps = Path(root), maps
        self.masks = {}
        self.spawn_points = {}
        self.edges = {}

    def _mask(self, map_id):
        if map_id not in self.masks:
            area = self.maps[map_id]
            path = area.get("walkable")
            if not path:
                self.masks[map_id] = None
            else:
                from PIL import Image
                with Image.open(self.root / path) as source:
                    mask = source.convert("1", dither=Image.Dither.NONE)
                    self.masks[map_id] = (mask.width, mask.height,
                                          (mask.width + 7) // 8, mask.tobytes())
        return self.masks[map_id]

    def walkable(self, map_id, x, y):
        area = self.maps[map_id]
        if not (12 <= x <= area["width"] - 12 and 12 <= y <= area["height"] - 12):
            return False
        mask = self._mask(map_id)
        if mask is None:
            return True
        width, height, stride, data = mask
        px = min(width - 1, int(x * width / area["width"]))
        py = min(height - 1, int(y * height / area["height"]))
        return bool(data[py * stride + (px >> 3)] & (0x80 >> (px & 7)))

    def trace(self, map_id, start, target):
        """Exact grid-DDA supercover, including both cells at diagonal corners.

        Fixed-distance samples can miss a sliver of a blocked pixel. This walks
        every crossed collision cell and stops just inside the final safe cell.
        """
        x, y = map(float, start)
        tx, ty = map(float, target)
        area = self.maps[map_id]
        if not self.walkable(map_id, x, y):
            return x, y
        dx, dy = tx - x, ty - y
        # Trigonometric near-zero components can round back onto the opposite
        # pixel boundary when interpolated. Normalize sub-nanopixel movement.
        dx = 0.0 if abs(dx) < 1e-9 else dx
        dy = 0.0 if abs(dy) < 1e-9 else dy
        limit = 1.0
        for position, delta, maximum in ((x, dx, area["width"] - 12), (y, dy, area["height"] - 12)):
            if delta > 0:
                limit = min(limit, (maximum - position) / delta)
            elif delta < 0:
                limit = min(limit, (12 - position) / delta)
        dx, dy = dx * max(0, limit), dy * max(0, limit)
        mask = self._mask(map_id)
        if mask is None or max(abs(dx), abs(dy)) < 1e-9:
            return x + dx, y + dy
        width, height, stride, data = mask
        sx, sy = x * width / area["width"], y * height / area["height"]
        vx, vy = dx * width / area["width"], dy * height / area["height"]
        cell_x, cell_y = math.floor(sx), math.floor(sy)
        step_x = 1 if vx > 0 else -1
        step_y = 1 if vy > 0 else -1
        delta_x = abs(1 / vx) if vx else math.inf
        delta_y = abs(1 / vy) if vy else math.inf
        cross_x = ((cell_x + 1 - sx) / vx if vx > 0 else (cell_x - sx) / vx) if vx else math.inf
        cross_y = ((cell_y + 1 - sy) / vy if vy > 0 else (cell_y - sy) / vy) if vy else math.inf

        def free(cx, cy):
            return (0 <= cx < width and 0 <= cy < height
                    and bool(data[cy * stride + (cx >> 3)] & (0x80 >> (cx & 7))))

        epsilon = 1e-5 / max(1, abs(dx), abs(dy))
        while min(cross_x, cross_y) <= 1:
            crossing = min(cross_x, cross_y)
            crosses_x = cross_x <= crossing + 1e-12
            crosses_y = cross_y <= crossing + 1e-12
            nx = cell_x + step_x if crosses_x else cell_x
            ny = cell_y + step_y if crosses_y else cell_y
            # Supercover: require both side cells when a diagonal touches a
            # corner, so reversed edges are safe too despite float rounding.
            clear = free(nx, ny)
            if crosses_x and crosses_y:
                clear = clear and free(nx, cell_y) and free(cell_x, ny)
            if not clear:
                fraction = max(0.0, crossing - epsilon)
                return x + dx * fraction, y + dy * fraction
            cell_x, cell_y = nx, ny
            if crosses_x:
                cross_x += delta_x
            if crosses_y:
                cross_y += delta_y
        return (min(area["width"] - 12, max(12, x + dx)),
                min(area["height"] - 12, max(12, y + dy)))

    def plan(self, map_id, x, y, rng: random.Random):
        # Eight headings match the imported eight-direction NDS animations.
        headings = list(range(8))
        rng.shuffle(headings)
        best, distance = (float(x), float(y)), 0.0
        for heading in headings:
            unit_x, unit_y = ((1, 0), (1, 1), (0, 1), (-1, 1),
                              (-1, 0), (-1, -1), (0, -1), (1, -1))[heading]
            magnitude = math.hypot(unit_x, unit_y)
            length = rng.uniform(72, 260)
            target = (x + unit_x * length / magnitude, y + unit_y * length / magnitude)
            point = self.trace(map_id, (x, y), target)
            travel = math.dist((x, y), point)
            if travel > distance:
                best, distance = point, travel
            if travel >= 48:
                break
        return best if distance >= 2 else None

    def spawn(self, map_id, ordinal=0):
        """Spread first appearances along a connected, validated walkable cloud."""
        if map_id not in self.spawn_points:
            area = self.maps[map_id]
            start = tuple(map(float, area.get("spawn", [area["width"] / 2, area["height"] / 2])))
            if not self.walkable(map_id, *start):
                raise ValueError(f"Rival spawn is blocked in {map_id}; verify collision assets.")
            # Stable across process restarts; Python's salted hash is not used.
            rng = random.Random("venom-rival-spawn:" + map_id)
            points = [start]
            edges = {0: []}
            for index in range(32):
                origin_index = len(points) - 1 if index % 8 else 0
                origin = points[origin_index]
                target = self.plan(map_id, *origin, rng)
                if target:
                    target_index = len(points)
                    points.append(target)
                    edges.setdefault(origin_index, []).append(target_index)
                    edges[target_index] = [origin_index]
            self.spawn_points[map_id] = points
            self.edges[map_id] = edges
        points = self.spawn_points[map_id]
        return points[ordinal % len(points)]

    def route(self, map_id, x, y, rng, now, seconds=12):
        """Chain cached safe edges into one long, continuous authoritative route.

        Pixel checks are shared per map instead of repeated 5,000 times every
        half-second. A resumed mid-edge position connects through a verified line.
        Sampling still returns the exact current heading at every corner.
        """
        self.spawn(map_id)
        points, edges = self.spawn_points[map_id], self.edges[map_id]
        start = (float(x), float(y))
        nearest = sorted(range(len(points)), key=lambda index: math.dist(start, points[index]))
        anchor = None
        for index in nearest:
            target = points[index]
            if math.dist(start, target) < .01 or math.dist(self.trace(map_id, start, target), target) < .01:
                anchor = index
                break
        if anchor is None:
            target = self.plan(map_id, x, y, rng)
            if target is None:
                return None
            distance = math.dist(start, target)
            return {"from": start, "to": target, "start": now, "end": now + distance / self.SPEED}
        segments = []
        clock = now
        current, previous = start, None

        def append(target):
            nonlocal clock, current
            distance = math.dist(current, target)
            if distance < .01:
                return
            end = clock + distance / self.SPEED
            segments.append({"from": current, "to": target, "start": clock, "end": end})
            clock, current = end, target

        append(points[anchor])
        for _ in range(120):
            if clock >= now + seconds:
                break
            options = [index for index in edges[anchor] if index != previous] or edges[anchor]
            if not options:
                break
            target_index = rng.choice(options)
            append(points[target_index])
            previous, anchor = anchor, target_index
        if not segments:
            return None
        return {"from": start, "to": current, "start": now, "end": clock,
                "segments": segments, "ends": [segment["end"] for segment in segments]}

    @staticmethod
    def sample(path, now):
        if not path:
            return None
        if "segments" in path:
            index = min(len(path["segments"]) - 1, bisect.bisect_right(path["ends"], now))
            return Navigation.sample(path["segments"][index], now)
        start, end = path["from"], path["to"]
        duration = path["end"] - path["start"]
        fraction = max(0.0, min(1.0, (now - path["start"]) / max(.001, duration)))
        x = start[0] + (end[0] - start[0]) * fraction
        y = start[1] + (end[1] - start[1]) * fraction
        distance = math.dist(start, end)
        moving = fraction < 1 and distance > 0
        dx = (end[0] - start[0]) / distance if moving else 0.0
        dy = (end[1] - start[1]) / distance if moving else 0.0
        return x, y, dx, dy
