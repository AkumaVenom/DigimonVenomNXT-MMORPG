# Digimon Venom NXT — DigiFarm v0.6.0

This release makes the DigiFarm your private home. It uses the supplied island
and DigiMeat artwork, the existing Digimon sprites and a dedicated original
soundtrack, **A Place to Grow**. Your stored partners wander gently between rest
periods. Walk around as your selected tamer with your lead partner following,
and zoom the camera just as on a normal map. Click a resident to inspect it and
choose food through its management card. Feeding is optional: there is no
hunger meter, decay, upkeep or requirement to buy food.

This corrected **v0.6.0** source release adds playable tamer movement and camera
zoom to the original DigiFarm release. Update and rebuild **both applications**,
including installations already running v0.6.0.

## Home and collection

- The top-left **Home · DigiFarm** button and **F2** shortcut are available across signed-in screens.
  Returning during an active battle requires confirmation that the encounter
  will be abandoned; leaving grants no victory XP, credits or meat drops.
  Scan already earned from defeated enemies is retained.
- New accounts begin in their DigiFarm with three Friendship DigiMeat.
  Existing accounts keep their previous saved location, battle and progress.
- Each account has its own farm. Other players and AI rivals do not enter it.
- The DigiFarm holds **100 stored residents**. Your **six active-party slots**
  are separate. Depositing a partner or materializing directly into storage
  requires a free farm slot.
- Existing saves with more than 100 stored partners retain every partner.
  The first 100 are farm residents; overflow remains in storage and can be
  withdrawn. With a full party, choose its slot in DigiBank and use **Swap into
  slot** to exchange with any stored partner without needing spare capacity.
  Swaps preserve both Digimon and the stored count. No more residents can be
  added until storage is below the cap.
- Party management, materialization, evolution and shopping are available from home.
  At least one Digimon must remain in your active party.
- Click a resident to view its stats, CAM, accumulated training and food choices.
  An unavailable item or capped benefit cannot be fed. The server validates the
  selected resident, ownership, inventory, location and amount before consuming
  food or changing stats.

### Rotate a full party or an archived partner

When all six party slots are occupied, DigiBank shows a named party-slot selector.
Choose the slot, click **Swap into slot N** on the stored partner, then confirm
the displayed pair. The two partners exchange places without changing either
collection count. The incoming party partner is restored, and both partners
retain their identity, training and progression. This works with a full
100-resident farm and with legacy overflow; no partner needs to be deleted.

Only the first 100 stored partners are resident and feedable on the island. To
bring an archived partner into those resident slots, first swap it into your
party, then swap that same party slot with a resident among the first 100. The
archived partner now occupies a resident slot and can be fed normally. These
swaps rotate existing partners; they do not create additional farm capacity.

The farm keeps the established screen style, native display scaling and audio
preferences. Music volume and mute apply to its soundtrack. Leaving the farm
returns to the relevant destination's music.

## Walking and camera

- **WASD / arrow keys** move your selected tamer in eight directions, using the
  same 180 source-pixel-per-second speed and directional animations as field
  maps. Your lead party partner follows you.
- The client and server use the same island boundary. Your tamer stays on the
  grass and cannot walk into the surrounding water. The farm remains private
  and safe: walking there never triggers encounters.
- Your farm position is saved separately from your field position. Returning
  home restores your farm position without overwriting your saved world location.
- Use the **− / +** camera buttons, **minus / plus keys**, or the **mouse wheel
  over the island** to zoom from **1× to 8×**. **Fit level / 0** restores the
  whole-island view. At closer zoom the camera follows your tamer.
- Farm zoom is saved independently of field zoom. Interface size and other
  display/audio preferences keep their existing behavior.
- Clicking a resident opens its feeding card. Movement pauses while feeding,
  typing in a search field, or using menus, settings or confirmation dialogs.
  Mouse-wheel input over a list scrolls the list instead of zooming the island.

## Optional DigiMeat

All prices are in ordinary credits. Buy meat in the Shop and feed it to a stored
resident from its DigiFarm management card. Capsules retain their existing
recovery behavior; DigiMeat is a separate item family.

| Item | Permanent effect per serving | Price |
|---|---|---:|
| Friendship DigiMeat | +5 CAM, up to 100 CAM | 150 |
| Vitality DigiMeat +1 | +1 HP | 2,500 |
| Spirit DigiMeat +1 | +1 SP | 2,500 |
| Power DigiMeat +1 | +1 ATK | 2,500 |
| Guard DigiMeat +1 | +1 DEF | 2,500 |
| Wisdom DigiMeat +1 | +1 INT | 2,500 |
| Swift DigiMeat +1 | +1 SPD | 2,500 |
| Rare Vitality / Spirit / Power / Guard / Wisdom / Swift DigiMeat +5 | +5 to the named stat | 25,000 each |

Training bonuses are limited to **+100 in any one stat** and **+300 combined** per
Digimon. The management card shows the current bonus and remaining capacity.
Bonuses persist through saving, leveling, Digivolution and De-digivolution, and
are included in ranked combat snapshots. Evolution's existing level and other
progression rules still apply.

An eligible PvE victory has an **18% chance** to award **one Friendship DigiMeat**.
Losses, fleeing, abandoned battles and ranked matches do not award meat. Stat
training meat is purchased; its rare +5 tier is deliberately more expensive per
point than the +1 tier. Feeding grants no XP and creates no offline training.
These are original Venom NXT balance rules inspired by optional friendship
feeding, not a claim of exact Cyber Sleuth item values.

## Download packages

`VenomNXT_v0.6.0_DigiFarm_Patch.zip` contains only the changes for the exact
supplied UI2 source baseline or the previous v0.6.0 DigiFarm source release.
It is the smallest download for existing owners and replaces the earlier
v0.6.0 patch. Apply all its files even if v0.6.0 is already installed.

The complete source is supplied as four split ZIP parts (`.001`–`.004`). Put
all four parts in one folder with their names unchanged. Open the `.001` file
with 7-Zip and extract `DigimonVenomNXT`. All four parts are required. Do not
extract individual parts separately. The full source includes the patch.

## Upgrade an existing portable installation

This is a source-and-assets release. **Build and update both the client and world
server**; replacing only the client, as older UI2 instructions describe, is not
sufficient. Windows executables must be built on **Windows x64** with **64-bit
Python 3.11 or newer**. Linux checks do not produce Windows executables.

1. Run **STOP_SERVER.bat** in your existing server installation and wait for
   successful world and MySQL shutdown. Back up the **complete stopped server
   folder**, including `mysql` and `config`. Back up the client `config` folder.
2. Extract the full v0.6.0 source into a separate writable source directory.
   If using the v0.6.0 patch, merge its `DigimonVenomNXT` contents into a copy of
   the exact supplied UI2 source baseline or the previous v0.6.0 source,
   replacing included files and keeping files absent from the patch. A patch
   alone is not the complete game.
3. Run **BUILD_ALL.bat**. Both packages appear in `dist`. Keep live installations
   outside `dist`: build outputs are recreated. The source includes all required
   artwork, music and the same bundled MySQL 8.4.11 engine.
4. Extract the **complete** new `dist/Windows_Client_x64.zip` into a new client
   folder. Copy the old client `config` folder into it, including `client.json`
   and the trusted `server-ca.pem`. Display/audio preferences remain in Local
   AppData. Do not replace only the client executable.
5. For the server, work on a **copy of your complete stopped server backup**.
   Extract `dist/Windows_Server_x64.zip` separately. Replace the copied server's
   `VenomWorldServer.exe`, `_internal`, `admin`, `assets`, `data`, `docs`,
   `mysql/manager`, launchers (`*.bat`), `build-info.json` and readme files with
   their newly built equivalents. Replace each listed application directory in
   full so it cannot retain obsolete binary dependencies.
6. Preserve the server's **entire `config` folder**, **`mysql/data`**,
   **`mysql/instance.json`**, **`mysql/game-login.json`**, other private MySQL
   configuration and the bundled **`mysql/runtime`**. The top-level `data`
   directory is game content; it is distinct from the saved database in
   `mysql/data`. Do not initialize a fresh database, delete saves, or run fresh
   server setup for this upgrade.
7. Start **START_MYSQL.bat** and **START_WORLD_SERVER_CONSOLE.bat** from the
   updated server folder. Connect using the rebuilt v0.6.0 client, sign in to an
   existing account and check its party, stored collection and farm. Only one
   copy of the portable server may use port 3307 at a time.

The database schema is unchanged. Missing farm fields and training bonuses are
added to existing character data as it is loaded; existing collections are not
reset or truncated. Retain your stopped backup until the upgraded installation
has been checked. To roll back, stop the updated server and restore the complete
pre-upgrade backup rather than mixing old executables with newly modified saves.

## New installation

Follow [SETUP.md](SETUP.md) and [../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md).
Fresh setup is appropriate only when intentionally creating a new server and
new accounts. The source archive is not a precompiled game installer.

## Assets, build checks and verification

The client distribution includes `assets/ui/digifarm/level.png`,
`assets/ui/digifarm/digimeat.png` and
`assets/audio/original/digifarm_home.ogg`. Existing source artwork is retained.
The music is an original 80-second stereo composition at 96 BPM. Its reproducible
composition script is `tools/compose_digifarm_music.py`; regeneration requires
NumPy and FFmpeg, while game playback uses the existing audio runtime.

`data/ui_assets.json` records the supplied artwork and `data/ui_audio.json`
records the farm track. `data/asset_manifest.json` contains content hashes and is
verified before each build. Run these checks from the source folder:

```sh
python tools/build.py --verify-only
python -m pytest -q
```

Automated checks cover game rules, ownership and persistence, navigation and
feeding, capacity, presentation and packaging. Final run results accompany the
release separately. The build packaging test simulates Windows packaging; it
does not execute native Windows EXEs. Native Windows launch, physical audio
playback and performance on the target host still need a Windows run.
