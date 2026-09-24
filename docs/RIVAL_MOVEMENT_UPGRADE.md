# Historical guide — v0.3.1 rival movement and team training

**The installation instructions formerly at this filename are retired.** The
current release uses a fresh, dedicated portable MySQL process inside its own
server folder. Read [../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md)
and [SETUP.md](SETUP.md) for the current build and installation procedure.
Do not reuse an external-database configuration or follow the earlier setup-skipping
instructions. This fresh release does not import an earlier server's data.

The v0.3.1 walking and training behavior described below remains in the game. This
file is a gameplay reference, not an upgrade or database migration procedure.

For this release, build both applications from the complete source on Windows
x64, extract the generated server and client into separate permanent folders,
and run **01_SETUP_SERVER.bat** in the server folder. Extract its generated
connection kit into the client. Run **START_MYSQL.bat**, then
**START_WORLD_SERVER_CONSOLE.bat**, wait for readiness and register a fresh tamer.

To back up or move this portable installation, run **STOP_SERVER.bat**, wait for
confirmed world and database shutdown, and ZIP the whole server folder. Keep it
stopped until copying or compression finishes. The operating guide explains the
compatible Windows x64 requirement and one-time prerequisite on another PC;
restoring this complete folder does not require resetting the database.

## Retained movement, training and shared-state checks

1. Register a tamer in the configured client and enter a level.
   Watch several rivals through an activity cycle. Rivals walk during
   exploration and can stand still while battling; they disappear from the
   field while in the DigiLab.
2. Connect a second client to the same level. Both clients should show the same
   server-owned rivals walking along the same routes, with ordinary network
   interpolation delay. Their supplied tamer walking frames follow movement.
3. Watch an arriving rival: it uses a safe arrival point spaced from current
   residents. Rivals already on the map are not teleported sideways to separate
   them. Existing clusters disperse as their exploration turns begin.
4. Click a rival to inspect its party and progress, and use **O** for Bot Activity.
   Let several normal cycles complete. Compare actual walking/travel, wild and
   ranked results, collection and training activity rather than expecting
   every counter to change instantly.
5. Check both low-level and higher-level sectors over time. Travel considers
   quieter eligible maps, and younger teams return to safer sectors. Experienced
   teams make limited visits to underfilled higher-level sectors, then return
   to a stretch of normal team training. Pending arrivals are counted when
   assigning these visits so the same gap does not attract the whole fleet.
   Occupancy changes naturally with travel, Lab visits, battles and the
   configured population.
6. Use **R** for Ranked Arena and **V** for the Rivals Hub. Ranked attacks still
   require energy and follow the same season rules. Friendly challenges and
   the rest of the activity cycle continue alongside training.

Training rounds keep real partner identities. Mature partners can be stored
while younger owned partners train, then return to the party later. New
partners require at least **100% earned scan data**. The Lab chooses and stores
party members before checking evolution, keeping a rival's only established
partner until it has earned another through scanning. Legal evolution and
de-evolution use the existing game rules. Veteran coverage visits are limited
and followed by normal training time, so they cannot permanently replace that
rival's younger-team progression. The update does not invent XP or
reset collections. Team changes and population rebalancing occur during normal
play, not as an immediate database-wide rewrite. Default map dwell periods
remain several minutes, with earlier relocation when a team needs safer combat.

## Gameplay troubleshooting

- **Some rivals stand still:** inspect their activity. Battles and other tasks
  legitimately pause movement. If rivals marked Exploring remain stationary,
  retain console error details for diagnosis; do not delete the rival saves.
- **Some maps have fewer visible rivals:** population counts include residents
  temporarily in other activities. Balancing does not mean every map has exactly
  the same visible count, especially with fewer configured rivals.

For setup, certificates or saved-data problems, follow the current portable server
operating guide. This file does not prescribe database replacement or rollback.
