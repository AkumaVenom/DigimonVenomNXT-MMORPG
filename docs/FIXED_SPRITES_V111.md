# FixedSpritesPart2 v1.1.1 — source overlay

## Installation and target

Use the complete uploaded 29-volume `DigimonVenomNXT` source as the baseline.
This already contains the previous v1.1.0 sprite patch. Close the client/server,
back up the source, then merge the ZIP contents into the source root beside
`BUILD_ALL.bat`. Replace matching files; do not remove the existing directories.
Run `VERIFY_FIXED_SPRITES.bat`. Rebuild existing executable distributions through
the original Windows build workflow after applying the source overlay.

No database migration, setup rerun, account reset or new game is necessary.
No files need deletion. No new PNG naming scheme or alternative renderer is added.
The underlying application version remains the uploaded value, **1.0.1**;
**v1.1.0 and v1.1.1 here identify the sprite-patch lineage**, not a rewritten release identity.

## Complete replacement accounting

The fixed archive contains **68 PNGs**, one ignored `desktop.ini`, and its folder
entry. Each supplied PNG matches one existing normal-species asset unambiguously.
All 68 are installed. Seven additional destinations are proven duplicate copies
of supplied poses, for **75 overwritten PNG paths**: 59 numbered frames,
12 primary images and four labelled poses. No source image is discarded.

Every output preserves its selected input's exact file bytes, RGBA pixels, size,
transparency and dimensions. There is no resizing, cropping, redraw, palette
conversion or re-encoding. `-transparent` is removed from destination filenames
only; the exceptional `Barbamon_Frame_002-.png` explicitly maps to the existing
`Barbamon_Frame_002.png`. Input filenames are retained in the audit record.

| Digimon | Direct supplied PNGs | Synchronized copies | PNG destinations |
| --- | ---: | ---: | ---: |
| Aquilamon | 5 | 1 | 6 |
| Barbamon | 5 | 1 | 6 |
| Birdramon | 4 | 0 | 4 |
| Chaosmon | 6 | 0 | 6 |
| Crowmon | 3 | 0 | 3 |
| GallantmonCrimsonMode | 2 | 0 | 2 |
| ImperialdramonFighterMode | 1 | 1 | 2 |
| KingChessmon | 1 | 0 | 1 |
| Knightmon | 4 | 1 | 5 |
| LadyDevimon | 3 | 0 | 3 |
| Leopardmon | 4 | 1 | 5 |
| Lilamon | 3 | 1 | 4 |
| LucemonChaosMode | 6 | 0 | 6 |
| MachGaogamon | 6 | 0 | 6 |
| MasterTyrannomon | 1 | 0 | 1 |
| MetalSeadramon | 1 | 0 | 1 |
| Palmon | 1 | 0 | 1 |
| Shawjamon | 4 | 0 | 4 |
| Skullknightmon | 4 | 1 | 5 |
| Taomon | 4 | 0 | 4 |
| **Total** | **68** | **7** | **75** |

## Duplicate-pose coverage

Simply copying the named inputs would leave old portrait copies for several
Digimon and an old idle copy for Skullknightmon. These seven extra replacements
reuse the supplied PNG bytes exactly. They do not invent missing poses.

| Additional canonical image | Supplied PNG used | Evidence |
| --- | --- | --- |
| `Aquilamon_Primary.png` | `Aquilamon_Frame_001.png` | Identical baseline RGBA pixels |
| `Knightmon_Primary.png` | `Knightmon_Frame_001-transparent.png` | Identical baseline RGBA pixels |
| `Lilamon_Primary.png` | `Lilamon_Frame_001-transparent.png` | Identical baseline RGBA pixels |
| `Barbamon_Primary.png` | `Barbamon_Frame_002-.png` | Identical original bytes recorded by v1.1.0 |
| `ImperialdramonFighterMode_Primary.png` | `ImperialdramonFighterMode_Frame_001.png` | Identical baseline RGBA pixels |
| `Leopardmon_Primary.png` | `Leopardmon_Frame_001-transparent.png` | Identical baseline RGBA pixels |
| `Skullknightmon_Frame_001.png` | `Skullknightmon_Primary.png` | Identical original bytes recorded by v1.1.0 |

Barbamon's primary and frame 002, and Skullknightmon's primary and frame 001,
have identical original-file hashes in the immutable v1.1.0 record. That establishes
their common pose even though the earlier independently corrected copies differ.
The other five pairs have exactly matching decoded baseline RGBA pixels.
All seven evidence records and source/destination hashes are included in
`data/fixed_sprites_v111.json`.

## Runtime, portraits and rebuild safety

The existing `Assets.sprite_path()` and shared image cache remain unchanged.
All corrected files overwrite the existing canonical paths, so existing battle,
world, partner, farm and other shared-renderer uses resolve the fixed artwork.
The 20 affected records receive explicit `front` routes and matching
`animation.json` metadata. Supplied/synchronized primary files are used as front
portraits; species without a new primary retain their existing front route or
use their existing idle image. No unrelated portrait is guessed or discarded.

All prior idle, walking and attack sequences and all non-front pose assignments
are preserved exactly. Original `source_frame_count` values remain historical
counts. The established `animation_override()` importer honors the sidecars,
and a complete species catalog rebuild preserves all 148 species covered by
either sprite patch. There are 20 sidecars in this overlay: five replace existing
sidecars and 15 are new.

## Manifest and historical compatibility

`data/asset_manifest.json` retains the existing version-1 `path`, `size` and
`sha256` schema. It contains **21,970 records** after the overlay: 82 existing
records updated, 16 added (15 sidecars plus the new sprite record), and zero
removed. The manifest does not include itself, matching the normal builder.
All untouched records are preserved, including all 985 audio records.

`data/source_assets.json` gains one v1.1.1 provenance entry. The earlier provenance
entry remains unchanged, and `data/fixed_sprites_v110.json` is retained byte-for-byte. Fourteen older corrected paths are explicitly
superseded; the other 695 older fixed PNGs remain strict verification targets.
The combined effective inventory contains **770 corrected PNG paths**.

`tools/fixed_sprites.py --verify` delegates to the v1.1.1 verifier when the new
record is installed. The older `--source` action refuses to overwrite a newer
installation. Historical v1.1.0 documentation and its old delivery inventory
remain historical records; the v1.1.1 documents and inventory describe this overlay.

## Gameplay and unrelated assets

Only the catalog's existing art fields are changed: `sprites`, `animations`,
`mirrored_frames`, `source_frame_count`, `frame_selection` and `art_provenance`.
The values of the sequences, counts and selection rules are preserved; metadata
and front routes describe the corrected source art. A canonical fingerprint
checks every non-art field, not just a handful of stats.

All **1,004 species** remain, including all **502 Paradox forms**. The complete
records of the **984 species outside this pack** are unchanged. Unprovided poses
and separate Paradox artwork remain untouched. No file under `venom/` is included
in the overlay. Story modes, quests, boss badges, scan mastery, Digirubies, ranked
systems, XP, levels, items, encounters, evolution routes and balance are preserved.
The verifier also checks the original hashes of unrelated data JSON and runtime
Python files; intentional subsequent gameplay changes will be reported rather
than silently reset.

## Verification and optional reapplication

Normal installation requires only the file overlay. From the source root:

```text
python tools/fixed_sprites_v111.py --verify
python tools/build.py --verify-only
```

The first verifies both generations of corrected PNGs, alias coverage, sidecar /
catalog / importer agreement, retained gameplay fingerprints and the full normal
build manifest. `VERIFY_FIXED_SPRITES.bat` runs this full check. It uses the existing
Python environment and Pillow; it does not install dependencies or touch databases.

For a deliberately partial source checkout, an explicitly limited check exists:

```text
python tools/fixed_sprites_v111.py --verify --sprites-only
```

Its output states `full_build_integrity_checked: false`. It validates Digimon
assets and data, not all media, and must not be substituted for full release checks.

To reapply from the original extracted fixed pack after installing this overlay's
metadata/tools:

```text
python tools/fixed_sprites_v111.py --source "C:\Assets\FixedSpritesPart2"
```

All 68 exact input PNGs are required; `desktop.ini` is ignored. Unknown, missing,
corrupt, duplicate-named or symlinked sources are rejected before game-file writes.
Only the uploaded v1.1.0 or already-patched v1.1.1 destination hashes and known
art assignments are accepted. The action is byte-idempotent, preserves unrelated
manifest records, stages all writes and uses the existing rollback-on-I/O-error
publisher. Close running processes and keep a backup: a multi-file overlay is not
an atomic filesystem transaction across power loss. This command is not an importer
for an arbitrary older/raw sprite archive.

The full installation checks, test commands and environment limitations are in
`FIXED_SPRITES_V111_QA.md` and the captured test-results file.
