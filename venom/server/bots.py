"""Persistent, authoritative rival population without synthetic player sockets.

Wild combat, scan conversion, shopping, evolution and party changes go through
GameEngine.handle, exactly like human requests. Ranked combat belongs to the
shared RankedService. Counters are consequences of these operations, never dice
rolls masquerading as battles. Fresh rivals have one level-seeded Rookie so all
254 sectors have viable inhabitants; that initial level is not reported as XP.
"""
from __future__ import annotations

import copy
import heapq
import math
import random
import threading
import time
import uuid
from collections import Counter, deque

from venom.common.game import GameError, SHOP, STAGE_RANK, effectiveness
from .navigation import Navigation


STAT_KEYS = (
    "wild_wins", "wild_losses", "wild_started", "ranked_wins", "ranked_losses",
    "ranked_started", "rival_wins", "rival_losses", "scans", "scan_data",
    "materialized", "paradox_materialized", "level_ups", "xp_earned",
    "evolutions", "devolutions", "heals", "items_used", "purchases",
    "party_swaps", "travels", "walking_distance", "exploration_steps", "errors",
)
PHASE_NAMES = {"explore": "Exploring", "battle": "Wild battle", "lab": "DigiLab",
               "ranked": "Ranked battle", "recover": "Recovering"}
NEXT_PHASE = {"explore": "Wild battle", "battle": "DigiLab and party care",
              "lab": "Ranked battle", "ranked": "Exploration", "recover": "DigiLab"}


class BotManager:
    """Single-worker scheduler; small synchronized reads are safe from networking.

    ``now`` is monotonic seconds. No offline catch-up loop runs after a restart.
    A min-heap rotates due work fairly, bounded by count *and* a wall-time budget.
    Storage and ranked methods are synchronous and are called from the worker.
    """

    def __init__(self, engine, store, ranked=None, config=None):
        self.engine, self.store, self.ranked = engine, store, ranked
        self.config = dict(config or {})
        self.count = max(0, min(5000, int(self.config.get("count", 5000))))
        self.enabled = bool(self.config.get("enabled", True))
        if not self.enabled:
            self.count = 0
        self.seed = int(self.config.get("seed", 741029))
        self.rng = random.Random(self.seed)
        self.lock = threading.RLock()
        self.navigation = Navigation(engine.root, engine.maps)
        self.bots = {}
        self.by_map = {key: set() for key in engine.maps}
        self.heap = []
        self.serial = 0
        self.dirty = set()
        self.counters = Counter({key: 0 for key in STAT_KEYS})
        self.events = deque(maxlen=100)
        self.pending_events = []
        self.pending_counters = Counter()
        self.last_save = 0.0
        self.last_tick = 0.0
        self.processed = 0
        self.last_tick_ms = 0.0
        self.max_lateness = 0.0
        self.initialized = False
        self.dwell_min = max(30.0, float(self.config.get("dwell_min", self.config.get("min_dwell", 300))))
        self.dwell_max = max(self.dwell_min, float(self.config.get("dwell_max", self.config.get("max_dwell", 900))))
        self.event_interval = max(.1, float(self.config.get("action_interval", 1.0)))
        self.walk_seconds = max(2.0, float(self.config.get("explore_seconds", 16.0)))
        self.turn_budget_ms = max(2.0, min(100.0, float(self.config.get("tick_budget_ms", 20))))
        self.history_limit = 100
        self.seen_matches = deque(maxlen=20000)
        self.seen_match_ids = set()

    def initialize(self, now=None):
        now = time.monotonic() if now is None else float(now)
        with self.lock:
            if self.initialized:
                return
            loaded = {str(row["id"]): row for row in self.store.bot_load_all()}
            ranked_totals = self.store.ranked_totals() if hasattr(self.store, "ranked_totals") else {}
            maps = sorted(self.engine.maps)
            tamers = sorted(self.engine.tamers)
            profiles, new_rows = [], []
            for ordinal in range(self.count):
                ident = f"bot:{ordinal + 1:05d}"
                row = loaded.get(ident)
                if row is None:
                    area = self.engine.maps[maps[ordinal % len(maps)]]
                    name = self._name(ordinal)
                    starter = self.engine.starters[ordinal % len(self.engine.starters)]
                    state = self.engine.new_player(name, tamers[ordinal % len(tamers)], starter)
                    self.engine.handle(state, "travel", {"map_id": area["id"]})
                    # Initial rival difficulty is openly labelled, not fake training.
                    seed_level = min(99, max(1, int(area.get("level", 1)) + 2))
                    state["party"] = [self.engine._monster(starter, level=seed_level, cam=10)]
                    self.engine._refresh(state)
                    state["x"], state["y"] = self.navigation.spawn(area["id"], ordinal // len(maps))
                    state["events"] = []
                    row = {"id": ident, "state": state,
                           "runtime": {"phase": "explore", "cycle": 0, "seed_level": seed_level},
                           "stats": {key: 0 for key in STAT_KEYS}}
                    new_rows.append(row)
                if ident in ranked_totals:
                    row.setdefault("stats", {}).update(ranked_totals[ident])
                self._restore(row, ordinal, now)
                profiles.append(self._rank_profile(self.bots[ident]))
            # One batch establishes directory membership, rather than 5,000 commits.
            if self.ranked and profiles:
                self.ranked.register_many(profiles)
            if new_rows:
                for start in range(0, len(new_rows), 500):
                    self.store.bot_save_batch([self._serialize(self.bots[row["id"]], now)
                                               for row in new_rows[start:start + 500]])
            if hasattr(self.store, "activity"):
                history = self.store.activity(limit=100)
                self.events.extend(reversed(history.get("events", [])))
            self.dirty.clear()
            self.last_save = self.last_tick = now
            self.initialized = True

    @staticmethod
    def _name(ordinal):
        first = ("Nova", "Echo", "Cobalt", "Luna", "Aster", "Rift", "Pixel", "Terra",
                 "Ember", "Frost", "Kite", "Sora", "Onyx", "Comet", "Azure", "Violet")
        second = ("Scout", "Cipher", "Ranger", "Pulse", "Warden", "Link", "Voyager", "Spark")
        return f"AI {first[ordinal % len(first)]}{second[(ordinal // len(first)) % len(second)]}{ordinal + 1:04d}"

    def _restore(self, row, ordinal, now):
        state = copy.deepcopy(row["state"])
        if state.get("map_id") not in self.engine.maps or not state.get("party"):
            raise ValueError(f"Saved rival {row['id']} has an invalid map or empty party; restore its backup.")
        if any(m.get("species_id") not in self.engine.species for m in state["party"] + state.get("storage", [])):
            raise ValueError(f"Saved rival {row['id']} refers to missing Digimon assets.")
        runtime = dict(row.get("runtime", {}))
        remaining = max(30, min(self.dwell_max, float(runtime.pop("dwell_remaining", self.rng.uniform(self.dwell_min, self.dwell_max)))))
        phase = runtime.get("phase", "explore")
        # A persisted battle resumes its real timeline; partial lab visits can safely
        # repeat maintenance, because purchases/conversion enforce actual inventory.
        if state.get("battle"):
            phase = "battle"
        elif state.get("in_lab"):
            phase = "lab"
        elif phase not in ("explore", "ranked"):
            phase = "explore"
        runtime.update(phase=phase, path=None, leave_at=now + remaining,
                       phase_until=now + self.walk_seconds * self.rng.uniform(.7, 1.5),
                       phase_step=0, next_at=now, visited_at=now,
                       recovery_until=0.0, last_ranked=0.0)
        runtime.setdefault("cycle", 0)
        runtime.setdefault("seed_level", state["party"][0]["level"])
        runtime.setdefault("relocate", False)
        runtime.setdefault("consecutive_losses", 0)
        bot = {"id": row["id"], "state": state, "runtime": runtime,
               "stats": {key: row.get("stats", {}).get(key, 0) for key in STAT_KEYS},
               "ordinal": ordinal, "rng": random.Random(self.seed + ordinal * 7919)}
        self.bots[bot["id"]] = bot
        self.by_map[state["map_id"]].add(bot["id"])
        self.counters.update(bot["stats"])
        # Stagger the complete fleet over five seconds, without favouring low IDs.
        delay = ((ordinal * 3571) % max(1, self.count)) / max(1, self.count) * 5
        self._schedule(bot, now + delay)

    def _schedule(self, bot, when):
        self.serial += 1
        bot["runtime"]["next_at"] = float(when)
        bot["runtime"]["ticket"] = self.serial
        heapq.heappush(self.heap, (float(when), self.serial, bot["id"]))

    def _increment(self, bot, key, value=1):
        if not value:
            return
        bot["stats"][key] += value
        self.counters[key] += value
        self.pending_counters[key] += value
        self.dirty.add(bot["id"])

    def _record(self, bot, kind, text, **metadata):
        event = {"id": uuid.uuid4().hex, "bot_id": bot["id"], "name": bot["state"]["username"],
                 "kind": kind, "text": text, "at": time.time(), "metadata": metadata}
        self.events.append(event)
        self.pending_events.append(event)
        # Only the latest 100 events are requested; retain bounded memory even if
        # persistence is temporarily unavailable. Totals remain in bot documents.
        if len(self.pending_events) > 100:
            del self.pending_events[:-100]

    def _execute(self, bot, op, payload):
        state = bot["state"]
        old_levels = {m["uid"]: m["level"] for m in state["party"]}
        old_wins, old_losses = state.get("wins", 0), state.get("losses", 0)
        self.engine.handle(state, op, payload)
        self.dirty.add(bot["id"])
        self._increment(bot, "wild_wins", state.get("wins", 0) - old_wins)
        self._increment(bot, "wild_losses", state.get("losses", 0) - old_losses)
        for monster in state["party"]:
            levels = max(0, monster["level"] - old_levels.get(monster["uid"], monster["level"]))
            self._increment(bot, "level_ups", levels)
        for event in state.get("events", []):
            kind = event.get("kind")
            if kind == "scan" and event.get("amount", 0) > 0:
                self._increment(bot, "scans")
                self._increment(bot, "scan_data", int(event["amount"]))
            elif kind == "win":
                self._increment(bot, "xp_earned", int(event.get("xp", 0)))
                self._record(bot, "wild_win", event["text"], map_id=state["map_id"],
                             level=max(m["level"] for m in state["party"]))
            elif kind == "lose":
                self._record(bot, "wild_loss", event["text"], map_id=state["map_id"])
        if state.get("losses", 0) > old_losses:
            bot["runtime"]["consecutive_losses"] += 1
            bot["runtime"]["relocate"] = True
            # Recovery leaves the bot absent in the Lab for a visible pause.
            bot["runtime"]["recovery_until"] = self.last_tick + 12
            self._increment(bot, "heals")  # Engine emergency recovery actually occurred.
        elif state.get("wins", 0) > old_wins:
            bot["runtime"]["consecutive_losses"] = 0

    def tick(self, now=None, dt=.1, budget=160):
        now = time.monotonic() if now is None else float(now)
        started = time.perf_counter()
        with self.lock:
            if not self.initialized:
                raise RuntimeError("Initialize the rival population before ticking it.")
            self.last_tick = now
            handled = 0
            while self.heap and self.heap[0][0] <= now and handled < max(1, int(budget)):
                if handled and (time.perf_counter() - started) * 1000 >= self.turn_budget_ms:
                    break
                due, ticket, ident = heapq.heappop(self.heap)
                bot = self.bots[ident]
                if bot["runtime"]["ticket"] != ticket:
                    continue
                self.max_lateness = max(self.max_lateness, max(0.0, now - due))
                try:
                    self._step(bot, now)
                except GameError as exc:
                    # A gameplay rejection should never strand a rival's scheduler.
                    self._increment(bot, "errors")
                    self._record(bot, "recovery", f"Action postponed: {exc}")
                    self._stop(bot, now)
                    if bot["state"].get("battle"):
                        self._execute(bot, "battle", {"action": "flee"})
                    bot["runtime"].update(phase="lab", phase_step=0)
                    self._schedule(bot, now + 3)
                except Exception:
                    # A transient SQL/ranked failure remains visible to the world
                    # host, but cannot permanently remove this bot from the heap.
                    self._schedule(bot, now + 5)
                    raise
                handled += 1
            self.processed += handled
            if now - self.last_save >= max(2, float(self.config.get("save_interval", self.config.get("checkpoint_seconds", 3)))):
                self.flush(now=now)
            self.last_tick_ms = (time.perf_counter() - started) * 1000
            return {"processed": handled, "pending": len(self.heap),
                    "overdue_seconds": max(0.0, now - self.heap[0][0]) if self.heap else 0.0}

    def _step(self, bot, now):
        runtime, state = bot["runtime"], bot["state"]
        phase = runtime["phase"]
        if phase == "explore":
            self._explore(bot, now)
        elif phase == "battle":
            self._wild_turn(bot, now)
        elif phase in ("lab", "recover"):
            self._lab_step(bot, now)
        elif phase == "ranked":
            self._ranked_step(bot, now)
        else:
            raise ValueError(f"Unknown persisted rival phase: {phase}")

    def _stop(self, bot, now):
        runtime, state = bot["runtime"], bot["state"]
        path = runtime.get("path")
        if path:
            x, y, _, _ = self.navigation.sample(path, now)
            # Routes have multiple corners: distance is travelled time * speed,
            # not displacement between their first and final coordinates.
            distance = self.navigation.SPEED * max(0, min(now, path["end"]) - path["start"])
            self._increment(bot, "walking_distance", round(distance, 3))
            state["x"], state["y"] = x, y
            runtime["path"] = None

    def _explore(self, bot, now):
        runtime, state, rng = bot["runtime"], bot["state"], bot["rng"]
        self._stop(bot, now)
        if state.get("in_lab"):
            self._execute(bot, "digilab", {"action": "return"})
        if runtime.get("relocate") or now >= runtime["leave_at"]:
            self._relocate(bot, now, easier=runtime.get("relocate", False))
        if now >= runtime["phase_until"]:
            self._execute(bot, "encounter", {})
            self._increment(bot, "wild_started")
            runtime["phase"] = "battle"
            self._schedule(bot, now + self.event_interval)
            return
        path = self.navigation.route(state["map_id"], state["x"], state["y"], rng, now,
                                     seconds=max(2, runtime["phase_until"] - now))
        if path:
            runtime["path"] = path
            self._increment(bot, "exploration_steps", len(path.get("segments", [path])))
            self._schedule(bot, min(runtime["phase_until"], runtime["path"]["end"]))
        else:
            # No teleport escape: remain at safe ground and try another heading.
            self._schedule(bot, now + 1.5)

    def _wild_turn(self, bot, now):
        state, runtime = bot["state"], bot["runtime"]
        if state.get("battle"):
            payload = self._battle_action(bot)
            self._execute(bot, "battle", payload)
            if payload["action"] == "swap":
                self._increment(bot, "party_swaps")
            elif payload["action"] == "item":
                self._increment(bot, "items_used")
        if state.get("battle"):
            self._schedule(bot, now + self.event_interval * bot["rng"].uniform(.85, 1.2))
        else:
            runtime.update(phase="lab", phase_step=0)
            self._schedule(bot, now + 2.5)

    def _battle_action(self, bot):
        state, battle = bot["state"], bot["state"]["battle"]
        actor_index = battle["actor"]
        actor = state["party"][actor_index]
        health = actor["hp"] / actor["max_hp"]
        if health < .23:
            reserve = [i for i, m in enumerate(state["party"]) if i not in battle["active"]
                       and m["hp"] / m["max_hp"] > .6]
            if reserve:
                return {"action": "swap", "party_index": max(reserve, key=lambda i: state["party"][i]["hp"])}
            for item in ("hp_s", "hp_m", "hp_l"):
                if state["inventory"].get(item, 0):
                    return {"action": "item", "item": item, "party_index": actor_index}
        affordable = [(i, skill) for i, skill in enumerate(actor["skills"]) if actor["sp"] >= skill["sp"]]
        living = [(i, enemy) for i, enemy in enumerate(battle["enemies"]) if enemy["hp"] > 0]
        # Finish an enemy quickly, while comparing its real defenses and affinity.
        choices = []
        for target, enemy in living:
            for skill_index, skill in affordable:
                attack = actor["int"] if skill.get("kind") == "magic" else actor["atk"]
                defense = enemy["int"] if skill.get("kind") == "magic" else enemy["def"]
                damage = max(1, (8 + attack * .72 - defense * .28) * skill["power"]
                             * effectiveness(actor, enemy, skill["attribute"]))
                choices.append((damage / max(1, enemy["hp"]), target, skill_index))
        if choices:
            _, target, skill_index = max(choices)
            return {"action": "skill", "target": target, "skill_index": skill_index}
        if actor["sp"] == 0 and state["inventory"].get("sp_s", 0) and actor["max_sp"] >= 25:
            return {"action": "item", "item": "sp_s", "party_index": actor_index}
        target = min(living, key=lambda pair: pair[1]["hp"] / max(.1, effectiveness(actor, pair[1])))[0]
        return {"action": "struggle" if actor["sp"] == 0 else "attack", "target": target}

    def _lab_step(self, bot, now):
        state, runtime = bot["state"], bot["runtime"]
        self._stop(bot, now)
        step = runtime.get("phase_step", 0)
        if step == 0:
            self._execute(bot, "digilab", {"action": "heal" if state.get("in_lab") else "enter"})
            self._increment(bot, "heals")
            self._record(bot, "heal", "Recovered party HP and SP in the DigiLab.")
        elif step == 1:
            self._materialize(bot)
        elif step == 2:
            self._evolve(bot)
        elif step == 3:
            self._manage_party(bot)
        elif step == 4:
            self._shop(bot)
        else:
            if now < runtime.get("recovery_until", 0):
                self._schedule(bot, runtime["recovery_until"])
                return
            self._execute(bot, "digilab", {"action": "return"})
            runtime.update(phase="ranked", phase_step=0)
            self._schedule(bot, now + 2)
            return
        runtime["phase_step"] = step + 1
        self._schedule(bot, now + self.event_interval * 1.4)

    def _materialize(self, bot):
        state = bot["state"]
        if len(state["storage"]) >= 48:
            return
        ready = [sid for sid, progress in state["scan"].items() if progress >= 100]
        known = {m["species_id"] for m in state["party"] + state["storage"]}
        # New species first; enough duplicates to fill all six real party slots.
        ready.sort(key=lambda sid: (sid in known, not self.engine.species[sid].get("paradox"), sid))
        for sid in ready[:2]:
            if sid in known and len(state["party"]) >= 6:
                continue
            progress = state["scan"][sid]
            self._execute(bot, "materialize", {"species_id": sid})
            self._increment(bot, "materialized")
            if self.engine.species[sid].get("paradox"):
                self._increment(bot, "paradox_materialized")
            self._record(bot, "materialize", f"Materialized {self.engine.species[sid]['name']} from {progress}% scan data.",
                         species_id=sid, scan_before=progress)
            known.add(sid)

    def _evolve(self, bot):
        state, runtime = bot["state"], bot["runtime"]
        if len(state["party"]) == 1 and int(self.engine.maps[state["map_id"]].get("level", 1)) > 3:
            # Keep one capable partner while scan collection earns a second one.
            return
        # At most one identity-preserving evolution per cycle; do not downgrade a
        # sole partner without a clear ABI requirement, or repeatedly flip forms.
        for index in sorted(range(len(state["party"])), key=lambda slot: state["party"][slot]["level"]):
            monster = state["party"][index]
            sector_level = int(self.engine.maps[state["map_id"]].get("level", 1))
            other_strength = max((member["level"] for slot, member in enumerate(state["party"][:3]) if slot != index), default=1)
            if sector_level > 3 and other_strength < sector_level + 1:
                # Never reset the only capable partner just because its first
                # freshly materialized level-one recruit has joined the party.
                continue
            options = self.engine.evolution_options(monster)
            eligible = [route for route in options if route["eligible"] and not route.get("devolve")]
            down = False
            if not eligible and monster["level"] >= 30 and len(state["party"]) >= 3:
                needs_abi = any(not route.get("devolve") and route.get("abi", 0) > monster["abi"] for route in options)
                if needs_abi:
                    eligible = [route for route in options if route["eligible"] and route.get("devolve")
                                and route["to"] in monster.get("history", [])]
                    down = True
            if eligible:
                route = eligible[bot["rng"].randrange(len(eligible))]
                old_name = monster["name"]
                self._execute(bot, "evolve", {"party_index": index, "to": route["to"]})
                self._increment(bot, "devolutions" if down else "evolutions")
                self._record(bot, "devolve" if down else "evolve", f"{old_name} became {route['name']}.")
                # A reset-to-level-one team must choose a viable training sector.
                strongest = max(m["level"] for m in state["party"][:3])
                if strongest + 3 < int(self.engine.maps[state["map_id"]].get("level", 1)):
                    runtime["relocate"] = True
                break

    def _manage_party(self, bot):
        state = bot["state"]
        # Rotate reserves into active slots so every earned partner trains; keeping
        # the strongest lead protects a fresh level-one recruit in tougher areas.
        if len(state["party"]) > 3:
            index = min(range(3, len(state["party"])), key=lambda i: state["party"][i]["level"])
            self._execute(bot, "party", {"action": "lead", "index": index})
            self._increment(bot, "party_swaps")
        if len(state["party"]) > 1:
            strongest = max(range(len(state["party"])), key=lambda i: (state["party"][i]["level"], state["party"][i]["max_hp"]))
            if strongest:
                self._execute(bot, "party", {"action": "lead", "index": strongest})
                self._increment(bot, "party_swaps")
        # Periodically train a banked species by exchanging a mature duplicate.
        if state["storage"] and bot["runtime"].get("cycle", 0) % 5 == 4:
            if len(state["party"]) >= 6:
                duplicate = next((i for i in range(3, len(state["party"]))
                                  if sum(m["species_id"] == state["party"][i]["species_id"] for m in state["party"]) > 1), None)
                if duplicate is not None:
                    self._execute(bot, "party", {"action": "deposit", "index": duplicate})
                    self._increment(bot, "party_swaps")
            if len(state["party"]) < 6:
                self._execute(bot, "party", {"action": "withdraw", "index": 0})
                self._increment(bot, "party_swaps")

    def _shop(self, bot):
        state = bot["state"]
        for item, desired in (("hp_s", 3), ("sp_s", 2)):
            quantity = min(max(0, desired - state["inventory"].get(item, 0)),
                           max(0, (state["credits"] - 150) // SHOP[item]["price"]))
            if quantity:
                self._execute(bot, "shop", {"item": item, "quantity": quantity})
                self._increment(bot, "purchases", quantity)
                self._record(bot, "shop", f"Bought {quantity} {SHOP[item]['name']}.", item=item, quantity=quantity)

    def _rank_profile(self, bot):
        state = bot["state"]
        return {"id": bot["id"], "name": state["username"], "username": state["username"],
                "tamer": state["tamer"], "kind": "bot", "is_bot": True,
                "map_id": state["map_id"], "party": copy.deepcopy(state["party"])}

    def _ranked_step(self, bot, now):
        runtime = bot["runtime"]
        if self.ranked:
            self.ranked.register_participant(bot["id"], self._rank_profile(bot))
            try:
                result = self.ranked.start_match(bot["id"])
            except GameError as exc:
                # Energy/cooldown limits apply equally to rivals. Move on to
                # training while entry refills, rather than looping in the Lab.
                runtime["ranked_wait_reason"] = str(exc)[:200]
            else:
                if not result.get("duplicate"):
                    self._increment(bot, "ranked_started")
                self.record_ranked_result(result)
                runtime["last_ranked"] = now
                runtime.pop("ranked_wait_reason", None)
        runtime["cycle"] += 1
        runtime.update(phase="explore", phase_until=now + self.walk_seconds * bot["rng"].uniform(.7, 1.5))
        self._schedule(bot, now + 1)

    def record_ranked_result(self, result):
        """Call once for externally initiated human/bot ranked results as well."""
        with self.lock:
            match_id = result.get("id", result.get("match_id"))
            if result.get("duplicate") or (match_id and match_id in self.seen_match_ids):
                return
            if match_id:
                if len(self.seen_matches) == self.seen_matches.maxlen:
                    self.seen_match_ids.discard(self.seen_matches[0])
                self.seen_matches.append(match_id)
                self.seen_match_ids.add(match_id)
            for ident in (result.get("attacker_id"), result.get("defender_id")):
                bot = self.bots.get(ident)
                if not bot:
                    continue
                won = ident == result.get("winner_id")
                key = ("ranked_" if result.get("ranked", True) else "rival_") + ("wins" if won else "losses")
                self._increment(bot, key)
                self._record(bot, ("ranked_" if result.get("ranked", True) else "rival_") + ("win" if won else "loss"),
                             ("Won" if won else "Lost") + (" a ranked battle." if result.get("ranked", True) else " a friendly rival challenge."),
                             match_id=result.get("id", result.get("match_id")),
                             opponent_id=result.get("defender_id") if ident == result.get("attacker_id") else result.get("attacker_id"))

    def record_rival_result(self, bot_id, result):
        self.record_ranked_result({**result, "ranked": False})

    def _relocate(self, bot, now, easier=False):
        state, runtime = bot["state"], bot["runtime"]
        old_map = state["map_id"]
        old_level = int(self.engine.maps[old_map].get("level", 1))
        strength = max(m["level"] for m in state["party"][:3])
        if easier:
            ceiling = max(1, min(strength, old_level - max(2, runtime.get("consecutive_losses", 1) * 2)))
            candidates = [area for area in self.engine.maps.values()
                          if max(1, ceiling - 4) <= int(area.get("level", 1)) <= ceiling and area["id"] != old_map]
        else:
            candidates = [area for area in self.engine.maps.values()
                          if max(1, strength - 12) <= int(area.get("level", 1)) <= strength + 2 and area["id"] != old_map]
        if not candidates:
            candidates = [area for area in self.engine.maps.values() if area["id"] != old_map
                          and int(area.get("level", 1)) <= max(1, strength)]
        if candidates:
            # Density first; a tiny deterministic jitter breaks ties without a
            # handful of alphabetically first sectors receiving the whole fleet.
            target = min(candidates, key=lambda area: len(self.by_map[area["id"]]) + bot["rng"].random() * .7)
            self._execute(bot, "travel", {"map_id": target["id"]})
            # Travel uses the same exact catalog spawn as a player's sector change.
            self.by_map[old_map].discard(bot["id"])
            self.by_map[target["id"]].add(bot["id"])
            self._increment(bot, "travels")
            self._record(bot, "travel", f"Moved to {target['name']}" + (" for safer training." if easier else " to explore."),
                         from_map=old_map, map_id=target["id"], reason="difficulty" if easier else "exploration")
        runtime.update(relocate=False, visited_at=now, leave_at=now + bot["rng"].uniform(self.dwell_min, self.dwell_max))

    def snapshot(self, map_id, now=None):
        now = time.monotonic() if now is None else float(now)
        with self.lock:
            result = []
            for ident in sorted(self.by_map.get(map_id, ())):
                bot = self.bots[ident]
                state, runtime = bot["state"], bot["runtime"]
                if state.get("in_lab"):
                    continue
                sample = self.navigation.sample(runtime.get("path"), now)
                x, y, dx, dy = sample if sample else (state["x"], state["y"], 0.0, 0.0)
                result.append({"id": ident, "username": state["username"], "name": state["username"],
                               "is_bot": True, "tamer": state["tamer"], "map_id": map_id,
                               "x": x, "y": y, "dx": round(dx, 5), "dy": round(dy, 5),
                               "moving": bool(dx or dy), "lead": state["party"][0]["species_id"],
                               "battle": bool(state.get("battle")), "in_lab": False,
                               "status": PHASE_NAMES.get(runtime["phase"], "Exploring"),
                               "activity": runtime["phase"], "level": max(m["level"] for m in state["party"])})
            return result

    def profile(self, ident):
        with self.lock:
            bot = self.bots.get(str(ident))
            if not bot:
                raise GameError("That rival was not found.")
            state, runtime = bot["state"], bot["runtime"]
            result = {"id": bot["id"], "name": state["username"], "username": state["username"],
                      "is_bot": True, "kind": "bot", "tamer": state["tamer"], "map_id": state["map_id"],
                      "map_name": self.engine.maps[state["map_id"]]["name"],
                      "status": PHASE_NAMES.get(runtime["phase"], "Exploring"), "activity": runtime["phase"],
                      "party": copy.deepcopy(state["party"]), "stats": dict(bot["stats"]),
                      "scan_ready": sum(value >= 100 for value in state["scan"].values()),
                      "scan_species": sum(value > 0 for value in state["scan"].values()),
                      "storage_count": len(state["storage"]), "credits": state["credits"],
                      "cycle": runtime["cycle"], "next_activity": NEXT_PHASE.get(runtime["phase"], "Exploration"),
                      "seed_level": runtime["seed_level"]}
            sample = self.navigation.sample(runtime.get("path"), self.last_tick)
            result.update(x=sample[0] if sample else state["x"], y=sample[1] if sample else state["y"],
                          in_lab=bool(state.get("in_lab")), battle=bool(state.get("battle")))
            return result

    def directory(self, query="", offset=0, limit=50):
        query = str(query).strip().casefold()[:64]
        offset, limit = max(0, int(offset)), max(1, min(100, int(limit)))
        with self.lock:
            matches = [bot for bot in self.bots.values() if not query or query in bot["id"].casefold()
                       or query in bot["state"]["username"].casefold()
                       or query in self.engine.maps[bot["state"]["map_id"]]["name"].casefold()]
            entries = []
            for bot in matches[offset:offset + limit]:
                state, runtime = bot["state"], bot["runtime"]
                entries.append({"id": bot["id"], "name": state["username"], "username": state["username"],
                                "tamer": state["tamer"], "is_bot": True, "map_id": state["map_id"],
                                "map_name": self.engine.maps[state["map_id"]]["name"],
                                "level": max(m["level"] for m in state["party"]),
                                "party_size": len(state["party"]), "activity": runtime["phase"],
                                "status": PHASE_NAMES.get(runtime["phase"], "Exploring"),
                                "stats": dict(bot["stats"])})
            return {"entries": entries, "total": len(matches), "offset": offset, "limit": limit}

    def challenge_candidates(self, state, limit=5):
        """Only actual present rivals can issue a same-sector invitation."""
        with self.lock:
            entries = [entry for entry in self.snapshot(state["map_id"], self.last_tick)
                       if not entry["battle"] and entry["activity"] == "explore"]
            entries.sort(key=lambda entry: (math.hypot(entry["x"] - state["x"], entry["y"] - state["y"]), entry["id"]))
            return entries[:max(0, min(10, int(limit)))]

    def activity(self, limit=100):
        limit = max(1, min(100, int(limit)))
        with self.lock:
            phases = Counter(bot["runtime"]["phase"] for bot in self.bots.values())
            return {"population": len(self.bots), "active": len(self.bots),
                    "total_maps": len(self.by_map), "occupied_maps": sum(bool(v) for v in self.by_map.values()),
                    "counters": dict(self.counters), "phases": dict(phases),
                    "events": list(reversed(copy.deepcopy(list(self.events))))[:limit],
                    "scheduler": {"processed": self.processed, "last_tick_ms": round(self.last_tick_ms, 3),
                                  "max_lateness_seconds": round(self.max_lateness, 3),
                                  "overdue_seconds": round(max(0.0, self.last_tick - self.heap[0][0]), 3) if self.heap else 0},
                    "maps": [{"id": ident, "name": self.engine.maps[ident]["name"], "count": len(members),
                              "level": int(self.engine.maps[ident].get("level", 1))}
                             for ident, members in self.by_map.items()]}

    def _serialize(self, bot, now):
        state = copy.deepcopy(bot["state"])
        state["events"] = []
        sample = self.navigation.sample(bot["runtime"].get("path"), now)
        if sample:
            state["x"], state["y"] = sample[:2]
        runtime = {key: copy.deepcopy(value) for key, value in bot["runtime"].items()
                   if key not in {"path", "ticket", "next_at", "leave_at", "phase_until", "visited_at",
                                  "recovery_until", "last_ranked"}}
        runtime["dwell_remaining"] = max(0.0, bot["runtime"]["leave_at"] - now)
        return {"id": bot["id"], "state": state, "runtime": runtime, "stats": dict(bot["stats"])}

    def flush(self, force=False, now=None):
        now = self.last_tick if now is None else float(now)
        with self.lock:
            # Sort by ordinal rotation so continuously dirty early IDs cannot starve
            # later rows. Taking every dirty row in bounded SQL chunks is inexpensive
            # compared with serializing the world for every websocket recipient.
            ids = sorted(self.dirty)
            if not force and ids:
                cursor = int(getattr(self, "save_cursor", 0))
                ids.sort(key=lambda ident: (self.bots[ident]["ordinal"] - cursor) % max(1, self.count))
                ids = ids[:max(50, min(500, int(self.config.get("save_batch", 100))))]
            for start in range(0, len(ids), 500):
                subset = ids[start:start + 500]
                self.store.bot_save_batch([self._serialize(self.bots[ident], now) for ident in subset])
                self.dirty.difference_update(subset)
            if ids:
                self.save_cursor = (self.bots[ids[-1]]["ordinal"] + 1) % max(1, self.count)
            if (self.pending_events or self.pending_counters) and hasattr(self.store, "add_events"):
                self.store.add_events(list(self.pending_events), dict(self.pending_counters))
                self.pending_events.clear()
                self.pending_counters.clear()
            self.last_save = now

    def close(self):
        self.flush(force=True)
