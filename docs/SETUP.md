# Windows x64 build and fresh portable setup

**Existing v0.6.0 upgrade:** use [DIGIFARM_V060.md](DIGIFARM_V060.md). Both the client and server must be updated while preserving the existing database, credentials and configuration. The fresh setup steps below are for new installations only.

This release uses the bundled **MySQL Community Server 8.4.11** as a separate
process inside the server folder. Its production database files and game saves
stay in **`mysql/data`**. It does not need XAMPP, an installed MySQL service or a
previous database account. Setup starts a fresh game; no earlier server data is
imported.

## 1. Build the source package

1. Extract the complete source into a writable folder such as
   `C:\Games\DigimonVenomNXT-Source`. Open the folder containing `BUILD_ALL.bat`.
   Do not run it inside an archive.
2. Install **Python 3.11 or newer for Windows x64**, with the Python launcher or
   Python on PATH and Tcl/Tk support. Allow internet access for the first build's
   dependency downloads.
3. Run **BUILD_ALL.bat**. It verifies the shipped content, prepares `.venv-build`,
   and builds the client, world server, setup utility and MySQL controller.
4. Extract `dist/Windows_Server_x64.zip` into a permanent private server folder
   and `dist/Windows_Client_x64.zip` into a separate client folder. Keep both
   working installations **outside `dist`**, which is recreated by a later build.

The source already includes its game artwork, maps, audio and the Windows MySQL
engine. The separate original asset archives are not needed to build it.
`python tools/build.py --verify-only` checks imported game content without
building. `BUILD_ALL.bat --offline` requires an already populated build environment.

The source package is not a prebuilt Windows application. Windows executables
must be built on Windows x64. Once built, neither the client nor the server needs
a separate Python installation.

## 2. Prepare Windows and open setup

The bundled MySQL requires the Microsoft Visual C++ x64 runtime. If it is missing,
run **mysql/prerequisites/INSTALL_VC_RUNTIME.bat** in the permanent server folder.
The helper downloads Microsoft's installer, so this one-time prerequisite needs
internet access. Windows may request administrator approval for installation;
normal server use runs as your user.

Run **01_SETUP_SERVER.bat** in the permanent server folder. Its database, game
login, hosting and readiness stages keep the full setup in one window.

### Prepare this folder's database

Choose **Prepare MySQL**. Setup initializes the private database directory, creates
administrator credentials automatically and starts `mysql/runtime/bin/mysqld.exe`.
It then authenticates to verify that the process belongs to this folder and uses
its data directory. The fixed local address is **`127.0.0.1:3307`**.

No external host, administrator username or existing password is required. A port
conflict stops setup with an error; it never silently adopts another database.

### Create the game login

Keep the default database name **digimon_venom_nxt** and game database user unless
you have a reason to choose other names. Leave the optional password blank to
have setup generate a strong one. This internal database login is not a player
account. Setup creates the application's schema and verifies access before saving
`config/server.json`.

The generated credentials stay inside the private server folder. Once configured,
reopening this setup preserves the folder's database, login and saves. Do not copy
old configuration into a fresh server folder or point this release at an external
database.

## 3. Choose the player connection

**Local on this PC:** choose local hosting. The client connects to `localhost`
using TLS and the production MySQL saves. No router forwarding is needed.

**LAN or public hosting:** enter the hostname or IP address that players will use,
without `http://`, a path or a port suffix. Choose a game TCP port, normally
**8765**. The listener's bind address is separate from the player-facing address;
public hosting normally binds `0.0.0.0`.

The wizard creates the private certificate authority and server certificate,
then writes **Public_Player_Connection_Kit.zip**. The kit contains
`config/client.json` and `config/server-ca.pem`. Extract it **inside each client
folder**, merging `config`. The client checks the bundled CA and matching hostname;
players do not need to install a certificate into Windows.

For internet players, allow the chosen **game TCP port** through Windows Firewall
and forward it to the server's LAN address on your router. DNS must resolve to
your reachable public address. **Do not forward MySQL port 3307.** MySQL is bound
to loopback and used only by this server. Setup cannot configure your router, DNS
or ISP, and local readiness does not establish internet reachability. Test from
another network after configuring public hosting.

## 4. Finish and play

Complete the readiness checks. If a step fails, read the visible error, correct
its cause and retry. Setup writes a sanitized diagnostic report to
**logs/setup-latest.json**; passwords are omitted.

Run **START_MYSQL.bat**, followed by **START_WORLD_SERVER_CONSOLE.bat**. The world
launcher also starts MySQL when needed and checks readiness before launching.
Wait for the world and initial rival population to finish loading. Run
**PLAY_DIGIMON_VENOM_NXT.bat** in the configured client folder and use **Register**
to create a fresh tamer account.

Keep the server folder private. It contains database credentials, every player's
saves and certificate private keys. Distribute only the client and player kit.

## 5. Stop, back up and move

Use **STOP_SERVER.bat** for the normal shutdown: it requests final world saves,
waits for the world process, and shuts MySQL down cleanly. **STOP_MYSQL.bat** stops
the database alone and refuses while the world is active. Closing the world
console alone leaves MySQL running.

After **STOP_SERVER.bat** succeeds, use your normal ZIP program to ZIP the
**entire server folder**. Keep the server stopped until compression finishes. Include `mysql`, `config`, the server programs and game
content. That ZIP keeps the physical database and every save together with the
matching engine and credentials. Never ZIP a running database or copy only the
game's schema subfolder. A failed stop is not confirmation that copying is safe.

On another compatible Windows x64 PC, extract the full backup into a writable
folder, install the Visual C++ x64 prerequisite if needed, and use the normal
start launchers. Retain the same bundled MySQL engine with its data. No new
installation, database import or fresh setup is needed for this backup restore.
Database paths are regenerated for the new folder location. If the player-facing
address changes, reopen hosting setup and give clients the updated connection kit.

[../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md) contains the daily
control table, file locations and recovery notes.

## Other setup entry points

- **02_SETUP_MYSQL.bat** reopens the database stage.
- **03_SETUP_PUBLIC_HOSTING.bat** reopens hosting setup.
- **MYSQL_STATUS.bat** identifies this folder's running database and data location.

Source commands, with the declared dependencies installed:

```powershell
python -m tools.setup --root C:\VenomServer wizard
python -m tools.setup --root C:\VenomServer wizard --stage database
python -m tools.setup --root C:\VenomServer wizard --stage hosting
python -m tools.portable_mysql --root C:\VenomServer status
```

Put `--root` before the subcommand. The folder must include the matching runtime
and game files. The normal BAT launchers already select their own folder.

## Certificate renewal and development mode

Server certificates last 397 days. Stop the world and reopen hosting setup before
expiry; retaining the private CA lets clients trust a renewed certificate from
that CA. A changed player hostname or port requires an updated client kit. Keep
the full `config` folder in every server backup.

**START_LOCAL_DEV.bat** and **PLAY_LOCAL_DEV.bat** remain optional source-development
helpers. They use a separate `runtime/development.sqlite3` save and unencrypted
loopback networking. Their saves are not the production MySQL saves; normal local
play uses the main setup and server launchers.

The Windows engine is bundled and its provenance is recorded, but preparation on
Linux is not a native Windows execution test. See [PORTABLE_MYSQL_VALIDATION.md](PORTABLE_MYSQL_VALIDATION.md) for the checks
actually run and [PORTABLE_MYSQL.md](PORTABLE_MYSQL.md) for implementation limits.
