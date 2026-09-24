# Portable MySQL implementation notes

For the operating steps, use
[../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md). This release starts
with a fresh database and does not import an earlier server's data.

## One server folder

| Item | Location or behavior |
|---|---|
| Engine | Oracle MySQL Community Server 8.4.11, Windows x64, in `mysql/runtime`. |
| Process | `mysql/runtime/bin/mysqld.exe`; started directly, not installed as a Windows service. |
| Database files | `mysql/data`, including player accounts, character saves, persistent rivals and ranked history. |
| Local endpoint | `127.0.0.1:3307`; no remote database connection or fallback. |
| Credentials | Generated private instance and application credentials under `mysql`, with the application's configuration under `config`. |
| Paths | `mysql/my.ini` is regenerated for the current folder before database startup. |
| Readiness | Authenticated connection plus instance/data-directory checks, not only a listening TCP port. |
| Shutdown | World final saves first, then a full InnoDB shutdown and verified database process exit. |
| Engine origin | Original signature, archive hash and included runtime manifest recorded in `mysql/provenance`. |

All mutable database files, including logs and temporary files, stay below
`mysql`. Keep the entire server folder together. The player connection uses a
separate game TCP port, normally `8765`; never forward the database port.

## Start, stop, ZIP, continue

Use **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. The world launcher
also starts or verifies the folder's database automatically. **STOP_SERVER.bat**
saves and stops the world before stopping MySQL. **STOP_MYSQL.bat** refuses while
the world is active.

After **STOP_SERVER.bat** confirms success, ZIP the whole server folder with your
normal archive program. Extract the full ZIP on a compatible Windows x64 PC,
install the Microsoft Visual C++ x64 prerequisite if needed, and use the same
start launchers. Keep the bundled engine version unchanged. No database import
or first-time setup is needed to continue from that complete folder copy.

A live database ZIP is not a safe substitute for shutdown. Retain the shared files
in `mysql/data`, the database credentials, `config` and the runtime binaries;
copying only a database schema directory is incomplete. Client files are a
separate package; copy the configured client separately if moving the player too.

## Failure behavior

A database on port 3307 that does not match this folder is rejected. Missing
credentials beside nonempty data are treated as an incomplete installation;
setup does not overwrite those files. An interrupted first initialization keeps
its data and logs for inspection. Do not delete data to make a startup error go
away; restore a complete known-good folder or, for a first setup with no saves,
extract a fresh original package into a different empty folder.

Shutdown waits for the actual database process to exit. If it times out, inspect
`mysql/logs` and wait; a timeout is not permission to copy live files. No force-kill
is used. `MYSQL_STATUS.bat` identifies the running instance and data directory.

## Build and validation boundary

The source includes the Windows engine and game content. **BUILD_ALL.bat** must
run on Windows x64 with Python 3.11 or newer and internet access for the initial
Python dependency download. It produces a separate client package and a server
package with the compiled administration tools and database runtime. These built
applications need no separately installed Python or MySQL.

MySQL requires the Microsoft Visual C++ x64 runtime on each host. The included
`mysql/prerequisites/INSTALL_VC_RUNTIME.bat` downloads Microsoft's installer for
that one-time prerequisite. Windows may request administrator approval for it.

The package is prepared on Linux. Archive/signature checks and Linux tests do not
establish native Windows execution. A Windows build and execution check remain
necessary on the target system. See
[PORTABLE_MYSQL_VALIDATION.md](PORTABLE_MYSQL_VALIDATION.md) for the checks actually
run; this guide does not claim Windows end-to-end acceptance.
