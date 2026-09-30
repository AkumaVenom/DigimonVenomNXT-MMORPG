# Digimon Venom NXT v1.2.0 — Shiny and Cyber Paradox varieties

This source release implements 502 Shiny varieties and replaces the artwork for
all 502 existing Paradox varieties with the supplied Cyber Paradox sprites.
The normal roster remains 502 species, for 1,506 catalog entries in total.
Normal and existing Paradox IDs remain unchanged, preserving saved ownership,
scan totals, evolution histories, story guardians and ranked teams.

## Encounter and capture rules

| Variety | Chance per eligible wild encounter | Scan per defeated enemy |
| --- | ---: | ---: |
| Normal | Remaining encounters | 20 percentage points |
| Paradox | 2.5% | 5 percentage points; existing mastery rules retained |
| Shiny | 1% | 5 percentage points |

The server rolls once per wild encounter, not once per enemy. A successful
Shiny roll replaces one enemy with a Shiny from the area's eligible normal
species family. Every scan-capture world map in both the Dawn and World DS
map sets has a Shiny pool. Manual Search and walking-triggered encounters
use the same server-owned logic. A battle contains at most one rare variety;
disjoint roll ranges preserve the exact 1% Shiny and 2.5% Paradox chances.
The 1% probability is a long-run chance, not a guarantee every 100 searches.

Eligible story field-training battles also use the Shiny roll. Safe story hubs
remain safe; authored tamer teams, story bosses, ranked opponents and private
Season teams are not randomly replaced or made into scan rewards.

Scan is earned on defeat, once per enemy. Fleeing or losing after a defeat keeps
scan already earned, as in the baseline. Simply seeing, targeting or fleeing
from an undefeated Shiny gives no scan. Shiny always awards 5 percentage
points; Paradox Scan Mastery applies only to Paradox. Scan caps at 200%.

Shiny, Paradox and normal scans are separate. At 100% Shiny scan, convert that
Shiny at the DigiLab or DigiFarm using the existing capacity and ABI rules.
Starting from zero, 20 defeats of the same Shiny species reach 100%. Shiny art,
name and variety remain through party changes, storage, feeding, evolution,
de-digivolution, ranked participation and save/reconnect. Shiny stats mirror the
normal species; rarity does not grant a hidden combat multiplier.

## Artwork and collection

The client includes a separate Shiny collection filter and gold variety labels.
New art is loaded by the actual species ID in battles, menus, the world follower,
DigiFarm, story guardians and multiplayer displays. Animation poses follow the
baseline's selected frame mappings, including corrected frames and opposite
facing poses; whole sprite sheets are not used as animation frames.

The supplied Champion/Shoutmon folder contains a missing-2D-source notice and
is not an existing playable catalog entry. Rookie Shoutmon is included normally.
Every one of the 502 playable baseline species has both supplied varieties.

The local server console supports `/setshiny <player> <partner> <true|false>`
under the same GAME_MASTER permission as `/setparadox`. These are administrative
operations on actual catalog counterparts, not client requests. Players acquire
Shinies through encounters, scan conversion and same-variety evolution.

## Upgrade an existing installation

1. Stop the existing world server and MySQL cleanly, then back up the complete
   stopped installation.
2. Download **both v1.2.0 Source ZIP parts**. Extract each into the **same new
   parent folder**, merging the `DigimonVenomNXT` directories. Both ZIPs are
   required and are ordinary, independently extractable archives. Do not place
   one part inside the other or merge old Paradox asset folders into this release. Their superseded files have been
   removed from the new source tree.
3. On Windows x64 with 64-bit Python 3.11 or newer (including Tcl/Tk), run
   **BUILD_ALL.bat**. The first build needs internet access for dependencies.
   This creates `dist/Windows_Client_x64.zip` and `dist/Windows_Server_x64.zip`.
4. Deploy **both** complete rebuilt applications. On a copy of the stopped
   server, replace application code, `_internal`, `admin`, top-level `data`,
   application `assets`, `docs`, `mysql/manager`, launchers and build metadata.
   Replace these application directories in full to remove outdated assets.
5. Preserve **`config`**, **`mysql/data`**, `mysql/instance.json`,
   `mysql/game-login.json`, private MySQL configuration, `mysql/runtime` and
   runtime logs. Top-level `data` is game content; `mysql/data` is your saved
   database. No schema reset, fresh setup or deletion of saves is required.
6. Extract the rebuilt client separately and copy its previous `config` folder,
   including `client.json` and `server-ca.pem`, into the new client. Distribute
   the new client to all players; older clients lack the new species and art.
7. Start MySQL and the server. Wait for **World ready**, connect with v1.2.0,
   then check existing partners, scans, currencies and both story campaigns.
   Open the collection's **Shiny** filter and inspect an existing Paradox partner.

This deliverable contains source and assets. Native Windows executables must
be built on Windows; a live production deployment is not performed here.
Current checks and their limits are recorded in
[validation/release_v120/README.md](validation/release_v120/README.md).

## Verification and configuration

- **VERIFY_VARIETIES.bat** checks all Shiny and Paradox sprite files and animation paths.
- `python tools/build.py --verify-only` validates shipped asset/catalog hashes.
- `python -m pytest -q` runs the regression suite.
- `python -m pytest -q tests/test_shiny_gameplay_v120.py tests/test_shiny_server_v120.py tests/test_shiny_client_v120.py tests/test_variety_assets_v120.py`
  runs the focused release checks.
- `data/mechanics.json` owns `shiny_encounter_chance: 0.01` and
  `shiny_scan_gain: 5`. Change server rules deliberately and rebuild/redeploy
  both applications when changing catalog or assets.

The baseline's DigiLab, DigiFarm, ABI DigiMeat, DigiRuby economy, both story
campaigns, Paradox mastery, Season career, ranked arena and persistent rivals
remain available with the new varieties.
