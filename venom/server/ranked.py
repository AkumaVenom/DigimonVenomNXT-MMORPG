"""Persistent Battle Park adaptation for Venom NXT's three-active-party combat.

The original game's exact reward table, real-time cooldown battle engine and
season clock are not present in the supplied assets. Numeric balance below is
explicitly NXT's, while weekly seasons, promotion battles, defender teams and
DigiRuby placement/grade rewards follow the documented Battle Park structure.
"""
from __future__ import annotations

import bisect
import copy
from datetime import datetime, timezone
import hashlib
import heapq
import logging
import math
import random
import threading
import time
import uuid

from venom.common.game import GameError, effectiveness

LOG = logging.getLogger('venom.ranked')


GRADES = (
    {"name": "Bronze", "points": 0, "digirubies": 10},
    {"name": "Silver", "points": 100, "digirubies": 20},
    {"name": "Gold", "points": 300, "digirubies": 40},
    {"name": "Platinum", "points": 600, "digirubies": 70},
    {"name": "Diamond", "points": 1000, "digirubies": 100},
    {"name": "Master", "points": 1800, "digirubies": 150},
)
PLACEMENT_REWARDS = (
    {"rank_max": 1, "digirubies": 300}, {"rank_max": 10, "digirubies": 200},
    {"rank_max": 25, "digirubies": 150}, {"rank_max": 50, "digirubies": 100},
    {"rank_max": 100, "digirubies": 75}, {"rank_max": 500, "digirubies": 40},
    {"rank_max": 1000000000, "digirubies": 20},
)
DEFAULTS = {
    "season_seconds": 7 * 24 * 3600, "season_anchor": 4 * 24 * 3600,  # Monday 1970-01-05 UTC
    "energy_capacity": 30, "energy_refill_seconds": 300,
    "win_points": 20, "loss_points": 5, "match_cooldown": 2.0,
    "opponent_cooldown": 60.0, "turn_limit": 240,
}


def _party_power(party):
    # Consider three starters plus the contribution of three usable reserves.
    powers = [m.get("max_hp", 1) * .08 + m.get("atk", 1) + m.get("int", 1) + m.get("def", 1) * .5 + m.get("spd", 1) * .5
              for m in party[:6]]
    return round(sum(powers[:3]) + sum(powers[3:]) * .7)


class RankedService:
    def __init__(self, engine, store, config=None, clock=time.time):
        self.engine, self.store, self.clock = engine, store, clock
        supplied = config or {}
        supplied = supplied.get("ranked", supplied)
        self.config = {**DEFAULTS, **{key: supplied[key] for key in DEFAULTS if key in supplied}}
        self.config["season_seconds"] = max(60, int(self.config["season_seconds"]))
        self.config["energy_capacity"] = max(1, min(50, int(self.config["energy_capacity"])))
        self.config["energy_refill_seconds"] = max(1, int(self.config["energy_refill_seconds"]))
        self.config["win_points"] = max(1, int(self.config["win_points"]))
        self.config["loss_points"] = max(0, int(self.config["loss_points"]))
        self.config["turn_limit"] = max(12, min(500, int(self.config["turn_limit"])))
        self.config["match_cooldown"] = max(0, float(self.config["match_cooldown"]))
        self.config["opponent_cooldown"] = max(0, float(self.config["opponent_cooldown"]))
        self.requested_config = dict(self.config)
        store.configure_ranked_schedule(self.config["season_seconds"], self.config["season_anchor"])
        self.lock = threading.RLock()
        LOG.info('Ranked startup: restoring saved defender profiles...')
        self.profiles = {p["id"]: p for p in store.profiles()}
        LOG.info('Ranked startup: restored %s defender profiles; checking season settlement...', len(self.profiles))
        self._power_order = []
        self._indexed_ids = set()
        self._power_at = -math.inf
        self._season = None
        self._standings_cache = {}
        self._generation = 0
        self._matches_started = 0
        self.tick()
        LOG.info('Ranked startup: current season and automatic DigiRuby rewards are ready.')

    def register_participant(self, participant_id, profile):
        return self.register_many([{**profile, "id": participant_id}])

    def register_many(self, profiles):
        """Batch initial profiles; later writes only persist changed snapshots."""
        changed = []
        with self.lock:
            for raw in profiles:
                profile = copy.deepcopy(raw)
                participant_id = str(profile.get("id", ""))
                if not participant_id or len(participant_id) > 64:
                    raise GameError("Invalid competitor identifier.")
                if profile.get("kind") not in ("bot", "player"):
                    profile["kind"] = "bot" if participant_id.startswith("bot:") else "player"
                profile["name"] = str(profile.get("name", profile.get("username", participant_id)))[:64]
                profile["tamer"] = str(profile.get("tamer", ""))[:128]
                party = profile.get("party", [])
                if not isinstance(party, list) or not 1 <= len(party) <= 6:
                    raise GameError("Battle Park needs a party of one to six partners.")
                for monster in party:
                    if monster.get("species_id") not in self.engine.species:
                        raise GameError("A defender snapshot contains an unknown Digimon.")
                    for stat in ("max_hp", "max_sp", "atk", "def", "int", "spd"):
                        value = monster.get(stat)
                        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 1:
                            raise GameError("A defender snapshot contains invalid partner stats.")
                profile["power"] = _party_power(party)
                if profile != self.profiles.get(participant_id):
                    changed.append(profile)
            if changed:
                self.store.register_many(changed, self.clock(), self.config["energy_capacity"])
                self.profiles.update((p["id"], p) for p in changed)
                # New participants must be immediately matchable; movement-only
                # changes do not cause the sorted defender index to rebuild.
                if any(p["id"] not in self._indexed_ids for p in changed):
                    self._power_at = -math.inf
        return len(changed)

    @staticmethod
    def _label(season):
        season = dict(season)
        season["label"] = "Season " + datetime.fromtimestamp(season["starts_at"], timezone.utc).strftime("%d %b %Y")
        return season

    def tick(self, now=None):
        now = self.clock() if now is None else float(now)
        with self.lock:
            duration = self.requested_config["season_seconds"]
            anchor = self.requested_config["season_anchor"]
            season_id = math.floor((now - anchor) / duration)
            start = anchor + season_id * duration
            if self._season is None or self._season["id"] != season_id:
                frozen = {"version": "nxt-battle-park-1", "config": dict(self.requested_config),
                          "grades": list(GRADES), "placement_rewards": list(PLACEMENT_REWARDS),
                          "eligibility": "At least one attacking ranked match in this season."}
                self._season = self._label(self.store.season(season_id, start, start + duration, now, self.reward_for, rules=frozen))
                self.config.update(self._season["rules"].get("config", {}))
                self._standings_cache.clear()
            return {**self._season, "seconds_remaining": max(0, int(self._season["ends_at"] - now))}

    ensure_season = tick

    @staticmethod
    def reward_for(rank, points, grade_index=0):
        placement = next(row["digirubies"] for row in PLACEMENT_REWARDS if rank <= row["rank_max"])
        grade = GRADES[max(0, min(len(GRADES) - 1, int(grade_index)))]
        return placement + grade["digirubies"]

    def seasons(self, limit=20):
        self.tick()
        return [self._label(row) for row in self.store.seasons(limit)]

    def _standings(self, season_id=None, career=False):
        key = (season_id, career)
        cached = self._standings_cache.get(key)
        if cached and cached[0] == self._generation:
            return cached[1]
        rows = self.store.standings(season_id, career)
        snapshot = self.store.season_info(season_id) if season_id is not None else None
        grades = (snapshot or {}).get("rules", {}).get("grades", GRADES)
        for row in rows:
            row["grade"] = grades[max(0, min(len(grades) - 1, row["grade_index"]))]["name"]
        self._standings_cache[key] = self._generation, rows
        return rows

    def leaderboard(self, scope="current", season_id=None, limit=100):
        with self.lock:
            season = self.tick()
            if scope not in ("current", "history", "career", "overall"):
                raise GameError("Choose the current, historical or career ladder.")
            career = scope in ("career", "overall")
            if scope == "history":
                history = self.store.seasons(100)
                if season_id is None:
                    selected = next((s for s in history if s["status"] == "closed"), None)
                    if selected is None:
                        return {"scope": scope, "season": None, "entries": [], "total": 0}
                else:
                    selected = self.store.season_info(int(season_id))
                    if selected is None:
                        raise GameError("That ranked season is not available.")
                season = self._label(selected)
            rows = self._standings(None if career else season["id"], career)
            return {"scope": "career" if career else scope, "season": None if career else season,
                    "entries": copy.deepcopy(rows[:max(1, min(100, int(limit)))]), "total": len(rows)}

    def _own(self, participant_id, now=None):
        now = self.clock() if now is None else float(now)
        season = self.tick(now)
        own = self.store.competitor(participant_id)
        record = self.store.record(participant_id, season["id"])
        own.update(record)
        own.update(self.store.entry_counts(participant_id, season["id"]))
        own["rank"] = next((row["rank"] for row in self._standings(season["id"]) if row["id"] == participant_id), None)
        own["grade"] = GRADES[record["grade_index"]]["name"]
        next_grade = GRADES[record["grade_index"] + 1] if record["grade_index"] + 1 < len(GRADES) else None
        own["next_grade"] = dict(next_grade) if next_grade else None
        current, stamp = self.store.energy(own, now, self.config["energy_capacity"], self.config["energy_refill_seconds"])
        own["energy"] = {"current": current, "capacity": self.config["energy_capacity"],
                         "next_in": 0 if current == self.config["energy_capacity"] else max(0, math.ceil(stamp + self.config["energy_refill_seconds"] - now)),
                         "refill_seconds": self.config["energy_refill_seconds"]}
        own.pop("energy_at", None)
        own.pop("last_attack", None)
        return own

    def overview(self, participant_id, now=None):
        with self.lock:
            return {"season": self.tick(now), "own": self._own(participant_id, now),
                    "opponents": self.available_opponents(participant_id),
                    "rewards": list(PLACEMENT_REWARDS), "grades": list(GRADES),
                    "recent": self.store.recent_matches(participant_id, 10),
                    "rules": {**self.config, "label": "Venom NXT Battle Park adaptation",
                              "eligibility": "Start at least one attacking ranked battle in the season; passive defenses alone do not qualify.",
                              "promotion": "Reach the next grade's points, then win an attacking promotion match.",
                              "reward": "Season placement bonus plus earned grade bonus; delivered automatically.",
                              "defense": "Attacks and defenses both count toward seasonal and career records.",
                              "combat": "Three active partners with up to three reserves; fully restored defender snapshots."}}

    def available_opponents(self, participant_id, limit=15):
        with self.lock:
            profile = self.profiles.get(participant_id)
            if not profile:
                raise GameError("Register a defender team before entering Battle Park.")
            now = self.clock()
            if not self._power_order or now - self._power_at >= 30:
                self._power_order = sorted((p["power"], pid) for pid, p in self.profiles.items())
                self._indexed_ids = set(self.profiles)
                self._power_at = now
            power = profile["power"]
            at = bisect.bisect_left(self._power_order, (power, participant_id))
            candidates = [pid for _, pid in self._power_order[max(0, at - 40):at + 41] if pid != participant_id]
            candidates.sort(key=lambda pid: (abs(self.profiles[pid]["power"] - power), pid))
            # Stable per-minute shuffle within comparable teams prevents the
            # first equal-power identifier receiving every rival's attacks.
            seed = hashlib.sha256(f"{participant_id}:{int(now // 60)}".encode()).digest()
            rng = random.Random(int.from_bytes(seed[:8], "big"))
            shortlist = candidates[:max(15, min(50, int(limit) * 3))]
            rng.shuffle(shortlist)
            season = self.tick(now)
            selected = shortlist[:max(1, min(100, int(limit)))]
            records = self.store.candidate_records(selected, season["id"])
            result = []
            for pid in selected:
                p = self.profiles[pid]
                row = {"id": pid, "name": p["name"], "kind": p["kind"], "tamer": p["tamer"], "power": p["power"],
                       "party": copy.deepcopy(p["party"]), "points": 0, "wins": 0, "losses": 0, "rank": None,
                       "grade": "Bronze", "career_rating": 1000}
                row.update(records.get(pid, {}))
                row["grade"] = GRADES[row.get("grade_index", 0)]["name"]
                result.append(row)
            return result

    def start_match(self, attacker_id, defender_id=None, match_id=None, ranked=True, now=None):
        with self.lock:
            now = self.clock() if now is None else float(now)
            season = self.tick(now)
            match_id = str(match_id or uuid.uuid4().hex)
            if not match_id or len(match_id) > 64:
                raise GameError("Invalid arena match identifier.")
            previous = self.store.match(match_id)
            if previous:
                if previous["attacker_id"] != attacker_id or (defender_id and previous["defender_id"] != defender_id) or previous["ranked"] != bool(ranked):
                    raise GameError("That match identifier belongs to a different arena request.")
                return {**previous, "duplicate": True}
            if attacker_id not in self.profiles:
                raise GameError("Register a defender team before entering Battle Park.")
            if defender_id is None:
                candidates = self.available_opponents(attacker_id, 30)
                if not candidates:
                    raise GameError("No other ranked competitors are available yet.")
                defender_id = candidates[self._matches_started % len(candidates)]["id"]
            if defender_id == attacker_id or defender_id not in self.profiles:
                raise GameError("Choose another registered competitor.")
            attacker, defender = self.profiles[attacker_id], self.profiles[defender_id]
            # Check energy before the simulation; commit_match checks again in
            # the same transaction that updates both competitors and the ledger.
            record = self.store.competitor(attacker_id)
            if ranked and self.store.energy(record, now, self.config["energy_capacity"], self.config["energy_refill_seconds"])[0] < 1:
                raise GameError("Battle Park energy is recovering. Rival challenges remain available.")
            if now - record["last_attack"] < self.config["match_cooldown"]:
                raise GameError("Please wait a moment before starting another arena battle.")
            # The idempotency key can include a client request number. Seed
            # combat independently, so choosing request IDs cannot choose rolls.
            result = self._fight(attacker, defender, uuid.uuid4().hex)
            result.update({"id": match_id, "match_id": match_id, "attacker_id": attacker_id, "defender_id": defender_id,
                           "attacker_name": attacker["name"], "defender_name": defender["name"],
                           "winner_id": attacker_id if result["attacker_won"] else defender_id,
                           "ranked": bool(ranked), "season_id": season["id"], "played_at": now})
            result = self.store.commit_match(result, now, self.config["energy_capacity"], self.config["energy_refill_seconds"],
                                              self.config["match_cooldown"], self.config["win_points"], self.config["loss_points"],
                                              GRADES, self.config["opponent_cooldown"])
            self._matches_started += 1
            self._generation += 1
            self._standings_cache.clear()
            # Human results need the wallet/record immediately. Bot callers
            # inspect ledger counters without rebuilding the full ladder.
            if attacker["kind"] == "player":
                result["own"] = self._own(attacker_id, now)
            return result

    def _fight(self, attacker, defender, match_id):
        """Resolve real stats/skills/type/CAM turns on isolated healed snapshots.

        Calling the shared strike function from each team's player perspective
        gives both sides the same damage/combo rules: no wild-enemy handicap.
        Neither this engine clone nor the combat copies can change world saves.
        """
        local_engine = copy.copy(self.engine)
        seed = int.from_bytes(hashlib.sha256(match_id.encode()).digest()[:16], "big")
        local_engine.rng = random.Random(seed)
        teams = [copy.deepcopy(attacker["party"][:6]), copy.deepcopy(defender["party"][:6])]
        for party in teams:
            for monster in party:
                monster["hp"], monster["sp"] = monster["max_hp"], monster["max_sp"]
                monster.pop("guard", None)
                monster.setdefault("skills", local_engine._skills(monster))
        initial = copy.deepcopy(teams)
        active = [list(range(min(3, len(team)))) for team in teams]
        queue = []
        serial = 0
        for side, party in enumerate(teams):
            for index in active[side]:
                serial += 1
                # Alternating random ties avoids a permanent attacker-first edge.
                heapq.heappush(queue, (500 / party[index]["spd"], local_engine.rng.random(), serial, side, index))
        events = []
        turns = 0
        while queue and turns < self.config["turn_limit"] and all(any(m["hp"] > 0 for m in t) for t in teams):
            clock, _, _, side, index = heapq.heappop(queue)
            actor = teams[side][index]
            if actor["hp"] <= 0 or index not in active[side]:
                continue
            other = 1 - side
            living = [i for i in active[other] if teams[other][i]["hp"] > 0]
            if not living:
                break
            skills = [skill for skill in actor["skills"] if actor["sp"] >= skill.get("sp", 0)]
            options = [(None, i) for i in living] + [(skill, i) for skill in skills for i in living]
            def score(option):
                skill, target_index = option
                target = teams[other][target_index]
                magic = skill is not None and skill.get("kind") == "magic"
                attack = actor["int"] if magic else actor["atk"]
                defense = target["int"] if magic else target["def"]
                expected = max(1, (8 + attack * .72 - defense * .28) * (skill["power"] if skill else 1.0))
                expected *= effectiveness(actor, target, skill["attribute"] if skill else "neutral")
                # Focus a finish when available; avoid wasting all SP on a tiny
                # final hit when a free physical attack will already do it.
                return min(target["hp"], expected) + (80 if expected >= target["hp"] else 0) - (skill["sp"] * .8 if skill else 0)
            skill, target_index = max(options, key=score)
            action = "skill" if skill else "attack"
            if skill:
                actor["sp"] -= skill["sp"]
            state = {"party": teams[side], "battle": {"active": active[side]}, "events": []}
            target = teams[other][target_index]
            local_engine._strike(state, actor, target, "player", index, target_index, action, skill)
            event = state["events"][-1]
            event.update({"side": "enemy" if other else "player", "attacker_side": "enemy" if side else "player",
                          "seq": len(events), "turn": turns, "hp": target["hp"], "sp": actor["sp"],
                          "hp_after": target["hp"], "sp_after": actor["sp"],
                          "multiplier": event["effectiveness"]})
            events.append(event)
            turns += 1
            if target["hp"] <= 0:
                reserve = next((i for i, m in enumerate(teams[other]) if i not in active[other] and m["hp"] > 0), None)
                if reserve is not None:
                    slot = active[other].index(target_index)
                    active[other][slot] = reserve
                    serial += 1
                    heapq.heappush(queue, (clock + 1000 / teams[other][reserve]["spd"], local_engine.rng.random(), serial, other, reserve))
                    events.append({"kind": "reserve", "side": "enemy" if other else "player", "index": reserve,
                                   "retired_index": target_index, "seq": len(events), "turn": turns,
                                   "text": f"{teams[other][reserve]['name']} enters from the reserves."})
            serial += 1
            heapq.heappush(queue, (clock + 1000 / actor["spd"], local_engine.rng.random(), serial, side, index))
        fractions = [sum(m["hp"] / max(1, m["max_hp"]) for m in team) / max(1, len(team)) for team in teams]
        eliminated = [not any(m["hp"] > 0 for m in team) for team in teams]
        if eliminated[0] or eliminated[1]:
            attacker_won = eliminated[1] and not eliminated[0]
            reason = "knockout"
        else:
            # Explicit deterministic turn-limit tiebreak, never a random win.
            attacker_won = fractions[0] > fractions[1]
            reason = "turn_limit_hp" if fractions[0] != fractions[1] else "turn_limit_defender_holds"
        return {"attacker_won": attacker_won, "turns": turns, "reason": reason,
                "remaining_hp": {"attacker": round(fractions[0], 4), "defender": round(fractions[1], 4)},
                "points": {}, "replay": {"party": initial[0], "enemies": initial[1],
                                         "active": list(range(min(3, len(initial[0])))),
                                         "enemy_active": list(range(min(3, len(initial[1])))), "events": events}}
