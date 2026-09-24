# Portable MySQL validation

This validation applies to the fresh portable database changes on the supplied
0.3.1 baseline. Historical validation files describe earlier releases.

## Checks actually run

- **236 regression checks passed, 9 GUI checks skipped** in the initial full run
  (41.15 seconds). The skips require a graphical desktop. **28 final targeted checks passed**
  (1.60 seconds), including the shutdown and system-account guards.
- **The production MySQL/WSS relocation test passed** (26.72 seconds). It used
  MySQL 8.4.11, the real game engine, an actual separate world process and TLS.
  It registered an account, bought an item, moved the player, and requested a
  clean stop while the player was connected. Player data, released leases, eight
  rival saves and ranked season data were checked directly in MySQL.
- The same test then made an **ordinary ZIP of the whole stopped test folder**,
  extracted it to a different path containing spaces and Unicode, and made the
  original path unavailable. Restart preserved the exact player JSON, revision
  and every rival save. The same account and password logged in successfully.
- A separate manager test verified fresh initialization, repeat setup without
  resetting progress, folder ownership rejection, SQL table health, and refusal
  to start or stop another folder's running database.
- **All 21,149 asset/catalog SHA-256 records passed.** Game content was preserved.
- Source/build packaging tests verify all launcher dependencies and the bundled
  runtime are included, and that rebuilding refuses to erase a live server.
- The Windows MySQL archive's detached signature was verified against the
  official MySQL key fingerprint. Original per-file hashes and licensing are
  retained in `mysql/provenance` and `mysql/runtime`.

## Platform limits

The live engine, game and relocation tests ran on **Linux** using the matching
MySQL 8.4.11 Linux runtime in temporary fixtures. The delivered runtime is
**Windows x64**. Windows executables were not built or run here; Windows GUI,
batch commands, native process/lock branches and Microsoft prerequisite helper
have static checks but still require execution on a Windows PC. The simulated
Windows packaging test is not a native Windows build.

The package contains a fresh source distribution and no initialized database,
player saves, private passwords or test accounts. `BUILD_ALL.bat` creates the
Windows server/client application distributions. The server's database runtime
is already bundled; it does not fetch MySQL on first use.

For the intended manual move, run `STOP_SERVER.bat` and wait for success before
zipping the entire server folder. Keep it stopped until zipping finishes.
Extract the full folder on compatible Windows x64, retaining the same engine,
credentials and TLS files. The destination must have the Microsoft Visual C++
x64 runtime. No database reinstall, SQL import or fresh initialization is needed
for a previously configured folder.

Machine-readable results: `PORTABLE_MYSQL_VALIDATION.json`.
