# v1.1.1 sprite-patch QA

## Results

**1,072 automated tests passed.** This is 979 focused sprite / compatibility /
reapplication tests plus 93 existing gameplay regression tests. One optional
runtime test module was skipped because `pygame-ce` is not installed. Two tests
that require complete audio-inclusive asset verification were deliberately
excluded locally; they remain present and enabled for a complete source tree.
No failed test was relabelled as a pass.

Environment: Python 3.13.5, Pillow 12.3.0, pytest 9.0.2 on Linux.

## Source and archive validation

All 29 baseline RAR volumes were located. The source and non-audio/non-database
assets were extracted, and **21,411 files** were independently checked against
the archive's uncompressed sizes and CRC32 values. All **20,969 non-audio baseline
manifest records** were also independently checked against their SHA-256 values.
The fixed archive's 69 files (68 PNGs plus ignored shell metadata) passed CRC32 checks.
Every supplied fix matches its record's byte hash and decoded RGBA hash.

The installed libarchive reader cannot decode at least one compressed audio block
in this archive. Audio and bundled MySQL runtime binaries are unrelated to this
patch and were excluded from the validated working extraction. The original
uploaded archives were not modified. This is an extraction-tool limitation, not
a claim that the uploaded archive is corrupt.

After patching, **20,985 non-audio manifest records** were independently SHA-256
verified. The **985 unchanged audio records** were compared with and retained
verbatim from the baseline manifest; their media bytes are **not** claimed to have
been independently rehashed here. The full 21,970-entry manifest still includes
them normally. No record was removed to make a check pass.

## Focused checks

The checks cover all 75 output PNGs, all 68 inputs, all seven duplicate-pose
synchronizations, all 20 updated species, old/new provenance, the 695 retained
v1.1.0 PNGs, the exact 14 superseded paths, and all new and inherited sprite routes.
The production `Assets.sprite_path()` method was executed directly for animation
and portrait routing. This tests real resolver code but is not a substitute for
SDL image loading or live screen rendering. All input comparisons were also
inspected in before/after contact sheets without changing the supplied PNGs.

A full 1,004-species importer rebuild preserved the art assignments of all 148
species touched by either fixed pack. Existing animation sequences, original
source-frame counts, every non-art catalog field, all 984 currently unaffected
species, all 502 Paradox records and the protected runtime/data files passed their
preservation checks.

The reapply action was tested from the uploaded v1.1.0 PNG and catalog bytes. Its
99 asset/data outputs exactly matched the delivery overlay. Repeating it produced
identical bytes. Additional tests exercise malformed packs, duplicate source names,
unknown destination bytes, symlink rejection, gameplay-change detection, duplicate
manifest/record entries, older-pack rollback refusal and the shared publisher's
rollback after simulated I/O failure. All modified Python files compile.

## Commands run

```text
python tools/fixed_sprites_v111.py --verify --sprites-only

python -m pytest -q tests/test_fixed_sprites.py tests/test_fixed_sprites_v111.py tests/test_fixed_sprites_runtime.py -k "not test_manifest_contains_every_fixed_sprite_sidecar_and_catalog_reference and not test_verifier_checks_images_metadata_and_original_gameplay" --tb=short

python -m pytest -q tests/test_catalog.py tests/test_digiruby_transactions.py tests/test_paradox_scan_mastery.py tests/test_story_engine.py tests/test_world_ds_story_engine.py tests/test_world_ds_engine.py tests/test_ranked.py --tb=short
```

The second command produced **979 passed, 1 skipped, 2 deselected**. The third
produced **93 passed**. Gameplay tests use the existing engine, catalog, story,
World DS, scan-reward, ranked and Digiruby transaction checks; they do not modify
any live account or server database.

## Not executed here

Real Pygame/SDL rendering, native Windows batch execution, Windows executable
builds and full audio-inclusive build verification were not run. The overlay
contains tests and the normal full verifier for these checks in the complete
source/development environment. There are no runtime stubs or fabricated SDL
results in the delivery.

After merging into the complete source, run:

```text
VERIFY_FIXED_SPRITES.bat
python tools/build.py --verify-only
python -m pytest -q tests/test_fixed_sprites.py tests/test_fixed_sprites_v111.py tests/test_fixed_sprites_runtime.py
```

These full-source commands are installation recommendations, not additional
commands claimed to have passed in this partial-media Linux extraction.
The machine-readable delivery inventory hashes every payload file except the
inventory itself, which is explicitly marked to avoid a self-hash cycle.
