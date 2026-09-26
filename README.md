# Digimon Venom NXT

**Local Admin Console v0.8.0 — host-only administration and player titles.**

Type `/help` in the existing **START_WORLD_SERVER_CONSOLE.bat** window on the
server PC. Manage Digimon, items, credits, live encounters, moderation, accounts,
saves and server restarts through permission-checked local commands. Broadcasts
and warnings appear as trusted native notices, and persistent cosmetic titles
appear above player usernames. Players cannot execute these commands in chat.
Your v0.7.0 private Season careers, DigiFarm, shared rivals and Ranked Arena are
retained.

**Upgrade from v0.7.0: rebuild and update both client and world server with
BUILD_ALL.bat.** Apply the source patch to a copy of the v0.7.0 Season Mode source,
or use the complete v0.8.0 source. Stop and back up the existing server first;
retain its configuration and `mysql/data` when replacing application files.
Do not run fresh database setup. Administration tables are added automatically.
Existing configurations enable the local console at OWNER by default.

Read [docs/ADMIN_CONSOLE_V080.md](docs/ADMIN_CONSOLE_V080.md) for the full command
reference, console tiers, hidden password prompts, confirmation rules, and exact
upgrade procedure. Windows executables must be built on Windows x64.

The following v0.7.0 and earlier notes describe retained features. For the current
release, use the v0.8.0 upgrade procedure above.

**Retained Season Mode v0.7.0 — private, persistent tamer careers.**

Enter **Season Mode** from the top-left navigation. Review your fictional week's
match card, play your own scheduled Digimon battle with the normal controls,
reveal the rest of the league results, and continue directly to the next week.
Your private roster, rivalries, championship and career records carry forward
through an open-ended Gregorian calendar. Nothing advances while you are away.
Fleeing is disabled in league matches; logging out preserves the active turn.
The shared world, DigiFarm, persistent rivals and Ranked Arena remain available.

The v0.7.0 release built on the supplied v0.6.2 High Ping Disconnect Fix source
and added private career archives without resetting existing character saves.
Read [docs/SEASON_MODE_V070.md](docs/SEASON_MODE_V070.md) for Season controls,
rules and save behavior. Its upgrade section is historical; use the v0.8.0
procedure linked above for this release.

The following DigiFarm and earlier-release notes describe retained features.
For the current update, use the v0.8.0 upgrade procedure above.

**Retained DigiFarm — native Windows x64 client and dedicated world server.**

Your tamer now has a private DigiFarm home using the supplied island artwork,
with up to 100 stored Digimon, gentle wandering, click-to-manage feeding and
its own original soundtrack. Walk the island as your selected tamer with your
lead partner following, and use the normal 1×–8× camera controls. Optional
Friendship DigiMeat raises CAM; six kinds
of training DigiMeat permanently improve HP, SP, ATK, DEF, INT or SPD. Shop
purchases and occasional PvE victory drops use authoritative server rules.
The existing native UI, rivals, arena and FPS improvements are retained.

This is a **source release**. Rebuild **both the client and world server** on
Windows x64 with `BUILD_ALL.bat`. Existing portable-server saves are retained;
do not reset the database or run fresh setup for an upgrade. Follow
[docs/DIGIFARM_V060.md](docs/DIGIFARM_V060.md) for the feature rules, controls,
prices and exact update procedure. Previous UI-only upgrade instructions are
historical and do not apply to v0.6.0.

This corrected **v0.6.0** release includes DigiFarm walking and camera zoom.
Owners of the earlier v0.6.0 release must also rebuild both applications. The
replacement patch applies over either the supplied UI2 source or that previous
v0.6.0 source. Farm position and zoom are saved separately from their field
counterparts; home stays private and free of wild encounters.

## Retained baseline features

**Rival walking and repeat team training.** Rivals start their walking time when
scheduled work actually begins, follow continuous collision-checked patrols, and
arrive at spaced safe positions when changing sectors. Training rounds keep earned
partners in storage, field younger teams, and bring experienced rivals back to
quieter eligible maps. Veteran visits to underfilled higher-level sectors are
limited, followed by a dedicated stretch of normal team training. Arrival
reservations spread those assignments between sectors. Ranked battles,
collection, healing and travel continue.

**Fresh portable database setup.** This release includes its own **MySQL Community
Server 8.4.11 for Windows x64** under `mysql/runtime`. MySQL runs as a separate
process; every production database file and save stays in `mysql/data` inside the
server folder. It uses `127.0.0.1:3307` and needs no XAMPP, installed database
service, external database, or existing administrator password.

This is the **complete source package**, including the game assets and Windows
MySQL engine. For a new installation, build the Windows applications first, then
use the generated server folder for play. A new server setup starts with fresh
accounts and progress; it does not import an older installation. Existing
portable-baseline players should follow the v0.6.0 upgrade guide to update both
applications while keeping their accounts and progress.

For day-to-day use, run **START_MYSQL.bat**, then
**START_WORLD_SERVER_CONSOLE.bat**. When you want to back up or move the server,
run **STOP_SERVER.bat**, wait for confirmed shutdown, then ZIP the complete server
folder. Extract that ZIP on another compatible Windows x64 PC and run the same
launchers to continue. **Never ZIP a running database.**

Read [PORTABLE_SERVER_README.md](PORTABLE_SERVER_README.md) for the short operating
guide and [docs/SETUP.md](docs/SETUP.md) for the full build and setup procedure.

A playable multiplayer foundation built around the supplied Digimon v7 / Paradox artwork and x2 Dawn maps. The desktop client uses pygame-ce / SDL; the authoritative Python world server owns movement, combat, scanning, inventory and persistent character saves. There are no browser pages or page-refresh movement.

This is an alpha release, not a finished commercial-scale MMO or a data-exact reconstruction of Cyber Sleuth. Its imported artwork, native tamer movement and collision masks come from the supplied files. Numerical balance, moves, progression and many evolution routes are original Venom NXT rules. Read `docs/MECHANICS.md` and `docs/RELEASE_STATUS.md` for the precise boundaries.

## Persistent rivals and Battle Park in v0.2.0

The dedicated server now runs a default population of **5,000 persistent AI tamers**. They walk through the shared maps, fight wild Digimon, earn levels and scan data, materialize partners, care for their parties, travel, and compete in ranked battles. Click a rival in the field, press **V** for the Rivals Hub, **R** for Ranked Arena, or **O** for Bot Activity.

Battle Park adds automatic weekly seasons, current and career records, top-100 ladders and season archives, promotion battles, and DigiRuby rewards. Its points, rewards, stamina and three-active-partner battles are published NXT rules. The mode adapts documented ReArise features; it is not an exact recreation of every ReArise rule. See `docs/RIVALS_AND_RANKED.md` for the complete rules and `docs/REARISE_RULES_RESEARCH.md` for the recovered official references.

## High-DPI display and camera

The client now renders text and interface shapes at native display resolution, supports Windows high DPI and borderless fullscreen (**F11 / Alt + Enter**), and provides saved display/audio preferences (**Settings / F10**). World zoom ranges from a complete-level **1×** view to a close-up **8×**, with plus/minus buttons, keyboard and mouse-wheel controls. Artwork uses crisp nearest-neighbor sampling; its original resolution remains unchanged.

The display improvements from v0.1.1 are retained. `docs/DISPLAY_UPGRADE.md` describes their settings and historical client-only release. Historical gameplay upgrade guides do not describe this fresh portable database setup.

## First installation on Windows

Build on Windows x64 with **Python 3.11 or newer, 64-bit**, the Python launcher or
Python on PATH, and Tcl/Tk support. The first build needs internet access for its
Python dependencies. The resulting client and server applications do not need a
separate Python installation.

1. Extract the entire source package to a writable folder, such as
   `C:\Games\DigimonVenomNXT-Source`. Do not run files from inside an archive.
2. Run **BUILD_ALL.bat**. It verifies shipped game content, creates an isolated
   build environment, and builds the client, world server and administration tools.
3. Extract `dist\Windows_Server_x64.zip` into a permanent private server folder
   **outside `dist`**. Extract `dist\Windows_Client_x64.zip` into a separate client
   folder. Rebuilding replaces the build outputs.
4. Install the Microsoft Visual C++ x64 runtime if needed by running
   **mysql\prerequisites\INSTALL_VC_RUNTIME.bat** in the server folder. This
   helper downloads Microsoft's installer and needs internet access; Windows may
   request administrator approval for that prerequisite.
5. Run **01_SETUP_SERVER.bat**. Prepare the bundled MySQL, create the game database
   login, and choose local or public hosting. Database credentials are generated
   automatically when the optional game password is left blank. No old account,
   password, database or configuration is needed.
6. Extract `Public_Player_Connection_Kit.zip` **inside the client folder**, merging
   `config`. Run **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. The
   world launcher also starts MySQL when needed and verifies it before launching.
7. Wait for initial rival creation to finish. Run **PLAY_DIGIMON_VENOM_NXT.bat** in
   the configured client folder and use **Register** to create a new tamer.

The server folder and its backups contain credentials, player saves and private
TLS keys. Keep them private; share the client and player connection kit only.
For internet hosting, allow and forward the **game** TCP port, normally **8765**.
MySQL stays local on **3307** and must not be forwarded. Hosting setup cannot
configure your router, ISP or DNS.

## Local development

For an optional source-development game without the production MySQL database, run `START_LOCAL_DEV.bat`, then `PLAY_LOCAL_DEV.bat`. This explicitly uses a localhost server and a separate development SQLite save. It is not the production database. `START_LOCAL_DEV.bat` installs the source runtime dependencies on first use.

On any supported development OS:

```sh
python -m pip install -r requirements.txt
python -m venom.server.main --dev
# In another terminal:
python -m venom.client.main --dev
```

Public play uses TLS and MySQL. The public server refuses the development database/plaintext configuration.

## What is included

- 1,004 Digimon entries: 502 normal and 502 Paradox records, including alternate artwork sets supplied under different stages. Every entry belongs to an encounter pool.
- 64 selectable original Dawn/Dusk/guest tamer appearances, each with eight directional movement animations decoded from the ROM.
- 254 map backgrounds and 97 foreground overlays, using the supplied x2 images. All 254 traversable maps use original ROM pixel collision data.
- One Rookie starter, up to six party partners, a three-partner active battle team, 100-resident private DigiFarm storage, leader selection and an overworld follower.
- A walkable DigiFarm with your selected animated tamer and lead follower, shared client/server shoreline collision, independent saved position and 1×–8× zoom, click-to-manage residents, gentle wandering, optional CAM treats, six permanent stat-training meat families and unique original home music.
- One to three wild enemies, speed-based turns, physical and elemental skills, SP, a free attack/Struggle, item use, movement effects, particles, 96 decoded original battle-effect sequences, and floating damage/effectiveness text.
- Defeated-enemy scan data, DigiLab materialization at 100% or more, a 200% scan cap, evolution/de-evolution requirements, levels, ABI and CAM.
- A 2.5% chance for an encounter to include a Paradox; Paradox defeats award less scan data than normal defeats.
- Free DigiLab healing and return to the saved world position; a shop with small, medium and large HP/SP capsules.
- Shared world presence, map-local chat, account authentication, durable progression, per-pixel movement validation and rate limits.
- 5,000 configurable persistent AI rivals, initially distributed evenly across the maps, with authentic walking frames, continuous server-owned patrols, spaced sector arrivals, real combat/collection progression, repeat team training, party storage, density-aware travel and clickable profiles.
- Ranked auto battles against saved defender teams, weekly UTC seasons, season and career wins/losses, top-100 current/career/archive ladders, earned-grade and placement rewards in a persistent DigiRuby wallet.
- Nearby friendly rival invitations, an accept/decline hub, head-to-head history, and a bot activity screen with cumulative counters and the latest 100 population events.
- Original-ROM sequence/sample audio rendered into 46 music tracks and 183 sound effects. The renderer approximates some NDS synthesis behavior; it is not a hardware-perfect emulator.
- Windows build, a native setup wizard, bundled portable MySQL with readiness checks, graceful shutdown for manual whole-folder ZIP backups, local/public TLS connection kits, content verification and automated tests.

## Source layout

| Location | Purpose |
|---|---|
| `venom/client/` | Native desktop presentation, input, animation, audio and networking |
| `venom/server/` | Authoritative world networking, accounts, persistent rivals, navigation, ranking and database persistence |
| `venom/common/game.py` | Combat, progression, scanning, evolution, items and party rules |
| `data/` | Catalog, original balance rules, provenance and content hashes |
| `assets/` | Supplied artwork and extracted runtime content |
| `tools/` | Reproducible import/extraction, verification, build, setup and portable database utilities |
| `mysql/` | Bundled Windows database engine, its provenance and prerequisites; runtime saves and private credentials are created here during setup |
| `tests/` | Gameplay, collision, persistence, network and setup checks |
| `docs/` | Setup, controls, mechanics, extraction notes and release status |

The preimported runtime assets are included. The three original uploads are not required to build this package; retain your originals if you want to reproduce the extraction.

## Verification

```sh
python tools/build.py --verify-only
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Windows executables must be built on Windows. Linux verification does not establish that a Windows binary has been built or tested. See [docs/PORTABLE_MYSQL_VALIDATION.md](docs/PORTABLE_MYSQL_VALIDATION.md) for the new database checks and [docs/PORTABLE_MYSQL.md](docs/PORTABLE_MYSQL.md) for implementation boundaries. A successful build on the target Windows host remains necessary.
