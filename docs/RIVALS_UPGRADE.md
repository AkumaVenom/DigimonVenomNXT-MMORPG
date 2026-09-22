# Upgrade to v0.2.0 — rivals and ranked seasons

This upgrade requires **both the new dedicated server and the new client**.
It retains your existing accounts, characters, database password and certificate
trust. The additional rival/ranked tables initialize automatically in the same
database. The usual upgrade does not require `02_SETUP_MYSQL.bat` or
`03_SETUP_PUBLIC_HOSTING.bat` again.

## 1. Stop and back up the working installation

1. Ask connected players to exit. Stop the old world server cleanly with Ctrl+C
   in its console and wait for shutdown. Do not run two world processes against
   the same database.
2. Export the game database with your existing MySQL/MariaDB backup method, such
   as phpMyAdmin's SQL export. Keep the export outside the installation folder.
3. Copy the entire old private server folder somewhere safe, especially its
   `config` directory. This includes `server.json`, `server-cert.pem`,
   `server-key.pem`, `server-ca.pem`, and `authority/server-ca-key.pem`.
4. Back up each player's client `config` folder or retain the current
   `Public_Player_Connection_Kit.zip`. It contains the working address and trusted
   CA. Display preferences stay in
   `%LOCALAPPDATA%\DigimonVenomNXT\display.json`; keep a copy if desired.
5. For SQLite development/local play, also back up
   `runtime\development.sqlite3` **after the development server has stopped**.
   A MySQL account is not stored in this development file.

Do not share the server backup or database export with players. The public
connection kit contains only the client configuration and public CA certificate.

## 2. Build in a separate source folder

If you downloaded the smaller **v0.1.1-to-v0.2.0 patch**, first copy your complete
v0.1.1 source folder to a separate writable folder. Extract the patch into its
parent so that the patch's `DigimonVenomNXT` directory merges with the copied
source directory of the same name, and allow source-file replacement. Confirm
that `venom/server/bots.py` now exists inside that source folder. Keep the
v0.1.1 assets in place; the patch does not contain them. Then run `BUILD_ALL.bat`
there and continue with step 3 below. Do not apply this source patch directly to
an installed EXE folder or to a v0.1.0 source tree.

For the complete source download:

1. Extract the complete v0.2.0 source package into a new writable directory, for
   example `C:\Games\VenomNXT_Source_0.2.0`.
2. Install 64-bit Python 3.11 or newer if it is not already installed. The first
   build needs Internet access to download the declared dependencies.
3. Run **`BUILD_ALL.bat`**. It verifies all included assets and metadata before
   building the Windows client, console server and setup utility.
4. Wait for a successful completion message. The independent outputs are:

   - `dist\Windows_Server_x64.zip`
   - `dist\Windows_Client_x64.zip`

The builder recreates its output folders. Keep your live installations and
backups outside the source tree's `dist` directory. Copy the **complete** built
folders, including `_internal`, data and assets; replacing only an EXE is not an
upgrade.

## 3. Install the new server with the existing configuration

1. Extract the complete new server ZIP to a permanent private directory, for
   example `C:\Games\VenomNXT_Server_0.2.0`.
2. Copy the old server's entire `config` directory into it, merging and retaining
   the existing files. Keep the database name, database account, password,
   certificate/key paths, host and port unchanged.
3. If configuration values refer to absolute paths, ensure those paths still
   point to the correct files. The standard relative `config/...` paths work
   when the entire directory is copied.
4. Start MySQL/MariaDB in XAMPP.
5. Run **`START_WORLD_SERVER_CONSOLE.bat`** in the new server folder.
6. Wait for initialization and the rival population readiness messages. First
   startup creates the additional tables and initial rival records. Later
   startups load the saved population and progress.

The original setup gives the dedicated database account the CREATE, ALTER and
INDEX permissions needed for schema updates. If an administrator later removed
those permissions, startup reports a database error; restore the required
privileges on the game database using that administrator's normal process.
Do not change the game or XAMPP password to fix a privilege error.

Existing configurations enable the default 5,000 rivals. To choose another
population, stop the server and merge a `rivals` property into `config/server.json`
as documented in `RIVALS_AND_RANKED.md`. Do not overwrite your working database
or TLS settings with a sample configuration.

Re-run MySQL setup only for a genuinely new database/account configuration.
Re-run public-hosting setup only when its hostname/IP settings need to change or
its certificate needs renewal. Preserve the existing certificate authority when
renewing. A normal v0.2.0 upgrade needs neither step.

## 4. Install and connect the new client

1. Extract the complete new client ZIP into a separate client directory.
2. Copy the old client's `config` directory into it, replacing the newly built
   default `client.json` with the working one and retaining `server-ca.pem`.
   Alternatively, extract the existing public player connection kit into the
   new client folder, merging `config`.
3. Run **`PLAY_DIGIMON_VENOM_NXT.bat`**. Sign in using the existing account.
4. Give other players this updated, configured client package. They need the
   updated client to access the new screens and existing connection files to
   trust your server. They do not install Python, MySQL or certificates in
   Windows for a built client.

The existing 4K UI, saved display/audio preferences, 1×–8× zoom, **F10 settings**
and **F11 fullscreen** are retained.

## 5. Check the new features

1. Confirm your existing character and party are present.
2. Enter a level and watch AI rivals move. Click one to inspect its profile.
3. Press **O** to open Bot Activity. Check population, map distribution, current
   activities and the recent-event feed. Give training time to complete; new
   rivals do not receive fabricated scan captures or win counts at startup.
4. Press **V** to open the Rivals Hub. Inspect nearby tamers and accept or decline
   an available invitation. Friendly results contribute to head-to-head history.
5. Press **R** to open Ranked Arena. Start a ranked match with your party and check
   its result, points, energy and season/career record.
6. Connect a second client to the same level and verify that both see the same
   rivals. Positions come from one server population rather than independent
   client simulations.

The default ranked season resets Monday at 00:00 UTC. At least one completed
ranked attack during the season is required for DigiRuby rewards. A closed
season appears in the archive after its normal reset; you do not need to alter
the clock or server configuration to create one. See `RIVALS_AND_RANKED.md` for
the full rules and reward tables.

## Local play without MySQL

For the source development mode, stop the old development server, build or
install the new source runtime as usual, and copy the stopped server's
`runtime\development.sqlite3` to the same relative path in the new source tree.
Copy any existing source `config` directory if it contains a custom local port or
population settings.

Run **`START_LOCAL_DEV.bat`**, wait for startup, then run
**`PLAY_LOCAL_DEV.bat`**. This remains a localhost-only SQLite development world.
It has its own accounts and rival/ranked records, separate from the production
MySQL database. Do not configure public hosting to expose development mode.

For a built local TLS server backed by XAMPP, follow the normal server/client
upgrade above and retain the localhost connection kit previously generated for
that server.

## Troubleshooting and rollback

- **New screens report an older server:** start the v0.2.0 server and check the
  client's configured address/port. Rebuilding only the client is insufficient.
- **Population is still starting:** allow initialization to finish; inspect the
  console if it reports an error rather than a readiness message.
- **Another server owns the population:** stop the old process. After an
  unclean crash, its ownership lease may need up to 90 seconds to expire.
- **Certificate or hostname error:** restore the working client configuration
  and CA from the old connection kit. Ensure the new server retained its old
  TLS files and is listening at the configured address.
- **Some rivals are absent from a map:** they can be in the DigiLab or another
  sector. The activity screen shows the live distribution.
- **No ranked energy:** energy recovers automatically. Friendly challenges and
  wild training remain available.

To roll back, stop the new world server and restore the old application folders
and the database backup together. This restores the backup's point in time and
discards progression earned afterward. Do not run old and new servers together
against the same database. Keep the v0.2.0 backup separately if you might resume
the updated world later.
