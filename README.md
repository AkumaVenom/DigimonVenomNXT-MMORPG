# Digimon Venom NXT

**v0.2.0 alpha — native Windows x64 client and dedicated world server**

A playable multiplayer foundation built around the supplied Digimon v7 / Paradox artwork and x2 Dawn maps. The desktop client uses pygame-ce / SDL; the authoritative Python world server owns movement, combat, scanning, inventory and persistent character saves. There are no browser pages or page-refresh movement.

This is an alpha release, not a finished commercial-scale MMO or a data-exact reconstruction of Cyber Sleuth. Its imported artwork, native tamer movement and collision masks come from the supplied files. Numerical balance, moves, progression and many evolution routes are original Venom NXT rules. Read `docs/MECHANICS.md` and `docs/RELEASE_STATUS.md` for the precise boundaries.

## Persistent rivals and Battle Park in v0.2.0

The dedicated server now runs a default population of **5,000 persistent AI tamers**. They walk through the shared maps, fight wild Digimon, earn levels and scan data, materialize partners, care for their parties, travel, and compete in ranked battles. Click a rival in the field, press **V** for the Rivals Hub, **R** for Ranked Arena, or **O** for Bot Activity.

Battle Park adds automatic weekly seasons, current and career records, top-100 ladders and season archives, promotion battles, and DigiRuby rewards. Its points, rewards, stamina and three-active-partner battles are published NXT rules. The mode adapts documented ReArise features; it is not an exact recreation of every ReArise rule. See `docs/RIVALS_AND_RANKED.md` for the complete rules and `docs/REARISE_RULES_RESEARCH.md` for the recovered official references.

**Already playing v0.1.0 or v0.1.1? Update both server and client.** Follow `docs/RIVALS_UPGRADE.md`. Preserve the working database, server/client `config` folders and private TLS keys. The new server creates its additional tables automatically; the normal upgrade does not need either setup wizard or a password change. Build in a separate folder because `BUILD_ALL.bat` recreates its `dist` outputs.

## High-DPI display and camera

The client now renders text and interface shapes at native display resolution, supports Windows high DPI and borderless fullscreen (**F11 / Alt + Enter**), and provides saved display/audio preferences (**Settings / F10**). World zoom ranges from a complete-level **1×** view to a close-up **8×**, with plus/minus buttons, keyboard and mouse-wheel controls. Artwork uses crisp nearest-neighbor sampling; its original resolution remains unchanged.

The display improvements from v0.1.1 are retained. `docs/DISPLAY_UPGRADE.md` describes their settings and historical client-only release; use `docs/RIVALS_UPGRADE.md` for the current server-and-client upgrade.

## Start on Windows

Use Windows 10/11 x64 with **Python 3.11 or newer, 64-bit**, installed with the Python launcher or on PATH. Internet access is needed on the first build. MySQL 8 or MariaDB through XAMPP must already be installed and running for a public server.

1. Extract this entire archive to a writable folder, for example `C:\Games\DigimonVenomNXT`. Do not run a BAT from inside the ZIP.
2. Double-click **`BUILD_ALL.bat`**. It verifies the shipped content hashes, creates an isolated Python environment, downloads the declared dependencies, and builds the client, console server and setup utility.
3. Open `dist\Windows_Server_x64`. Run **`02_SETUP_MYSQL.bat`**. Enter your existing XAMPP administrator password, including a blank password if that is your setup. The wizard creates a separate game database account; it does not change your XAMPP administrator password.
4. Run **`03_SETUP_PUBLIC_HOSTING.bat`**. Enter the DNS name or IP address players will use and the TCP port. It creates a server certificate and `Public_Player_Connection_Kit.zip`.
5. Extract that connection kit **into `dist\Windows_Client_x64`**, merging its `config` directory. Give players this configured client folder or ZIP. The client verifies the bundled CA and hostname without asking players to manually trust a Windows certificate.
6. Run **`START_WORLD_SERVER_CONSOLE.bat`** in the server folder. Allow initial rival creation to finish. Run **`PLAY_DIGIMON_VENOM_NXT.bat`** in the client folder. Register a tamer and choose a regular Rookie partner.

The builder also produces independent `dist\Windows_Client_x64.zip` and `dist\Windows_Server_x64.zip`. The initial client ZIP must receive your connection kit before public play. Keep the configured server folder private: it holds the database password and private certificate keys.

For internet hosting, allow and forward the chosen TCP port to your server. The certificate wizard cannot configure your router, ISP or DNS. A DNS hostname is useful when your public IP can change.

## Local development

For a local game without MySQL or public hosting, run `START_LOCAL_DEV.bat`, then `PLAY_LOCAL_DEV.bat`. This explicitly uses a localhost server and a separate development SQLite save. It is not the production database. `START_LOCAL_DEV.bat` installs the source runtime dependencies on first use.

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
- One Rookie starter, up to six party partners, a three-partner active battle team, storage, leader selection and an overworld follower.
- One to three wild enemies, speed-based turns, physical and elemental skills, SP, a free attack/Struggle, item use, movement effects, particles, 96 decoded original battle-effect sequences, and floating damage/effectiveness text.
- Defeated-enemy scan data, DigiLab materialization at 100% or more, a 200% scan cap, evolution/de-evolution requirements, levels, ABI and CAM.
- A 2.5% chance for an encounter to include a Paradox; Paradox defeats award less scan data than normal defeats.
- Free DigiLab healing and return to the saved world position; a shop with small, medium and large HP/SP capsules.
- Shared world presence, map-local chat, account authentication, durable progression, per-pixel movement validation and rate limits.
- 5,000 configurable persistent AI rivals, initially distributed evenly across the maps, with authentic walking frames, shared authoritative positions, real combat/collection progression, party care, map travel and clickable profiles.
- Ranked auto battles against saved defender teams, weekly UTC seasons, season and career wins/losses, top-100 current/career/archive ladders, earned-grade and placement rewards in a persistent DigiRuby wallet.
- Nearby friendly rival invitations, an accept/decline hub, head-to-head history, and a bot activity screen with cumulative counters and the latest 100 population events.
- Original-ROM sequence/sample audio rendered into 46 music tracks and 183 sound effects. The renderer approximates some NDS synthesis behavior; it is not a hardware-perfect emulator.
- Windows build, MySQL setup, TLS/connection-kit setup, an obvious console server launcher, content verification and automated tests.

## Source layout

| Location | Purpose |
|---|---|
| `venom/client/` | Native desktop presentation, input, animation, audio and networking |
| `venom/server/` | Authoritative world networking, accounts, persistent rivals, navigation, ranking and database persistence |
| `venom/common/game.py` | Combat, progression, scanning, evolution, items and party rules |
| `data/` | Catalog, original balance rules, provenance and content hashes |
| `assets/` | Supplied artwork and extracted runtime content |
| `tools/` | Reproducible import/extraction, verification, build and setup utilities |
| `tests/` | Gameplay, collision, persistence, network and setup checks |
| `docs/` | Setup, controls, mechanics, extraction notes and release status |

The preimported runtime assets are included. The three original uploads are not required to build this package; retain your originals if you want to reproduce the extraction.

## Verification

```sh
python tools/build.py --verify-only
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Windows executables must be built on Windows. Linux verification does not establish that a Windows binary has been built or tested. See the validation report for checks actually run on this release.
