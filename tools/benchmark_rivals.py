"""Measure the actual rival population in an isolated, temporary SQLite world.

Example (from the source folder):
    python tools/benchmark_rivals.py --bots 3000 --seconds 900 --output qa/rivals.json

Time advances at the production 10 Hz simulation interval without sleeping. This
measures server simulation and persistence work, not real network/player capacity,
Windows rendering speed, or MySQL hosting performance. No existing save is read or
modified, and normal production activity/energy/dwell timers remain in effect.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def memory_mib():
    """Return process memory measurements without a third-party dependency."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        current_process = ctypes.windll.kernel32.GetCurrentProcess
        current_process.restype = wintypes.HANDLE
        measure = ctypes.windll.psapi.GetProcessMemoryInfo
        measure.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
        measure.restype = wintypes.BOOL
        if measure(current_process(), ctypes.byref(counters), counters.cb):
            return {"current": round(counters.WorkingSetSize / 2**20, 2),
                    "peak": round(counters.PeakWorkingSetSize / 2**20, 2)}
        return {"current": None, "peak": None}
    import resource
    high_water = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = high_water / (2**20 if sys.platform == "darwin" else 1024)
    current = None
    status = Path("/proc/self/statm")
    if status.exists():
        current = int(status.read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    return {"current": round(current, 2) if current is not None else None,
            "peak": round(peak, 2)}


def timings(values):
    ordered = sorted(values)
    if not ordered:
        return {"samples": 0}
    percentile = lambda fraction: ordered[min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)]
    return {"samples": len(values), "mean_ms": round(statistics.fmean(values) * 1000, 3),
            "p50_ms": round(percentile(.50) * 1000, 3), "p95_ms": round(percentile(.95) * 1000, 3),
            "p99_ms": round(percentile(.99) * 1000, 3), "maximum_ms": round(ordered[-1] * 1000, 3)}


def ledger_totals(database):
    """Independent SQL reconciliation, without trusting UI aggregate counters."""
    with database.lock:
        cursor = database._connect().cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM venom_ranked_matches WHERE ranked=1")
            matches = int(cursor.fetchone()[0])
            cursor.execute("SELECT COALESCE(SUM(career_wins),0), COALESCE(SUM(career_losses),0) "
                           "FROM venom_competitors")
            wins, losses = map(int, cursor.fetchone())
            cursor.execute("SELECT COALESCE(SUM(wins),0), COALESCE(SUM(losses),0) "
                           "FROM venom_ranked_records")
            seasonal_wins, seasonal_losses = map(int, cursor.fetchone())
            cursor.execute("SELECT COUNT(DISTINCT attacker_id) FROM venom_ranked_matches WHERE ranked=1")
            unique_attackers = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM venom_ranked_rewards")
            rewards = int(cursor.fetchone()[0])
            database._connect().commit()
        finally:
            cursor.close()
    return {"matches": matches, "career_wins": wins, "career_losses": losses,
            "seasonal_wins": seasonal_wins, "seasonal_losses": seasonal_losses,
            "unique_ranked_attackers": unique_attackers, "season_reward_rows": rewards,
            "balanced": matches == wins == losses == seasonal_wins == seasonal_losses}


def run_benchmark(count=3000, simulated_seconds=900, observed_maps=16, seed=1907, progress=None):
    from venom.common.game import GameEngine
    from venom.server.bots import BotManager
    from venom.server.community_store import CommunityStore
    from venom.server.database import Database
    from venom.server.ranked import RankedService

    started = time.perf_counter()
    before_memory = memory_mib()
    source_hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in (ROOT / "venom/server/bots.py", ROOT / "venom/server/navigation.py",
                                  ROOT / "venom/server/ranked.py", ROOT / "venom/server/community_store.py")}
    wall_clock = [1_800_000_000.0]
    simulation_start, step = 1000.0, .1
    ticks = math.ceil(simulated_seconds / step)
    tick_times, snapshot_times = [], []
    previous_positions = {}
    motion_violations, collision_violations, snapshot_mismatches = [], [], []
    largest_snapshot_count = largest_snapshot_bytes = 0
    seen_bots = set()
    maximum_due_delay = 0.0
    with tempfile.TemporaryDirectory(prefix="venom-rival-benchmark-") as directory:
        database = Database({"driver": "sqlite", "path": str(Path(directory) / "benchmark.sqlite3")}, dev=True)
        try:
            database.initialize()
            store = CommunityStore(database)
            store.initialize()
            engine = GameEngine(ROOT, seed=seed)
            ranked = RankedService(GameEngine(ROOT, seed=seed + 1), store, clock=lambda: wall_clock[0])
            ranked.tick()
            manager = BotManager(engine, store, ranked, {"count": count, "seed": seed})
            initial_at = time.perf_counter()
            manager.initialize(now=simulation_start)
            initialization_seconds = time.perf_counter() - initial_at
            initial_occupancy = {map_id: len(ids) for map_id, ids in manager.by_map.items()}
            after_initialize_memory = memory_mib()
            map_ids = sorted(engine.maps)
            initial_ranked_totals = ledger_totals(database)
            if initial_ranked_totals["matches"]:
                raise AssertionError("A fresh benchmark must not start with invented ranked results.")
            initial_wild_totals = sum(bot["state"].get("wins", 0) + bot["state"].get("losses", 0)
                                      for bot in manager.bots.values())
            if initial_wild_totals:
                raise AssertionError("A fresh benchmark must not start with invented wild results.")
            simulation_at = time.perf_counter()
            if progress:
                progress({"simulated_seconds": 0, "population": count,
                          "initialization_seconds": round(initialization_seconds, 3),
                          "memory_mib": after_initialize_memory, "source_sha256": source_hashes})
            for index in range(1, ticks + 1):
                now = simulation_start + index * step
                wall_clock[0] = 1_800_000_000.0 + index * step
                tick_at = time.perf_counter()
                result = manager.tick(now=now, dt=step, budget=160)
                if index % 50 == 0:
                    ranked.tick()
                tick_times.append(time.perf_counter() - tick_at)
                maximum_due_delay = max(maximum_due_delay, result.get("overdue_seconds", 0))
                # Rotate the observed sectors once per second. Timing includes
                # JSON encoding as the production server performs it, but no I/O.
                offset = (index // 10 * max(1, observed_maps)) % len(map_ids)
                watched = [map_ids[(offset + number) % len(map_ids)] for number in range(observed_maps)]
                snapshot_at = time.perf_counter()
                samples = {map_id: manager.snapshot(map_id, now=now) for map_id in watched}
                payloads = [json.dumps({"op": "world", "map_id": map_id, "players": entries}, separators=(",", ":"))
                            for map_id, entries in samples.items()]
                snapshot_times.append(time.perf_counter() - snapshot_at)
                largest_snapshot_count = max(largest_snapshot_count, max((len(v) for v in samples.values()), default=0))
                largest_snapshot_bytes = max(largest_snapshot_bytes, max((len(v.encode("utf-8")) for v in payloads), default=0))
                for map_id, entries in samples.items():
                    if index % 100 == 0 and entries != manager.snapshot(map_id, now=now):
                        if len(snapshot_mismatches) < 20:
                            snapshot_mismatches.append({"map_id": map_id, "time": now})
                    for entry in entries:
                        ident = entry["id"]
                        seen_bots.add(ident)
                        current = (entry["x"], entry["y"])
                        previous = previous_positions.get(ident)
                        if previous and previous[0] == map_id:
                            elapsed = now - previous[1]
                            distance = math.dist(previous[2], current)
                            # Snapshot positions are rounded to .001 world units.
                            if distance > 180 * elapsed + .004 and len(motion_violations) < 20:
                                motion_violations.append({"id": ident, "map_id": map_id,
                                                          "distance": distance, "elapsed": elapsed})
                        previous_positions[ident] = (map_id, now, current)
                        if index % 10 == 0 and not manager.navigation.walkable(map_id, *current):
                            if len(collision_violations) < 20:
                                collision_violations.append({"id": ident, "map_id": map_id, "position": current})
                if progress and index % 600 == 0:
                    progress({"simulated_seconds": round(index * step, 1), "population": count,
                              "wall_seconds": round(time.perf_counter() - started, 3),
                              "tick": timings(tick_times[-600:]), "processed": manager.processed,
                              "counters": dict(manager.counters), "overdue_seconds": result.get("overdue_seconds", 0),
                              "motion_violations": motion_violations, "collision_violations": collision_violations})
            simulation_wall_seconds = time.perf_counter() - simulation_at
            flush_at = time.perf_counter()
            manager.flush(force=True, now=simulation_start + ticks * step)
            final_flush_seconds = time.perf_counter() - flush_at
            activity = manager.activity(limit=100)
            totals = ledger_totals(database)
            bots = list(manager.bots.values())
            coverage = {key: sum(bot["stats"].get(key, 0) > 0 for bot in bots)
                        for key in ("wild_started", "wild_wins", "wild_losses", "ranked_started",
                                    "materialized", "party_swaps", "level_ups", "purchases", "travels",
                                    "exploration_steps", "evolutions")}
            coverage["completed_activity_cycle"] = sum(bot["runtime"].get("cycle", 0) > 0 for bot in bots)
            counters = activity["counters"]
            wild_consistent = all(bot["stats"]["wild_wins"] == bot["state"].get("wins", 0)
                                  and bot["stats"]["wild_losses"] == bot["state"].get("losses", 0) for bot in bots)
            occupancy = list(initial_occupancy.values())
            checks = {
                "exact_requested_population": len(bots) == count,
                "initial_population_evenly_distributed": max(occupancy) - min(occupancy) <= 1,
                "no_preseeded_battle_wins_or_losses": initial_wild_totals == initial_ranked_totals["matches"] == 0,
                "snapshots_match_at_shared_timestamp": not snapshot_mismatches,
                "observed_movement_at_or_below_human_speed": not motion_violations,
                "observed_positions_collision_safe": not collision_violations,
                "wild_counters_match_canonical_states": wild_consistent,
                "ranked_counters_match_transaction_ledger": totals["balanced"]
                    and counters["ranked_wins"] == counters["ranked_losses"] == totals["matches"],
                "recent_activity_limited_to_100": len(activity["events"]) <= 100,
                "directory_pages_limited_to_100": len(manager.directory(limit=100000)["entries"]) <= 100,
                "no_gameplay_recovery_errors": counters.get("errors", 0) == 0,
            }
            if count == 3000:
                minimum, remainder = divmod(count, len(occupancy))
                expected = {minimum, minimum + 1} if remainder else {minimum}
                checks["initial_3000_rival_occupancy_matches_map_count"] = set(occupancy) == expected
            if simulated_seconds >= 300:
                checks["every_bot_explored_and_started_wild_battle"] = coverage["exploration_steps"] == coverage["wild_started"] == count
                checks["every_bot_completed_activity_cycle"] = coverage["completed_activity_cycle"] == count
                if count > 1:
                    checks["every_bot_initiated_ranked_battle"] = coverage["ranked_started"] == count
            return {
                "scope": "Actual rival simulation with normal timers and temporary SQLite; no network players or render loop.",
                "source_sha256": source_hashes,
                "environment": {"platform": platform.platform(), "python": platform.python_version(),
                                "cpu_count": os.cpu_count(), "database": "temporary SQLite, WAL"},
                "population": count, "seed": seed, "simulated_seconds": round(ticks * step, 3),
                "tick_hz": 10, "observed_maps_per_tick": observed_maps,
                "initialization_seconds": round(initialization_seconds, 3),
                "simulation_wall_seconds": round(simulation_wall_seconds, 3),
                "final_flush_seconds": round(final_flush_seconds, 3),
                "wall_seconds": round(time.perf_counter() - started, 3),
                "memory_mib": {"before": before_memory, "initialized": after_initialize_memory, "end": memory_mib()},
                "tick": timings(tick_times), "snapshot_and_json": timings(snapshot_times),
                "initial_occupancy_histogram": dict(Counter(occupancy)),
                "final_occupancy_histogram": dict(Counter(len(ids) for ids in manager.by_map.values())),
                "largest_observed_map_snapshot": {"actors": largest_snapshot_count, "bytes": largest_snapshot_bytes},
                "distinct_bots_observed": len(seen_bots), "coverage": coverage, "activity_counters": counters,
                "activity_phases": activity["phases"], "scheduler": activity["scheduler"],
                "maximum_due_delay_seconds": round(maximum_due_delay, 3), "ranked_ledger": totals,
                "motion_violations": motion_violations, "collision_violations": collision_violations,
                "snapshot_mismatches": snapshot_mismatches, "checks": checks,
            }
        finally:
            database.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bots", type=int, default=3000, help="Population size (1–3000; default 3000).")
    parser.add_argument("--seconds", type=float, default=900, help="Simulated seconds using normal activity timers.")
    parser.add_argument("--observed-maps", type=int, default=16,
                        help="Map snapshots sampled per 10 Hz tick (no real network clients).")
    parser.add_argument("--seed", type=int, default=1907)
    parser.add_argument("--output", type=Path, required=True, help="Destination for the JSON measurements.")
    args = parser.parse_args(argv)
    if not 1 <= args.bots <= 3000 or not math.isfinite(args.seconds) or not 1 <= args.seconds <= 86400:
        parser.error("Use 1–3000 bots and 1–86400 simulated seconds.")
    if not 0 <= args.observed_maps <= 254:
        parser.error("Observed maps must be between 0 and 254.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def progress(snapshot):
        args.output.with_suffix(".progress.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"progress_seconds": snapshot["simulated_seconds"],
                          "wall_seconds": snapshot.get("wall_seconds", snapshot.get("initialization_seconds")),
                          "overdue_seconds": snapshot.get("overdue_seconds", 0),
                          "wild_wins": snapshot.get("counters", {}).get("wild_wins", 0),
                          "wild_losses": snapshot.get("counters", {}).get("wild_losses", 0),
                          "ranked_wins": snapshot.get("counters", {}).get("ranked_wins", 0)}, separators=(",", ":")),
              file=sys.stderr, flush=True)
    report = run_benchmark(args.bots, args.seconds, args.observed_maps, args.seed, progress=progress)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output.resolve()), "population": report["population"],
                      "simulated_seconds": report["simulated_seconds"],
                      "wall_seconds": report["wall_seconds"], "tick": report["tick"],
                      "ranked_ledger": report["ranked_ledger"], "checks": report["checks"]}, indent=2))
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
