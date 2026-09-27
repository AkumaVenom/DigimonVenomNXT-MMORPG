"""Shared scene identity for authoritative world snapshots.

Map names identify shared fields across both regions. Private activities add
the owner's account key, so delayed frames cannot cross an activity boundary.
"""


def world_scope(state):
    battle = state.get("battle") or {}
    owner = str(state.get("username", "")).lower()
    if isinstance(state.get("admin_jail"), dict):
        space = "jail"
    elif state.get("in_season") or battle.get("kind") == "season" or battle.get("season"):
        space = "season"
    elif state.get("in_story") or battle.get("kind") == "story":
        space = "story"
    elif state.get("in_farm"):
        space = "farm"
    else:
        space, owner = ("lab" if state.get("in_lab") else "field"), None
    return [state.get("map_id"), space, owner]


def snapshot_matches(state, message):
    if not state:
        return False
    expected = world_scope(state)
    if "scope" in message:
        return message["scope"] == expected
    # Older compatible servers have no envelope. Their own-player row still
    # identifies the scene; never infer ownership from another player's row.
    own = next((row for row in message.get("players", [])
                if row.get("username") == state.get("username")), None)
    if own is None:
        return False
    if own.get("in_jail"):
        own = {**own, "admin_jail": {}}
    return world_scope(own) == expected
