"""Client prediction and presentation; the dedicated server still owns movement."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MoveInput:
    dx: float
    dy: float
    dt: float

    def payload(self):
        return {'dx': self.dx, 'dy': self.dy, 'dt': self.dt}


def move_position(position, movement, entry, mask=None, speed=180.0):
    """Use the server's bounds, mask coordinates and per-pixel wall sliding."""
    x, y = float(position[0]), float(position[1])
    width, height = entry.get('width', 1536), entry.get('height', 768)
    dx, dy = movement.dx, movement.dy
    length = math.hypot(dx, dy)
    if length > 1:
        dx, dy = dx / length, dy / length
    target_x = min(max(12, x + dx * speed * movement.dt), max(12, width - 12))
    target_y = min(max(12, y + dy * speed * movement.dt), max(12, height - 12))
    steps = max(1, math.ceil(max(abs(target_x - x), abs(target_y - y))))
    step_x, step_y = (target_x - x) / steps, (target_y - y) / steps

    def walkable(px, py):
        if mask is None:
            return True
        mx = max(0, min(mask.get_width() - 1, int(px * mask.get_width() / width)))
        my = max(0, min(mask.get_height() - 1, int(py * mask.get_height() / height)))
        return mask.get_at((mx, my)).r >= 128

    for _ in range(steps):
        if walkable(x + step_x, y):
            x += step_x
        if walkable(x, y + step_y):
            y += step_y
    return x, y


class MovementPredictor:
    """Replay input newer than an acknowledgement instead of snapping one RTT back."""
    def __init__(self):
        self.pending = {}
        self.buffer = []
        self.transition_pending = None
        self.last_direction = (0.0, 0.0)

    @property
    def buffered_time(self):
        return sum(item.dt for item in self.buffer)

    def reset(self):
        self.pending.clear()
        self.buffer.clear()
        self.transition_pending = None
        self.last_direction = (0.0, 0.0)

    def advance(self, position, dx, dy, dt, entry, mask=None):
        movement = MoveInput(float(dx), float(dy), min(.1, max(0.0, dt)))
        if self.buffer and (self.buffer[-1].dx, self.buffer[-1].dy) == (dx, dy) and self.buffer[-1].dt + movement.dt <= .1:
            previous = self.buffer.pop()
            self.buffer.append(MoveInput(movement.dx, movement.dy, previous.dt + movement.dt))
        else:
            self.buffer.append(movement)
        return move_position(position, movement, entry, mask)

    def take_buffer(self):
        buffered, self.buffer = self.buffer, []
        return buffered

    def track(self, rid, payload):
        self.pending[rid] = MoveInput(float(payload.get('dx', 0)), float(payload.get('dy', 0)), float(payload.get('dt', 0)))
        # Bound memory if a connection stalls before its transport timeout.
        while len(self.pending) > 256:
            del self.pending[next(iter(self.pending))]

    def reconcile(self, rid, authoritative, entry, mask=None, reset=False):
        if reset:
            self.reset()
            return float(authoritative[0]), float(authoritative[1])
        if isinstance(rid, int):
            for pending_rid in tuple(self.pending):
                if pending_rid <= rid:
                    del self.pending[pending_rid]
        position = authoritative
        for movement in (*self.pending.values(), *self.buffer):
            position = move_position(position, movement, entry, mask)
        return float(position[0]), float(position[1])


class RemoteMotion:
    """Render 10 Hz world snapshots on a short interpolation timeline."""
    def __init__(self, delay=.1):
        self.delay = delay
        self.samples = {}

    def push(self, now, players):
        for name in tuple(self.samples):
            if name not in players:
                del self.samples[name]
        for name, player in players.items():
            point = (float(player.get('x', 0)), float(player.get('y', 0)))
            sample = (now, point, player.get('map_id'), float(player.get('dx', 0)), float(player.get('dy', 0)))
            history = self.samples.setdefault(name, deque(maxlen=16))
            # Map travel and large discontinuities must not sweep across the scene.
            if history and (history[-1][2] != sample[2] or math.dist(history[-1][1], point) > 180):
                history.clear()
            if history and now <= history[-1][0]:
                history[-1] = sample
            else:
                history.append(sample)

    def positions(self, now):
        target_time = now - self.delay
        result = {}
        for name, history in self.samples.items():
            while len(history) > 2 and history[1][0] <= target_time:
                history.popleft()
            first, last = history[0], history[-1]
            if target_time <= first[0]:
                result[name] = first[1]
                continue
            for left, right in zip(history, tuple(history)[1:]):
                if left[0] <= target_time <= right[0]:
                    alpha = (target_time - left[0]) / max(.000001, right[0] - left[0])
                    result[name] = tuple(a + (b - a) * alpha for a, b in zip(left[1], right[1]))
                    break
            else:
                # A small amount of bounded extrapolation absorbs one jittery tick;
                # never let missing packets send another player walking indefinitely.
                extra = min(.05, max(0, target_time - last[0]))
                length = max(1.0, math.hypot(last[3], last[4]))
                result[name] = (last[1][0] + last[3] / length * 180 * extra,
                                last[1][1] + last[4] / length * 180 * extra)
        return result
