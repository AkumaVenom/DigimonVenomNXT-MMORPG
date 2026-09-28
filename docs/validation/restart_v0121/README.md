# Restart benchmark evidence — v0.12.1

The full automated suite completed with **785 passed and 10 skipped** in
230.05 seconds on 2026-09-27. The suite includes the 18 new startup, lease,
saved-progress and loading-I/O regressions. The skips and exact run output are
recorded in [full_suite.log](full_suite.log), with machine-readable results in
[full_suite.xml](full_suite.xml). The package-copy regression also passed after
adding this evidence folder to both Windows package manifests.

These JSON files record one before/after measurement in the Linux development
environment using SQLite, with the archived v0.12.0 population code and repaired
v0.12.1 code. Each measurement used the same generated saved fleet of 5,000
grown rivals: 30,000 party Digimon, 240,000 stored Digimon and 2,500 unfinished
battles. This fixture exercises substantial saved progression; it is not a copy
of the affected user's database or an elapsed-day Windows playtest.

| Measurement | v0.12.0 baseline | v0.12.1 repair |
|---|---:|---:|
| Community initialization | 19.072 seconds | 8.216 seconds |
| Peak process resident memory | 1,821.9 MiB | 1,184.1 MiB |
| Loaded rivals | 5,000 | 5,000 |
| Party Digimon | 30,000 | 30,000 |
| Stored Digimon | 240,000 | 240,000 |
| Unfinished battles | 2,500 | 2,500 |
| Simulated actions while loading | 0 | 0 |

The benchmark hashes each rival's identifier, saved state and statistics before
loading and compares that hash with the restored fleet. Both result files show
the same exact progress hash. It separately verifies the human character's full
saved state and DigiRuby wallet. That fixture has **391 DigiRubies** and
**76,543 credits**, retained through both runs.

`initialize_seconds` measures community initialization, not the complete process
launch or client sign-in time. `peak_rss_mib` is peak resident memory for the
benchmark process, not additional memory attributable only to loading. These
single-run figures demonstrate this fixture's improvement; they are not a
Windows/MySQL performance guarantee or a maximum loading time. The separate
lease-expiry regression uses a simulated long restore to exercise the original
90-second failure path; these timing runs finish inside 90 seconds.

- [Baseline measurement](baseline_5000_result.json)
- [Repaired measurement](current_5000_result.json)
