# v0.12.3 validation evidence

The complete automated suite finished with **818 passed and 10 skipped** in
**228.94 seconds**. The skips are one opt-in live-MySQL check and nine graphical
setup-wizard checks that require a desktop/Xvfb; they are not passes.

- [Complete test log](full_suite.log)
- [Complete JUnit results](full_suite.xml)
- [Focused network JUnit results](network_tests.xml)
- [World-update bandwidth measurements](world_bandwidth.json)

## Population migration and recovery

The full saved-population regression writes all **5,000 persistent rival IDs**
to an isolated database using actual game-state templates. Startup removes
exactly `bot:03001` through `bot:05000`, leaving **3,000 saved and live rivals**.
Retained partner identities and earned state are checked through repeated
restarts with the old `count: 5000` configuration. Human saves, wallets, match
history and retained historical placements are checked for preservation.
Retired profiles no longer appear as live competitors and cannot be challenged.

Other regressions cover bounded committed cleanup, repeat starts, a disabled
population, exclusive ownership and stale-owner rejection. An interruption
fixture stops after a committed 100-rival page, advances beyond the original
season and lease expiry, and resumes with a legitimate replacement owner. The
durable plan completes the same captured-season cleanup while preserving
already-expired/closed historical rows and human progress. Invalid retirement
plans fail before population deletion. Existing expiry and unpaid human reward
checks remain covered.

The acceptance suite also checks the current 3,000-rival population against the
real 404-map catalog, distribution, collision-safe movement and scheduler
coverage. A fresh population begins with 7–8 rivals per map; this is not a claim
that a mature roaming population keeps that occupancy. Retained rivals are not
redistributed as part of the removal.

## Compression and complete world updates

Tests connect the real native client and an uncompressed peer to the same
server. They verify negotiated compression, identical decoded snapshots with
all actors, unchanged sequence/update semantics, private-instance isolation,
independent per-message compression history and the existing decompressed
request-size limit. The full suite also includes TLS/WSS integration checks.
Existing v0.12.2 clients support negotiation; uncompressed fallback remains.

The benchmark uses production `broadcast_once` JSON and WebSocket frame
serialization with real rivals following collision-checked patrols, sampled
at 10 Hz. Its final crowded-map measurements are:

| Moving rivals plus one human | Uncompressed bytes/second | Compressed bytes/second | Frame-byte reduction |
|---|---:|---:|---:|
| 100 rivals | 315,255 | 56,846 | 81.97% |
| 160 rivals | 502,677 | 88,684 | 82.36% |

All actors and decoded game information remain present. The JSON report also
includes 8- and 13-rival samples, encoder timings, compression settings and
source hashes. It measures WebSocket frame bytes, excluding TLS/TCP/IP overhead,
acknowledgements and other game traffic. These Linux development measurements
are not measurements of the user's network or a Windows hosting guarantee.

To reproduce the isolated measurement from the complete source folder:

```text
python tools/benchmark_world_bandwidth.py --samples 100 --output qa/world_bandwidth.json
```

## Release scope

The suite retains the existing 12-hour Bot Activity, startup ownership/long
loading, DigiRuby economy and both story-campaign regressions. Historical
evidence folders retain their original release versions and populations.

This is a **source release**. Native Windows executables were not built in the
Linux test environment. Rebuild and deploy the server on Windows using the
[upgrade guide](../../POPULATION_V0123.md), then check the intended host. Existing
v0.12.2 clients remain compatible; installing the rebuilt client is optional.
