# Digimon Venom NXT — portable server

**Upgrading to DigiFarm v0.6.0?** Follow [docs/DIGIFARM_V060.md](docs/DIGIFARM_V060.md) to update both applications and retain your existing saves. The first-use procedure below is for new installations only.

This server owns its database. **MySQL 8.4.11 runs from `mysql/runtime` as a
separate process, and all production saves live in `mysql/data`.** No XAMPP or
separately installed MySQL service is needed. The database listens only on this
PC at `127.0.0.1:3307`; the game normally listens on TCP `8765`.

## First use

If your folder contains `BUILD_ALL.bat` but no `VenomWorldServer.exe`, it is the
**source package**. Install Windows x64 Python 3.11 or newer with Tcl/Tk, run
`BUILD_ALL.bat`, then extract `dist/Windows_Server_x64.zip` to a permanent folder
outside `dist`. Extract the client ZIP separately. The initial build needs
internet access for dependencies. See [docs/SETUP.md](docs/SETUP.md).

In the generated server folder:

1. Install the Microsoft Visual C++ x64 runtime if needed with
   `mysql/prerequisites/INSTALL_VC_RUNTIME.bat`. It downloads Microsoft's installer
   and may prompt for Windows administrator approval. No Python installation is
   needed for the compiled server.
2. Run **01_SETUP_SERVER.bat**. Prepare MySQL, create the fresh game database, and
   choose local or public hosting. Leave the optional game database password blank
   to generate it automatically. There are no old credentials or saves to import.
3. Extract **Public_Player_Connection_Kit.zip** inside the client folder, merging
   `config`.
4. Run **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. Wait for the
   world and initial rivals to finish loading, then launch the configured client
   and register a new tamer account.

## Daily controls

| File | Action |
|---|---|
| `START_MYSQL.bat` | Starts this folder's separate MySQL process and waits for verified readiness. |
| `START_WORLD_SERVER_CONSOLE.bat` | Starts or verifies this folder's MySQL, then runs the world server in a console. |
| `START_SERVER.bat` | Convenience alias for the world server launcher. |
| `STOP_SERVER.bat` | Requests final world saves, waits for world shutdown, then cleanly shuts down MySQL. |
| `STOP_MYSQL.bat` | Cleanly shuts down MySQL; refuses while this folder's world is active. |
| `MYSQL_STATUS.bat` | Shows whether this folder's MySQL is running and identifies its data directory. |

Closing the world console does not stop MySQL. Prefer **STOP_SERVER.bat** and
wait for its successful completion before copying the folder or turning off the
PC. If shutdown reports an error, the folder is not confirmed safe to copy.

## Back up the complete server

1. Run **STOP_SERVER.bat** and wait for confirmation that both the world and MySQL
   have stopped successfully. The world saves its active players and rivals
   before the database shuts down.
2. Use your normal ZIP program to ZIP the **entire server folder**. Leave both
   processes stopped until copying or compression finishes.
3. Keep that ZIP somewhere safe. It contains your game progress and everything
   needed to run this server again, apart from the Windows runtime prerequisite.

Include the complete `mysql` and `config` folders, the server programs and game
content. Never copy or ZIP live database files, and never copy only the named
database subfolder: MySQL also needs the shared files in `mysql/data` and this
server's saved credentials and configuration. Keep the server ZIP private.

## Continue on another PC

1. Run **STOP_SERVER.bat** and wait for successful shutdown, then ZIP or copy the
   entire server folder.
2. Extract the complete folder on a compatible **Windows x64** PC into a writable
   location. Keep the bundled MySQL engine with its data; do not replace it with
   another version.
3. Install the Microsoft Visual C++ x64 runtime on the new PC if needed using the
   included prerequisite helper. A compiled server needs no Python or MySQL
   installation.
4. Run **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. Do not reset
   `mysql/data` or run fresh database setup after moving this complete folder. The saved accounts, characters, rivals
   and ranked history are already in the restored folder. Database paths are
   regenerated for its new location at startup.

For local play, the `localhost` connection kit remains usable. If the address
players use has changed, stop the server and reopen **03_SETUP_PUBLIC_HOSTING.bat**
to generate the matching certificate and client kit. Apply the new kit to each
client and update the game port's firewall/router rules where needed. Do not
forward port `3307`. The client lives separately; retain or copy it and its kit too.

## Where things live

| Location | Contents |
|---|---|
| `mysql/runtime/` | Bundled Oracle MySQL 8.4.11 Windows x64 engine and tools. |
| `mysql/data/` | All production database files, including player and rival saves. |
| `mysql/instance.json` | Generated private database administrator credentials and instance state. |
| `mysql/game-login.json` | Private application database credentials. |
| `mysql/my.ini` | Database configuration regenerated for this folder on startup. |
| `mysql/logs/` | Database initialization, startup and error logs. |
| `config/` | Game settings, database login and private TLS configuration. |
| `runtime/logs/server.log` | World server diagnostics. |
| `logs/setup-latest.json` | Sanitized setup diagnostic report. |

Keep the full server folder and backups private. Give players only the client
package and public connection kit.

## If setup or startup fails

- **Missing Visual C++ runtime:** run the included prerequisite helper, then retry.
- **Port 3307 is occupied:** stop the other process using that port, or run only
  one portable server copy at a time. The launcher does not attach to an unrelated
  database or change its settings.
- **MySQL is still starting or shutting down:** wait and inspect `mysql/logs`.
  Do not force-kill it or make a manual ZIP while shutdown is incomplete.
- **Incomplete folder or credentials:** restore a complete backup into a separate
  folder. Do not delete `mysql/data` or replace credential files independently.
- **First initialization was interrupted:** preserve the failed folder and its
  logs. If no play has occurred and you want another fresh attempt, extract the
  original server package into a different empty folder and run setup there.
  Initialization never silently wipes a partially created data directory.

Send the sanitized `logs/setup-latest.json` when asking for setup help. Do not
send private configuration, credentials, database files or server keys publicly.

This package was prepared on Linux. Windows executables must be built on Windows;
Linux checks do not establish native Windows end-to-end execution. See
[docs/PORTABLE_MYSQL_VALIDATION.md](docs/PORTABLE_MYSQL_VALIDATION.md) for results
and their limits. Engine origin and verification records are in `mysql/provenance`.
