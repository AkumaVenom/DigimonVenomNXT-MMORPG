# Setup redesigned in v0.3.0 — complete source

Use **01_SETUP_SERVER.bat** in the newly built server folder. Database, account,
hosting and readiness now belong to one native setup wizard. The complete source
includes the assets and all existing gameplay and rival systems.

## Start here

1. Extract the full source into a new folder and run **BUILD_ALL.bat** on Windows
   x64 with Python 3.11 or newer and Tcl/Tk enabled.
2. Extract the resulting server ZIP to a permanent private server folder outside
   `dist`. For an upgrade only, stop the old server, back up its database and copy
   its complete `config` folder into the new server folder. A fresh installation
   needs no old account or configuration.
3. Start MySQL in XAMPP and run **01_SETUP_SERVER.bat**. Verify version **0.3.0**.
4. Test the XAMPP connection using its existing administrator password. A blank
   password is allowed when the administrator account has no password.
5. Create the game's database login. Automatic generation is available for the
   game database password. No existing game database or player account is needed.
6. Choose local or public hosting, create the connection kit and run readiness
   checks. Extract the kit inside the client folder, merging `config`.
7. Run **START_WORLD_SERVER_CONSOLE.bat**, then launch the configured client with
   **PLAY_DIGIMON_VENOM_NXT.bat**. Create your tamer account using **Register**.

The XAMPP administrator password is used for setup and is not saved. Setup keeps
the game database credentials in private server config so the world server can
connect. Occupied game usernames are handled without resetting another game's
credentials. Retain the same database name on an upgrade to retain saved progress.
Existing certificate authorities are retained when renewing hosting certificates.

## When something fails

The wizard keeps the error visible and records its stage and exact code in
**logs/setup-latest.json**. Copy the diagnostic text or attach that report;
passwords are omitted. Correct the failing setting and retry in the same wizard.

**1043** means the database rejected the connection handshake. **1045** means
authentication was rejected. A remembered code is not enough to establish the
cause; use the actual diagnostic report. The database usually listens on **3306**,
while the game normally listens on **8765**. Check which service the port belongs
to before changing passwords.

This release does not reset root's password or any other MMO's existing account
password. The existing XAMPP service can be shared while this game uses its own
database and an available game TCP port.

## Optional advanced workflows

**02_SETUP_MYSQL.bat** and **03_SETUP_PUBLIC_HOSTING.bat** reopen the corresponding
wizard stage. Add **--console** for their console workflows. Existing
**--answers** and **--console-passwords** options remain available for database
automation and masked console input. An old `setup_fix` directory does not override
the rebuilt setup utility.

See **SETUP.md** for build, local/LAN/Internet hosting, upgrade and certificate
renewal details; **VALIDATION.md** lists checks actually run. Windows build and
XAMPP acceptance need to be checked on the target Windows computer.
