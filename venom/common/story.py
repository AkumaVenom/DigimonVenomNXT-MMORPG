"""Private, action-driven story campaigns using real character systems.

Partners, inventory, credits, scan data and progression remain on the character.
Each campaign owns its itinerary, NPC clears, badges and finale. The module
never reads a real clock, another account, or a client-supplied battle result.
"""
from __future__ import annotations

import copy
import math
import uuid

from venom.common import story_content

TALK_RADIUS = 128
HISTORY_LIMIT = 30
MAX_CREDITS = 2 ** 53 - 1
LOCATION_FIELDS = ("map_id", "x", "y", "in_lab", "in_farm", "return_location", "farm_position")
DAWN_CAMPAIGN = "dawn_relay"
DS_CAMPAIGN = "world_ds_paradox"
CAMPAIGN_IDS = (DAWN_CAMPAIGN, DS_CAMPAIGN)


class StoryError(ValueError):
    """A safe, player-readable campaign rejection."""


def content(engine, campaign_id=DAWN_CAMPAIGN):
    if campaign_id not in CAMPAIGN_IDS:
        raise StoryError("Choose Dawn Relay or World DS: Paradox Chronicle.")
    if campaign_id == DS_CAMPAIGN:
        from venom.common import world_ds_story_content
        cached = getattr(engine, "_world_ds_story_content", None)
        if cached is None:
            cached = world_ds_story_content.build_content(engine)
            engine._world_ds_story_content = cached
        return cached
    cached = getattr(engine, "_story_content", None)
    if cached is None:
        cached = story_content.build_content(engine)
        engine._story_content = cached
    return cached


def _campaign(profile):
    return profile.get("campaign_id", DAWN_CAMPAIGN)


def _data(engine, profile):
    return content(engine, _campaign(profile))


def _is_ds(profile):
    return _campaign(profile) == DS_CAMPAIGN


def _badges(data):
    return [row["badge"]["id"] for row in _regions(data) if row.get("badge")]


def _snapshot(state):
    saved = {key: copy.deepcopy(state[key]) for key in LOCATION_FIELDS if key in state}
    saved["_absent"] = [key for key in LOCATION_FIELDS if key not in state]
    return saved


def _restore(state, saved):
    for key in LOCATION_FIELDS:
        if key in saved:
            state[key] = copy.deepcopy(saved[key])
        elif key in saved.get("_absent", []):
            state.pop(key, None)


def _regions(data):
    return data["regions"]


def _all_npcs(data):
    return {**data["npcs"], **{row["id"]: row for row in data.get("challengers", [])}}


def _champion_npc(profile, data):
    champion = profile["champion"]
    challengers = data.get("challengers", [])
    if not champion["first_victory"] or not challengers:
        return data["npcs"][data["champion_id"]]
    if champion["status"] == "reclaim":
        return _all_npcs(data).get(champion["holder_id"], data["npcs"][data["champion_id"]])
    return challengers[champion["matches"] % len(challengers)]


def _visible_npcs(profile, data, map_id):
    rows = []
    for npc in data["npcs"].values():
        if npc["id"] == data["champion_id"]:
            npc = _champion_npc(profile, data)
        if npc["map_id"] == map_id:
            rows.append(npc)
    return rows


def _ready(profile, npc):
    return (all(ident in profile["completed"] for ident in npc.get("requires", []))
            and all(ident in profile.get("quest_accepted", []) for ident in npc.get("requires_accepted", [])))


def _status(profile, npc):
    if npc.get("role") in ("mentor", "healer", "shop", "lab", "farm"):
        return "service"
    if not _ready(profile, npc):
        return "locked"
    if npc.get("role") == "quest" and npc["id"] not in profile["completed"]:
        if npc["id"] not in profile.get("quest_accepted", []):
            return "ready"
        return "turn_in" if all(ident in profile["completed"] for ident in npc.get("quest_requires", [])) else "active"
    if npc.get("role") == "final" and profile["champion"]["first_victory"]:
        return "complete"
    if npc.get("role") == "champion" and profile["champion"]["first_victory"]:
        return profile["champion"]["status"]
    return "complete" if npc["id"] in profile["completed"] else "ready"


def _region_for_map(data, map_id):
    return next((region for region in _regions(data) if map_id in region["maps"]), _regions(data)[0])


def _available_region(profile, index, data=None):
    if _is_ds(profile):
        # The safe hub and the first field are available immediately. An exact
        # prefix of earned crests, rather than a count, opens each later field.
        if index <= 1:
            return True
        return data is not None and all(ident in profile["badges"] for ident in _badges(data)[:index - 1])
    return index <= len(profile["badges"])


def _objective(profile, data, region):
    if _is_ds(profile):
        if profile["champion"]["first_victory"]:
            return "Paradox Chronicle complete. Permanent +20% Paradox scan gain is active on wild battle victories. Revisit any field or return to the world."
        if region["index"] == 0:
            return f"Welcome to {region['name']}. Meet your guides, prepare at the DigiLab, and travel to {_regions(data)[1]['name']} when ready. This hub has no battles."
        for ident in region.get("npc_ids", []):
            npc = data["npcs"].get(ident)
            if not npc or ident in profile["completed"] or not _ready(profile, npc):
                continue
            if npc.get("role") == "quest":
                status = _status(profile, npc)
                if status == "ready":
                    return f"Speak to {npc['name']} to accept {npc.get('quest_title', 'the local assignment')}."
                if status == "turn_in":
                    return f"Return to {npc['name']} to complete the assignment and reveal the Paradox guardian."
            elif npc.get("role") == "trainer":
                return f"Defeat {npc['name']} in a story tamer battle, then report back to the quest giver."
            elif npc.get("role") == "warden":
                return f"Defeat {npc['name']} to earn this field's Paradox Crest."
            elif npc.get("role") == "final":
                return "All 17 Paradox Crests are secured. Speak to the final summoner to face three level 100 Paradox Megas."
        if region.get("badge", {}).get("id") in profile["badges"]:
            if region["index"] + 1 < len(_regions(data)):
                return f"Paradox Crest secured. Travel to {_regions(data)[region['index'] + 1]['name']} when ready."
        return "Speak to the local quest giver, prepare your partners, and follow the assignment in your Story journal."
    if region["index"] == 8 and profile["champion"]["first_victory"]:
        npc = _champion_npc(profile, data)
        if profile["champion"]["status"] == "reclaim":
            return f"Challenge {npc['name']} at the Citadel to reclaim your championship."
        return f"Defend your championship against {npc['name']} at the Citadel."
    for ident in region.get("npc_ids", []):
        npc = data["npcs"].get(ident)
        if npc and npc.get("role") in ("trainer", "warden", "champion") and ident not in profile["completed"] and _ready(profile, npc):
            return f"Meet {npc['name']} in {data['maps'][npc['map_id']]['name']}."
    if region["index"] < 8 and len(profile["badges"]) > region["index"]:
        return f"DigiBadge secured. Travel to {_regions(data)[region['index'] + 1]['name']} when ready."
    return "Explore the region, speak with its tamers, and prepare your partners at the DigiLab."


def _choices(profile, npc, dialogue):
    if dialogue["page"] + 1 < len(dialogue["lines"]):
        return [{"id": "next", "label": "Continue"}, {"id": "leave", "label": "Speak later"}]
    if dialogue.get("result_only"):
        return [{"id": "leave", "label": "Continue the journey"}]
    choices = []
    role = npc.get("role")
    if role == "quest" and _ready(profile, npc):
        status = _status(profile, npc)
        if status == "ready":
            choices.append({"id": "accept_quest", "label": "Accept assignment"})
        elif status == "turn_in":
            choices.append({"id": "complete_quest", "label": "Complete assignment"})
    if role in ("trainer", "warden", "champion", "final") and _ready(profile, npc):
        label = "Challenge"
        if role == "final":
            label = "Replay final battle" if profile["champion"]["first_victory"] else f"Summon {npc.get('battle_name', 'final trio')} · Lv. 100"
        elif role == "champion" and profile["champion"]["first_victory"]:
            label = "Reclaim the title" if profile["champion"]["status"] == "reclaim" else "Defend the title"
        elif npc["id"] in profile["completed"]:
            label = "Friendly rematch"
        choices.append({"id": "challenge", "label": label})
    if role in ("healer", "mentor"):
        choices.append({"id": "heal", "label": "Recover partners"})
    if role in ("shop", "lab"):
        choices.append({"id": "camp", "label": "Visit DigiLab & shop"})
    if role == "farm":
        choices.append({"id": "farm", "label": "Visit DigiFarm"})
    choices.append({"id": "leave", "label": "Back to exploring"})
    return choices


def update_view(engine, state):
    profile = state.get("story")
    if not profile or not profile.get("started"):
        return
    profile.setdefault("campaign_id", DAWN_CAMPAIGN)
    profile.setdefault("quest_accepted", [])
    data = _data(engine, profile)
    # A jailed character temporarily has in_story=False; never move its itinerary.
    if state.get("in_story") and not state.get("in_lab") and not state.get("in_farm"):
        profile["location"] = {key: copy.deepcopy(state[key]) for key in ("map_id", "x", "y")}
    location = profile["location"]
    region = _region_for_map(data, location["map_id"])
    profile["chapter"] = region["index"]
    badges, chapters = [], []
    for row in _regions(data):
        badge = row.get("badge")
        if badge:
            badges.append({**copy.deepcopy(badge), "earned": badge["id"] in profile["badges"], "chapter": row["index"]})
        chapters.append({"index": row["index"], "name": row["name"], "subtitle": row.get("subtitle", ""),
                         "synopsis": row.get("synopsis", ""), "map_id": row["maps"][0],
                         "level": row.get("level_min", 1), "level_min": row.get("level_min", 1),
                         "level_max": row.get("level_max", 5), "unlocked": _available_region(profile, row["index"], data),
                         "complete": bool(badge and badge["id"] in profile["badges"]),
                         "maps": [{"id": ident, "name": data["maps"][ident]["name"], "active": ident == location["map_id"],
                                   "unlocked": _available_region(profile, row["index"], data)} for ident in row["maps"]]})
    npcs = [{key: copy.deepcopy(npc.get(key)) for key in ("id", "map_id", "name", "tamer_id", "role", "x", "y", "display_species", "display_level", "quest_title")}
            | {"status": _status(profile, npc), "level": max((partner["level"] for partner in npc.get("team", [])), default=0)}
            for npc in _visible_npcs(profile, data, location["map_id"])]
    dialogue = profile.get("dialogue")
    dialogue_view = None
    if dialogue:
        npc = _all_npcs(data)[dialogue["npc_id"]]
        page = dialogue["page"]
        dialogue_view = {"npc_id": npc["id"], "name": npc["name"], "tamer_id": npc.get("tamer_id", npc.get("tamer")),
                         "display_species": npc.get("display_species"), "display_level": npc.get("display_level"),
                         "text": dialogue["lines"][page], "page": page + 1, "pages": len(dialogue["lines"]),
                         "token": dialogue["token"], "choices": _choices(profile, npc, dialogue),
                         "result_only": bool(dialogue.get("result_only")), "result": copy.deepcopy(dialogue.get("result"))}
    objective = _objective(profile, data, region)
    training_available = not (_is_ds(profile) and region["index"] == 0)
    if training_available and state.get("party") and max(monster["level"] for monster in state["party"][:3]) < region.get("level_min", 1):
        objective += " Field training and free recovery are available in your Story journal."
    exits = [{**copy.deepcopy(row), "map_id": location["map_id"], "chapter": _region_for_map(data, row["to_map"])["index"],
              "unlocked": _available_region(profile, _region_for_map(data, row["to_map"])["index"], data) and
              (not row.get("requires_badge") or row["requires_badge"] in profile["badges"])}
             for row in data["maps"][location["map_id"]].get("exits", [])]
    final = data["npcs"][data["champion_id"]]
    profile["view"] = {"title": data.get("name", "Dawn Relay"), "started": True, "campaign_id": _campaign(profile),
                       "chapter": region["index"], "chapter_name": region["name"], "map_name": data["maps"][location["map_id"]]["name"],
                       "map_id": location["map_id"], "objective": objective, "exits": exits,
                       "synopsis": region.get("synopsis", ""), "badges": badges, "badge_count": len(profile["badges"]),
                       "badge_total": len(_badges(data)), "badge_name": "Paradox Crest" if _is_ds(profile) else "DigiBadge",
                       "hub": not training_available, "training_available": training_available,
                       "completed": bool(profile["champion"]["first_victory"]),
                       "scan_bonus": 20 if state.get("permanent_rewards", {}).get("paradox_scan_mastery") else 0,
                       "final_npc_id": final["id"], "final_map_id": final["map_id"], "final_name": final["name"],
                       "final_team": [{"species_id": partner["species"], "name": engine.species[partner["species"]]["name"],
                                       "level": partner["level"], "stage": engine.species[partner["species"]].get("stage", "")}
                                      for partner in final.get("team", [])],
                       "chapters": chapters, "npcs": npcs, "dialogue": dialogue_view,
                       "champion": copy.deepcopy(profile["champion"]), "stats": copy.deepcopy(profile["stats"]),
                       "recent": copy.deepcopy(profile["recent"]), "talk_radius": TALK_RADIUS,
                       "training_level": max(1, region.get("level_min", 1)), "can_return": not state.get("battle"),
                       "shared_partners": True, "shared_rewards": True}


def _nearby(state, npc):
    if state.get("in_lab") or state.get("in_farm") or state.get("map_id") != npc["map_id"]:
        raise StoryError("Meet this tamer on their Story map first.")
    if math.hypot(float(state["x"]) - npc["x"], float(state["y"]) - npc["y"]) > TALK_RADIUS:
        raise StoryError("Walk closer to this tamer to speak with them.")


def _npc(state, data, ident):
    if not isinstance(ident, str):
        raise StoryError("Choose a Story tamer.")
    npc = next((row for row in _visible_npcs(state["story"], data, state["map_id"]) if row["id"] == ident), None)
    if not npc:
        raise StoryError("This Story tamer is not in your current region.")
    _nearby(state, npc)
    return npc


def _heal(engine, state):
    for monster in state["party"]:
        monster["hp"], monster["sp"] = monster["max_hp"], monster["max_sp"]
        monster.pop("guard", None)
    engine._event(state, "heal", text="Story recovery restored every partner's HP and SP. No credits charged.")


def _travel(engine, state, data, index, map_id=None):
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(_regions(data)):
        raise StoryError("Choose a valid Story chapter.")
    if not _available_region(state["story"], index, data):
        raise StoryError("Earn the preceding Paradox Crests before entering this chapter." if _is_ds(state["story"]) else "Earn the preceding DigiBadges before entering this chapter.")
    region = _regions(data)[index]
    map_id = map_id or region["maps"][0]
    if not isinstance(map_id, str) or map_id not in region["maps"]:
        raise StoryError("Choose a map in this Story chapter.")
    x, y = data["maps"][map_id]["arrival"]
    state.update(map_id=map_id, x=float(x), y=float(y), in_lab=False, in_farm=False)
    state["story"]["chapter"] = index
    state["story"]["dialogue"] = None
    engine._event(state, "message", text=f"{data.get('name', 'Dawn Relay')}: {data['maps'][map_id]['name']}. {_objective(state['story'], data, region)}")


def _new_profile(data, campaign_id):
    first = _regions(data)[0]
    initial = data["maps"][first["maps"][0]]
    boss = data["npcs"][data["champion_id"]]
    return {"id": uuid.uuid4().hex, "version": 2, "campaign_id": campaign_id, "started": True, "chapter": 0,
            "badges": [], "completed": [], "met": [], "quest_accepted": [], "dialogue": None, "active_battle": None,
            "location": {"map_id": first["maps"][0], "x": float(initial["arrival"][0]), "y": float(initial["arrival"][1])},
            "stats": {"wins": 0, "losses": 0, "training_wins": 0, "training_losses": 0, "credits_earned": 0, "battles": 0},
            "recent": [], "champion": {"holder": boss["name"], "holder_id": boss["id"], "status": "challenger",
                                      "first_victory": False, "reigns": 0, "defenses": 0, "streak": 0,
                                      "best_streak": 0, "matches": 0}}


def handle(engine, state, payload):
    action = payload.get("action", "enter")
    if action == "enter":
        requested = payload.get("campaign_id", _campaign(state.get("story") or {}))
        if not isinstance(requested, str) or requested not in CAMPAIGN_IDS:
            raise StoryError("Choose Dawn Relay or World DS: Paradox Chronicle.")
        if state.get("in_story"):
            if requested != _campaign(state.get("story") or {}):
                raise StoryError("Save & Return to World before switching Story campaigns.")
            engine._event(state, "message", text="Your Story journey is ready to continue.")
            return
        engine._peace(state)
        if state.get("in_season"):
            raise StoryError("Save & Return to World from Season Mode before entering Story Mode.")
        if state.get("admin_jail"):
            raise StoryError("Story Mode is unavailable while detained.")
        data = content(engine, requested)
        active = state.get("story")
        if active and _campaign(active) != requested:
            active.setdefault("campaign_id", DAWN_CAMPAIGN)
            state.setdefault("story_campaigns", {})[_campaign(active)] = active
            state["story"] = state["story_campaigns"].pop(requested, None)
        if not state.get("story"):
            state["story"] = _new_profile(data, requested)
        state["story"].setdefault("campaign_id", requested)
        state["story"].setdefault("quest_accepted", [])
        state["story_return_state"] = _snapshot(state)
        state.update(copy.deepcopy(state["story"]["location"]))
        state.update(in_story=True, in_lab=False, in_farm=False)
        message = (f"Welcome to World DS: Paradox Chronicle. Begin in peaceful {_regions(data)[0]['name']}, restore 17 fields, and earn every Paradox Crest to summon three level 100 Paradox Megas. Your own partners, DigiLab, DigiFarm, bag and shop stay with you."
                   if requested == DS_CAMPAIGN else "Welcome to Dawn Relay. Bring your own partners, earn eight DigiBadges, and claim a championship that remains yours to defend.")
        engine._event(state, "message", text=message)
        return
    if not state.get("in_story") or not state.get("story"):
        raise StoryError("Enter Story Mode to continue your journey.")
    engine._peace(state)
    profile = state["story"]
    data = _data(engine, profile)
    if "campaign_id" in payload and payload["campaign_id"] != _campaign(profile):
        raise StoryError("This action belongs to a different Story campaign.")
    if action == "return":
        if not state.get("in_lab") and not state.get("in_farm"):
            profile["location"] = {key: copy.deepcopy(state[key]) for key in ("map_id", "x", "y")}
        saved = state.get("story_return_state")
        if not saved:
            raise StoryError("The saved world return point is missing. Reconnect before leaving Story Mode.")
        profile["dialogue"] = None
        state.pop("story_return_state")
        _restore(state, saved)
        state["in_story"] = False
        engine._event(state, "message", text=f"{data.get('name', 'Story')} saved. Your partners and rewards return with you; the Story will wait exactly where you left it.")
    elif action == "travel":
        _travel(engine, state, data, payload.get("chapter", profile["chapter"]), payload.get("map_id"))
    elif action == "exit":
        if state.get("in_lab") or state.get("in_farm"):
            raise StoryError("Return to the Story field before using a relay gate.")
        gate = next((row for row in data["maps"][state["map_id"]].get("exits", []) if row["id"] == payload.get("exit_id")), None)
        if not gate or math.hypot(state["x"] - gate["x"], state["y"] - gate["y"]) > TALK_RADIUS:
            raise StoryError("Walk closer to this Story relay gate first.")
        if gate.get("requires_badge") and gate["requires_badge"] not in profile["badges"]:
            raise StoryError("Earn this field's Paradox Crest to open the next gate." if _is_ds(profile) else "Earn this region's DigiBadge to open the next relay gate.")
        region = _region_for_map(data, gate["to_map"])
        _travel(engine, state, data, region["index"], gate["to_map"])
    elif action == "talk":
        npc = _npc(state, data, payload.get("npc_id"))
        status = _status(profile, npc)
        branch = "locked" if status == "locked" else ("repeat" if status in ("complete", "defending", "reclaim") else "ready")
        if npc.get("role") == "quest":
            branch = {"ready": "quest_start", "active": "quest_progress", "turn_in": "quest_complete"}.get(status, branch)
        if npc.get("role") == "mentor" and (npc.get("region_id") in profile["badges"] or (npc.get("region_id") == "citadel" and profile["champion"]["first_victory"])):
            branch = "won"
        text = npc.get("dialogue", {})
        lines = list(text.get(branch) or text.get("intro") or [f"Welcome to {data.get('name', 'Dawn Relay')}."])
        if status != "locked" and npc["id"] not in profile.setdefault("met", []):
            intro = list(text.get("intro", []))
            lines = intro + [line for line in lines if line not in intro]
            profile["met"].append(npc["id"])
        profile["dialogue"] = {"npc_id": npc["id"], "page": 0, "lines": lines, "token": uuid.uuid4().hex}
    elif action in ("dialogue", "challenge"):
        dialogue = profile.get("dialogue")
        if not dialogue or not isinstance(payload.get("token"), str) or payload["token"] != dialogue["token"]:
            raise StoryError("This conversation has changed. Speak to the tamer again.")
        if dialogue.get("result_only"):
            npc = _all_npcs(data)[dialogue["npc_id"]]
            _nearby(state, npc)
        else:
            npc = _npc(state, data, dialogue["npc_id"])
        if action == "challenge" and payload.get("npc_id", npc["id"]) != npc["id"]:
            raise StoryError("This challenge belongs to a different tamer.")
        choice = "challenge" if action == "challenge" else payload.get("choice")
        if not isinstance(choice, str) or choice not in {row["id"] for row in _choices(profile, npc, dialogue)}:
            raise StoryError("Choose an available conversation response.")
        if choice == "next":
            dialogue["page"] += 1
            dialogue["token"] = uuid.uuid4().hex
        elif choice == "challenge":
            _begin(engine, state, npc, training=False)
        elif choice == "accept_quest":
            # Server-derived choices and rotating conversation capabilities make
            # accepting or turning in the same quest twice impossible.
            profile.setdefault("quest_accepted", []).append(npc["id"])
            profile["dialogue"] = None
            engine._event(state, "message", text=f"Assignment accepted: {npc.get('quest_title', npc['name'])}. Defeat the marked tamer, then return to report your findings.")
        elif choice == "complete_quest":
            before = copy.deepcopy(state["inventory"])
            credits = _grant_reward(engine, state, npc.get("reward", {}), True)
            profile["completed"].append(npc["id"])
            profile["stats"]["credits_earned"] += credits
            lines = list(npc.get("dialogue", {}).get("won") or ["Assignment complete. The Paradox guardian is ready to challenge."])
            result = {"opponent": npc["name"], "role": "quest", "won": True, "first_clear": True, "credits": credits,
                      "items": [{"id": item, "name": state.get("shop", {}).get(item, {}).get("name", item), "quantity": quantity - before.get(item, 0)}
                                for item, quantity in state["inventory"].items() if quantity > before.get(item, 0)]}
            profile["dialogue"] = {"npc_id": npc["id"], "page": 0, "lines": lines, "token": uuid.uuid4().hex,
                                   "result_only": True, "result": result}
            engine._event(state, "story_quest", text=f"Assignment complete: {npc.get('quest_title', npc['name'])}. +{credits} credits. Challenge the Paradox guardian when ready.")
        elif choice == "heal":
            profile["dialogue"] = None
            _heal(engine, state)
        elif choice == "camp":
            profile["dialogue"] = None
            engine._enter_lab(state)
        elif choice == "farm":
            profile["dialogue"] = None
            engine._digifarm(state, {"action": "enter"})
        else:
            profile["dialogue"] = None
    elif action == "heal":
        profile["dialogue"] = None
        _heal(engine, state)
    elif action == "camp":
        profile["dialogue"] = None
        engine._enter_lab(state)
    elif action == "field":
        if state.get("in_farm"):
            engine._digifarm(state, {"action": "return"})
        else:
            engine._digilab(state, {"action": "return"})
    elif action == "train":
        if state.get("in_lab") or state.get("in_farm"):
            raise StoryError("Return to your Story map before training.")
        region = _region_for_map(data, state["map_id"])
        if _is_ds(profile) and region["index"] == 0:
            raise StoryError(f"{region['name']} is a peaceful hub. Travel to a field to train or battle.")
        pool = [partner["species"] for ident in region["npc_ids"] for partner in data["npcs"][ident].get("team", [])]
        living = [monster for monster in state["party"][:3] if monster["hp"] > 0]
        if not living:
            raise StoryError("Recover your partners before training.")
        level = min(max(1, min(monster["level"] for monster in living)), max(1, region.get("level_min", 1)))
        from venom.common.game import STAGE_RANK
        rank_limit = 2 if level < 15 else 3 if level < 30 else 4 if level < 45 else 5 if level < 60 else 6
        pool = [ident for ident in pool if STAGE_RANK.get(engine.species[ident].get("stage"), 2) <= rank_limit] or list(engine.starters)
        team = []
        for monster in living[:3]:
            # Type-safe opening practice prevents a low-level loss/RNG death loop.
            safe_pool = [ident for ident in pool if engine.species[ident].get("type") in (monster.get("type"), "free")]
            ident = monster["species_id"] if level < 10 else engine.rng.choice(safe_pool or [monster["species_id"]])
            team.append({"species": ident, "level": level})
        _begin(engine, state, {"id": "training", "name": "Paradox Field Training" if _is_ds(profile) else "Relay Field Training", "role": "training", "team": team}, training=True)
    else:
        raise StoryError("Unknown Story Mode action.")


def _begin(engine, state, npc, training=False):
    profile = state["story"]
    data = _data(engine, profile)
    if state.get("battle") or profile.get("active_battle"):
        raise StoryError("Finish your current battle before starting another Story challenge.")
    if _is_ds(profile) and _region_for_map(data, state["map_id"])["index"] == 0:
        raise StoryError(f"{_regions(data)[0]['name']} is a peaceful hub. Travel to a field to train or battle.")
    if not training:
        if not _ready(profile, npc):
            raise StoryError("Complete this tamer's preceding Story challenges first.")
        if npc.get("role") == "champion" and len(profile["badges"]) < 8:
            raise StoryError("All eight DigiBadges are required for the championship.")
        if npc.get("role") == "final" and (len(_badges(data)) != 17 or not all(ident in profile["badges"] for ident in _badges(data))):
            raise StoryError("All 17 different Paradox Crests are required to summon the final three Paradox Megas.")
    active = [index for index, monster in enumerate(state["party"][:3]) if monster["hp"] > 0]
    if not active:
        raise StoryError("Recover your partners before challenging this tamer.")
    enemies = [engine._monster(partner["species"], partner["level"], abi=min(100, partner["level"] // 2), cam=min(100, partner["level"])) for partner in npc["team"][:3]]
    if training:
        for enemy in enemies:
            enemy["hp"] = enemy["max_hp"] = max(20, int(enemy["hp"] * .60))
    ident = uuid.uuid4().hex
    battle = {"id": ident, "kind": "story", "story_campaign_id": _campaign(profile), "story_profile_id": profile["id"],
              "story_training": training, "story_npc_id": npc["id"],
              "story_role": npc.get("role"), "story_badge": npc.get("badge"), "opponent_name": npc.get("battle_name", npc["name"]),
              "enemies": enemies, "active": active, "turn": 0, "actor": active[0], "clock": 0.0, "queue": [], "scanned": []}
    profile["dialogue"] = None
    profile["active_battle"] = {"id": ident, "npc_id": npc["id"], "training": training,
                                "campaign_id": _campaign(profile), "profile_id": profile["id"]}
    state["battle"] = battle
    for index in active:
        battle["queue"].append({"side": "player", "index": index, "at": 500 / max(1, state["party"][index]["spd"])})
    for index, enemy in enumerate(enemies):
        battle["queue"].append({"side": "enemy", "index": index, "at": 500 / max(1, enemy["spd"]) + .001})
    engine._event(state, "message", text=("Wild Digimon approach for field training. Fight, collect scan data, or withdraw with your normal controls." if training else f"{npc.get('battle_name', npc['name'])} challenges your partners. Choose every player action with the normal battle controls."))
    engine._advance(state)


def cancel_training(state):
    if state.get("story"):
        state["story"]["active_battle"] = None


def _training_xp(engine, state, floor):
    from venom.common.game import xp_required
    floor = min(99, max(1, int(floor)))
    for index, monster in enumerate(state["party"]):
        if monster["level"] < floor:
            amount = sum(xp_required(level) for level in range(monster["level"], floor)) - monster["xp"]
            engine._add_xp(state, monster, max(0, amount), index)


def _grant_reward(engine, state, reward, first, training=False):
    credits = max(0, int(reward.get("credits", 0)))
    if not first and not training:
        credits = max(25, credits // 5)
    actual = max(0, min(credits, MAX_CREDITS - state.get("credits", 0)))
    state["credits"] = min(MAX_CREDITS, state.get("credits", 0) + actual)
    if first or training:
        for item, quantity in reward.get("items", {}).items():
            if item in state.get("shop", {}):
                state["inventory"][item] = min(999, state["inventory"].get(item, 0) + max(0, int(quantity)))
        if reward.get("training_level"):
            _training_xp(engine, state, reward["training_level"])
        partner = reward.get("partner")
        if partner in engine.species:
            level = min(99, max(1, int(reward.get("training_level", 5))))
            monster = engine._monster(partner, level, abi=min(60, level // 2), cam=30)
            if len(state["party"]) < 6:
                state["party"].append(monster)
                engine._event(state, "message", text=f"Story companion: {monster['name']} joined your party!")
            elif len(state.get("storage", [])) < 100:
                state["storage"].append(monster)
                engine._event(state, "message", text=f"Story companion: {monster['name']} is waiting in your DigiFarm.")
            else:
                state["scan"][partner] = 200
                engine._event(state, "message", text=f"Your roster is full. {monster['name']}'s 200% scan data is saved for later materialization.")
    return actual


def settle(engine, state, won):
    profile, battle = state.get("story"), state.get("battle")
    binding = profile.get("active_battle") if profile else None
    if (not battle or not binding or binding["id"] != battle["id"] or binding["npc_id"] != battle.get("story_npc_id")
            or battle.get("kind") != "story"
            or battle.get("story_campaign_id", DAWN_CAMPAIGN) != _campaign(profile)
            or binding.get("campaign_id", DAWN_CAMPAIGN) != _campaign(profile)
            or battle.get("story_profile_id", profile["id"]) != profile["id"]
            or binding.get("profile_id", profile["id"]) != profile["id"]
            or bool(binding.get("training")) != bool(battle.get("story_training"))):
        raise StoryError("The saved Story challenge does not match this battle. Reconnect before continuing.")
    data = _data(engine, profile)
    training = bool(battle.get("story_training"))
    npc = None if training else _all_npcs(data).get(binding["npc_id"])
    if not training and not npc:
        raise StoryError("This Story opponent is unavailable. Reconnect before continuing.")
    first = not training and npc["id"] not in profile["completed"]
    role = "training" if training else npc.get("role")
    stats = profile["stats"]
    stats["battles"] += 1
    stats[("training_" if training else "") + ("wins" if won else "losses")] += 1
    state["wins" if won else "losses"] = state.get("wins" if won else "losses", 0) + 1
    credits = xp = 0
    inventory_before = copy.deepcopy(state["inventory"])
    party_uids = {monster["uid"] for monster in state["party"]}
    storage_uids = {monster["uid"] for monster in state.get("storage", [])}
    reward = {}
    rewardable_win = won and not (role == "final" and not first)
    if rewardable_win:
        xp = sum(24 + enemy["level"] * 16 for enemy in battle["enemies"])
        for index, monster in enumerate(state["party"]):
            monster["cam"] = min(100, monster.get("cam", 0) + (5 if first else 2))
            if first:
                monster["abi"] = min(200, monster.get("abi", 0) + 3)
            engine._add_xp(state, monster, xp, index)
        if training:
            region = _region_for_map(data, state["map_id"])
            floor = min(99, max(1, region.get("level_min", 1)))
            weakest = min(monster["level"] for monster in state["party"])
            reward = {"credits": 40 + region["index"] * 70, "training_level": min(floor, weakest + 4), "items": {"hp_s": 1}}
        else:
            reward = npc.get("reward", {})
        credits = _grant_reward(engine, state, reward, first or role == "champion", training)
        if not training and first:
            profile["completed"].append(npc["id"])
            badge = npc.get("badge")
            if badge and badge not in profile["badges"]:
                profile["badges"].append(badge)
                badge_name = "Paradox Crest" if _is_ds(profile) else "DigiBadge"
                suffix = "All 17 crests are secured. The final three Paradox Megas can now be summoned." if _is_ds(profile) and len(profile["badges"]) == 17 else "The next chapter is open."
                engine._event(state, "story_badge", badge=badge, text=f"{badge_name} {len(profile['badges'])}/{len(_badges(data))} earned! {suffix}")
    if role == "final":
        champion = profile["champion"]
        champion["matches"] += 1
        if won:
            champion.update(first_victory=True, status="completed", holder=state["username"], holder_id="player")
            if first:
                champion["reigns"] = 1
                if not state.setdefault("permanent_rewards", {}).get("paradox_scan_mastery"):
                    state["permanent_rewards"]["paradox_scan_mastery"] = True
                    engine._event(state, "story_mastery", text="Paradox Chronicle complete! Permanent Paradox Scan Mastery unlocked: +20% scan gain wherever you win Paradox wild battles.")
    if role == "champion":
        champion = profile["champion"]
        champion["matches"] += 1
        if won:
            if champion["status"] == "defending":
                champion["defenses"] += 1
                champion["streak"] += 1
            else:
                champion["reigns"] += 1
                champion["streak"] = 0
            champion.update(first_victory=True, status="defending", holder=state["username"], holder_id="player")
            champion["best_streak"] = max(champion["best_streak"], champion["streak"])
        else:
            champion.update(holder=npc["name"], holder_id=npc["id"], streak=0,
                            status="reclaim" if champion["first_victory"] else "challenger")
    stats["credits_earned"] += credits
    result = {"number": stats["battles"], "opponent": battle["opponent_name"], "won": bool(won),
              "role": role, "credits": credits, "first_clear": bool(first and won),
              "items": [{"id": item, "name": state.get("shop", {}).get(item, {}).get("name", item),
                         "quantity": quantity - inventory_before.get(item, 0)}
                        for item, quantity in state["inventory"].items() if quantity > inventory_before.get(item, 0)]}
    if role == "final":
        result["scan_mastery_unlocked"] = bool(first and won)
        result["replay"] = bool(not first)
    if won and (first or training) and reward.get("partner"):
        ident = reward["partner"]
        destination = "scan data"
        if any(monster["uid"] not in party_uids for monster in state["party"]):
            destination = "party"
        elif any(monster["uid"] not in storage_uids for monster in state.get("storage", [])):
            destination = "DigiFarm"
        result["partner"] = {"species_id": ident, "name": engine.species[ident]["name"], "destination": destination}
    profile["recent"].insert(0, result)
    del profile["recent"][HISTORY_LIMIT:]
    profile["active_battle"] = None
    state["battle"] = None
    # ABI changes must affect stats even when a partner was already level 99.
    for monster in state["party"]:
        values = engine.stats_for(engine.species[monster["species_id"]], monster["level"], monster.get("abi", 0), monster.get("farm_bonuses"))
        for key in ("atk", "def", "int", "spd"):
            monster[key] = values[key]
        monster["max_hp"], monster["max_sp"] = values["hp"], values["sp"]
    _heal(engine, state)
    engine._event(state, "win" if won else "lose", amount=credits, xp=xp,
                  text=f"Story victory! +{credits} credits. Partners recovered." if won else "Story defeat. Your progress is safe and your partners have recovered. Try again whenever you are ready.")
    if not training:
        branch = "rematch_won" if _is_ds(profile) and won and not first else "won" if won else "lost"
        lines = npc.get("dialogue", {}).get(branch, npc.get("dialogue", {}).get("won" if won else "lost", []))
        if lines:
            # An outgoing champion can speak after the next challenger appears.
            # Result capabilities never issue another challenge or another reward.
            profile["dialogue"] = {"npc_id": npc["id"], "page": 0, "lines": list(lines),
                                   "token": uuid.uuid4().hex, "result_only": True, "result": copy.deepcopy(result)}
            engine._event(state, "story_result", text=" ".join(lines), won=bool(won), opponent=npc["name"], role=role)
