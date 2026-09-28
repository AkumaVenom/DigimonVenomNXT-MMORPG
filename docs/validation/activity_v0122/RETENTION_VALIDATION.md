# Rolling activity retention validation — v0.12.2

The persistence check submitted **40,320 timestamped batches across 28 simulated days** to an isolated in-memory SQLite development database. Each minute added all 27 activity counters, including 1.25 units of fractional walking distance, and one feed event. It exercised the production `CommunityStore` methods without simulating gameplay.

| Checkpoint | Minute buckets | Batch receipts | Feed events | Retained counter JSON | Aggregate counter JSON |
| --- | ---: | ---: | ---: | ---: | ---: |
| Day 1 | 720 | 720 | 100 | 318,960 bytes | 496 bytes |
| Day 7 | 720 | 720 | 100 | 318,960 bytes | 496 bytes |
| Day 28 | 720 | 720 | 100 | 318,960 bytes | 496 bytes |

These row counts were also the maximum observed during the run. All 27 counters survived aggregation; the retained window contained 720 wild wins and 900.0 walking-distance units at each checkpoint. The global counter payload stopped growing by day 1 and had the same size at day 28.

The **720-minute-bucket limit applies to the shared global aggregate**, independently of rival population. The measured 720 receipts reflect this test's one-batch-per-minute schedule; production receipt counts depend on checkpoint frequency, with receipts expiring after twelve hours. Feed events are additionally capped at 100.

Counter expiry uses minute starts strictly newer than the twelve-hour cutoff. This excludes all older activity and can retire the oldest partial minute less than one minute early. Feed events use their precise timestamps. Byte figures count compact JSON content, excluding database row and index overhead; they do not measure the complete game database, allocated disk space, Windows performance, or MySQL startup duration.

Separate regression tests cover idle expiry, a restart after three days, legacy lifetime-counter migration, receipt cleanup in pages, expired retries, a lost commit acknowledgement followed by new activity, transactional rollback, four-week in-memory retention, fractional distance, and preservation of player saves, DigiRubies, ranked history, and rival progression.

Machine-readable results: `retention_28_days.json`.
