# v1.0.0 validation evidence

This folder records development verification for the cyber-blue battle stage,
Fanglongmon artwork integration and v1.0.0 release packaging. The release is
based on the complete v0.12.3 source.

The complete automated suite finished with **873 passed and 10 skipped** in
**240.66 seconds**, with zero failures and zero errors. The skips are one
opt-in live-MySQL check and nine graphical setup-wizard checks requiring a
desktop/Xvfb; they are not passes.

- [Complete test log](full_suite.log)
- [Complete JUnit results](full_suite.xml)

The full suite includes the new arena, target layout and Fanglongmon checks together with the
retained story campaigns, DigiRuby economy, 3,000-rival population, 12-hour
activity retention, saved-world startup and compressed network regressions.
Focused selections below overlap with the full suite and are not additional
passes to add to its total.

## Cyber-blue arena

The [arena report](arena/README.md) records the original **70 passing focused
tests**, eight refreshed native live-battle/replay captures and earlier local
background-rendering measurements. Captures
cover 960×600, 1920×1080, 2047×1155 and 3840×2160. All input-bound checks report
zero actions outside the display. The same battle background is used by live
combat and ranked replays. The corrected live target layout uses a measured,
padded selection card and stable click area.

- [Live battle at the supplied screenshot size](arena/battle_2047x1155.png)
- [Ranked replay at the supplied screenshot size](arena/ranked_replay_2047x1155.png)
- [Minimum-window battle](arena/battle_960x600.png)
- [Native 4K battle](arena/battle_3840x2160.png)
- [Arena test results](arena/focused_tests.xml)
- [Rendering measurements and source hashes](arena/performance.json)

The arena retains one native background plate up to 32 MiB and redraws it only
when the viewport or UI scale changes. Oversized arenas use direct vector
drawing without allocating an oversized background. The local headless timings
cover only background rendering; they are not full-client frame rates or
measurements of the user's Windows hardware.

## Corrected target cards

The [target-layout evidence](targeting/README.md) records **18 passing focused
tests** and 12 native captures using normal/Paradox Fanglongmon and the catalog's
longest names. It covers the minimum window, 1280×800, 1080p, 4K and both 1.0625
and 1.25 UI scales at 2047×1155. Names wrap in full and the padded target card
contains the name, level/affinity details, sprite and HP bar. The outline and
click area remain anchored during attack lunges and recoils.

- [Corrected Fanglongmon target at 2047×1155 / scale 1.0625](targeting/fanglongmon_2047x1155_1.0625.png)
- [Longest-name targets at the minimum window](targeting/longest_960x600_0.75.png)
- [Native target geometry](targeting/target_geometry.json)
- [Target regression results](targeting/target_tests.xml)

## Fanglongmon artwork

The [combined battle preview](fanglongmon/fanglongmon_battle_2047x1155.png)
shows normal and Paradox Fanglongmon in the native client. Its
[visual report](fanglongmon/visual_report.json) records six original 1254×1254
RGBA frames per form and preserved original image bytes. The current preview
uses the corrected target fixture at 2047×1155 with UI scale **1.0625**, 16
actions and no off-screen actions. The earlier focused artwork, animation and
gameplay selection reported **61 passes**; the target correction has its own
18-test selection linked above.

The species retain their existing IDs, statistics, habitats, scan rewards,
materialization rules and evolution/devolution routes. Checks cover both forms'
idle and attack poses, authored left-facing movement, bounded sprite caches,
catalog regeneration and saved-partner restoration. The
[Fanglongmon guide](../../FANGLONGMON_V100.md) documents the exact content scope
and source-image provenance.

## Release metadata and packaging

[Focused release checks](package_tests.xml) completed with **23 passed**. These
exercise setup diagnostics, v1.0.0 version metadata, bundled current/historical
guides and validation evidence, source-package filtering and saved-data/privacy
exclusions. Windows packaging is simulated with dummy executables; the checks
do not run a native Windows compiler or execute Windows launchers.

The regenerated asset manifest contains **21,820 files**. It includes all twelve
supplied Fanglongmon poses alongside the retained content; no species migration
or database reset is required. Native battle, replay and combined Fanglongmon
captures were refreshed after the target-card correction. The original arena
background timings and focused artwork results retain their earlier scope;
they are not new performance measurements of the target-card correction.

Older reports under the other validation folders retain their original versions
and measurement scope. They are historical evidence, not new measurements of
v1.0.0. The current release does not change the world-update protocol or its
compression settings.

## Release scope

These are source checks in the development environment. Native Windows
executables have not been built or deployed here. Use the
[v1.0.0 upgrade guide](../../RELEASE_V100.md) to rebuild and deploy both Windows
applications when upgrading from v0.12.3. Existing v1.0.0 installations need
the rebuilt client for the target correction and may retain their server.
Preserve the existing database, configuration and credentials, then check the
intended host.
