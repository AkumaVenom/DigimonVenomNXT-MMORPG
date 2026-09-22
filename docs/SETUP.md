# Windows x64 build and setup — v0.3.0

Use **01_SETUP_SERVER.bat** for the complete setup. The wizard keeps database,
hosting and readiness checks in one window. You can correct a field and retry
without restarting a chain of password prompts.

## 1. Build the complete source

1. Extract the full source ZIP into a new writable folder, such as
   `C:\Games\DigimonVenomNXT`. Open the inner folder containing `BUILD_ALL.bat`.
   Do not run files from inside the ZIP.
2. Install **Python 3.11 or newer, Windows x64**, with the Python launcher,
   **Add Python to PATH** and Tcl/Tk support. Internet access is needed for the
   first dependency download.
3. Run **BUILD_ALL.bat**. It verifies the hashes and sizes of the included assets
   and catalog, creates an isolated `.venv-build`, downloads the dependencies,
   checks them, and builds the native client, dedicated server and setup utility.
4. After it finishes, extract `dist/Windows_Server_x64.zip` into a permanent
   private server folder and `dist/Windows_Client_x64.zip` into a separate client
   folder. Keep working installations outside `dist`: rebuilding replaces it.

The source contains all imported runtime artwork, maps and audio. Original upload
archives are not required. A missing or changed asset stops the build rather than
being silently replaced. `python tools/build.py --verify-only` verifies the assets
on any supported OS. `BUILD_ALL.bat --offline` reuses a populated build environment.
Windows executables must be built on Windows x64; players running the resulting
client do not need Python.

MySQL 8 or MariaDB 10.4+ must already be installed and running. XAMPP provides a
compatible database service. The setup does not install or restart XAMPP.

## 2. Open the setup wizard

Start MySQL in XAMPP. In the permanent server folder, run **01_SETUP_SERVER.bat**.
The title/version should show **0.3.0**. On a fresh installation, there is no old
configuration to copy and no existing game account to supply.

For an existing server, first stop the world server and back up its database and
complete private `config` folder. Copy that entire `config` folder into the new
server folder before opening setup. Keep the saved database name to retain your
characters. Existing credentials, hosting settings and certificate authority are
loaded for reuse. Do not merge executable files from different releases.

### Check the database connection

Enter the database host, port, administrator name and the password that already
works with XAMPP. Local defaults are `127.0.0.1`, **3306**, and `root`. A genuinely
blank XAMPP administrator password is supported. Password fields allow typing,
pasting and checking the entered value.

Run the connection check before creating the game database. This verifies the
service and administrator login. A connection error remains visible with its
exact stage and error code; it does not repeatedly ask for an unrelated password.
The database port is separate from the game's listening port, usually **8765**.

### Create the game's database login

Keep the default game database name `digimon_venom_nxt` for a fresh install, or the
saved name when repairing an existing installation. The game uses its own limited
database login. Automatic password generation avoids a second password to invent
or remember. If choosing a game database password yourself, MySQL's password
policy applies.

No existing game database account is required. Setup creates and verifies the
login and initializes the schema before saving the database configuration. If a
requested username is already occupied by an account with a different password,
setup can allocate a separate NXT login for the same game database. Existing
characters and tables remain in that database. Setup does not change root's
password or passwords belonging to other MMOs, and does not save the administrator
password. The game's database credentials are stored in the private server config.

For a database on the same computer, use `localhost` as the game account's allowed
host. For a remote database, use the database-visible address of the world server.
The administrator must have permission to create databases, users and grants.

## 3. Choose local or public hosting

**Local on this PC:** choose local hosting. The connection uses `localhost` and
TLS, with the configured MySQL database. No router forwarding is needed for a
client on the same computer. This is distinct from the optional SQLite development
mode described below.

**Public or LAN:** enter the DNS name or IP address that the clients will use.
Do not include `https://`, a path, or `:port` in the hostname field. Choose an
available game TCP port, default **8765**. Use a different port if another MMO
already uses it. The server bind address is a local listening address; it is
separate from the hostname players connect to. Public hosting normally binds
`0.0.0.0`.

The wizard creates or reuses the certificate authority, issues a matching server
certificate, and creates `Public_Player_Connection_Kit.zip`. This kit contains:

```text
config/client.json
config/server-ca.pem
```

Extract the kit **inside the Windows client folder**, merging `config`. The client
checks the bundled CA and hostname automatically. Players do not install a
certificate into Windows. Only the configured client and public kit are player
downloads; never share the server folder or certificate private keys.

For Internet hosting, allow the selected TCP game port through Windows Firewall
and forward it to the server's LAN address on your router. DNS must resolve to
your reachable public address. Setup cannot configure the router, DNS or ISP, and
local readiness does not prove reachability through an external network. Test
from another connection after configuring forwarding. For LAN play, use the
server's LAN hostname or address and generate a kit for that address.

## 4. Check readiness and play

Complete the wizard's readiness checks. If a check fails, keep the window open,
read its stage and error code, correct the indicated field and retry. Setup writes
`logs/setup-latest.json` with diagnostic information and omits password values.
Use the wizard's copy function or attach that report if asking for help.

Run **START_WORLD_SERVER_CONSOLE.bat** in the server folder and wait for startup,
including the initial rival population, to finish. Run
**PLAY_DIGIMON_VENOM_NXT.bat** in the configured client folder. Use **Register** to
create your player/tamer account. That account is separate from both the XAMPP
administrator and the game's internal database login.

Back up the game database and the entire private `config` folder regularly.

## Errors and retries

| Error | Meaning and next action |
|---|---|
| 1043 | MySQL/MariaDB rejected the connection handshake. Confirm that the host and port belong to MySQL, check the server/version details and retry. This code alone does not mean the password is wrong. |
| 1045 | Database authentication was rejected. Check the username, password and account host for the stage shown in the report. |
| 2003 / connection refused | Start the database service and check its host, configured port and firewall. |
| Password policy rejection | Choose a game database password accepted by the database policy, or use automatic generation. This is not a request for an existing game account. |
| Game port already occupied | Stop the other instance of this game or choose a different unused game port; update the client with the new kit. |

The reported user failure has not been confirmed as 1043. Diagnostics retain the
actual code so a handshake failure and a password failure can be distinguished.
Do not send passwords or `config/server.json` when requesting help; send the
sanitized diagnostic report instead.

## Reopening one page and advanced console mode

- **01_SETUP_SERVER.bat** opens the complete wizard.
- **02_SETUP_MYSQL.bat** opens its database stage.
- **03_SETUP_PUBLIC_HOSTING.bat** opens its hosting stage.
- Adding **--console** to 02 or 03 runs the legacy console workflow.
- Existing **--answers** and **--console-passwords** arguments on 02 remain
  supported and select the legacy workflow. The old optional `setup_fix` repair
  payload never takes priority over the new full-release setup utility.

Source commands, after installing `requirements.txt`:

```powershell
python -m tools.setup --root C:\VenomServer wizard
python -m tools.setup --root C:\VenomServer wizard --stage database
python -m tools.setup --root C:\VenomServer wizard --stage hosting
python -m tools.setup --root C:\VenomServer mysql --console
python -m tools.setup --root C:\VenomServer hosting --console
```

Pass `--root` before the subcommand. Legacy `mysql --answers path.json` accepts
`host`, `port`, `name`, `admin_user`, `admin_password`, `user`, `password` and
`account_host`. Legacy `hosting --answers path.json` accepts `host`, `port` and
`bind`; `--output path.zip` chooses its connection-kit destination. Answers files
may contain credentials: keep them private and outside player distributions.

## Certificate renewal and optional development mode

Server certificates last 397 days. Reopen hosting setup before expiry and retain
the existing CA; clients continue to trust a renewed certificate from that CA.
Restart the world server after renewal. A changed hostname or port requires a new
client connection kit. Loss or replacement of the CA requires a newly trusted kit
for every player; preserve the full private config backup.

For source development without XAMPP, run **START_LOCAL_DEV.bat**, then
**PLAY_LOCAL_DEV.bat**. The first launch installs dependencies into `.venv-dev`.
This mode uses a separate SQLite development save and unencrypted loopback
networking; it does not change the normal MySQL/TLS configuration.

See `VALIDATION.md` for the checks actually run. Native Windows executables and
acceptance on the target XAMPP computer require testing on that Windows host.
