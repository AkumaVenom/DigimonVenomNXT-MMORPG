"""Audit real rival movement and training over accelerated simulation time.

This uses temporary SQLite and the actual ranked and wild battle engines. The
simulation clock advances without sleeping; it is not a real-time network soak,
Windows rendering benchmark, or MySQL load test. ``--mature-save`` is explicitly
a migration fixture: existing partners start at level 60 with empty scan data,
and the whole saved population has drifted into level 48–60 sectors.
No wins, captures, currency, or subsequent progression are pre-awarded.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.benchmark_rivals import ledger_totals, memory_mib, timings
from venom.common.game import GameEngine
from venom.server.bots import BotManager
from venom.server.community_store import CommunityStore
from venom.server.database import Database
from venom.server.ranked import RankedService


def owned(state):
    return {member["uid"]: member for member in state["party"] + state["storage"]}


class AuditManager(BotManager):
    """Observe canonical operations; never replace outcomes or progression."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provenance_errors = []
        self.earned_uids = set()
        self.audit_operations = Counter()

    def _execute(self, bot, op, payload):
        members = owned(bot["state"])
        before = {uid: (member["level"], member["species_id"]) for uid, member in members.items()}
        scan = bot["state"]["scan"].get(payload.get("species_id"), 0)
        self.audit_operations[op] += 1
        super()._execute(bot, op, payload)
        after = owned(bot["state"])
        errors = []
        if set(before) - set(after):
            errors.append("owned partners disappeared")
        born = set(after) - set(before)
        if born:
            if op != "materialize" or scan < 100 or len(born) != 1:
                errors.append("new partner without canonical full-scan materialization")
            self.earned_uids.update(born)
        for uid in set(before) & set(after):
            level, species = before[uid]
            member = after[uid]
            if op != "evolve" and (member["level"] < level or member["species_id"] != species):
                errors.append("partner reset outside canonical evolution")
        for error in errors:
            if len(self.provenance_errors) < 20:
                self.provenance_errors.append({"bot": bot["id"], "operation": op, "error": error})


def run(count=3000, seconds=1800, mature_save=False, seed=7281, progress=None):
    started = time.perf_counter()
    source = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (ROOT / "venom/server/bots.py", ROOT / "venom/server/navigation.py",
                           ROOT / "venom/server/ranked.py", Path(__file__))}
    clock = [1_800_000_000.0]
    start, step = 1000.0, .1
    tick_times, occupancy, previous = [], [], {}
    movers, observed, motion_errors, collision_errors = set(), set(), [], []
    max_heap = 0
    with tempfile.TemporaryDirectory(prefix="venom-cycle-audit-") as folder:
        database = Database({"driver": "sqlite", "path": str(Path(folder) / "audit.sqlite3")}, dev=True)
        try:
            database.initialize()
            store = CommunityStore(database)
            store.initialize()
            engine = GameEngine(ROOT, seed=seed)
            ranked = RankedService(GameEngine(ROOT, seed=seed + 1), store, clock=lambda: clock[0])
            ranked.tick()
            config = {"count": count, "seed": seed}
            manager = AuditManager(engine, store, ranked, config)
            manager.initialize(start)
            if mature_save:
                # A controlled old-save fixture. Normal GameEngine combat earns
                # every subsequent scan, item, partner, level and ranked result.
                high_maps = sorted(mid for mid, area in engine.maps.items() if area["level"] >= 48)
                for ids in manager.by_map.values():
                    ids.clear()
                for bot in manager.bots.values():
                    for member in bot["state"]["party"]:
                        upgraded = engine._monster(member["species_id"], level=60,
                                                   abi=member["abi"], cam=member["cam"])
                        upgraded["uid"] = member["uid"]
                        member.clear()
                        member.update(upgraded)
                    destination = high_maps[bot["ordinal"] % len(high_maps)]
                    engine.handle(bot["state"], "travel", {"map_id": destination})
                    manager.by_map[destination].add(bot["id"])
                    manager.dirty.add(bot["id"])
                manager.flush(force=True, now=start)
                legacy_rows = store.bot_load_all()
                for row in legacy_rows:
                    for key in list(row["runtime"]):
                        if any(term in key for term in ("training", "home", "team", "circuit", "coverage")):
                            row["runtime"].pop(key)
                store.bot_save_batch(legacy_rows)
                manager = AuditManager(GameEngine(ROOT, seed=seed), store, ranked, config)
                manager.initialize(start)
            initial_uids = {uid for bot in manager.bots.values() for uid in owned(bot["state"])}
            map_ids = sorted(engine.maps)
            initialized = time.perf_counter() - started
            def checkpoint(elapsed):
                values = [len(manager.by_map[mid]) for mid in map_ids]
                row = {"simulated_seconds": round(elapsed, 1),
                       "occupied_maps": sum(value > 0 for value in values),
                       "minimum_population": min(values), "maximum_population": max(values),
                       "low_level_occupancy": sum(len(manager.by_map[mid]) for mid in map_ids
                                                  if engine.maps[mid]["level"] <= 10),
                       "histogram": dict(Counter(values)), "counters": dict(manager.counters)}
                occupancy.append(row)
                if progress:
                    progress({"simulated_seconds": elapsed, "wall_seconds": time.perf_counter() - started,
                              "occupied_maps": row["occupied_maps"], "moving_bots_seen": len(movers),
                              "counters": row["counters"]})
            checkpoint(0)
            for tick in range(1, math.ceil(seconds / step) + 1):
                now = start + tick * step
                clock[0] = 1_800_000_000 + tick * step
                before = time.perf_counter()
                manager.tick(now, step, budget=160)
                tick_times.append(time.perf_counter() - before)
                max_heap = max(max_heap, len(manager.heap))
                if tick % 50 == 0:
                    ranked.tick()
                # Rotate all maps while revisiting each frequently enough to
                # detect immobilized actors and movement above the human speed.
                for index in range(8):
                    map_id = map_ids[(tick * 8 + index) % len(map_ids)]
                    rows = manager.snapshot(map_id, now)
                    if tick % 100 == 0 and rows != manager.snapshot(map_id, now):
                        raise AssertionError("Observers received inconsistent authoritative snapshots")
                    for row in rows:
                        ident, point = row["id"], (row["x"], row["y"])
                        observed.add(ident)
                        last = previous.get(ident)
                        if last and last[0] == map_id:
                            elapsed, distance = now - last[1], math.dist(last[2], point)
                            if distance > .05:
                                movers.add(ident)
                            if distance > 180 * elapsed + .01 and len(motion_errors) < 20:
                                motion_errors.append({"bot": ident, "elapsed": elapsed, "distance": distance})
                        previous[ident] = (map_id, now, point)
                        if not manager.navigation.walkable(map_id, *point) and len(collision_errors) < 20:
                            collision_errors.append({"bot": ident, "map": map_id, "point": point})
                if tick % 600 == 0:
                    checkpoint(tick * step)
            end = start + math.ceil(seconds / step) * step
            if not occupancy or occupancy[-1]["simulated_seconds"] != round(seconds, 1):
                checkpoint(seconds)
            manager.flush(force=True, now=end)
            final_uids = {uid for bot in manager.bots.values() for uid in owned(bot["state"])}
            expected_uids = initial_uids | manager.earned_uids
            saved = {bot["id"]: manager._serialize(bot, end) for bot in manager.bots.values()}
            counters = dict(manager.counters)
            totals = ledger_totals(database)
            operations = dict(manager.audit_operations)
            provenance_errors = list(manager.provenance_errors)
            restored = AuditManager(GameEngine(ROOT, seed=seed), store, ranked, config)
            restored.initialize(end + 10)
            restart_partners = all(owned(bot["state"]) == owned(saved[ident]["state"])
                                   for ident, bot in restored.bots.items())
            restart_stats = all(bot["stats"] == saved[ident]["stats"] for ident, bot in restored.bots.items())
            # Runtime deadlines are intentionally restarted; persisted training
            # plans and counters must retain their exact checkpointed values.
            plan_keys = {key for row in saved.values() for key in row["runtime"]
                         if any(term in key for term in ("training", "home", "team", "circuit", "coverage"))}
            restart_plans = all(all(bot["runtime"].get(key) == saved[ident]["runtime"].get(key)
                                       for key in plan_keys) for ident, bot in restored.bots.items())
            coverage = {key: sum(bot["stats"].get(key, 0) > 0 for bot in manager.bots.values())
                        for key in counters}
            training_participation = {
                "bots_with_training_plan": sum(bool(bot["runtime"].get("training_uids"))
                                               for bot in manager.bots.values()),
                "bots_on_coverage_duty": sum(bool(bot["runtime"].get("coverage_duty"))
                                            for bot in manager.bots.values()),
                "rotation_histogram": dict(Counter(bot["stats"].get("training_rotations", 0)
                                                   for bot in manager.bots.values())),
                "long_active_bots_without_rotation": [
                    {"id": bot["id"], "cycles": bot["runtime"].get("cycle", 0),
                     "coverage_duty": bool(bot["runtime"].get("coverage_duty")),
                     "training_plan": bool(bot["runtime"].get("training_uids")),
                     "field_levels": [m["level"] for m in bot["state"]["party"]],
                     "stored_partners": len(bot["state"]["storage"])}
                    for bot in manager.bots.values()
                    if bot["runtime"].get("cycle", 0) >= 50 and bot["stats"].get("training_rotations", 0) == 0][:50],
            }
            checks = {"exact_population": len(manager.bots) == count,
                      "every_observed_rival_actually_moved": movers == observed,
                      "every_rival_observed": len(observed) == count,
                      "motion_within_human_speed": not motion_errors,
                      "sampled_positions_walkable": not collision_errors,
                      "all_owned_partners_retained": expected_uids == final_uids,
                      "progression_uses_canonical_game_rules": not provenance_errors,
                      "scheduler_heap_bounded": max_heap <= count * 2,
                      "activity_history_bounded": len(manager.activity()["events"]) <= 100,
                      "ranked_ledger_balanced": totals["balanced"],
                      "restart_keeps_partners": restart_partners,
                      "restart_keeps_stats": restart_stats,
                      "restart_keeps_training_plans": restart_plans,
                      "no_gameplay_recovery_errors": counters.get("errors", 0) == 0}
            if count >= len(map_ids) * 4:
                checks["all_maps_still_populated"] = occupancy[-1]["occupied_maps"] == len(map_ids)
                checks["low_level_population_survives"] = occupancy[-1]["low_level_occupancy"] > 0
            if seconds >= 900:
                checks["every_rival_started_wild_battles"] = coverage.get("wild_started", 0) == count
                checks["every_rival_healed_and_kept_exploring"] = coverage.get("heals", 0) == coverage.get("exploration_steps", 0) == count
                if count > 1:
                    checks["every_rival_started_ranked_battles"] = coverage.get("ranked_started", 0) == count
            return {"scope": __doc__.strip(), "mature_save_fixture": mature_save,
                    "source_sha256": source, "population": count, "simulated_seconds": seconds,
                    "initialization_seconds": round(initialized, 3),
                    "wall_seconds": round(time.perf_counter() - started, 3), "tick": timings(tick_times),
                    "memory_mib": memory_mib(), "occupancy_checkpoints": occupancy,
                    "observed_bots": len(observed), "moving_bots_seen": len(movers),
                    "maximum_heap_entries": max_heap, "initial_partner_count": len(initial_uids),
                    "earned_partner_count": len(manager.earned_uids), "final_partner_count": len(final_uids),
                    "operation_counts": operations, "activity_counters": counters, "coverage": coverage,
                    "training_participation": training_participation,
                    "ranked_ledger": totals, "persisted_plan_keys": sorted(plan_keys),
                    "provenance_errors": provenance_errors, "motion_errors": motion_errors,
                    "collision_errors": collision_errors, "checks": checks}
        finally:
            database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bots", type=int, default=3000)
    parser.add_argument("--seconds", type=float, default=1800)
    parser.add_argument("--mature-save", action="store_true")
    parser.add_argument("--seed", type=int, default=7281)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.bots <= 3000 or not math.isfinite(args.seconds) or not 1 <= args.seconds <= 86400:
        parser.error("Use 1–3000 bots and 1–86400 simulated seconds.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def progress(row):
        args.output.with_suffix(".progress.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in row.items() if key != "counters"}), flush=True)
    report = run(args.bots, args.seconds, args.mature_save, args.seed, progress)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output.resolve()), "checks": report["checks"]}, indent=2))
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
