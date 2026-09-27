# Digimon World DS region — v0.10.0

The shared Digital World now includes a **Digimon World DS** region alongside
the existing Dawn sectors. Explore the supplied DS field artwork, encounter wild
Digimon from level 1 through level 99, gather scan data and meet the same roaming
AI tamers that already live in your server.

Your character, partners, inventory, credits and DigiFarm remain the same.
This is a shared MMO region. Your private Story Mode and Season careers remain
separate activities with their existing progression and saves.

## Find the new maps

Open **Worlds** in the top-left navigation, then choose **Digimon World DS**.
Use the region's search and level filters to find a route suitable for your team.
Each destination shows its actual artwork and wild level range. Transfer uses
the normal server-confirmed travel action. You can travel back to Dawn at any
time outside combat, without starting a different character or resetting progress.

The atlas remembers its region-specific search and page. Use its current-location
shortcut to find your current sector again. From DigiFarm, you may transfer into
an adventure map or return to your saved field position. Leave DigiLab before
transferring. Finish or flee a wild battle before changing maps. Returning home during an
ordinary wild battle uses the existing forfeit confirmation.

Players in the same DS map share the existing authoritative multiplayer world.
Movement, battle presence and roaming tamers stay synchronized for players on
the same shared map.
Map changes and reconnects continue through the same server connection rules.

Wild encounters use the existing battle controls. Fight, use skills and items,
withdraw, collect scan data and materialize new partners through the normal
systems. New map names, level progression and encounter placements are authored
Venom NXT rules using the supplied assets; they are not a claim to reproduce the
original Nintendo DS encounter tables or story.

## Routes and wild levels

| Area | Maps | Wild levels |
|---|---:|---:|
| Forest Glade | 1 | 1–4 |
| Green Valley | 5 | 1–8 |
| Sandstone Pass | 6 | 8–14 |
| Drainage Tunnels | 7 | 14–22 |
| Canopy Ridge | 7 | 22–30 |
| Sun Spire | 7 | 30–38 |
| Crystal Mine | 9 | 38–45 |
| Mirage Marsh | 8 | 45–53 |
| Silver Strand | 9 | 53–61 |
| Amber Badlands | 9 | 61–68 |
| Clockwork Fort | 10 | 68–75 |
| Frost Shelf | 8 | 75–81 |
| Radiant Citadel | 9 | 81–86 |
| Coral Archipelago | 12 | 86–90 |
| Magma Citadel | 12 | 90–94 |
| Shadow Grid | 12 | 94–97 |
| Core Terminal | 3 | 97–99 |
| Emerald Spire | 4 | 84–89 |
| Dusk Highlands | 4 | 88–92 |
| Void Isles | 4 | 92–96 |
| Eclipse Sanctum | 4 | 96–99 |

Levels describe wild opponents, not an entry requirement. Stronger side routes
and endgame areas remain repeatable after you reach them.

## Shared tamers and progression

The existing AI tamer population is shared across Dawn and World DS. No second
population or set of story NPCs is created. Tamers use the same saved partners,
roaming, collision checks, wild battles, scan collection, materialization,
training, evolution, DigiLab visits and ranked activities.

An existing server keeps its rival identities, teams, experience and records.
Tamers choose new destinations at their normal activity boundaries. Lower-level
teams grow into difficult routes through ordinary earned progression; updating
does not grant levels or pull a tamer out of a battle. A freshly initialized
population uses the existing disclosed sector-appropriate seed rule across both
regions. New player accounts still begin in the existing home flow.

Coverage responds to the number and strength of configured tamers. The default
5,000-tamer population can occupy all playable sectors; a small population rotates
through suitable maps instead of creating extra tamers to fill the world. A map
can temporarily be quieter while residents battle, train or travel. Visible
activity follows the authoritative server simulation.

## Imported artwork and music

The new wild region uses 150 complete field layouts in addition to the original
254 Dawn sectors. Background layers, foreground artwork and supplied collision
masks retain their source dimensions. Each imported field receives a validated
walkable arrival point and roaming paths.

All 204 map groups in the upload are accounted for. Farm-upgrade variants,
classroom/service interiors, exact duplicate clearings and seven incomplete
water-only renders are reserved or excluded from the wild atlas. They are not
turned into improvised adventure terrain. The original uploads are unchanged.
The existing private DigiFarm remains intact. **Characters.rar is not imported or
used in this release**, as requested.

World DS maps use a separate selection of the uploaded DS music, with regional
exploration tracks, battle themes and a short victory cue. Supplied loop timing
is used where available, and clipping/decoding checks are applied. The original
Dawn soundtrack, private Story and Season themes, DigiFarm music and volume/mute
settings retain their existing roles. Track-to-route assignments are authored
for this expansion. Source preview audio is used as supplied; it is not described
as cycle-accurate Nintendo DS emulation.

Detailed import decisions and provenance are included in `data/world_ds_maps.json`
and `data/world_ds_audio.json`. The new region has its own map and music identifiers,
so source files with names like `map_048` or `bgm10` cannot replace Dawn assets.

## Upgrade from Story Mode v0.9.0

This is a source release. Rebuild **both the client and world server** on
Windows x64 with 64-bit Python 3.11 or newer. The new client assets and server
catalog/collision data must match.

1. Run **STOP_SERVER.bat** in the working installation and wait for confirmed
   world and MySQL shutdown. Back up the entire stopped server folder and the
   client's `config` folder.
2. Extract the complete v0.10.0 source into a separate writable folder, or merge
   the update archive's `DigimonVenomNXT` directory into a copy of the complete
   **v0.9.0 Story Mode source**, replacing included files. The update includes
   the new runtime assets; it still needs the baseline's existing assets and
   bundled MySQL runtime.
3. Run **BUILD_ALL.bat**. Use both resulting packages:
   `dist/Windows_Client_x64.zip` and `dist/Windows_Server_x64.zip`.
4. Extract the new client into a new folder and copy in the old client `config`,
   including its connection settings and `server-ca.pem`.
5. On a copy of the stopped server backup, replace application components from
   the new server package: `VenomWorldServer.exe`, `_internal`, `admin`, `assets`,
   `data`, `docs`, `mysql/manager`, launchers, build metadata and readme files.
   Replace application directories in full.
6. Preserve the complete server `config`, **`mysql/data`**, `mysql/instance.json`,
   `mysql/game-login.json`, private MySQL configuration and bundled `mysql/runtime`.
   The top-level `data` directory contains game content; `mysql/data` is your saved
   database. **Do not run fresh database setup.**
7. Start MySQL, the updated world server and the updated client. Check your
   original character, DigiFarm, Story and Season progress, then visit a low-level
   World DS route through the new region tab. Observe normal rival activity and
   confirm travel, a wild battle, scan rewards and reconnecting in the new region.

No account reset, rival reset or separate DS server is required. Existing saves
continue in place. For a new installation, follow the main README and portable
server setup guide.

## Re-importing assets and validation

Normal building and playing do not need the original RAR uploads or extraction
tools: the runtime maps and audio are already included. Optional import scripts
under `tools/import_world_ds_*.py` regenerate the region catalogs from the supplied
archives. They use the import requirements and a libarchive installation with
RAR support. Do not import `Characters.rar` for this release.

`tools/merge_world_ds.py` combines the standalone region catalogs with Dawn and
refreshes the authoritative encounter lists. The ordinary asset importer retains
this expansion on later catalog regeneration. Regenerate the asset manifest with
`tools/import_assets.py --manifest-only` after an intentional content import, then
run `tools/build.py --verify-only`.

See `docs/WORLD_DS_VALIDATION_V0100.json` for exact test results, import checks,
archive provenance and native-screen coverage. Source tests and headless previews
do not replace building both Windows executables and smoke-testing them on the
intended host. No Windows build or target-hardware performance certification is
implied by the automated results.
