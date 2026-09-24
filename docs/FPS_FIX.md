# FPS1 performance update

This is the historical FPS1 report. UI1 includes these optimizations and adds
the new screens, music and cyber background. For the current release and client
installation steps, use [UI_UPGRADE.md](UI_UPGRADE.md).

This update is based on the supplied four-part
`DigimonVenomNXT_Portable_MySQL.zip(1)` source archive. It changes the client
rendering path. Server logic, the default 5,000 persistent rivals, database
files, artwork, audio, catalog, and game rules are unchanged.

## Install for an existing game

1. Close the game client. Copy its COMPLETE working folder, including `config`,
   to a backup outside the source's `dist` directory before building. Keep that
   copy until the new client connects successfully. A rebuild replaces client
   output under `dist`, so take this copy first even if you currently play
   directly from there.
2. Extract the full FPS1 source ZIP into a new writable folder. Alternatively,
   extract the small FPS1 source patch into the parent of your existing
   `DigimonVenomNXT` source folder and merge its files. Check that the resulting
   `venom/client/assets.py` contains `IMAGE_CACHE_ITEMS = 4096`.
3. Run `BUILD_ALL.bat` in that source folder on Windows x64 with Python 3.11 or
   newer installed. This produces separate client and server packages. As with
   the original build, an existing build environment supports `BUILD_ALL.bat
   --offline`; the first build needs the runtime/build dependencies.
4. Extract `dist/Windows_Client_x64.zip` into a NEW client folder, then copy your
   backed-up client's complete `config` folder into it, replacing the defaults.
   Keep its `client.json` and trusted `server-ca.pem` together.
5. Start the new client's `PLAY_DIGIMON_VENOM_NXT.bat` and connect to your current
   server. Its `build-info.json` should say `0.3.2-portable-fps1`.

Your current portable MySQL server is compatible with this client-only change.
Continue using it and its saves. You do not need to run database setup, replace
the server, or create another account for this update. The builder creates
server output as part of its normal workflow, but that output is not needed
for an existing installation. Keep live installations outside the source's
`dist` directory, as required by the original builder.

If you run Python source directly, merging the patch and restarting the source
client is sufficient. Copying `.py` files beside an already compiled EXE does
not update the code embedded in that EXE: rebuild and use the complete new
client folder.

Rollback: close the new client and launch the previous client folder. This
update introduces no database migration or save conversion.

## What changed

- Fitted animation frames are reused before attempting to reload their source
  PNG. Hundreds of tiny frames now fit within the existing 128 MiB source and
  96 MiB fitted-art cache budgets instead of hitting low entry-count limits.
- World sprites retain more small frames within the existing 24 MiB budget.
  Native UI sprite scaling retains its 32 MiB budget. These caches remain
  bounded and use nearest-neighbour scaling.
- Camera scrolling reuses a native-resolution map patch with up to 128 physical
  pixels of margin on each side. It refreshes on zoom, resize, map changes, or
  when scrolling beyond the margin. Foreground transparency and draw order
  are retained. Fractional-scale sampling can differ slightly from the old
  per-frame crop resampling; the artwork is not reduced or blurred.
- Camera transforms are shared within each frame. Nameplate measurements and
  fitted UI text layouts are cached. The static background grid is cached at
  native resolution, with a 64 MiB limit and direct-draw fallback for larger
  windows.

No bot population, animation frequency, render resolution, high-DPI setting,
sprite detail, map, audio, collision rule, or gameplay feature is removed.
Frame-cap settings remain unchanged. Initial visits still load new artwork;
the fix targets needless repeated work once artwork has been encountered.

## Measured crowded-scene result

Three sequential before/after comparisons used the identical deterministic
scene: 160 rivals plus their companions, 322 world actors in total, 2048x1152
native pixels, 133% UI scale, Dawn Sector 004, and 1.5x zoom. Each run warmed up
for 960 frames and measured the next 360, covering all eight tamer directions.
The table reports the median result across the three runs.

| Metric | Supplied baseline | FPS1 |
|---|---:|---:|
| Mean CPU frame preparation | 43.13 ms | 11.73 ms |
| 95th-percentile frame time | 211.71 ms | 16.24 ms |
| PNG decodes during measured 360 frames | 8,948 | 0 |
| Rivals / total world actors | 160 / 322 | 160 / 322 |

That is about 73% less average frame-preparation time, or 3.68x CPU throughput,
for this workload. The large improvement in long frames is especially relevant
to the reported instability. These are controlled Linux software-rendering
measurements, not a claim that your Windows client will show a particular FPS.
Raw runs and additional crowd/scroll scenarios are in `FPS_BENCHMARK.json`.

## Compare on your PC

Use the same account, sector, resolution, UI scale, zoom, and similar local
crowd in the old and new clients. Enable the FPS counter in Settings. Keep the
frame cap identical and high enough to see the difference. Walk around as well
as standing still, and check camera motion and nearby rival animation after
the area has loaded. The selected cap and display hardware still bound the
FPS you can see.

## Reproduce the developer benchmark

From the source folder with its dependencies installed:

```sh
python -m tools.benchmark_client_fps --bots 160 --frames 360 --warmup 960 --json fps-local.json
python -m tools.benchmark_client_fps --bots 160 --frames 360 --warmup 960 --pan --json fps-pan.json
```

The tool renders the real client at 2048x1152, 133% UI scale, 1.5x map zoom,
with all 64 tamer appearances, varied Digimon companions, and synthetic 10 Hz
world snapshots. `--project` selects another source checkout for an identical
workload. It uses an SDL dummy display, fixed simulation timing, and no frame
limiter; it measures CPU frame preparation rather than monitor FPS, GPU
presentation, network latency, or live server/database contention. Benchmark
snapshots are local fixtures and do not change real bots or saves.

The release was checked in Linux. Windows executable creation and FPS on your
particular PC must be checked on Windows; no fixed Windows FPS is promised.

## Regression and preservation checks

- Full suite: 254 passed, 10 skipped. The skips require an opt-in live MySQL
  runtime or a graphical setup-wizard test environment; none are client render
  failures. Final build/instruction checks were rerun and all three passed.
- All 21,149 shipped asset/catalog size and SHA-256 records verified.
- All 21,505 original source-package files are still present. Artwork, audio,
  data, MySQL runtime, server code, and common gameplay code match the supplied
  baseline byte for byte.
- Regression coverage includes native 4K UI, resize/fullscreen, zoom, camera
  edges/clipping, foreground alpha, rival clicks/facing, sprite-cache limits,
  player prediction, combat views, network integration, and the real 5,000-rival
  population scheduler. See `FPS_VALIDATION.json` for details.
