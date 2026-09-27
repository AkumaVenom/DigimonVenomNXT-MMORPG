"""Persistent moderation state, separate from fictional Season calendar time."""
from __future__ import annotations

import copy
import math
import time

from venom.server.navigation import Navigation


# Preserve field presence as well as values: a jail visit must not rewrite an
# interrupted Season battle, private farm position, or return destination.
SUSPENDED_FIELDS = (
    "map_id", "x", "y", "in_lab", "in_farm", "in_season", "in_story", "farm_position",
    "return_location", "battle",
)


def is_jailed(state):
    return isinstance(state.get("admin_jail"), dict)


def jail_expired(state, now=None):
    jail = state.get("admin_jail")
    if not isinstance(jail, dict):
        return False
    until = jail.get("until")
    return until is not None and float(until) <= (time.time() if now is None else now)


def jail_state(engine, state, until, reason):
    """Suspend all activity and place this tamer in their private holding cell."""
    if until is not None:
        if isinstance(until, bool) or not isinstance(until, (int, float)) or not math.isfinite(until):
            raise ValueError("Jail expiry must be a finite real timestamp or permanent.")
        until = float(until)
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 240 or not all(c.isprintable() for c in reason):
        raise ValueError("A jail reason must contain 1–240 printable characters.")
    maps = getattr(engine, "maps", {})
    if not maps:
        raise ValueError("No safe holding-cell map is available.")
    navigation = Navigation(getattr(engine, "root", "."), maps)
    cell = None
    for area in sorted(maps.values(), key=lambda m: (int(m.get("level", 1)), m["id"])):
        try:
            x, y = area.get("spawn", [area.get("width", 1024) / 2, area.get("height", 768) / 2])
            if math.isfinite(x) and math.isfinite(y) and navigation.walkable(area["id"], x, y):
                cell = (area["id"], float(x), float(y))
                break
        except (ValueError, TypeError, OSError):
            continue
    if cell is None:
        raise ValueError("No safe holding-cell spawn is available; verify the server maps.")
    previous = state.get("admin_jail")
    if isinstance(previous, dict):
        suspended = copy.deepcopy(previous["suspended"])
    else:
        suspended = {name: {"present": name in state, "value": copy.deepcopy(state.get(name))}
                     for name in SUSPENDED_FIELDS}
    state["admin_jail"] = {"until": until, "reason": reason.strip(), "issued_at": time.time(),
                           "suspended": suspended}
    state.update(map_id=cell[0], x=cell[1], y=cell[2], battle=None,
                 in_season=False, in_story=False, in_lab=False, in_farm=False)
    state["events"] = []
    return state


def clear_jail(state):
    """Resume the exact suspended activity without advancing a career or turn."""
    jail = state.get("admin_jail")
    if not isinstance(jail, dict):
        return False
    suspended = jail.get("suspended")
    # v0.8 holding cells predate Story Mode. Missing only the new flag means
    # that the original activity had no Story state; other missing fields still
    # indicate a damaged return snapshot and must not be guessed.
    if not isinstance(suspended, dict) or any(not isinstance(suspended.get(key), dict)
            for key in SUSPENDED_FIELDS if key != "in_story"):
        raise ValueError("The saved holding-cell return state is incomplete; administrator repair is required.")
    if "in_story" in suspended and not isinstance(suspended["in_story"], dict):
        raise ValueError("The saved holding-cell return state is incomplete; administrator repair is required.")
    for name in SUSPENDED_FIELDS:
        original = suspended.get(name, {"present": False})
        if original.get("present"):
            state[name] = copy.deepcopy(original.get("value"))
        else:
            state.pop(name, None)
    state.pop("admin_jail", None)
    state["events"] = []
    return True
