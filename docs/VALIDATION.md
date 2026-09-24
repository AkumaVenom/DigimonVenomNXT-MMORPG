# Validation report — v0.3.1 rival movement and team training

## Final automated gate

**257 tests passed, 32 skipped, no failures or errors**, in
55.58 seconds on Linux / Python 3.12.14.
The skipped tests require a disposable MariaDB server (23) or a Tk graphical
desktop (9), neither enabled for this run. The previously verified setup source
and launchers remain byte-for-byte unchanged from v0.3.0; historical setup
results below are not presented as new database or Windows runs.

The final suite includes delayed startup and post-ranked dispatch, patrols that
continue through scheduler delays, exact stopping distance, safe separated
arrivals on all 254 maps, and actual native interpolation driving the imported
NDS walking frames. Real encrypted two-client integration checks that both
players receive the same authoritative map snapshot and observe movement.

Training regressions exercise real victories earning full scan data, conversion
of duplicate species only at 100%, banking veterans without changing their
UID/XP/ABI/CAM, repeated training rounds, six-member limits, restart persistence,
and legal devolution of terminal forms with a full bank and no prior history.
Coverage tests require bounded veteran visits, protected training time, distinct
reserved destinations, and reservations retained across resumed Lab maintenance.

## Full-population migration audit

`RIVAL_TRAINING_VALIDATION.json` contains the full reproducible audit using the
actual wild battle, ranked and SQLite implementations. Its explicitly labelled
legacy-save fixture starts **5,000 level-60 rivals crowded into 57
high-level maps**, with no granted scan data, victories or subsequent progression.
The simulation runs 900 seconds with normal action,
exploration and travel timers, advancing the clock without real-time sleeps.

All **19 acceptance checks passed**. Every rival was observed moving;
all 254 maps were occupied by the 420-second checkpoint and remained
occupied at the end. The final map counts ranged from
7 to 340; low-level maps
(level 10 or below) held 1,663 rivals. This measures
resident assignment; rivals in the DigiLab are intentionally hidden on maps.

| Observed result | Count |
| --- | ---: |
| Wild victories / defeats | 28,577 / 10,651 |
| Ranked matches started | 25,000 |
| Partners materialized from earned scan data | 1,597 |
| Training-team rotations | 1,451 |
| Earned level increases | 3,250 |
| Evolutions / de-evolutions | 0 / 0 |
| Sector transitions | 13,090 |
| Gameplay recovery errors | 0 |

The audit checks positive movement, collision/speed bounds, bounded scheduler
and activity history, every original and earned partner identity, canonical
progression operations, ranked ledger reconciliation, and saved partners,
counters and training plans after reload. Conditional activities are never
fabricated to fill counters. Smaller controlled 90-minute runs additionally
exercise repeated team changes; the twelve-bot coverage fixture gave every bot
3–6 team rotations and retained all four test sectors. That small fixture uses a
ranked-call recorder; actual ranked combat is covered by the full-population
SQLite audit and WSS tests.

The full-population run took 230.20 seconds of wall time on
this shared Linux host. Its source hashes identify the exact measured revision.
Those hashes match the packaged implementation. A preceding longer diagnostic
exposed a runtime-only checkpoint bug: training/phase changes were not always
marked for saving when no gameplay operation occurred. The final suite and this
release gate include the correction, including exhausted ranked-energy waits.
`RIVAL_FIX_VALIDATION.json` records the final packaged hashes. Benchmark timing is not a Windows frame-rate,
MySQL throughput or human-player capacity guarantee.

## Assets, client and build packaging

- All **21,149 content records (485.8 MiB)** passed the builder's size/SHA-256 and
  catalog-reference verifier. Every baseline asset and catalog is unchanged.
- Rival profile/activity screens show training and veteran-visit counters. They
  were rendered and visually checked at the minimum logical layout and native
  3840 × 2160; all eight community-client tests pass in the full suite.
- Windows build-packaging tests cover the complete client/server layouts,
  version metadata, wizard dependencies and launchers. PyInstaller execution is
  simulated by those tests. Source compilation succeeds.
- No Windows executable was compiled or run here. Public connectivity and target
  Windows/MySQL performance remain deployment checks.

Build the complete source on Windows and follow `RIVAL_MOVEMENT_UPGRADE.txt`.
Preserve the existing database and both config folders. **Do not rerun the
working setup or reset rivals for this upgrade.**

To reproduce the population audit after installing the declared dependencies:

```sh
python tools/benchmark_rival_cycles.py --bots 5000 --seconds 900 --mature-save --output qa/rival-cycles.json
```

The command uses an isolated temporary SQLite database and does not touch an
installed server or player saves.

---

# Historical validation report — 0.3.0 alpha

## Guided setup redesign

- **267 automated tests passed, with no failures or skips**, in 27.55 seconds on Linux/Python 3.12.14. Both the disposable MariaDB fixture and an authenticated temporary X display were enabled for the full run.
- **23 checks used real MariaDB 10.11.14**, with independent temporary data directories and loopback ports. These include read-only connection testing, editing a failed connection and retrying, rejected administrator credentials, actual CREATE USER and GRANT permission failures, automatic game passwords under the server's password policy, selected Unicode passwords, and preserved accounts/grants/data belonging to another MMO.
- The complete service workflow ran against the real database: create the game login and schema, generate local hosting settings and the two-file player kit, read the saved schema through the game's database code, complete a real TLS handshake with hostname/CA verification using memory BIOs, compare kit contents and check the local game listening port.
- **11 wizard tests passed with actual Tk** at both **1920 × 1080 / 96 DPI** and **3840 × 2160 / 192 DPI**. They exercise password entry and clipboard paste, exact Unicode/space preservation, retained fields and error codes after failure, edited retries, background-thread operation, duplicate-submission/close guards, the complete four-page flow, report copying and small-window scrolling. Windows uses Segoe UI; Linux display checks used scalable DejaVu Sans.
- Real loopback socket fixtures cover wrong-service ports, closed/truncated greetings, silent timeouts and a server error packet carrying **1043**. The 1043 check is deliberate fault injection; the user's remembered error code and original failure have **not** been confirmed or reproduced.
- Diagnostic tests check exact stage/code classification, nested driver errors, omitted raw driver/SQL/password text, bounded event history and preservation of an in-memory report if disk writing fails. Corrupt saved configuration and DNS errors are also reported without changing the original config.
- Two builder smoke tests verify wizard/Tk/PyMySQL-metadata packaging, current launchers, separated server/setup dependencies and complete client asset copying. External PyInstaller execution is simulated in these tests; they do not establish a native Windows build.
- **21,149 asset/catalog records verified** by size and SHA-256 (485.8 MiB). No imported artwork, audio, maps or gameplay catalog was replaced. Those benchmark hashes identify the historical implementation; rival/navigation changes in v0.3.1 are covered separately.
- Source byte-compilation succeeded. The setup version command reports **0.3.0**; no-argument and explicit wizard/stage CLI dispatch were checked.

`SETUP_REDESIGN_VALIDATION.json` records final test totals, environment, limits and
tested source hashes. The complete source retains all assets and previous game
systems. Start with `BUILD_ALL.bat`, then use **01_SETUP_SERVER.bat** in the new
server distribution. `PASSWORD_SETUP_FIX.txt` explains fresh installation and
repairing an existing installation.

No native Windows executable or Windows XAMPP distribution was run in this
environment. Local readiness verifies saved configuration, database access,
certificates, the connection kit and an available bind port. It does not establish
public DNS, Windows Firewall, router forwarding or Internet reachability.

# Historical v0.2.2 verification

## Fresh-install database login repair

- **195 automated tests passed**, with no skips or failures (`python -m pytest -q --junitxml=qa/setup_release_0.2.2_results.xml`, 25.32 seconds on Linux/Python 3.12.14). The disposable MariaDB fixture was enabled using `VENOM_TEST_MARIADB_ROOT`.
- **13 tests ran against a real MariaDB 10.11.14 server**, started in an independent temporary data directory and bound to loopback. They cover fresh short passwords, punctuation/spaces/Unicode, occupied usernames, rebuilding with saved settings and data, database grant scope, rejected administrator credentials, schema failure recovery, and password-policy rejection followed by either a chosen or automatically generated password.
- The old installer was reproduced failing after a fresh-folder attempt reused an occupied database username with a newly chosen password. The corrected installer created a separate working game login automatically. A second MMO's original account credentials, grants and saved data remained unchanged in the live regression.
- Actual player registration, authentication and saved-player loading succeeded with Unicode database credentials. The community schema and an eight-bot population also initialized through the actual MySQL persistence path. This is functional database coverage, not a new 5,000-bot performance benchmark.
- Unit regressions additionally cover administrator verification before game-password entry, exact password preservation, cancellation, failed configuration writes, cleanup limited to accounts created by that setup attempt, and MySQL `partial_revokes` grant modes. Oracle MySQL's `partial_revokes=ON` mode has unit coverage only; MariaDB does not provide that mode.
- **21,149 asset/catalog records verified** by byte size and SHA-256 (485.8 MiB). The four bot/navigation/ranked/store source hashes match the retained benchmark below. All assets remain in this complete source release.
- Source byte-compilation succeeded for `venom`, `tools` and `tests`. `python tools/setup.py --version` reports **0.2.2**.

`MYSQL_SETUP_VALIDATION.json` records the final database checks and tested source
hashes. The live tests use their own disposable server and never connect to an
existing installation. The MariaDB checks ran on Linux; the Windows setup EXE,
Windows XAMPP distribution and Oracle MySQL server were not executed here.
Build with `BUILD_ALL.bat` and use the new distribution's `02_SETUP_MYSQL.bat`.
The complete fresh-install procedure is in `PASSWORD_SETUP_FIX.txt`.

# Historical v0.2.1 verification

## Password setup hotfix

- **158 automated tests passed** (`python -m pytest -q`, 23.01 seconds on Linux/Python 3.12.14).
- **22 new password regressions** cover exact spaces/punctuation/Unicode, paste, edit/delete/clear, cancellation, GUI-versus-console dispatch, masked Windows input, administrator credential handling, dedicated-account failures and redacted errors.
- **Seven setup-repair helper tests** cover explicit installation roots, dependency bootstrap, payload layout, cancellation/error boundaries and console-mode forwarding.
- **Ten checks against the actual Tk password window passed** under a temporary Linux virtual display, including typed input, final ASCII asterisk masking, show/hide, paste replacing a selection, multiline paste rejection, Clear, exact submission and cancellation. The final masked window was visually inspected. `PASSWORD_DIALOG_QA.json` records these checks; this is not a Windows screenshot or Windows executable acceptance test.
- **21,149 asset/catalog records verified** by byte size and SHA-256, totalling 485.8 MiB. All original assets and the four bot/navigation/ranked/store benchmark source hashes are unchanged.
- Development dependencies now include the optional import/decoder libraries required by the complete shipped test suite. Game runtime dependencies are unchanged.
- Source byte-compilation succeeded. The builder explicitly collects Tkinter for VenomSetup and supplies its Windows DPI manifest.

For v0.2.1, no native Windows executable or live MySQL/XAMPP instance was run. The MySQL
credential and failure paths were tested with a mocked driver; all network/game
integration checks in the suite passed. The complete Windows source includes the
usual BUILD_ALL.bat and setup launchers. Use PASSWORD_SETUP_FIX.txt at the source
root for the rebuild and existing-configuration procedure.

# Prior v0.2.0 verification

## Rivals and ranked verification

- **129 automated tests passed** (`python -m pytest -q`, 23.42 seconds on this Linux runtime). After the final shutdown cleanup and Battle XP label adjustment, the 15 community integration, persistence-safety and client checks passed again.
- **21,149 asset/catalog records verified** by byte size and SHA-256 (485.8 MiB). Imported assets and the original content manifest are unchanged.
- Source byte-compilation succeeded for `venom`, `tools` and `tests`.
- Actual WSS integration connects two accounts to the same world and checks identical bot positions/timestamps, field scoping, movement, public profiles, authoritative ranked outcomes, invitation ownership, duplicate acceptance and friendly/ranked accounting. Client-supplied wins and rewards are ignored.
- Every one of the 254 map navigation graphs was checked along continuous routes, including diagonal corner crossings. The population acceptance suite checks all 5,000 initial rivals and scheduler coverage.
- Ranked tests exercise real combat, repeat-request idempotency, energy recovery, promotion, current/career/archive ordering, season rollover, frozen season rules and one-time reward settlement. Both sides' wins/losses and points settle in one database transaction.
- Persistence safety tests cover normal shutdown, lease takeover before shutdown, stale bot/event writes, and a battle computed before takeover but submitted afterward. An expired server cannot commit those writes.
- The new screens were rendered at the minimum supported window size and at **3840 × 2160**. Client checks cover real 6-v-6 authoritative battle replay, modal input isolation, click-to-profile, idle direction and coalesced polling. Ranked, rival and activity preview images use an isolated 128-bot demonstration world and are explicitly marked offline previews; those images are not the 5,000-bot benchmark.

The reproducible full-population measurements and limitations are in
`RIVALS_BENCHMARK.md` and `RIVALS_BENCHMARK.json`. The benchmark exercises the
actual bot, navigation, ranked and SQLite persistence code. It advances 900 seconds
of simulation time; it is not a long-duration live server or human concurrency test.

## Previous v0.1.1 display upgrade verification

- **86 automated tests passed** (`python -m pytest -q`, 11.63 seconds on this Linux runtime), including the original gameplay, server/TLS and content tests.
- **21,149 asset/catalog records verified** again by byte size and SHA-256; original artwork, game data, server code and account schema are unchanged.
- Actual **1920 × 1080 and 3840 × 2160 framebuffers** rendered sign-in, whole-level fit, close/8× world views, settings and battle/hit-effect scenes. The automatic UI scale is 125% and 250%, respectively. Native font rendering is checked against the physical-size font surface, not an enlarged low-resolution screen image.
- Camera tests cover whole-map fit, transform inverses, edge clamps, zoom limits, player framing and viewport-sized crop allocations at 8×. UI tests exercise real physical 4K button coordinates, settings isolation and fullscreen/settings shortcuts while typing.
- Display checks cover validated preferences, corrupted settings recovery, atomic saves, secret exclusion, nonpersistent previews, window restoration and the Windows PerMonitorV2 manifest. Interactive window sizes fit the current monitor's work area. A multiresolution executable/window icon is included.
- Movement tests compare client collision prediction to the actual server, preserve input across direction changes, and simulate a delayed acknowledgement with 350 ms of newer movement. Pending-input replay prevents the previous 63-pixel backward correction. Remote snapshots are interpolated on a short timeline.
- New native 4K screenshots are in `docs/previews/world_4k.png`, `settings_4k.png` and `battle_4k.png`; all are explicitly marked offline previews. Source CLI rendering and screenshot export were also exercised.

These are Linux/headless software-rendering checks. A Windows executable, real monitor DPI changes, physical refresh/synchronization and a guaranteed 4K frame rate were not verified here. The supplied builder creates the Windows x64 binaries on the target Windows machine.

## Original baseline validation retained

Validation performed on Linux with Python 3.12.14, pygame-ce 2.5.8 / SDL 2.32.10, websockets 16.0, PyMySQL 1.1.1, cryptography 46.0.0 and Pillow 12.3.0. Dependency versions are recorded in requirements files.

- **49 automated tests passed** across nine test modules. The native-client subset was rerun successfully after the final floating-text contrast adjustment.
- **21,149 content files verified** by expected byte size and SHA-256 (485.8 MiB). Catalog references resolve; gameplay rules JSON is covered.
- **All 1,004 playable forms are reachable** in encounter pools. Every normal record has its matching Paradox record.
- **All 254 destinations** have correctly sized collision masks and valid safe spawns. Foreground image dimensions match their backgrounds, including the supplied map 088 crop.
- **All 64 tamer appearances** have eight directions and four native walking frames per direction.
- **All 46 music tracks and 183 sound effects** decode successfully and contain finite, nonzero audio. The source-missing drum notes and synthesis approximations are recorded in the audio documentation.
- **All 96 exported battle-effect sequences** have valid transparent frames with consistent per-sequence canvases. Decoder tests cover flips and transparency.
- Real local **WSS integration with the actual catalog** exercised two accounts, shared-world updates, battle victory/scans, escape, lab recovery/return, purchases, rollback and saved relogin.
- The native threaded client connected over verified TLS and completed registration, compact position updates, lab entry/return and an encounter.
- Certificate checks accepted the bundled CA, rejected an incorrect hostname, and rejected an untrusted CA. Re-running hosting setup retained the existing CA. The public connection ZIP contained only `config/client.json` and `config/server-ca.pem`.
- Account tests cover password hashing, case-insensitive uniqueness, duplicate sessions, database leases and stale-save revision rejection. Movement tests cover elapsed-time limits and a one-pixel collision wall.
- A regression check with 2,000 stored partners and 1,004 scan entries verifies that an ordinary movement acknowledgment remains below 180 bytes; automatic encounters still persist and return complete battle state.
- Source byte-compilation succeeded. Case-insensitive filename collision check found zero collisions. The longest imported relative asset path was 118 characters.
- Account creation, tamer picker, world, battle, hit effects, collection, party, shop, map travel and lab screens were rendered and visually reviewed. Preview images in this folder's `previews` directory are explicitly marked offline visual previews.

## Not validated here

No Windows executable was compiled or executed in this Linux environment. The v0.2.2 setup and basic runtime persistence now have real MariaDB coverage as described above; Windows XAMPP and Oracle MySQL were not run. No internet deployment, Windows firewall/router setup, human concurrency load test, long-duration soak test or exact comparison to every Cyber Sleuth/ReArise value was performed. The retained 5,000-bot simulation establishes measured behavior on this Linux/SQLite runtime; Windows/MySQL host performance still requires verification.

The ZIP is a clean source release with preimported assets. Run `BUILD_ALL.bat` on the target Windows x64 machine to create its native client, console server and setup executables, then perform the numbered setup steps.
