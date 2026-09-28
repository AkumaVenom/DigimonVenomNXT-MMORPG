# 3,000 persistent tamer rivals — v0.12.3

The dedicated server now runs **3,000 tamer rivals by default, with a maximum
of 3,000**. Existing configurations requesting 5,000 are capped automatically.
Lower configured counts and the option to disable rivals remain supported.
The retained population continues to walk, train, collect, travel and battle
using the existing game rules.

## Removal and saved progress

The upgrade keeps rivals **`bot:00001` through `bot:03000`**. It removes the
extra **`bot:03001` through `bot:05000`** from the live population and retires
their saved rival state, competitor profiles, recent activity entries and
entries in still-open ranked seasons during startup. This happens only after
the server has acquired exclusive ownership of the rival population. Cleanup
is saved in bounded batches and resumes if startup is interrupted. Once a
season is captured for cleanup, that work finishes consistently even if the
season expires during an interruption. Back up the complete stopped server
before applying this intentional removal.

The retained rivals keep their earned partners, levels, collection and
currencies. Human accounts, partners, inventories, wallets, story campaigns
and Season progress remain intact. Closed and already-expired Season records
that were not captured for cleanup, match outcomes, reward records and human
battle history remain as earned history; they do not put removed rivals back into the live world or directory.
Do not create a new database or reset the whole rival population.

The existing **latest-12-hours Bot Activity window** remains active, with its
latest 100 events inside that window and automatic expiry. The startup lease
repair also remains: **saved-world loading has no overall deadline**, renews
its ownership during loading, restores rivals in batches and reports progress.

## Capacity and upload traffic

World updates now negotiate WebSocket message compression with compatible
clients. The existing v0.12.2 client already supports that negotiation. The
server uses a low-cost compression setting and does not retain compression
history between messages. It continues to send all actors on the current map
at the existing update rate; the decoded game information is unchanged. A
client that cannot negotiate compression can still connect using the existing
uncompressed messages.

Removing 2,000 of 5,000 rivals reduces the number of simulated rivals by 40%.
It also removes those rivals' saved state from future restores. It does not
mean that every server's total upload traffic or loading duration falls by
exactly 40%; these depend on map occupancy, connected players, runtime work
and the host machine.

Removing database rows makes space available for reuse. MySQL may retain that
space inside its existing data files rather than immediately shrinking their
size on disk. Keep the existing database files intact.

## Rebuild and update the Windows server

These downloads contain **source code, not prebuilt Windows executables**.
The **server must be rebuilt and deployed**. Existing v0.12.2 clients remain
compatible and support the compression change; installing the rebuilt client
is optional and updates its displayed version.

1. Run **STOP_SERVER.bat** and wait for the world server and MySQL to stop.
   Back up the **complete stopped server folder**. Keep the original backup
   intact while preparing and checking the update.
2. Extract the complete v0.12.3 source into a separate writable source folder,
   or merge the update's `DigimonVenomNXT` directory into a copy of the complete
   **v0.12.2 source**. Keep all baseline assets and the bundled MySQL runtime.
   If using the full source download, extract **both ZIP parts into the same
   parent folder**, merging their `DigimonVenomNXT` directories.
3. On **Windows x64**, use 64-bit Python 3.11 or newer with Tcl/Tk support and
   run **BUILD_ALL.bat**. The first build needs internet access for Python
   build dependencies. It produces `dist/Windows_Server_x64.zip` and
   `dist/Windows_Client_x64.zip`. Keep live installations outside `dist`.
4. Work on a copy of the stopped server. Replace the application components
   using the new server package: `VenomWorldServer.exe`, `_internal`, `admin`,
   `assets`, top-level `data`, `docs`, `mysql/manager`, launchers, build metadata
   and readmes. Replace application directories in full.
5. Preserve **`config`**, **`mysql/data`**, `mysql/instance.json`,
   `mysql/game-login.json`, private MySQL configuration, **`mysql/runtime`** and
   runtime logs. Top-level `data` is game content; **`mysql/data` is the saved
   database**. Do not run fresh setup or manually clear rivals or ranked rows.
6. You can keep the existing v0.12.2 client. If also updating the client, extract
   the new client into a separate folder and copy in the old client `config`
   folder, including `client.json` and the trusted `server-ca.pem`.
7. Start **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. Allow
   startup migration and restoration to finish; wait for **World ready**.
   Periodic progress messages during a long stage are not loading deadlines.
8. Connect with the existing v0.12.2 client or the rebuilt client. Check that
   your original partners, wallets and story progress are present. Open **Rivals Hub / V** and **Bot Activity /
   O** to confirm the reduced population. Check map movement and a rival battle,
   then cleanly restart once more to confirm the reduced population persists.

If startup ends with an error, leave the database unchanged and follow the log
instructions in [RESTART_REPAIR_V0121.md](RESTART_REPAIR_V0121.md).

## Verification

The complete automated suite passed with **818 passed and 10 skipped** in
228.94 seconds. The skips are one opt-in live-MySQL check and nine graphical
setup-wizard checks. A saved 5,000-rival fixture becomes exactly 3,000 rivals,
retains the surviving state and human progress across repeated starts, and
cannot recreate removed rivals from the old 5,000 setting. Recovery checks
also cover interruption across a season boundary, stale owners and retained
historical payouts. Real client connections verify complete, identical decoded
world updates with compression and with uncompressed fallback.

A moving-map development benchmark measured the same complete 10 Hz world
updates before and after negotiated compression:

| Moving rivals on one map, plus one player | Uncompressed WebSocket bytes/second | Compressed WebSocket bytes/second |
|---|---:|---:|
| 100 | 315,255 | 56,846 |
| 160 | 502,677 | 88,684 |

These are isolated Linux measurements of production JSON and WebSocket frames,
not measurements from your Windows server. They exclude TLS/TCP/IP overhead,
acknowledgements and other game traffic. Rival movement and decoded snapshot
contents were unchanged. See [the measurement file](validation/population_v0123/world_bandwidth.json).

The release's automated checks and measurement scope are recorded in the
[validation evidence](validation/population_v0123/README.md). Earlier release
reports retain their original populations and versions. Native Windows builds
and a playtest on the intended Windows host remain separate checks; Linux
source checks do not establish that those Windows checks have already passed.
