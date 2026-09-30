"""Persistent, authoritative rival population without synthetic player sockets.

Wild combat, scan conversion, shopping, evolution and party changes go through
GameEngine.handle, exactly like human requests. Ranked combat belongs to the
shared RankedService. Counters are consequences of these operations, never dice
rolls masquerading as battles. Fresh rivals have one level-seeded Rookie so all
catalog sectors have viable inhabitants; that initial level is not reported as XP.
"""
from __future__ import annotations

import copy
import heapq
import logging
import math
import random
import threading
import time
import uuid
from collections import Counter, deque

from venom.common.game import GameError, SHOP, STAGE_RANK, effectiveness, variety_of
from venom.common.population import DEFAULT_BOTS, MAX_BOTS
from .activity_window import RollingActivity, WINDOW_SECONDS, EVENT_LIMIT
from .navigation import Navigation

LOG = logging.getLogger('venom.bots')
STARTUP_BATCH = 100


STAT_KEYS = (
    "wild_wins", "wild_losses", "wild_started", "ranked_wins", "ranked_losses",
    "ranked_started", "rival_wins", "rival_losses", "scans", "scan_data",
    "materialized", "paradox_materialized", "shiny_materialized", "firewall_materialized", "level_ups", "xp_earned",
    "evolutions", "devolutions", "heals", "items_used", "purchases",
    "party_swaps", "travels", "walking_distance", "exploration_steps", "errors",
    "training_rotations", "teams_trained", "coverage_visits",
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
        self.count = max(0, min(MAX_BOTS, int(self.config.get("count", DEFAULT_BOTS))))
        self.enabled = bool(self.config.get("enabled", True))
        if not self.enabled:
            self.count = 0
        self.seed = int(self.config.get("seed", 741029))
        self.rng = random.Random(self.seed)
        self.lock = threading.RLock()
        self.navigation = Navigation(engine.root, engine.maps)
        self.bots = {}
        self.by_map = {key: set() for key in engine.maps}
        self.map_order = sorted(engine.maps)
        self.map_indices = {key: index for index, key in enumerate(self.map_order)}
        self.training_ceiling = min(99, max(64, max(
            (int(area.get("level", 1)) for area in engine.maps.values()), default=1)))
        self.coverage_reservations = {key: set() for key in engine.maps}
        self.heap = []
        self.serial = 0
        self.dirty = set()
        self.activity_window = RollingActivity(STAT_KEYS)
        self.counters = self.activity_window.counters
        self.events = deque(maxlen=EVENT_LIMIT)
        self.pending_events = []
        self.pending_counters = Counter()
        self.pending_buckets = {}
        self.pending_activity_batch = None
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
        realtime = now is None
        now = time.monotonic() if now is None else float(now)
        with self.lock:
            if self.initialized:
                return
            LOG.info('Loading saved rival tamers in batches of %d; no overall loading deadline.', STARTUP_BATCH)
            # Keep only one decoded page in addition to the live population.
            # A mature world can contain hundreds of thousands of partners;
            # fetching every JSON document and then copying it doubles peak RAM.
            loaded = iter(self._saved_rows()) if self.count else iter(())
            saved = next(loaded, None)
            LOG.info('Reconciling rival counters with committed ranked matches...')
            ranked_totals = self.store.ranked_totals() if hasattr(self.store, "ranked_totals") else {}
            maps = sorted(self.engine.maps)
            tamers = sorted(self.engine.tamers)
            profiles, new_ids = [], []
            restored = created = 0
            for ordinal in range(self.count):
                ident = f"bot:{ordinal + 1:05d}"
                while saved is not None and str(saved['id']) < ident:
                    saved = next(loaded, None)
                row = saved if saved is not None and str(saved['id']) == ident else None
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
                    new_ids.append(ident)
                    created += 1
                else:
                    restored += 1
                if ident in ranked_totals:
                    row.setdefault("stats", {}).update(ranked_totals[ident])
                # Database pages and MemoryStore fixtures return owned decoded
                # objects; the live bot can adopt them without a second copy.
                self._restore(row, ordinal, now, owned=True)
                if row is saved:
                    saved = next(loaded, None)
                if self.ranked:
                    profiles.append(self._rank_profile(self.bots[ident]))
                if (ordinal + 1) % STARTUP_BATCH == 0 or ordinal + 1 == self.count:
                    if self.ranked and profiles:
                        self.ranked.register_many(profiles)
                        profiles.clear()
                    if new_ids:
                        self.store.bot_save_batch([self._serialize(self.bots[key], now) for key in new_ids])
                        new_ids.clear()
                    LOG.info('Rival tamers loaded: %d / %d (%d restored, %d new).',
                             ordinal + 1, self.count, restored, created)
            wall_now = time.time()
            if hasattr(self.store, "activity_snapshot"):
                history = self.store.activity_snapshot(now=wall_now)
                self.activity_window.restore(history, wall_now)
                self.events.extend(reversed(history.get("events", [])))
            elif hasattr(self.store, "activity"):
                # Legacy test adapters can retain their recent event feed, but
                # undated totals must never become new twelve-hour activity.
                history = self.store.activity(limit=EVENT_LIMIT)
                self.events.extend(reversed(history.get("events", [])))
            self._expire_activity(wall_now)
            self.dirty.clear()
            if realtime:
                # Loading time is not simulation time. Start saved dwell timers
                # and the staggered scheduler when the world is actually ready.
                ready_at = time.monotonic()
                elapsed = max(0.0, ready_at - now)
                for bot in self.bots.values():
                    for key in ('leave_at', 'phase_until', 'next_at', 'visited_at'):
                        bot['runtime'][key] += elapsed
                self.heap = [(due + elapsed, ticket, ident) for due, ticket, ident in self.heap]
                now = ready_at
            self.last_save = self.last_tick = now
            self.initialized = True
            LOG.info('Rival population ready: %d tamers; saved partners and progress retained.', len(self.bots))

    def _saved_rows(self):
        if not hasattr(self.store, 'bot_load_batch'):
            # Small in-memory test stores retain the original adapter contract.
            yield from sorted(self.store.bot_load_all(), key=lambda row: str(row['id']))
            return
        after = ''
        while True:
            rows = self.store.bot_load_batch(after_id=after, limit=STARTUP_BATCH)
            if not rows:
                return
            for row in rows:
                ident = str(row['id'])
                if ident <= after:
                    raise ValueError('Saved rival pages are out of order; no progress was discarded.')
                after = ident
                yield row

    @staticmethod
    def _name(ordinal):
        first = ("Nova", "Echo", "Cobalt", "Luna", "Aster", "Rift", "Pixel", "Terra",
                 "Ember", "Frost", "Kite", "Sora", "Onyx", "Comet", "Azure", "Violet")
        second = ("Scout", "Cipher", "Ranger", "Pulse", "Warden", "Link", "Voyager", "Spark")
        return f"AI {first[ordinal % len(first)]}{second[(ordinal // len(first)) % len(second)]}{ordinal + 1:04d}"

    def _restore(self, row, ordinal, now, *, owned=False):
        state = row["state"] if owned else copy.deepcopy(row["state"])
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
                       recovery_until=0.0, last_ranked=0.0, walk_pending=True)
        runtime.setdefault("cycle", 0)
        runtime.setdefault("seed_level", state["party"][0]["level"])
        runtime.setdefault("relocate", False)
        runtime.setdefault("consecutive_losses", 0)
        # A single stable cursor avoids a growing per-rival travel history. It
        # survives restarts and also works when new catalog regions are added.
        runtime.setdefault("route_after_map", state["map_id"])
        bot = {"id": row["id"], "state": state, "runtime": runtime,
               "stats": {key: row.get("stats", {}).get(key, 0) for key in STAT_KEYS},
               "ordinal": ordinal, "rng": random.Random(self.seed + ordinal * 7919)}
        self.bots[bot["id"]] = bot
        self.by_map[state["map_id"]].add(bot["id"])
        if runtime.get("coverage_target") in self.coverage_reservations:
            self.coverage_reservations[runtime["coverage_target"]].add(bot["id"])
        # Career counters are fixed-size gameplay records. Global observatory
        # totals come only from timestamped activity, never from a career sum.
        # Stagger the complete fleet over five seconds, without favouring low IDs.
        delay = ((ordinal * 3571) % max(1, self.count)) / max(1, self.count) * 5
        self._schedule(bot, now + delay)

    def _schedule(self, bot, when):
        self.serial += 1
        bot["runtime"]["next_at"] = float(when)
        bot["runtime"]["ticket"] = self.serial
        # Runtime-only transitions matter too (for example ranked energy waits,
        # completed training visits and resumed exploration). They must survive
        # a checkpoint even when no inventory or battle operation dirtied state.
        self.dirty.add(bot["id"])
        heapq.heappush(self.heap, (float(when), self.serial, bot["id"]))

    def _increment(self, bot, key, value=1):
        if not value:
            return
        bot["stats"][key] += value
        wall_now = time.time()
        stamp = self.activity_window.record(key, value, wall_now)
        if stamp not in self.pending_buckets:
            # Even a custom, unusually long checkpoint interval cannot build
            # an unbounded queue of expired minute aggregates in memory.
            self._expire_activity(wall_now)
        self.pending_buckets.setdefault(stamp, Counter())[key] += value
        self.pending_counters[key] += value
        self.dirty.add(bot["id"])

    def _record(self, bot, kind, text, **metadata):
        event = {"id": uuid.uuid4().hex, "bot_id": bot["id"], "name": bot["state"]["username"],
                 "kind": kind, "text": text, "at": time.time(), "metadata": metadata}
        self.events.append(event)
        self.pending_events.append(event)
        # Telemetry is bounded independently of durable gameplay checkpoints.
        if len(self.pending_events) > EVENT_LIMIT:
            del self.pending_events[:-EVENT_LIMIT]

    def _expire_activity(self, now):
        self.activity_window.advance(now)
        cutoff = now - WINDOW_SECONDS
        self.events = deque((event for event in self.events if cutoff < event.get('at', 0) <= now),
                            maxlen=EVENT_LIMIT)
        self.pending_events = [event for event in self.pending_events if cutoff < event.get('at', 0) <= now]
        self.pending_buckets = {at: values for at, values in self.pending_buckets.items() if cutoff < at <= now}
        self.pending_counters.clear()
        for values in self.pending_buckets.values():
            self.pending_counters.update(values)

    def _flush_activity(self, now):
        """Freeze retry identity and payload until a write is acknowledged.

        A lost commit acknowledgement must not double count an older batch
        when new activity arrives before its retry. Expired batches remain
        timestamped and are rejected by the store instead of being re-dated.
        """
        self._expire_activity(now)
        if hasattr(self.store, 'add_activity_batch'):
            while self.pending_activity_batch or self.pending_events or self.pending_buckets:
                if self.pending_activity_batch is None:
                    self.pending_activity_batch = {
                        'batch_id': uuid.uuid4().hex, 'batch_at': now,
                        'events': self.pending_events,
                        'buckets': [{'at': at, 'counters': dict(values)}
                                    for at, values in sorted(self.pending_buckets.items())]}
                    self.pending_events = []
                    self.pending_buckets = {}
                    self.pending_counters.clear()
                self.store.add_activity_batch(**self.pending_activity_batch, now=now)
                self.pending_activity_batch = None
        elif (self.pending_events or self.pending_counters) and hasattr(self.store, 'add_events'):
            self.store.add_events(list(self.pending_events), dict(self.pending_counters))
            self.pending_events.clear()
            self.pending_buckets.clear()
            self.pending_counters.clear()
        if hasattr(self.store, 'maintain_activity'):
            # This also runs for an idle or disabled population, so expired
            # telemetry does not depend on another battle being played.
            self.store.maintain_activity(now=now)

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
            distance = self.navigation.SPEED * max(0, (now if path.get("loop") else min(now, path["end"])) - path["start"])
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
        if runtime.pop("walk_pending", False):
            # Start the walking window on dispatch, not before SQL/startup work.
            runtime["phase_until"] = now + self.walk_seconds * rng.uniform(.7, 1.5)
        if now >= runtime["phase_until"]:
            self._execute(bot, "encounter", {})
            self._increment(bot, "wild_started")
            runtime["phase"] = "battle"
            self._schedule(bot, now + self.event_interval)
            return
        path = self.navigation.patrol(state["map_id"], state["x"], state["y"], rng, now,
                                     seconds=max(2, runtime["phase_until"] - now))
        if path:
            runtime["path"] = path
            self._increment(bot, "exploration_steps", len(path.get("segments", [path])))
            self._schedule(bot, runtime["phase_until"])
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
        return {"action": "attack", "target": target}

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
            self._manage_party(bot)
        elif step == 3:
            self._evolve(bot)
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
        # Earned duplicates supply later training rounds too; never mint scan data.
        ready.sort(key=lambda sid: (sid in known, variety_of(self.engine.species[sid]) == "normal", sid))
        for sid in ready[:2]:
            if len(state["storage"]) >= 48:
                break
            progress = state["scan"][sid]
            self._execute(bot, "materialize", {"species_id": sid})
            self._increment(bot, "materialized")
            if self.engine.species[sid].get("paradox"):
                self._increment(bot, "paradox_materialized")
            if self.engine.species[sid].get("shiny"):
                self._increment(bot, "shiny_materialized")
            if self.engine.species[sid].get("firewall"):
                self._increment(bot, "firewall_materialized")
            self._record(bot, "materialize", f"Materialized {self.engine.species[sid]['name']} from {progress}% scan data.",
                         species_id=sid, scan_before=progress)
            known.add(sid)

    @staticmethod
    def _field_level(party):
        # A high-level reserve must not send a fresh field team into lethal maps.
        return min((m["level"] for m in party[:3]), default=1)

    def _coverage_quota(self):
        """Aim for a fair share of the population on every catalog field.

        Visits remain bounded and capability checks still apply. This is a
        target for earned teams, never permission to create levels or partners.
        """
        return max(1, self.count // max(1, len(self.by_map)))

    def _map_load(self, map_id):
        """Residents plus reserved arrivals, without counting anyone twice.

        A planned departure remains a resident until travel actually succeeds;
        restored battles and Lab work must not advertise imaginary vacancies.
        """
        arriving = self.coverage_reservations[map_id] - self.by_map[map_id]
        return len(self.by_map[map_id]) + len(arriving)

    def _coverage_guard(self, bot):
        """Retain some capable teams while other residents start fresh cohorts.

        Count actual field strength, not merely map membership: low-level teams
        awaiting their next departure cannot stand in for experienced residents.
        Small custom populations remain free to train without a coverage quota.
        """
        if self.count < len(self.by_map) * 2:
            return False
        state = bot["state"]
        level = int(self.engine.maps[state["map_id"]].get("level", 1))
        if level <= 3:
            return False
        quota = self._coverage_quota()
        capable = sum(self._field_level(self.bots[ident]["state"]["party"]) + 2 >= level
                      for ident in self.by_map[state["map_id"]] if ident != bot["id"]
                      and self.bots[ident]["runtime"].get("coverage_target") in (None, state["map_id"]))
        capable += len(self.coverage_reservations[state["map_id"]] - self.by_map[state["map_id"]])
        return capable < quota

    def _observe_training(self, bot):
        runtime, state = bot["runtime"], bot["state"]
        cohort = set(runtime.get("training_uids", []))
        levels = [m["level"] for m in state["party"] if m["uid"] in cohort]
        if levels:
            runtime["training_peak"] = max(runtime.get("training_peak", 0), min(levels))

    def _reserve_coverage(self, bot, target=None):
        previous = bot["runtime"].pop("coverage_target", None)
        if previous in self.coverage_reservations:
            self.coverage_reservations[previous].discard(bot["id"])
        if target in self.coverage_reservations:
            self.coverage_reservations[target].add(bot["id"])
            bot["runtime"]["coverage_target"] = target

    def _evolve(self, bot):
        state, runtime = bot["state"], bot["runtime"]
        self._observe_training(bot)
        guarded = bool(runtime.get("coverage_duty"))
        frontier_goal = int(runtime.get("training_goal", 0))
        if len(state["party"]) + len(state["storage"]) == 1:
            # Earn a recruit before resetting the only established partner. This
            # leaves a real veteran available for later map-coverage visits.
            return
        for index in sorted(range(len(state["party"])), key=lambda i: state["party"][i]["level"]):
            monster = state["party"][index]
            if guarded and index < 3:
                continue
            # Endgame expeditions need genuinely earned high-level partners.
            # Resetting them at every eligible evolution/devolution threshold
            # would otherwise make the newly reachable 65-99 fields forever
            # inaccessible to an upgraded, previously level-60 population.
            if frontier_goal > 64 and monster["level"] < frontier_goal:
                continue
            options = self.engine.evolution_options(monster)
            eligible = [route for route in options if route["eligible"] and not route.get("devolve")]
            down = False
            if not eligible and monster["level"] >= 30:
                needs_abi = any(not route.get("devolve") and route.get("abi", 0) > monster["abi"] for route in options)
                # A full collection can keep training existing identities through
                # legitimate de-digivolution rather than deleting earned partners.
                if needs_abi or len(state["storage"]) >= 48:
                    eligible = [route for route in options if route["eligible"] and route.get("devolve")
                                and (len(state["storage"]) >= 48 or route["to"] in monster.get("history", []))]
                    down = True
            if eligible:
                if down:
                    familiar = [route for route in eligible if route["to"] in monster.get("history", [])]
                    eligible = familiar or eligible
                route = bot["rng"].choice(eligible)
                old_name = monster["name"]
                self._execute(bot, "evolve", {"party_index": index, "to": route["to"]})
                self._increment(bot, "devolutions" if down else "evolutions")
                self._record(bot, "devolve" if down else "evolve", f"{old_name} became {route['name']}.")
                if self._field_level(state["party"]) + 2 < int(self.engine.maps[state["map_id"]].get("level", 1)):
                    runtime["relocate"] = True
                break

    def _equip_party(self, bot, desired):
        """Change real Lab storage/party membership while retaining every UID."""
        state = bot["state"]
        desired = list(dict.fromkeys(desired))[:6]
        if not desired:
            return

        def action(kind, index):
            self._execute(bot, "party", {"action": kind, "index": index})
            self._increment(bot, "party_swaps")

        for index in range(len(state["party"]) - 1, -1, -1):
            if len(state["party"]) > 1 and state["party"][index]["uid"] not in desired:
                action("deposit", index)
        for uid in desired:
            index = next((i for i, m in enumerate(state["storage"]) if m["uid"] == uid), None)
            if index is not None:
                action("withdraw", index)
                # The last old partner protected the nonempty-party invariant;
                # release it as soon as the first requested partner is active.
                for slot in range(len(state["party"]) - 1, -1, -1):
                    if len(state["party"]) > 1 and state["party"][slot]["uid"] not in desired:
                        action("deposit", slot)
        for index in range(len(state["party"]) - 1, -1, -1):
            if len(state["party"]) > 1 and state["party"][index]["uid"] not in desired:
                action("deposit", index)
        for uid in reversed(desired):
            index = next(i for i, m in enumerate(state["party"]) if m["uid"] == uid)
            if index:
                action("lead", index)

    def _manage_party(self, bot):
        state, runtime = bot["state"], bot["runtime"]
        self.dirty.add(bot["id"])
        self._observe_training(bot)
        owned = state["party"] + state["storage"]
        by_uid = {m["uid"]: m for m in owned}
        current = [uid for uid in runtime.get("training_uids", []) if uid in by_uid]
        round_number = int(runtime.get("training_round", 1))
        goal = int(runtime.get("training_goal", self._training_goal(bot, round_number)))
        wins = bot["stats"]["wild_wins"] - runtime.get("training_start_wins", bot["stats"]["wild_wins"])
        peak = runtime.get("training_peak", 0)
        completed = bool(current) and (peak >= goal or (
            goal <= 64 and peak >= 16 and wins >= 24 + bot["ordinal"] % 24))
        ranked = sorted(owned, key=lambda m: (m["level"], -m["abi"], m["uid"]))
        alternatives = [m for m in ranked if m["uid"] not in current]
        rotate = completed and bool(alternatives) and alternatives[0]["level"] < max(peak, goal)
        if not current or rotate:
            pool = alternatives if rotate else ranked
            lowest = pool[0]["level"]
            desired = [m["uid"] for m in pool if m["level"] <= lowest + 8][:6]
        else:
            desired = current[:6]
            lowest = min(by_uid[uid]["level"] for uid in desired)
            # Grow a young party, but do not continually restart its training
            # whenever another level-one recruit becomes available.
            desired += [m["uid"] for m in ranked if m["uid"] not in desired
                        and abs(m["level"] - lowest) <= 8][:6 - len(desired)]
        # A bounded veteran visit can use banked partners, then hands them back
        # to storage for at least twelve normal training cycles. No bot is a
        # permanent high-level caretaker and no levels are assigned to fill gaps.
        if runtime.get("coverage_duty"):
            duty_wins = bot["stats"]["wild_wins"] - runtime.get("coverage_start_wins", bot["stats"]["wild_wins"])
            duty_cycles = runtime["cycle"] - runtime.get("coverage_started_cycle", runtime["cycle"])
            if duty_wins >= 8 + bot["ordinal"] % 8 or duty_cycles >= 16:
                runtime.update(coverage_duty=False, coverage_rest_until_cycle=runtime["cycle"] + 12)
                self._reserve_coverage(bot)
        can_cover = (self.count >= len(self.by_map) * 2
                     and runtime["cycle"] >= runtime.get("coverage_rest_until_cycle", 0))
        target = None
        if can_cover:
            sector = self.engine.maps[state["map_id"]]
            pending = self.engine.maps.get(runtime.get("coverage_target"))
            if (pending and pending["id"] != state["map_id"]
                    and any(m["level"] + 2 >= pending.get("level", 1) for m in owned)):
                # Lab maintenance resumes from its first step after a restart.
                # Keep this bot's existing reservation rather than counting it
                # as somebody else's claim and picking another destination.
                target = pending
            elif self._coverage_guard(bot) and any(m["level"] + 2 >= sector.get("level", 1) for m in owned):
                target = sector
            else:
                quota = self._coverage_quota()
                strength = max(m["level"] for m in owned)
                # Map occupancy is cheap to inspect and applies only to remote
                # destinations; local protection counts capable field teams.
                choices = [area for area in self.engine.maps.values()
                           if 3 < area.get("level", 1) <= strength + 2
                           and self._map_load(area["id"]) < quota
                           and area.get("level", 1) > self._field_level([by_uid[uid] for uid in desired]) + 2]
                if choices:
                    target = min(choices, key=lambda area: (self._map_load(area["id"]),
                                                           -area.get("level", 1), area["id"]))
        if target:
            sector_level = int(target.get("level", 1))
            veterans = sorted((m for m in owned if m["level"] + 2 >= sector_level),
                              key=lambda m: (-m["level"], m["uid"]))[:3]
            if veterans:
                selected = [m["uid"] for m in veterans]
                if len(selected) == 3:
                    selected += [uid for uid in desired if uid not in selected][:3]
                self._equip_party(bot, selected)
                if not runtime.get("coverage_duty"):
                    runtime.update(coverage_start_wins=bot["stats"]["wild_wins"],
                                   coverage_started_cycle=runtime["cycle"])
                    self._record(bot, "coverage", "Fielded experienced partners for a short veteran visit.",
                                 map_id=target["id"])
                runtime["coverage_duty"] = True
                if target["id"] != state["map_id"]:
                    self._reserve_coverage(bot, target["id"])
                    runtime["relocate"] = True
                return
        runtime["coverage_duty"] = False
        self._reserve_coverage(bot)
        if not current or rotate:
            if rotate:
                self._increment(bot, "training_rotations")
                self._increment(bot, "teams_trained")
                round_number += 1
                goal = self._training_goal(bot, round_number)
            runtime.update(training_round=round_number, training_goal=goal,
                           training_started_cycle=runtime["cycle"],
                           training_start_wins=bot["stats"]["wild_wins"], training_peak=0)
            self._record(bot, "training", f"Started training team {round_number} with {len(desired)} partners.",
                         training_round=round_number, goal=goal, partner_uids=desired)
        runtime["training_uids"] = desired
        # Rotate the actual field slots so reserves also lead and receive full XP.
        if len(desired) > 3:
            offset = runtime["cycle"] % len(desired)
            desired = desired[offset:] + desired[:offset]
        self._equip_party(bot, desired)
        if self._field_level(state["party"]) + 2 < int(self.engine.maps[state["map_id"]].get("level", 1)):
            runtime["relocate"] = True

    def _training_goal(self, bot, round_number):
        """Only future cohorts adopt expanded catalog difficulty; no XP is minted."""
        return 16 + (bot["ordinal"] * 7 + (round_number - 1) * 11) % (self.training_ceiling - 15)

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
        runtime.update(phase="explore", walk_pending=True)
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
        strength = self._field_level(state["party"])
        if easier:
            ceiling = max(1, min(strength, old_level - max(2, runtime.get("consecutive_losses", 1) * 2)))
            candidates = [area for area in self.engine.maps.values()
                          if max(1, ceiling - 4) <= int(area.get("level", 1)) <= ceiling and area["id"] != old_map]
        else:
            candidates = [area for area in self.engine.maps.values()
                          if int(area.get("level", 1)) <= strength + 2 and area["id"] != old_map]
        if not candidates:
            candidates = [area for area in self.engine.maps.values() if area["id"] != old_map
                          and int(area.get("level", 1)) <= max(1, strength)]
        assigned = runtime.get("coverage_target")
        self._reserve_coverage(bot)
        if assigned in self.engine.maps and assigned != old_map and int(self.engine.maps[assigned].get("level", 1)) <= strength + 2:
            candidates = [self.engine.maps[assigned]]
        if candidates:
            # Shared density includes real pending Lab reservations, preventing
            # explorers from crowding the same empty destination. A persisted
            # circular cursor breaks ties fairly: even a one-rival custom world
            # can visit every eligible map instead of bouncing between a few.
            cursor = self.map_indices.get(runtime.get("route_after_map"), bot["ordinal"] % len(self.map_order))
            target = min(candidates, key=lambda area: (
                self._map_load(area["id"]),
                (self.map_indices[area["id"]] - cursor - 1) % len(self.map_order)))
            # A quiet field must not lose its final capable resident merely
            # because its dwell timer expired while other fields are fuller.
            # Equal-density visits still rotate normally; safe retreat and a
            # specific veteran reservation always take priority.
            if (not easier and not assigned and now >= runtime["leave_at"]
                    and self.count >= len(self.by_map) * 2
                    and (self._map_load(target["id"]) > self._map_load(old_map)
                         or (self._map_load(old_map) == 1 and self._map_load(target["id"]) >= 1))):
                runtime.update(relocate=False, visited_at=now, leave_at=now + self.dwell_min)
                return
            self._execute(bot, "travel", {"map_id": target["id"]})
            # Spread arrivals only on a real sector transition. Existing walkers
            # remain on their continuous path; every client sees the same point.
            peers = []
            for ident in self.by_map[target["id"]]:
                other = self.bots[ident]
                sample = self.navigation.sample(other["runtime"].get("path"), now)
                peers.append(sample[:2] if sample else (other["state"]["x"], other["state"]["y"]))
            state["x"], state["y"] = self.navigation.arrival(target["id"], peers, bot["ordinal"])
            if int(target.get("level", 1)) + 12 < strength:
                self._increment(bot, "coverage_visits")
            self.by_map[old_map].discard(bot["id"])
            self.by_map[target["id"]].add(bot["id"])
            runtime["route_after_map"] = target["id"]
            runtime["walk_pending"] = True
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
                      "seed_level": runtime["seed_level"],
                      "training_round": runtime.get("training_round", 1),
                      "training_goal": runtime.get("training_goal", 16),
                      "training_partners": len(runtime.get("training_uids", [])),
                      "coverage_duty": bool(runtime.get("coverage_duty", False))}
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
            wall_now = time.time()
            self._expire_activity(wall_now)
            phases = Counter(bot["runtime"]["phase"] for bot in self.bots.values())
            return {"population": len(self.bots), "active": len(self.bots),
                    **self.activity_window.metadata(wall_now),
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
            self._flush_activity(time.time())
            self.last_save = now

    def close(self):
        self.flush(force=True)
