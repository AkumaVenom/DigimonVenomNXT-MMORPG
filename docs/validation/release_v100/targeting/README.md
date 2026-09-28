# Corrected v1.0.0 battle target layout

The corrected target card measures the displayed name, level/affinity text,
sprite and HP bar and adds padding around the complete block. Long names wrap
in full. The selection outline and click target stay anchored to the normal
combat position during attack lunges and recoils.

`target_tests.xml` records **18 passing focused regressions**, with zero
failures, errors or skipped tests. The native captures and `target_geometry.json`
use an offline synthetic account, real catalog species and the native client
renderer. They do not represent a live account or change server progress.

There are **12 captures**, covering Fanglongmon/Paradox Fanglongmon and the
catalog's longest names at 960×600, 1280×800, 1920×1080, 3840×2160 and 2047×1155
with both 1.0625 and 1.25 UI scales. All report 16 actions, a chat input and
zero actions outside the display. Geometry includes measured text bounds,
target rectangles, selected outlines and viewport bounds.

The primary Fanglongmon release preview is copied byte for byte from
`fanglongmon_2047x1155_1.0625.png` here. It replaces the earlier preview with a
corrected padded highlight and full displayed names.

The files are copied from the source validation run under
`docs/validation/battle_target_fix`. No new rendering-performance benchmark is
claimed for this correction. The complete suite's current result is recorded
in [the release evidence](../README.md).
