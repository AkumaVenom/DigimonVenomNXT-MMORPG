# v1.5.0 FireWall release verification

The final source has **3,747 distinct passing tests, 10 skipped tests,
and no unresolved failures** across the complete regression run and its targeted
pagination-fixture recheck. The raw results are retained without alteration.

## Regression evidence

- `pytest.xml` / `pytest.log`: initial full run, 3,745 passed,
  2 failed, 10 skipped, 659.98 seconds.
- `QA_activity_recheck.xml` / `.log` and `QA_navigation_recheck.xml` / `.log`:
  all 23 distinct checks passed after updating the two old pagination
  button expectations to exercise all three current pages. The tests verify
  FireWall totals, exact counter coverage, real clicks, wraparound, map
  navigation, bounds at four resolutions and no server-data mutation.
  No production code changed after the full run began.
- `release_summary.json`: machine-readable final reconciliation. Overlapping
  focused runs are not added to the distinct passing-test count.
- `QA_review.json` and accompanying reports: independent acceptance,
  historical-art preservation, rarity boundaries and native layout checks.

## Coverage

The release checks all 502 FireWall forms and all 500 public habitats, exact
0.7% rarity intervals, scan and materialization, evolution and de-digivolution,
DigiFarm, real owned-partner stats, independent campaign rewards, first Dawn
championship and permanent reward retention, legacy champion migration,
restart-safe scan bonuses, bot/admin behavior and live WebSocket/SQLite saves.

`baseline_preservation.json` confirms all original 1,506 species, old map fields,
tamers and regional music remain intact. `build_verify.log` records successful
verification of all 41,180 asset/catalog SHA-256 records. The importer reports
preserve all 9,087 supplied files, including all 7,934 PNGs, byte-for-byte.

`ui/` contains 34 native-client previews at 960×600 and 1280×800.
Key scan, map, battle, DigiDex, world, farm and Dawn reward screens were visually
reviewed; compact controls and long names also have automated bounds checks.

## Environment and remaining deployment checks

Validation ran on Linux with Python 3.12 and pygame-ce 2.5.8. Skipped cases:

- 9: Requires a graphical desktop / Xvfb

- 1: Set VENOM_TEST_MYSQL_RUNTIME for opt-in Linux/MySQL validation

Windows executable generation and native setup dialogs, a production MySQL
connection and playback on the destination audio device must be checked on
the target machine. This is a complete source-and-assets release; follow
`docs/FIREWALL_V150.md` to rebuild and deploy both applications without resetting
existing saves or private server configuration.
