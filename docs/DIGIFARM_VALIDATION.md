# DigiFarm v0.6.0 validation

Validated on 24 September 2026 in a Linux source runtime with SDL dummy video/audio.
This revision adds playable farm walking and camera zoom to v0.6.0.

- Full automated suite: **442 passed, 10 skipped** (84.35 seconds).
- Skips: nine graphical setup-wizard checks require a desktop/Xvfb; one opt-in
  live MySQL runtime check requires `VENOM_TEST_MYSQL_RUNTIME`.
- Asset integrity: **21,360 SHA-256 records, 506.3 MiB verified**.
- All client/server/tool Python modules compiled successfully.
- Follow-up renderer/client checks passed after the final maximum-zoom framing
  adjustment; the whole tamer is visible at 8× on the minimum supported layout.
- New movement checks exercise all eight directions with WASD/arrows, normal
  speed and diagonal normalization, shared shoreline collision, pending-input
  replay, stale cross-scene packets, private persisted farm coordinates and
  exact restoration of the saved field position.
- Camera tests cover independent 1–8× farm zoom, player following, wheel/keyboard
  and button controls, native DPI coordinates, clipped resident hit areas,
  protected HUD controls and movement blocked by care/search/menu overlays.
- Real WebSocket and development database tests cover per-account farm isolation,
  unauthorized feeding rejection, atomic inventory consumption, and saved bonuses.
- Tests cover 100-resident capacity, preserved legacy overflow, capacity-neutral
  swaps, optional feeding, stat/total caps, evolution, leveling, ranked snapshots,
  battle loot, home forfeits and returning to the saved world location.
- Native UI captures reviewed at 1180×800, 1920×1080 and 3840×2160. Captures include
  empty farms, populated farms, 100 residents and the care menu. No offscreen actions
  or missing assets were reported. UI tests cover Home across signed-in screens,
  full-roster swap confirmation, search, paging and no modal click-through.
- Original farm soundtrack decodes and streams successfully; routing, fade, mute,
  loop boundary and volume behavior passed audio tests.

## 100-resident rendering sample (initial v0.6.0 release)

Historical baseline measurement before this walking/camera correction.
120 frames per size after 15 warm-up frames, synthetic offline fixture. These
numbers describe this test host; they are not a Windows hardware guarantee.

| Framebuffer | Median frame | 95th percentile |
|---|---:|---:|
| 1280×800 | 4.04 ms | 6.60 ms |
| 1920×1080 | 5.95 ms | 9.23 ms |
| 3840×2160 | 17.34 ms | 25.01 ms |

Reproduce captures with `python tools/preview_digifarm.py --benchmark`. Preview
images use labelled synthetic data and do not represent an actual player account.

## Target-platform check

This is a source release. Both Windows applications must be rebuilt using
`BUILD_ALL.bat` on Windows x64. Native Windows executable launch, physical sound
output and the production portable MySQL engine were not executed on this Linux
host. Build packaging is covered by simulated-distribution tests. Follow
[DIGIFARM_V060.md](DIGIFARM_V060.md) to preserve existing saves and configuration.
