# Cyber-blue arena verification

All eight PNGs are screenshots of the real native client using isolated synthetic
QA data. They cover live combat and a ranked replay at 960×600, the supplied
screenshot size of 2047×1155, 1920×1080, and 3840×2160. They are native-resolution
captures, not resized mockups. No accounts or server state were changed.
These screenshots and `report.json` were refreshed after the corrected v1.0.0
target-card layout. Dedicated long-name, padded-highlight and stable-anchor
checks are in [the target-layout evidence](../targeting/README.md).

`report.json` records UI scale and input bounds. All eight captures have zero
actions outside the display. The arena retains the existing actor positions,
HP/SP bars, combat commands and replay controls. The selected live target now
uses a measured, padded card around the full displayed block. The original
grid visual review covered readable health bars, commands and combat effects,
including the minimum window and native 4K output.
The decorative floor seal is omitted when the space between teams cannot keep
it clear of their labels; replay titles sit inside the arena's quiet header.

Reproduce the screenshots from the source root:

```sh
python tools/preview_ui_screens.py --output docs/validation/release_v100/arena --views battle ranked_replay --sizes 960x600 2047x1155 1920x1080 3840x2160
```

## Rendering and input contracts

`focused_tests.xml` records the original **70 passing tests**, with no warnings,
from before the target-card correction. The selection
includes native rendering, background caches, combat command input, minimum/4K
navigation, community replay behavior, and eight new arena regression cases.
The arena cases verify:

- Warm draws reuse the same native pixels without repainting the artwork.
- Moving the same-sized arena reuses its cache; size and DPI changes rebuild it.
- Exact incoming physical clipping survives fractional UI scales, direct
  rendering, and rendering exceptions, with no writes outside the clip.
- Failed cache creation can be retried.
- Oversized arenas allocate no background surface, including the boundary where
  the whole arena exceeds 32 MiB but its inset field would fit under that limit.
- Replays paint the shared background before drawing their heading and title.

Reproduce this test selection:

```sh
python -m pytest -q tests/test_battle_arena.py tests/test_render.py tests/test_background_cache.py tests/test_performance_caches.py tests/test_cyber.py tests/test_destinations_combat_design.py tests/test_ui_navigation.py tests/test_ui2_navigation.py tests/test_ui2_integration.py tests/test_community_client.py --junitxml=docs/validation/release_v100/arena/focused_tests.xml
```

## Local rendering measurements

`performance.json` records the original v0.12.3 stage and the v1.0.0 stage before
the target-card correction. It was not rerun for that correction. Both stages
used the same real App fixture, one cold cache build and 90 warm stage draws.
The report includes source hashes, Python/Pygame versions, and timing details.
These measurements cover the battle background only, not complete client frames.
They use headless software SDL on the validation machine; they are not a guarantee
of Windows hardware performance.

| Native display | UI scale | Old warm median | New warm median | New cold build | Retained arena cache |
| --- | ---: | ---: | ---: | ---: | ---: |
| 960×600 | 0.75 | 0.044 ms | 0.045 ms | 12.2 ms | 1.07 MiB |
| 2047×1155 | 1.25 | 0.150 ms | 0.143 ms | 17.0 ms | 5.07 MiB |
| 1920×1080 | 1.25 | 0.158 ms | 0.156 ms | 15.7 ms | 4.25 MiB |
| 3840×2160 | 2.5 | 1.941 ms | 2.035 ms | 32.8 ms | 16.99 MiB |

The more detailed artwork is built when the viewport or UI scale changes. Normal
frames retain the same native blit behavior and cache sizes as the old stage.
The retained plate is limited to 32 MiB; larger arenas use bounded direct vector
drawing without allocating an oversized gradient or arena cache.
