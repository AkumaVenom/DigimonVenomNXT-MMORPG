# Fixed-sprite pack v1.1.0 — source patch for v1.0.1

## Target and installation

This overlay was prepared against the complete, uploaded 29-part
`DigimonVenomNXT` archive. Its `venom/version.py` identifies the source as
**1.0.1**. The application version is deliberately not changed: **v1.1.0 is the
supplied sprite-pack name**, not a claim that this is a new complete game release.

Close the client and server, back up the source, and copy the ZIP's contents into
the existing source root beside `BUILD_ALL.bat`. Merge folders and replace the
individual files. Do not delete the original `assets`, `data`, `tools` or `tests`
folders. Run `VERIFY_FIXED_SPRITES.bat`, then restart source-running processes.
A previous executable build does not read edits from a different source folder;
rebuild it through the existing Windows build workflow to distribute the new art.

The patch contains no saves, credentials, server configuration, MySQL data,
portable runtime, dependencies or compiled executables. It does not require
schema migration, database initialization or a new game.

## Complete replacement accounting

| Item | Count |
| --- | ---: |
| PNG inputs in the supplied fixed pack | 711 |
| Unique canonical image replacements | 709 |
| Numbered animation-frame replacements | 584 |
| Primary-image replacements | 125 |
| Updated normal Digimon records | 133 |
| Duplicate input alternatives resolved | 2 |
| Unchanged other species records | 871 |
| Total playable catalog records retained | 1,004 |
| Complete post-patch asset/catalog manifest records | 21,954 |

All 709 canonical filenames matched exactly one existing asset. There are no
unmatched source images and no guessed species-name matches. The source suffix
`-transparent` is removed from the **destination filename only**, placing the
new bytes at the existing path. The chosen PNG data, RGBA pixels, transparent
background and supplied dimensions are preserved without resampling or
re-encoding. Every selected image has both a runtime catalog reference and a
manifest entry.

All 711 input filenames, sizes and SHA-256 hashes are recorded in
`data/fixed_sprites_v110.json`, together with the source RAR's hash. The two
superseded alternatives are explicitly accounted for rather than left as
additional animation frames or accidental fallbacks:

- **Snimon frame 001:** the plain and `-transparent` inputs are pixel-identical.
  The transparent-named input is published once at `Snimon_Frame_001.png`.
- **CherubimonGood frame 002:** the `-transparent` input is the later revision in
  the supplied archive (07:59:57 UTC versus 07:58:38 UTC, September 29, 2026).
  That supplied revision is published at `CherubimonGood_Frame_002.png` without
  further alterations.

The original pack's missing poses are not invented. Eight of the 133 supplied
Digimon have no new primary image, and some have only a subset of corrected
frames. Their unprovided original images remain in place. Separate Paradox
artwork was not supplied in this fixed pack, so all 502 existing Paradox forms
and their original art remain unchanged, including the earlier custom
Fanglongmon normal/Paradox six-pose implementation.

## Animation integration

The client already resolves Digimon frames through `Assets.sprite_path()` and
loads them through the shared `Assets` cache. Replacing the canonical PNGs
therefore updates their existing uses in battle, the overworld, partners,
DigiFarm, the DigiLab, shop portraits and other shared-renderer screens without
forking the renderer or adding a second asset-loading path.

The existing pose assignments are preserved for 132 of the 133 affected records.
Their catalog metadata now has matching per-species `animation.json` sidecars,
which the established `tools/import_assets.py` importer already honors. These
prevent a future catalog rebuild from guessing different frames or selecting
sheet components. All 125 supplied primary images also have explicit `front`
portrait entries, supported by the existing resolver. Animated views continue
to use their ordinary idle/walk/attack sequences.

### Daemon's previously excluded frame

The supplied `Daemon_Frame_003-transparent.png` is **201 × 169**, replacing the
old **201 × 352** component. The previous importer excluded the taller component
and therefore used frame 004 as a walking pose while both attack slots fell
back to idle. The supplied four corrected full-size poses now have these routes:

| Role | Canonical frame |
| --- | --- |
| Idle | 001 |
| First alternating step | 002 |
| Second alternating step | 003 |
| Attack | 004 |
| Attack recovery | 001 |

Idle and walking cycle through `001, 002, 001, 003`. Attacking cycles through
`004, 001`. No fifth pose or new artwork is generated. The supplied crop is
copied unchanged, not produced by the patch. Original source-component counts
remain historical counts; the sidecars specify which components are animated.

## Gameplay preservation

No file under `venom/` is changed. The catalog is edited only in art fields:
`sprites`, `animations`, `mirrored_frames`, `source_frame_count`,
`frame_selection` and `art_provenance`. The source-component counts themselves
remain unchanged. Species IDs, stats, types, attributes, evolution routes,
encounter pools, XP and level settings, scan rewards, ranked/Digiruby rules,
items, story progression, maps, tamers and audio are not altered.

The verifier compares a canonical SHA-256 fingerprint of **every non-art
catalog field** with the uploaded baseline. It independently checks the complete
records of all 871 unaffected species. This is stronger than checking only
species counts or a handful of stats. Intentional later gameplay edits will
change those fingerprints and must be reviewed separately.

## Integrity and reproducibility

`data/asset_manifest.json` is rebuilt using the existing version-1 schema and
covers all assets plus all data JSON files other than the manifest itself. It
includes every replacement, all 133 new animation sidecars, the updated catalog,
updated provenance and the fixed-sprite input/output record. The normal builder's
`verify_assets()` validates the resulting 21,954 records.

Run from the source root with Python 3.11+ and the existing Pillow dependency:

```bat
python tools/fixed_sprites.py --verify
python tools/build.py --verify-only
```

The first command checks all fixed PNG hashes and decoded pixels, dimensions,
transparency, catalog routes, sidecars, rebuild behavior, provenance, gameplay
fingerprints and the entire normal build manifest. It performs no writes.
The provided batch file selects an existing development/build Python environment
when present. It never installs dependencies or modifies database state.

Reimporting the old original sprite archive will overwrite these corrected PNGs.
To intentionally reapply the fixes afterward, extract the original fixed-sprite
RAR into a separate folder and run:

```bat
python tools/fixed_sprites.py --source "C:\Assets\ExtractedFixedSpritePack"
python tools/fixed_sprites.py --verify
```

All 711 original source PNGs must be present, including both duplicate
alternatives. The importer verifies every source hash before changing any target,
rejects unknown, missing, duplicate-named or modified inputs, and accepts only
the uploaded original or already-patched bytes at replacement targets. It
preserves unrelated catalog/provenance data and is idempotent. Writes are staged
and rolled back on an I/O exception. As with a normal file overlay, close running
processes first and keep a backup for power-loss recovery.

The reproducible assignments and hashes are in `data/fixed_sprites_v110.json`.
The delivery file inventory is `PATCH_FIXED_SPRITES_FILE_LIST.json`. Test scope,
results and environment limitations are in `docs/FIXED_SPRITES_V110_QA.md`.
