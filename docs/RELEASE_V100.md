# Digimon Venom NXT — v1.0.0

Version 1.0.0 builds on the complete v0.12.3 baseline. It introduces a blue
cyber-grid battle background and the supplied Fanglongmon and Paradox
Fanglongmon animation artwork. It keeps the existing game and saved progress
connected: both private story campaigns, shared worlds, DigiLab, DigiFarm,
shop, DigiRuby exchange, private Season careers and Ranked Arena.

## Battle presentation and Fanglongmon

The blue cyber-grid stage gives the battle scene a coherent digital setting
while keeping the characters and battle controls easy to read. It uses the
normal battle presentation, so wild, rival, story and Season fights share the
updated background. Ranked replays use the same scenery. Existing combat
positions, health bars and commands retain their familiar layout.

The corrected v1.0.0 target highlight measures the full displayed name,
level/affinity details, sprite and HP bar, then surrounds that block with
consistent padding. Long names wrap in full instead of crossing the highlight
or being cut off. The outline and click target stay anchored to the combatant's
position while its sprite lunges or recoils, so targeting does not jump during
an attack.

Fanglongmon and Paradox Fanglongmon retain their existing stable species IDs.
The supplied six-frame sets replace their placeholder artwork through the
existing animation system. Existing partners, scans and ownership remain
attached to the same species. See [FANGLONGMON_V100.md](FANGLONGMON_V100.md)
for the frame mapping and existing acquisition/evolution details.

The release keeps the prior **3,000-rival default and maximum**, **12-hour Bot
Activity window**, resumable retirement of the extra 2,000 old rivals, long-load
startup ownership renewal and negotiated world-update compression. The battle
background and animation artwork run in the client and do not require extra
world-update traffic.

## Upgrade from v0.12.3 or the earlier v1.0.0 release

These are **source downloads, not prebuilt Windows executables**. Rebuild and
deploy **both the client and world server** so the client artwork, game catalog
and server content come from the same release when upgrading from v0.12.3.
If you already installed the earlier v1.0.0 release, rebuild and redeploy the
**client** to receive the corrected target layout; your existing v1.0.0 server
can remain. The release version stays v1.0.0. Updating only the source folder
does not change an already-built installation.

1. Run **STOP_SERVER.bat** and wait for the world server and MySQL to stop.
   Back up the **complete stopped server folder**. Retain the backup while
   preparing and checking the upgrade.
2. Extract the complete v1.0.0 source into a separate writable source folder,
   or merge the update's `DigimonVenomNXT` directory into a copy of the complete
   **v0.12.3 or earlier v1.0.0 source**. Keep all unchanged baseline assets and
   the bundled MySQL runtime. For the full source download, extract **both ZIP
   parts into the same parent folder**, merging their `DigimonVenomNXT`
   directories.
3. On **Windows x64**, use 64-bit Python 3.11 or newer with Tcl/Tk support and
   run **BUILD_ALL.bat**. The first build needs internet access for Python
   build dependencies. The output packages are `dist/Windows_Server_x64.zip`
   and `dist/Windows_Client_x64.zip`. Keep live installations outside `dist`.
4. Work on a copy of the stopped server. Replace its application components
   using the new server package: `VenomWorldServer.exe`, `_internal`, `admin`,
   `assets`, top-level `data`, `docs`, `mysql/manager`, launchers, build metadata
   and readmes. Replace application directories in full.
5. Preserve **`config`**, **`mysql/data`**, `mysql/instance.json`,
   `mysql/game-login.json`, private MySQL configuration, **`mysql/runtime`** and
   runtime logs. Top-level `data` contains game content; **`mysql/data`
   contains the saved database**. Do not run fresh setup, create a new game
   database or manually remove any player, rival or ranked records.
6. Extract the complete new client into a separate folder. Copy the old
   client **`config`** folder into it, including `client.json` and the trusted
   `server-ca.pem`. Saved display preferences remain in Local AppData.
   Distribute the updated client to players so they receive the new scenery
   and both Fanglongmon animation sets.
7. Start **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. Wait for
   **World ready** and connect using the new client. Saved-world loading has
   no overall deadline; allow restoration to finish.
8. Check the **v1.0.0** version label, original partners, credits, DigiRubies,
   story progress, DigiLab and DigiFarm. Enter a battle to inspect the new
   stage and select a long-name opponent: its full name, sprite and HP bar
   should fit inside the padded outline. Check normal and Paradox Fanglongmon
   if already owned or encountered, then perform a clean server restart to
   confirm saved progress remains if you also updated the server.

For an existing v1.0.0 server, the application replacement steps for the server
are optional; the corrected client must still be built and distributed.

No save reset is part of this upgrade. If startup ends with an error, preserve
the database and use [RESTART_REPAIR_V0121.md](RESTART_REPAIR_V0121.md) for the
relevant log and recovery guidance.

## Verification and earlier releases

Current development checks and visual evidence are recorded in
[validation/release_v100](validation/release_v100/README.md). The complete suite
finished with **873 passed and 10 skipped** in **240.66 seconds**, with no
failures or errors. The skips are one opt-in live-MySQL check and nine graphical
setup-wizard checks. Final native battle and replay captures cover the minimum
window through 4K; the combined Fanglongmon preview shows both supplied forms.

Native Windows executables and a target-host playtest are separate checks; the
source release does not claim a native Windows build or deployment was performed
here.

Historical guides and reports retain their original versions and measurements.
The v0.12.3 network measurements describe that earlier implementation and are
not a new v1.0.0 bandwidth benchmark. For this upgrade, follow the instructions
above rather than an earlier guide's client/server deployment requirements.
