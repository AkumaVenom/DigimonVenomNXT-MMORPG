# Ghostline campaign map layout

Ghostline uses 31 distinct existing Super Xros Wars maps: one peaceful service hub and 30 connected field chapters. The private campaign changes the story attached to these maps, not the public region, supplied artwork, collision masks, music assignments, or public arrival points. All 31 source-art SHA-256 hashes are different.

Twenty-one maps use circuit boards, machinery, technological gates, or digital rooms. The remaining ten provide mineral data-excavation passages and ruined archive environments. Ghostline's location names and story are original Venom NXT fiction; they are not represented as canonical names or dialogue from another game.

| Campaign map | Source map | Visual setting |
| --- | --- | --- |
| 1 | `xros_175` | Neon service console; safe Backchannel hub |
| 2 | `xros_051` | Mechanical network causeway |
| 3 | `xros_052` | Mechanical network causeway |
| 4 | `xros_054` | Mechanical network causeway |
| 5 | `xros_126` | Crystal data-excavation passages |
| 6 | `xros_127` | Crystal data-excavation passages |
| 7 | `xros_128` | Crystal data-excavation passages |
| 8 | `xros_129` | Crystal data-excavation passages |
| 9 | `xros_130` | Crystal data-excavation passages |
| 10 | `xros_097` | Damaged archive fortress |
| 11 | `xros_098` | Damaged archive fortress |
| 12 | `xros_100` | Damaged archive fortress |
| 13 | `xros_133` | Damaged archive fortress |
| 14 | `xros_134` | Damaged archive fortress |
| 15 | `xros_152` | Purple circuit platforms |
| 16 | `xros_153` | Purple circuit platforms |
| 17 | `xros_154` | Purple circuit platforms |
| 18 | `xros_155` | Purple circuit platforms |
| 19 | `xros_156` | Purple circuit platforms |
| 20 | `xros_157` | Purple circuit platforms |
| 21 | `xros_160` | Purple circuit platforms |
| 22 | `xros_163` | Purple circuit platforms |
| 23 | `xros_164` | Purple circuit platforms |
| 24 | `xros_165` | Purple circuit platforms |
| 25 | `xros_161` | Mechanical network causeway |
| 26 | `xros_180` | Mechanical network causeway |
| 27 | `xros_182` | Mechanical network causeway |
| 28 | `xros_188` | Mechanical network causeway |
| 29 | `xros_119` | Technological firewall above the caldera |
| 30 | `xros_177` | Suspended digital terminal |
| 31 | `xros_176` | Neon central-control arena |

## Actor and portal placement

`venom/common/xros_story_layout.py` contains the ordered `CAMPAIGN_MAPS` tuple and nine `PLACEMENTS` for each map. The slots are arrival, quest/guide, medic, shop, tamer/lab, boss/farm, return portal, intel/archive, and forward portal. Content selects the slots appropriate to each chapter; unused slots never spawn an actor.

Every standing point is reachable from that map's unchanged public arrival using the authoritative `Navigation.trace` collision routine. The proof follows cardinal 16-unit steps and checks every intervening collision pixel, rather than assuming that individually walkable points belong to the same room. Every NPC and portal position has a clear foot-sized area and at least 96 world units of separation from every other authored slot. The safe-hub service characters surround the console floor; they do not occupy the console itself. The finale uses the arena's actual surrounding walkway, keeping the central machinery inaccessible as supplied. The caldera exit stands on the solid lower platform, clear of the lava.

Campaign content controls when portals open: the first map leads to the first assignment, field completion opens the next connected chapter, and the final map's completion exit returns to the safe hub. There is no nonexistent map 32. Backward routes support recovery and supply trips.

## Reproduce validation

From the project folder, run:

```text
python -m pytest tests/test_xros_story_layout.py -q
python tools/preview_ghostline_layout.py
```

The preview command verifies all 279 authored slots and writes a collision report, 31 full-map placement previews, and four contact sheets under `docs/validation/release_v140/layout/`. Markers identify each slot; the green line follows an actual collision-checked route to the forward portal. Supplied map assets are never rewritten. The dedicated layout tests independently verify the real movement paths, map identity, arrival preservation, spacing, and floor clearance.
