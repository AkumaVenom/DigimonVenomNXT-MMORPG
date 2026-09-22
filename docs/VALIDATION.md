# Validation report — 0.2.0 alpha

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

No Windows executable was compiled or executed in this Linux environment. No live MySQL/MariaDB daemon was available. The MySQL setup path and SQL provisioning arguments have unit coverage, and new MySQL transactions were code-reviewed, but that does not prove a live XAMPP install. No internet deployment, Windows firewall/router setup, human concurrency load test, long-duration soak test or exact comparison to every Cyber Sleuth/ReArise value was performed. The 5,000-bot simulation establishes measured behavior on this Linux/SQLite runtime; Windows/MySQL host performance still requires verification.

The ZIP is a clean source release with preimported assets. Run `BUILD_ALL.bat` on the target Windows x64 machine to create its native client, console server and setup executables, then perform the numbered setup steps.
