# Historical guide — v0.2.0 rivals and ranked seasons

**The installation instructions formerly at this filename are retired.** The
current release uses a fresh, dedicated portable MySQL process inside its own
server folder. Read [../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md)
and [SETUP.md](SETUP.md) for the current build and installation procedure.
Do not use an old external-database configuration or import an earlier server's
data into this fresh setup.

This file keeps the gameplay checks for the rival and ranked systems introduced
in v0.2.0. It is not an upgrade or database migration procedure.

For this release, build the complete source on Windows x64, extract the generated
server and client into separate permanent folders, and run **01_SETUP_SERVER.bat**
in the server folder. Install its generated connection kit in the client. Start
with **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. Create fresh
player accounts in the client.

After **STOP_SERVER.bat** confirms that the world and database have stopped, ZIP
the entire server folder to back up or move this portable installation. Do not
restart until copying or compression finishes. Retain the same engine, database,
credentials and configuration together; see the current operating guide for the
new-PC prerequisite and hosting-address details.

## Retained rivals and ranked feature checks

1. Register a tamer in the configured client and confirm the selected starter party is present.
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

## Gameplay troubleshooting

- **Population is still starting:** allow initialization to finish; inspect the
  console if it reports an error instead of a readiness message.
- **Some rivals are absent from a map:** they can be in the DigiLab or another
  sector. The activity screen shows the live distribution.
- **No ranked energy:** energy recovers automatically. Friendly challenges and
  wild training remain available.

For setup, certificates or saved-data problems, use the current portable server
operating guide. Keep the complete server folder and saves intact while diagnosing
an error.
