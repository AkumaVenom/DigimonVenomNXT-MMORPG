# Persistent-rival restart repair — v0.12.1

This source hotfix repairs a startup path that could expire the server's rival
ownership lease while it was still restoring a large saved population. It keeps
the lease renewed during loading and restores rivals incrementally. **There is
no overall startup loading deadline**: a healthy restoration can take the time
it needs.

Your saved rivals, ranked rewards, DigiRubies, credits, partners and story
progress stay in the existing database. There is no reset, database migration
procedure, new configuration setting or runtime repair script to run.

## What the fix addresses

The reported startup paused at **Starting ranked seasons and persistent tamer
rivals...** and later displayed an error. Source review found that v0.12.0 could
acquire a 90-second rival ownership lease, then spend longer than that restoring
saved rivals before its regular renewal loop started. A later protected database
operation could therefore reject that server's expired lease. Loading all saved
rival states at once also increased memory pressure during restoration.

The hotfix starts lease renewal for initialization and loads the saved rivals in
batches. The renewable lease still protects saved data from competing world
servers; it is not a maximum allowed loading time. This update does not replace
the old startup limit with a larger fixed timeout, discard excess rivals or
skip earned progress to make startup finish sooner.

Large startup database reads and the first creation of history indexes can also
finish without the normal gameplay socket timeout. Normal gameplay retains its
connection-failure handling after loading completes. The console prints each
startup stage, rival counts, and an elapsed-time message every 15 seconds during
a long stage. Those messages do not impose a loading limit.

This is a confirmed source failure path consistent with the reported pause.
The final error message from the affected installation was not provided, so the
exact cause of that particular failure cannot yet be established from its log.
The fix does not promise a particular number of seconds on every PC or database.

## Update the server and keep your saves

The hotfix requires a **rebuilt Windows world server**. Existing **v0.12.0
clients remain compatible**; their gameplay features and protocol are unchanged.
A newly built v0.12.1 client is optional and has the updated version label.

**BUILD_ALL.bat** builds both packages; for this hotfix, deploy the new server
package.

1. Run **STOP_SERVER.bat** in the existing server installation. Wait for
   confirmed world-server and MySQL shutdown, then back up the **complete
   stopped server folder**. Keep your original installation intact while
   preparing the update. If shutdown reports a save error, preserve the error
   and log before taking further action; do not delete data to clear it.
2. Extract the full v0.12.1 source into a separate writable source folder, or
   merge the hotfix's `DigimonVenomNXT` directory into a copy of the complete
   **v0.12.0 source**. Keep all baseline assets and the bundled MySQL runtime.
   Keep the working server installation outside the source's `dist` directory.
3. On **Windows x64**, use 64-bit Python 3.11 or newer with Tcl/Tk support and
   run **BUILD_ALL.bat**. The first build needs internet access for its Python
   build dependencies. The new server package is
   `dist/Windows_Server_x64.zip`.
4. Work on a copy of your stopped server backup. Replace these application
   components from the new server package: `VenomWorldServer.exe`, `_internal`,
   `admin`, `assets`, `data`, `docs`, `mysql/manager`, launchers, build metadata
   and readme files. Replace application directories in full.
5. Preserve the complete server **`config`** folder, **`mysql/data`**,
   `mysql/instance.json`, `mysql/game-login.json`, private MySQL configuration,
   the bundled **`mysql/runtime`**, and your existing runtime logs. Top-level
   `data` holds game content; **`mysql/data` holds the saved database**.
   Do not delete either to troubleshoot this issue. **Do not run fresh setup,
   reset the database, remove rivals, or clear ranked rewards.**
6. Start **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. Allow the
   saved population to restore. Startup progress and errors are written to
   `runtime/logs/server.log`. Wait for **World ready** before connecting.
7. Connect with your existing v0.12.0 client or an optional rebuilt v0.12.1
   client. Confirm your original account, wallets, partners, story and Season
   progress. Check the saved rival population and ranked records. After a clean
   shutdown, start it again to check the same saved population restores.

If you choose to replace the client as well, extract the complete new client
package into a new folder and copy in the old client `config` folder, including
`client.json` and `server-ca.pem`. Keep display preferences and connection
settings. This client replacement is optional for the v0.12.1 server hotfix.

## If startup still ends with an error

Keep the database and server configuration unchanged. Share the **complete
final error text** and the **last 60 lines** of the affected server folder's
`runtime/logs/server.log`, including the traceback if one appears. In PowerShell,
opened in that server folder, this read-only command shows the tail:

```powershell
Get-Content -LiteralPath .\runtime\logs\server.log -Tail 60
```

Review that short excerpt before sharing it and redact any passwords, tokens or
private addresses that appear. Do not share `config/server.json`, private MySQL
credential files, certificates with private keys, or the whole database. State
whether **World ready** appeared and which release number the server printed.
The log tail can distinguish another database or startup error from the lease
failure corrected here.

## Saved-population benchmark

A before/after check restored the same generated fleet of **5,000 grown rivals**
in the Linux development environment using SQLite. It included **30,000 party
Digimon**, **240,000 stored Digimon** and **2,500 unfinished battles**.

| Measurement | v0.12.0 baseline | v0.12.1 repair |
|---|---:|---:|
| Community initialization | 19.072 seconds | 8.216 seconds |
| Peak process resident memory | 1,821.9 MiB | 1,184.1 MiB |

The saved-state and statistics hash matched exactly after restoration. The
human fixture's **391 DigiRubies**, **76,543 credits** and other saved state
were preserved. Both runs performed **zero offline simulation actions** while
loading; the improvement did not come from discarding saved rivals or progress.

These are single-run **Linux/SQLite** measurements of community initialization,
not full Windows/MySQL startup timings or a promise for the affected PC. The
fixture is generated test data, not the user's database. Peak memory covers the
whole benchmark process. The separate long-restore regression exercises lease
expiry; these timing runs themselves finish inside 90 seconds.
See [the benchmark evidence](validation/restart_v0121/README.md) for the exact
JSON results and measurement boundaries.

## Release notes and verification boundary

The full automated suite completed with **785 passed and 10 skipped**, including
18 new regressions for long loading, saved progress, database I/O mode and
ownership protection. See the bundled
[validation evidence](validation/restart_v0121/README.md) for the complete test
log, skip reasons and the before/after 5,000-rival measurements.

- Keeps the rival ownership heartbeat active while ranked and rival startup
  work is running, with no overall loading-time limit.
- Restores saved rivals incrementally while retaining their saved progress.
- Preserves the existing database, rewards, wallets, world content and client
  gameplay behavior.
- Updates server/build/setup metadata and the optional newly built client label
  to v0.12.1; includes this guide in the Windows packages.

This is a source release. Build the Windows executables and check the restart
on the intended Windows machine. Source checks do not establish that a native
Windows build or the affected installation has already passed that check.
