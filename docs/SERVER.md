# Dedicated world server and portable MySQL

Use **01_SETUP_SERVER.bat** once in a fresh built server folder, then start with
**START_MYSQL.bat** and **START_WORLD_SERVER_CONSOLE.bat**. The world launcher
checks and starts the bundled database automatically. **START_SERVER.bat** is an
alias for that launcher. See [SETUP.md](SETUP.md) for building this source package
and [../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md) for daily use.

The production server requires its own **MySQL Community Server 8.4.11** and TLS.
MySQL runs as a separate process from `mysql/runtime/bin/mysqld.exe`, bound to
`127.0.0.1:3307`. Its entire database directory is `mysql/data`. Generated database
credentials, logs and configuration also remain inside the server folder. The
controller authenticates and checks the instance's data directory before treating
it as ready; a different database occupying the port is an error. No system
MySQL service or XAMPP configuration is used.

The world uses a limited application database login saved in `config/server.json`.
The private TLS keys stay in `config`; clients receive only the public connection
kit. Production mode never falls back to a plaintext listener or the development
database. `--config PATH` selects the world configuration, but production database
settings must identify this folder's portable instance.

For source development, `python -m venom.server.main --dev` explicitly binds
`127.0.0.1`, uses `runtime/development.sqlite3`, and accepts local plaintext
WebSockets. Source and frozen applications resolve content relative to the
application root through `venom.common.paths`.

## Persistence and gameplay

The world process validates all game mutations and commits successful battle, inventory, shop, evolution, travel, DigiLab and DigiFarm/feeding actions before returning success. Movement is limited to 180 source-map pixels per second using elapsed server time and normalized direction; the per-pixel foot-point collision mask prevents crossing thin walls. Regular movement acknowledgments carry only map and position, so stored partners and scan data are not resent on every step. Automatic encounters return their complete battle state. Regular movement is saved every 20 seconds and on clean disconnect. A process crash can lose the most recent unsaved movement; committed gameplay actions remain stored.

Players on the same map receive position, walking direction and lead-partner snapshots at 10 Hz. DigiLab sessions are grouped separately from the overworld. Each DigiFarm is private to its authenticated account, excluded from field snapshots, nearby rivals and local invitations. Farm movement does not change shared-world positions. Field chat is local to the current map; home chat is isolated to the owner. Battles are individual PvE sessions; this release does not implement shared raids, real-time command PvP, trading, guilds or multiple coordinated world shards. Asynchronous Battle Park remains available from home.

DigiFarm movement uses the same 180-source-pixel-per-second limit as field
movement, with a grass shoreline shared by server validation and client
prediction. It never triggers wild encounters. Each account's `farm_position`
is persisted separately from its field location, so walking at home preserves
the player's world return point. The selected tamer and lead follower are shown
locally; no other player's farm occupants are broadcast. The corrected v0.6.0
release requires rebuilding and updating both the client and world server,
including when upgrading the earlier v0.6.0 DigiFarm release.

Accounts use case-insensitive ASCII tamer names (3–24 letters, numbers or underscores). Passwords are 8–128 characters and are stored as salted scrypt hashes. The server limits messages, authentication attempts, concurrent authentication work, chat frequency, connection count per IP and gameplay requests. SQL uses bound parameters. A renewable 90-second database session lease blocks a duplicate login even across two processes; save revisions prevent silent overwrite. After an unclean world shutdown, an account may take up to 90 seconds to become available.

Player state uses versioned JSON and revision counters in transactional tables.
The game database also contains accounts, session leases, persistent rivals,
ranked seasons and their history. Setup initializes both the player and community
schemas in this folder's database. Every production save is physically stored
under `mysql/data`; keep that entire directory with its engine, credentials and
server configuration. Check `runtime/logs/server.log` for world startup and
persistence failures, and `mysql/logs` for database failures. Passwords and message
bodies are not logged.

A failing save closes that player's connection instead of continuing to mutate a state that cannot safely be persisted. Slow clients are disconnected; world delivery uses a bounded send timeout. A clean world shutdown closes active connections, commits their final saves, releases leases and closes the world's database connection. The separate MySQL process remains running until its own clean shutdown. No production capacity or availability guarantee is claimed: this is one world process with serialized transactional database access, and should be load-tested for the intended audience before a public launch.

Run `python -m pytest -q tests/test_server.py` for real local WebSocket round trips, authentication, duplicate login, save rollback/revisions, lease ownership, message validation, world/chat delivery, authoritative movement and thin-wall collision checks. These tests use temporary SQLite and require no public server or MySQL service. These SQLite tests do not establish MySQL behavior; the portable MySQL integration checks use a real matching engine separately.

`tests/test_integration.py` also exercises the real imported catalog over a local TLS listener using setup-generated certificates: two tamers, live world snapshots, authentic collision, a complete battle with scan rewards, flee, healing, exact world return, rejected malicious purchases, valid purchases and persisted relogin. It verifies that the client accepts the bundled CA while rejecting an untrusted CA or wrong hostname. All keys, accounts and SQLite data used by this test are temporary.

## Safe shutdown and whole-folder backup

**STOP_SERVER.bat** requests graceful world shutdown before stopping MySQL. The
world holds an operating-system lock while running, and database maintenance uses
that lock to prevent a second world process from starting during managed setup or shutdown. **STOP_MYSQL.bat** refuses to stop a database while the world is active.

The database controller requests a full InnoDB shutdown and waits for MySQL to
exit. It does not force-kill a process. Once **STOP_SERVER.bat** confirms both
processes have stopped, use your normal ZIP program to archive the entire server
folder, including `mysql/data`, `mysql/runtime`, private database state and
`config`. Copying one schema's directory or copying a live instance is not a
complete backup. Restore by extracting the whole folder and using its launchers.

Portability applies to a compatible Windows x64 host with the Microsoft Visual
C++ x64 prerequisite and the same bundled engine. It is not an automatic MySQL
version upgrade or Windows-to-Linux physical database conversion. Native Windows
build and launch acceptance require a Windows host; Linux integration tests alone
do not establish those results.
