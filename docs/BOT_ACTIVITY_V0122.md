# Bot Activity: latest 12 hours — v0.12.2

**Bot Activity / O** now reports the latest **12 hours** of global rival activity
instead of an ever-increasing lifetime total. Its recent feed contains at most
the **latest 100 events within those 12 hours**. Old activity display data and
expired activity receipt rows are removed from the database automatically at
startup and regularly while the server runs. Activity displays filter expired
entries immediately, including while rivals are idle.

The previous restart repair remains in place: saved-world loading has **no
overall startup deadline**, ownership renewal continues during loading, and
rivals restore in batches with visible progress.

## What changes and what stays

| Data | v0.12.2 behavior |
|---|---|
| Global counters in Bot Activity | Latest 12 hours, stored as compact minute totals. |
| Recent activity feed | Latest 100 events that are still inside the 12-hour window. |
| Activity persistence receipts | Expired receipts are removed with activity retention. |
| A rival's career statistics | Small, fixed sets of lifetime counters remain. These support individual records and training behavior. |
| Earned partners, XP, scans, inventory and currencies | Preserved. An activity counter expiring does not undo earned progress. |
| Player saves, both story campaigns, Season careers and ranked rewards | Preserved. |
| Ranked match outcomes | Retained for career records, rewards and duplicate-result protection. |

The window follows elapsed time, including time the server is stopped. Restarting
does not reset recent timestamped activity or turn old activity into new events.
If the server has been stopped for more than 12 hours, its previous activity has
aged out when it returns.

Counter retention has **minute precision**. To avoid reporting anything older
than 12 hours, the oldest partial minute is excluded; activity in that minute
can disappear less than one minute before its exact 12-hour anniversary. Recent
feed entries use their recorded event time.

## First start after upgrading

The old global counters held lifetime totals without timestamps. Those totals
cannot truthfully be converted into a last-12-hours total. The upgrade starts
new timestamped global tracking and retires those old global totals. The
rolling counters can therefore start at zero and build up with new activity.
Existing recent feed entries can remain if their recorded times are within the
window. Individual rival careers and earned game progress do not restart.

No manual SQL, database reset or new server setting is required. Keep the
existing saved database and let the updated application perform its normal
startup and activity cleanup.

## Database size and startup expectations

A large displayed counter is a number, not a saved list of every activity.
The original global counter table was small, and the recent feed was already
capped at 100 entries. This update also addresses the activity receipt table,
which previously accumulated a new row for each saved activity batch without
expiry. Receipts and minute counters now have bounded retention rather than
growing for the entire lifetime of the server.

Your database still stores real game progress and retained ranked outcomes.
Those can grow independently of the Bot Activity screen. This update does not
promise a fixed total database size or a particular startup duration. Deleting
expired rows makes database space available for reuse; MySQL data files do not
necessarily shrink immediately on disk. Do not delete database files to try to
force them smaller.

## Update both Windows applications and keep your saves

This is a **source release**, not prebuilt Windows executables. Rebuild and
deploy **both the server and client** for the complete 12-hour activity behavior
and its updated labels.

1. Run **STOP_SERVER.bat** in the existing installation. Wait for confirmed
   world-server and MySQL shutdown, then back up the **complete stopped server
   folder**. Keep the original installation intact while preparing the update.
2. Extract the complete v0.12.2 source into a separate writable source folder,
   or merge the update's `DigimonVenomNXT` directory into a copy of the complete
   **v0.12.1 source**. Keep all baseline assets and the bundled MySQL runtime.
   Keep live installations outside the source folder's `dist` directory.
3. On **Windows x64**, use 64-bit Python 3.11 or newer with Tcl/Tk support and
   run **BUILD_ALL.bat**. Its first build needs internet access for the Python
   build dependencies. It produces `dist/Windows_Server_x64.zip` and
   `dist/Windows_Client_x64.zip`.
4. Work on a copy of the stopped server backup. Replace the application
   components with those from the new server package: `VenomWorldServer.exe`,
   `_internal`, `admin`, `assets`, `data`, `docs`, `mysql/manager`, launchers,
   build metadata and readmes. Replace application directories in full.
5. Preserve the complete server **`config`** folder, **`mysql/data`**,
   `mysql/instance.json`, `mysql/game-login.json`, private MySQL configuration,
   **`mysql/runtime`**, and existing runtime logs. Top-level `data` contains
   game content; **`mysql/data` contains the saved database**. **Do not run
   fresh setup, delete the database, reset rivals or clear ranked rewards.**
6. Extract the complete new client package into a new folder. Copy in the old
   client `config` folder, including `client.json` and the trusted
   `server-ca.pem`. Keep your connection settings and display preferences.
7. Start **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. Let the
   saved population finish restoring and wait for **World ready**. A progress
   message every 15 seconds during a long stage is informational, not a
   loading deadline.
8. Connect with the rebuilt client. Confirm your original account, wallets,
   partners, story and Season progress. Open **Bot Activity / O** and check
   its 12-hour labels. New activity should increase its counters; a rival's
   separate career record should remain available. After a clean shutdown,
   restart and verify that recent activity and earned progress remain.

If startup ends with an error, keep the database unchanged and follow the log
instructions in [RESTART_REPAIR_V0121.md](RESTART_REPAIR_V0121.md). Share the
complete final error and relevant log tail, not private database credentials.

## Verification and its limits

The complete automated suite finished with **799 passed and 10 skipped** in
224.55 seconds. The skips are one opt-in live-MySQL check and nine graphical
setup-wizard checks; they are not reported as passes.

A persistence check submitted **40,320 minute batches over 28 simulated days**,
using all 27 activity counters including fractional walking distance. The
shared counter history stayed at **720 minute buckets** and the recent feed at
**100 events**. Retained counter JSON measured **318,960 bytes** at days 1, 7
and 28. That measurement excludes database overhead and other saved gameplay
data; it is not the size of the complete database. Receipt retention also
expired correctly; its row count depends on how often activity is saved within
12 hours, rather than a fixed 720-receipt limit.

See the [retention report](validation/activity_v0122/RETENTION_VALIDATION.md),
[machine-readable measurements](validation/activity_v0122/retention_28_days.json)
and [validation index with UI previews](validation/activity_v0122/README.md).
These are development checks using synthetic data. Native Windows building
and a playtest on the intended machine remain required; source checks do not
establish that those Windows checks have already passed.
