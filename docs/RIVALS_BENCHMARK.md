# Historical full-population validation — v0.2.0

This is retained baseline evidence. The rival and navigation implementation
changed in v0.3.1; see `RIVAL_TRAINING_VALIDATION.json` and `VALIDATION.md` for
the current source and movement/training audit.

This run used the actual rival, navigation, ranked and persistence implementation
with **5,000 rivals** across all **254 maps**. Normal activity, map-dwell, ranked
energy and progression rules remained enabled. A clock advanced at the server's
10 Hz simulation interval without real-time sleeps. It covered **900 simulated
seconds** in **198.762 seconds of wall time**, including initialization,
final database flush and result checks.

All **15 acceptance checks passed**. The four core source hashes in
`RIVALS_BENCHMARK.json` identify the original v0.2.0 source. No gameplay recovery errors,
observed collision violations, excessive movement speeds or inconsistent
same-timestamp snapshots were reported. Independent navigation tests also sample
continuous routes across every map, including corner crossings.

## Observed activity

| Measurement | Result |
| --- | ---: |
| Rivals that explored, entered wild combat and completed the recurring activity cycle | 5,000 |
| Rivals that initiated ranked combat | 5,000 |
| Wild victories | 42,306 |
| Wild defeats | 10,128 |
| Completed ranked matches | 25,000 |
| Materialized partners from earned full scan data | 4,057 |
| Partner level-ups earned | 36,918 |
| Evolutions | 286 |
| Party changes | 939 |
| Sector transitions | 12,424 |
| Initial rivals per sector | 19–20 |
| Final rivals per sector | 2–26 |
| Occupied sectors at the end | 254 |

The ranked ledger independently reconciled one career and season victory and
loss per match. Every bot won at least one wild battle. Captures, evolution,
shopping and party changes remained conditional on scan data, team eligibility
and available credits; those actions are not granted merely to fill counters.
No Paradox materialization or de-evolution preconditions were reached during this
15-minute simulated interval. Bots' initial sector seed levels are excluded from
earned XP and level-up totals. No real human accounts joined this benchmark, so
human-friendly challenge counters were zero; WSS integration tests cover those.

## Measured runtime

| Measurement | Result |
| --- | ---: |
| Population initialization | 4.650 seconds |
| Final complete bot checkpoint | 1.603 seconds |
| Process resident memory at end | 188.55 MiB |
| Simulation tick p95 | 24.268 ms |
| Simulation tick p99 | 69.873 ms |
| Slowest simulation tick | 330.876 ms |
| 16 map snapshots plus JSON encoding, p95 | 4.611 ms |
| Largest observed map snapshot | 26 actors / 7,982 bytes |
| Maximum recorded scheduler lateness | 6.0 simulated seconds |

This is Linux 3.12.14 Python with temporary SQLite/WAL,
9 reported logical CPUs, and no native client render
loop or real network players. The scheduler uses a bounded work budget; overdue
activities remain queued. Rare checkpoint/scheduling spikes exceed the 100 ms
world interval. These measurements do not certify a particular Windows frame
rate, production MySQL throughput, internet latency, or human connection capacity.

Weekly rollover, missed-reset recovery, energy replenishment, reward uniqueness,
restart recovery and lease takeover are covered by separate automated tests; a
900-second run does not establish long-duration operational stability. The
benchmark uses the store without a production world-ownership lease; separate
safety tests verify transaction fencing under lease takeover. The shipped default
checkpoint rotation and abrupt-crash boundary are documented in
`RIVALS_AND_RANKED.md`.

## Reproduce

From the source folder, after installing the declared dependencies:

```sh
python tools/benchmark_rivals.py --bots 5000 --seconds 900 --output qa/rivals-5000-900s.json
```

This creates an isolated temporary SQLite world and does not modify player saves.
It needs writable temporary disk space. Exact battle totals can vary with the
scheduler's wall-time budget; use the acceptance checks and measured distributions
to compare results. A separate attempt hit this workspace's disk limit at the final
flush; unused temporary downloads were cleared and the complete run reported
above subsequently passed, including its final flush.
