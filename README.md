# Digimon Venom NXT

**v1.0.0 — Cyber-blue battles and Fanglongmon artwork.**

The battle scene gains a polished blue cyber-grid background with clear space
for the combatants and readable battle controls. Corrected target cards size
their outline around the full name, details, sprite and HP bar with padding;
long names wrap, and selection stays anchored during attack animation.
Fanglongmon and Paradox
Fanglongmon use the supplied six-frame artwork for each form, integrated with
the existing animation system. Their stable species identities and earned
ownership, scans and progression carry forward.

The complete game retains both private story campaigns, DigiLab, DigiFarm,
DigiRuby shopping and exchange, private Season careers and Ranked Arena. The
**3,000-rival maximum**, **12-hour Bot Activity window**, startup ownership
repair and compressed world updates remain in place.

Read [docs/RELEASE_V100.md](docs/RELEASE_V100.md) for the current upgrade and
[docs/FANGLONGMON_V100.md](docs/FANGLONGMON_V100.md) for the artwork and species
details. **Run BUILD_ALL.bat and deploy BOTH rebuilt Windows applications.**
If already running the earlier v1.0.0 release, rebuild and redeploy the client
to receive the corrected target layout; the existing v1.0.0 server can remain.
Back up the complete stopped server and preserve its database, private
credentials and configuration. These downloads contain source, not prebuilt
Windows executables. Earlier upgrade instructions below describe their original
releases; use the v1.0.0 guide for this update.

**Retained v0.12.3 — 3,000 persistent tamer rivals.**

The default and maximum rival population is **3,000**, down from 5,000.
Existing settings above 3,000 are capped automatically. The startup migration
retires the extra 2,000 rivals and removes their saved rival state; the retained
3,000 and all human players keep their earned game progress. World updates use
negotiated WebSocket compression while preserving the complete map population
and update rate. Read [docs/POPULATION_V0123.md](docs/POPULATION_V0123.md) for
that migration's exact scope and historical measurements. For this release,
follow the v1.0.0 guide above and update both applications.

**Retained v0.12.2 — Bot Activity shows the latest 12 hours.**

Open **Bot Activity / O** for global activity counters covering the most recent
**12 hours** and the latest **100 events within that window**. Old activity
display data and persistence receipts expire automatically. Counter storage
uses compact minute totals; the oldest partial minute is excluded so counts
never include activity older than 12 hours.

The first upgrade starts new timestamped global tracking because the previous
lifetime totals have no timestamps. **Earned partners, XP, scans, currencies,
story progress, individual rival careers and ranked rewards are preserved.**
The previous restart repair also remains: **there is no overall startup
loading deadline**.

Read [docs/BOT_ACTIVITY_V0122.md](docs/BOT_ACTIVITY_V0122.md) for retention details
and its original upgrade. For the current update use the v1.0.0 guide above.
The original activity upgrade required both applications for the updated
display. Preserve `config`, `mysql/data`, private MySQL settings and
`mysql/runtime`; do not run fresh setup or clear saved progress.

The notes below retain earlier features and their original release context.
Use the v1.0.0 guide above for the current upgrade.

**Retained v0.12.1 — Persistent-rival startup and restart hotfix.**

The server now keeps its rival ownership lease renewed while restoring saved
ranked/rival state and loads saved rivals incrementally. **There is no overall
startup loading deadline.** A large saved population can finish restoring without
losing its lease merely because startup takes longer than 90 seconds.

This fixes a source failure path consistent with a long pause at “Starting
ranked seasons and persistent tamer rivals...”. The affected installation's final
error was not supplied, so the guide also explains which log excerpt to provide
if another error remains. Existing saves, rivals and rewards are preserved.

Read [docs/RESTART_REPAIR_V0121.md](docs/RESTART_REPAIR_V0121.md) for the original
repair details and restart checks. That server-only hotfix preserved
compatibility with v0.12.0 clients. For the current v1.0.0 update, rebuild and
deploy both applications using the guide above.

**Retained v0.12.0 — Spend DigiRubies in the shop or exchange them for credits.**

Open **Shop / B** and choose **Credits** or **DigiRubies** to buy any capsule or
DigiMeat. All 19 shop items support both currencies, with clearly displayed
prices. Open **Ranked Arena / R → DigiRuby Exchange** to convert earned
DigiRubies into credits at **1 DigiRuby = 100 credits**. The exchange is one-way;
review the amount before confirming.

The redundant Struggle option has been removed. **Attack remains free at 0 SP**,
so every partner can still act when its SP runs out. Existing partners, items,
credits, DigiRuby balances, both story campaigns and Season progress carry on.

Read [docs/DIGIRUBY_ECONOMY_V0120.md](docs/DIGIRUBY_ECONOMY_V0120.md) for the full
price table, shop and exchange controls, and safe upgrade instructions.

**Upgrade from v0.11.0: rebuild BOTH Windows applications with BUILD_ALL.bat.**
Use the full v0.12.0 source or apply the source patch to a copy of the complete
v0.11.0 baseline. Stop and back up the server first; preserve `mysql/data`,
private MySQL settings, and the existing client/server `config` folders.
**Do not run fresh database setup.** This is a source release. Build and check
both Windows x64 applications on the intended Windows machine.

The v0.12.0 guide describes the economy feature release and its original
upgrade. For the current update, follow the v1.0.0 guide above.

**Retained v0.11.0 — World DS: Paradox Chronicle, a second private story campaign.**

Open **Story Mode / F4** and choose **World DS: Paradox Chronicle**. Begin at a
peaceful service hub, then journey through 17 supplied Digimon World DS field
maps. Meet local quest characters, complete their stories, challenge authored
NPC tamers and defeat a different Paradox guardian in each area. Earn all
**17 Paradox Crests** to summon the final team of **three level-100 Paradox
Megas**. Opponents rise from around level 10 through the campaign.

Your first final victory permanently increases scan earned from winning wild
Paradox battles by **20%: the normal 5% becomes 6% per defeated Paradox**.
The benefit does not stack, and the existing 200% scan cap still applies.
Bring your existing partners and use the normal live battle controls, DigiLab,
DigiFarm, inventory and shop. Dawn Relay keeps its own progress, badges and
championship; the new story's NPCs belong to its private campaign.

Read [docs/WORLD_DS_STORY_V0110.md](docs/WORLD_DS_STORY_V0110.md) for the player
guide, progression, reward rules and upgrade procedure.

**Upgrade from v0.10.0: rebuild BOTH Windows applications with BUILD_ALL.bat.**
Use the full v0.11.0 source or apply its source patch to a copy of the complete
v0.10.0 World DS baseline. Stop and back up the existing server first. Preserve
`mysql/data`, private MySQL files and the complete server/client `config`
folders. **Do not run fresh database setup.** This is a source release;
Windows x64 executables must be built and checked on Windows.

The sections below preserve earlier release notes and their original upgrade
procedures. Use the v1.0.0 guide above for the current update.

**Retained World DS region v0.10.0 — shared maps, encounters and music.**

Open **Worlds** and choose **Digimon World DS** to explore 150 additional field
maps alongside the original 254 Dawn sectors. Wild encounters progress from level
1 to 99, using your existing team, live battle controls, scan collection, DigiLab
and DigiFarm. The same saved AI tamer population roams, trains, battles and travels
across both regions. New DS map music accompanies the journey.

Your private Story Mode, Season careers, Ranked Arena and host-only admin console
remain available. The v0.10.0 region used the existing character artwork.
Read [docs/WORLD_DS_V0100.md](docs/WORLD_DS_V0100.md) for the new atlas, imported
content, rival behavior and exact upgrade procedure.

**Upgrade from v0.9.0: rebuild BOTH Windows applications with BUILD_ALL.bat.**
Use the update on a copy of the complete v0.9.0 source, or the full v0.10.0 source.
Back up the stopped server and preserve its database and private configuration;
do not run fresh database setup. This is a source release, not prebuilt EXEs.

The v0.10.0 guide below documents the shared region and its historical upgrade.

**Retained Story Mode v0.9.0 — Dawn Relay, a private adventure with your own Digimon.**

Enter **Story Mode** from the top-left navigation or press **F4**. Explore 18
supplied Dawn maps, speak to authored NPC tamers, earn all eight DigiBadges and
challenge the Dawn Champion. Opponents progress from early levels to level 100.
After winning the championship, keep defending it; after a defeat, win it back.
Every fight uses the normal live battle controls. NPC tamer matches cannot be
fled; Field Training remains a normal wild encounter.

Bring your existing party at its actual strength. Your Digimon, DigiLab,
DigiFarm, inventory and credits stay connected to the main game. Only the story
journey, NPC progress, badges and championship belong to your private instance.
Story rewards and partner growth remain yours when you return to the MMO.
Season careers, shared rivals, Ranked Arena and the local admin console remain.

**Upgrade from v0.8.0: rebuild both client and world server with BUILD_ALL.bat.**
Apply the source update to a copy of the v0.8.0 Local Admin source, or use the
complete v0.9.0 source. Back up the stopped server and preserve its database and
configuration. Do not run fresh database setup. Read
[docs/STORY_MODE_V090.md](docs/STORY_MODE_V090.md) for controls, progression,
shared-system behavior and the exact upgrade procedure. This is a source release;
Windows x64 executables must be built on Windows.

The release notes below describe retained features and historical upgrades.

**Retained Local Admin Console v0.8.0 — host-only administration and player titles.**

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

The following v0.7.0 and earlier notes describe retained features. For the current upgrade, use the v1.0.0 guide linked above.

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
rules and save behavior. Its upgrade section is historical; use the v1.0.0
release guide for the current update.

The following DigiFarm and earlier-release notes describe retained features.
For the current update, use the v1.0.0 release guide above.

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
portable-baseline players should follow the current Bot Activity guide to
update both applications while keeping their accounts and progress.

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

The dedicated server now runs a default population of **3,000 persistent AI tamers**. They walk through the shared maps, fight wild Digimon, earn levels and scan data, materialize partners, care for their parties, travel, and compete in ranked battles. Click a rival in the field, press **V** for the Rivals Hub, **R** for Ranked Arena, or **O** for Bot Activity.

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
- One to three wild enemies, speed-based turns, physical and elemental skills, SP, a free basic Attack, item use, movement effects, particles, 96 decoded original battle-effect sequences, and floating damage/effectiveness text.
- Defeated-enemy scan data, DigiLab materialization at 100% or more, a 200% scan cap, evolution/de-evolution requirements, levels, ABI and CAM.
- A 2.5% chance for an encounter to include a Paradox; Paradox defeats award less scan data than normal defeats.
- Free DigiLab healing and return to the saved world position; a shop with HP/SP capsules and DigiMeat, each purchasable with credits or DigiRubies.
- Shared world presence, map-local chat, account authentication, durable progression, per-pixel movement validation and rate limits.
- 3,000 persistent AI rivals by default and at most, initially distributed evenly across the maps, with authentic walking frames, continuous server-owned patrols, spaced sector arrivals, real combat/collection progression, repeat team training, party storage, density-aware travel and clickable profiles.
- Ranked auto battles against saved defender teams, weekly UTC seasons, season and career wins/losses, top-100 current/career/archive ladders, earned-grade and placement rewards in a persistent DigiRuby wallet, and a DigiRuby-to-credit exchange.
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
