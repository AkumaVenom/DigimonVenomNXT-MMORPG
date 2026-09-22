# Windows x64 build and hosting

This source produces a native SDL2 Windows client and a separate console dedicated server. The build uses Python 3.11+ for Windows x64 and PyInstaller. An Internet connection is needed for the first dependency installation. MySQL 8 or MariaDB 10.4+ (including XAMPP) must already be installed and running on the administrator's machine or database host.

## 1. Build once

Extract the full source ZIP to a short local path such as `C:\Games\DigimonVenomNXT`. Install **64-bit Python 3.11 or newer** from Python.org and enable **Add Python to PATH**. Double-click `BUILD_ALL.bat`.

The builder checks Python and architecture, verifies SHA-256 and sizes for every asset and the catalog, creates `.venv-build`, downloads runtime and build dependencies, runs `pip check`, compiles Python sources, freezes the native applications and creates:

- `dist/Windows_Client_x64.zip` — client EXE, all sprites, maps, audio and data.
- `dist/Windows_Server_x64.zip` — console server EXE, setup application, server data and the numbered setup / launch BAT files.

Players need no Python installation. The server administrator also needs no Python when using the built server ZIP. A native Windows executable cannot be produced by running PyInstaller on Linux; build on your Windows x64 computer. The build artifacts replace prior folders in `dist`, so extract your live server elsewhere before configuring it.

The complete imported assets ship with source. The original uploaded ROM and archives are not needed to build the included snapshot. If an asset is missing or corrupted, restore it from the source ZIP or re-run the documented asset importer. The builder refuses to silently substitute artwork. `python tools/build.py --verify-only` verifies integrity on any platform. A second build can use `--offline` if `.venv-build` already contains every dependency.

## 2. Set up MySQL

Extract `Windows_Server_x64.zip` to a permanent private server directory. Start MySQL in XAMPP, then double-click `02_SETUP_MYSQL.bat` there. Enter:

- MySQL address and port; local XAMPP is usually `127.0.0.1:3306`.
- Game database name; default `digimon_venom_nxt`.
- Existing administrator account and its **current** password; a blank XAMPP password is accepted.
- Separate game account; default `venom`. Press Enter at its password prompt to generate a strong password, or preserve the saved game password when re-running setup.
- The allowed game account host; keep `localhost` for a database and game server on the same computer. For a remote database, enter the actual game server's database-visible address.

Setup creates the database and a limited game account, initializes the schema through the server's database implementation, validates the dedicated login and writes `config/server.json`. It **never changes the XAMPP administrator password** and does not save it. The dedicated password must have at least 12 characters. Existing dedicated accounts keep their passwords; supply their actual password or choose a new game account. An administrator able to create databases, users and grants is required for provisioning.

Back up the database regularly. Keep the server directory, `config/server.json` and the private TLS keys private. Only the client distribution and the explicitly generated public connection kit are player downloads.

## 3. Configure public hosting

Double-click `03_SETUP_PUBLIC_HOSTING.bat` in the server directory. Enter the exact public DNS hostname or IP address players will use, without `https://`, a path or a port. Set the game port (default TCP 8765). The bind address defaults to `0.0.0.0` so the game server listens on network interfaces; this is different from the public hostname.

This creates a private certificate authority, a signed server certificate with the correct DNS/IP SAN, and `Public_Player_Connection_Kit.zip`. The kit contains exactly:

```text
config/client.json
config/server-ca.pem
```

Extract the kit **inside the Windows client folder**, merging the `config` directory and replacing the client settings. Zip and share that configured client folder with players, or distribute the client ZIP and connection kit separately with the same extraction instructions. The native client loads this bundled public CA certificate and checks the server hostname automatically. Players do not install a certificate in Windows and must not disable certificate verification.

The CA private key stays in `config/authority/server-ca-key.pem`. The game server private key stays in `config/server-key.pem`. Neither private key is copied to the player kit. Distribute the kit through a trusted download location; it defines which server the client trusts.

Allow inbound TCP traffic on the chosen game port in Windows Firewall. If your server is behind a router, forward that TCP port to the server's LAN address. A public IP, correctly pointed DNS and reachable port are necessary; this setup does not alter a router, bypass carrier NAT or purchase hosting. For local testing, use `localhost` as the hosting name and install the resulting kit in the local client.

Run `START_WORLD_SERVER_CONSOLE.bat`. The dedicated world server opens a persistent console with startup errors and connection logs. Run `PLAY_DIGIMON_VENOM_NXT.bat` from the configured client to join.

## Renewal and configuration

Server certificates last 397 days. Re-run public hosting setup before expiry; it preserves the CA so existing clients continue to trust the renewed server certificate. Restart the world server after renewal. If the public hostname or IP changes, re-run hosting setup and distribute the new `client.json` through a new kit. If the CA private key is lost, restore the backup; replacing the CA requires every player to receive a new kit.

Source commands (after installing `requirements.txt`):

```powershell
python -m tools.setup --help
python -m tools.setup mysql --help
python -m tools.setup hosting --help
python -m tools.setup --root C:\VenomServer mysql
python -m tools.setup --root C:\VenomServer hosting
```

For automation, `mysql --answers path.json` accepts keys `host`, `port`, `name`, `admin_user`, `admin_password`, `user`, `password`, `account_host`. `hosting --answers path.json` accepts `host`, `port`, `bind`. Pass `--root` before the subcommand. Use `hosting --output path.zip` to choose a connection-kit destination. Answers files may contain credentials: keep them outside source and client packages, then remove them when no longer needed.

For local development only, double-click `START_LOCAL_DEV.bat`, wait for the server to start, then open `PLAY_LOCAL_DEV.bat`. The first launch creates a separate `.venv-dev` and downloads runtime dependencies; subsequent launches reuse it. You can also run the source server and client with `--dev` in separate terminals. This uses local SQLite and unencrypted loopback networking; it is deliberately separate from public TLS / MySQL hosting. No XAMPP configuration is needed for this mode. Public configuration files are not modified.
