# Fixed-sprite patch — verification record

**Target:** the uploaded 29-part Digimon Venom NXT v1.0.1 source.  
**Input pack:** `DigimonFixedSpritesFor_v1.1.0.rar`.  
**Validation date:** September 29, 2026.

## Archive integrity and replacement coverage

All 29 baseline volumes were present. All **22,459 regular baseline files**
were extracted and CRC-verified. All **711 fixed-pack PNGs** were extracted and
CRC-verified independently. Every replacement filename mapped to exactly one
existing source asset; there were no unmatched files.

| Verification | Result |
| --- | --- |
| Supplied PNG inputs accounted for | 711 / 711 |
| Canonical replacement PNGs checked byte-for-byte | 709 / 709 |
| Replacement RGBA pixel hashes, dimensions and transparency | Passed for all 709 |
| Fixed animation-frame routes | 584 / 584 |
| Supplied primary-image/front routes | 125 / 125 |
| Species with explicit, rebuild-stable art metadata | 133 / 133 |
| Runtime catalog species retained | 1,004 |
| Full asset/catalog manifest | 21,954 records verified |
| Non-art catalog fingerprint | Identical to the uploaded baseline |
| Unaffected complete species records | 871 unchanged, including all 502 Paradox forms |

The complete asset-manifest SHA-256 is:

```text
c17833be17032c05443e34ae7770f4ea9379f09af46f327180520b8d6de509dc
```

## Whole-baseline isolation audit

Each original archive file was compared with its patched counterpart. Exactly
**712 original files changed**: 709 PNGs plus `data/catalog.json`,
`data/source_assets.json` and `data/asset_manifest.json`. The other **21,747
original files** are unchanged. No original file is missing, and no unexpected
original file changed. New sidecars, the fixed-sprite registry, tools, tests and
patch documentation are additions rather than replacements for unrelated files.

All **8,609 files under the original Paradox directories** were checked and are
byte-identical. No file under `venom/` changed. The app remains version 1.0.1.

## Executed tests

**1,406 distinct tests passed** across the new sprite checks and runnable
baseline regression tests. Repeated checks on the fresh overlay below are not
counted twice. The baseline run also passed **1,346 subtests**, reported
separately rather than added to the test count.

| Run | Result |
| --- | --- |
| `tests/test_fixed_sprites.py` and optional runtime module | 866 passed; 1 SDL-module skip |
| Available baseline regression run | 531 passed; 12 environment-related failures; 1 existing skip |
| Nine desktop-wizard cases rerun with an Xvfb display | 9 passed |
| Unique baseline tests passing after the display rerun | 540 |
| Fresh copy of original baseline plus the prepared patch: sprite suite | 866 passed; 1 SDL-module skip |
| Fresh-overlay full fixed-sprite and normal-builder manifest verification | Passed |

The new tests cover all supplied image hashes, decoded pixels and dimensions;
input/duplicate accounting; all 133 species' routing through the actual pure
`Assets.sprite_path` method; explicit primary portraits; Daemon's corrected
step/attack sequence; full `species_catalog()` rebuild behavior; non-art and
unaffected-species fingerprints; Fanglongmon preservation; full manifest
coverage; path traversal and symlink rejection; input preflight; importer
idempotence; and rollback after a simulated disk-write failure.

### Environment limits, not hidden failures

This Linux test environment has Python 3.13.5, Pillow 12.3.0, pytest 9.0.2 and
websockets 16.0. The project's dependency files were not changed. `pygame-ce`,
PyMySQL and `ndspy` are not installed, and dependency downloads were unavailable.

Before selecting the runnable baseline tests, **52 original test modules** could
not collect: 45 depended on `pygame`, 5 on `pymysql` and 2 on `ndspy`. Those
modules are not described as passing.

The 56 collectable baseline modules contained 544 ordinary test cases. Their
initial run produced 531 passes, 12 failures and one skip. All 12 failures were
rerun against the **untouched original baseline** and reproduced with identical
exception messages. Nine were Tk display errors; providing Xvfb allowed all nine
to pass. The remaining three checks are blocked by missing modules:

- `test_foreign_database_identity_is_rejected_and_connection_closed` — `pymysql`.
- `test_native_rival_interpolation_drives_real_walking_frames_on_both_clients` — `pygame`.
- `test_in_flight_departed_map_frame_is_rejected_by_native_client_after_travel` — `pygame`.

The new `tests/test_fixed_sprites_runtime.py` deliberately skips when pygame is
unavailable. On a configured source environment it checks the real SDL image
loader, idle/walk/attack/front rendering at four UI/world/battle sizes, both flip
directions and bounded cache reuse for all 133 affected species. Those actual
SDL rendering checks were **not executed here**. The pure frame-resolver tests
and Pillow decoding are not represented as a substitute for a graphical client
play-through.

No Windows executable compilation or live Windows MySQL acceptance run is
claimed. This deliverable is a source overlay, not a prebuilt client/server.

## Fresh-overlay acceptance and local verification

The prepared replacement files were applied to a **fresh copy of the original
baseline**, not only tested in the editing tree. The standalone verifier passed
all image, reference, sidecar, gameplay and full-manifest checks. The 866 new
non-SDL tests passed again in that fresh overlay.

After copying the delivered ZIP contents into the source root, run:

```bat
VERIFY_FIXED_SPRITES.bat
```

Or use the existing development/build Python:

```bat
python tools/fixed_sprites.py --verify
python tools/build.py --verify-only
python -m pytest -q tests/test_fixed_sprites.py tests/test_fixed_sprites_runtime.py
```

The first two checks cover the installed source and build inputs. Rebuild
previously compiled Windows distributions through the existing build workflow.
The compact execution log is in `docs/FIXED_SPRITES_V110_TEST_RESULTS.txt`.
