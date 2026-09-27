# World DS: Paradox Chronicle — v0.11.0

A second private story adventure for your existing tamer. Begin in Forest
Glade, follow a trail of Paradox disturbances through 17 supplied Digimon World
DS field maps, and earn a Paradox Crest from every guardian. With all 17 crests,
summon the Convergence: three level-100 Paradox Megas in one final team battle.

Your first final victory permanently increases scan earned from winning wild
Paradox battles by **20%**. Normal Paradox scan changes from **5% to 6% per
defeated Paradox**. The existing 200% scan cap applies; completing the finale
again does not stack the bonus.

This is an original Venom NXT campaign using the supplied DS artwork. Chapter
names, quests, dialogue and encounter teams are authored for this game.

## Start your journey

1. Open **Story Mode / F4** and choose **World DS: Paradox Chronicle**. Your first
   visit begins at Forest Glade; later visits continue your saved journey.
2. Approach **Lyra** in the hub and press **E**, or click her, to begin. Read the
   conversation and choose its displayed action. **Enter / Space** advances
   dialogue. **Esc** closes a conversation when allowed.
3. Use the marked exits or the **World DS atlas** to travel. Chapters open as
   you earn the preceding crest. Press **J** to check the current objective.
4. In each field area, speak to the quest giver, accept the task, challenge its
   tamer, then return to turn in the quest. The completed quest unlocks that
   area's Paradox guardian. Defeat the guardian to receive its crest.
5. Collect all 17 crests, then use the final summon in **Eclipse Sanctum**.
   Prepare for **three level-100 opponents in one battle**.

Story characters show their dialogue and available actions when you approach.
The journal tracks the next objective, your atlas, crests and the final
Convergence. NPC matches use the same live attack, skill, target and item
controls as ordinary battles. Finish the match before changing activities;
logging out preserves an unresolved story battle for your return.

## A peaceful home base

Forest Glade is the first of the 18 campaign maps. Walking, searching and
training there do not start battles. Its characters help you prepare:

| Character | Service |
|---|---|
| Lyra | Campaign introduction and guidance |
| Medic Elio | Recovery |
| Outfitter Len | Shop |
| Researcher Hana | DigiLab access |
| Keeper Moss | DigiFarm access |
| Archivist Fenn | Local lore |

Use the existing shop, recovery items, DigiLab and DigiFarm throughout your
journey. The story brings your actual partners at their actual levels. It does
not reset an established team or create a replacement party. For the intended
opening difficulty, bring partners around level 10. A stronger team stays strong.

Field Training becomes available in combat areas and uses ordinary wild battle
rules, including scan and fleeing. Train, recover and adjust your active trio
when the next trial becomes difficult. Your first three party members enter
live battles; manage reserves and evolution through the existing services.

Two early first-clear rewards help a new tamer build an active trio: Scout Pip
introduces a level-12 Terriermon, and the Sandstone guardian introduces a
level-20 Gomamon. They join an open party slot, then DigiFarm storage. If both
are full, their scan data is saved for later materialization. These rewards
never replace an existing partner and cannot be claimed again in rematches.

## The 17-crest route

Each row is one distinct supplied DS field map with its own quest, tamer trial,
Paradox guardian and crest. Opponent levels are fixed campaign difficulty;
they do not reduce the level of your partners.

| Chapter | Area | Tamer level | Paradox guardian level |
|---:|---|---:|---:|
| Hub | Forest Glade | No battles | No battles |
| 1 | Green Valley | 10 | 13 |
| 2 | Sandstone Pass | 15 | 18 |
| 3 | Drainage Tunnels | 20 | 23 |
| 4 | Canopy Ridge | 25 | 28 |
| 5 | Sun Spire | 30 | 33 |
| 6 | Crystal Mine | 35 | 38 |
| 7 | Mirage Marsh | 40 | 43 |
| 8 | Silver Strand | 45 | 48 |
| 9 | Amber Badlands | 50 | 53 |
| 10 | Clockwork Fort | 55 | 58 |
| 11 | Frost Shelf | 60 | 63 |
| 12 | Radiant Citadel | 65 | 68 |
| 13 | Coral Archipelago | 70 | 73 |
| 14 | Magma Citadel | 75 | 78 |
| 15 | Shadow Grid | 80 | 83 |
| 16 | Dusk Highlands | 86 | 89 |
| 17 | Eclipse Sanctum | 92 | 96 |
| Finale | Convergence in Eclipse Sanctum | — | Three opponents at 100 |

The Convergence team is **Paradox Alphamon, Paradox Omnimon and Paradox
Imperialdramon Paladin Mode**, all Mega Digimon. The existing owned-partner
level cap remains 99; the level-100 opponents are authored story bosses.

## Crests, rewards and collecting

Paradox Crests are permanent campaign collectibles shown in the journal. A
crest records a guardian's first defeat and unlocks the next chapter. Defeat or
logout does not remove crests already earned. Story rewards and partner growth
carry back to the MMO with your character.

Tamer, guardian and finale encounters are **story battles**. Their opponents do
not award wild scan. Your collection bonus applies to **victorious wild Paradox
encounters after the finale**, including qualifying Field Training. It applies
across regions on the same character. It does not raise ordinary Digimon scan,
add bonus scan for a loss or flee, or increase the 200% maximum. The existing
base scan from defeated wild enemies is still retained after fleeing or losing.

| Situation | Paradox scan benefit |
|---|---|
| Before finishing the final battle | Existing wild scan rate |
| First final victory | Permanently unlocks the 20% increase |
| Normal wild Paradox victory afterwards | 5% becomes 6% for each defeated Paradox |
| Another final victory | Existing benefit retained; no extra multiplier |
| Story NPC battle, loss or flee | No wild-victory scan benefit |
| Species already at 200% scan | Remains at the cap |

## Your two stories stay separate

**Dawn Relay** retains its eight DigiBadges, completed trials, story location,
championship and defense/reclaim records. **Paradox Chronicle** has its own map,
quests, crests and completion reward. Return to the MMO outside combat before
choosing the other campaign with F4. Each resumes its own saved progress.

Both campaigns use your normal partners, XP, scan collection, credits,
inventory, DigiLab and DigiFarm. Story quest and battle tamers are authored
NPCs in your private instance. They do not use the shared AI rival population,
its training simulation, ranked records or Season schedule. Other players do
not enter your private campaign. The shared DS region remains available through
**Worlds** when you are outside Story Mode.

Use **Return to MMO / F4** outside combat to save your story position and return
to your previous activity. Normal reconnects and clean server restarts retain
story progress through the existing character save. There is no separate
account or new database to create.

## Upgrade from World DS v0.10.0

This is a **source release**. Rebuild **both the client and world server** on
Windows x64 with 64-bit Python 3.11 or newer and Tcl/Tk support. An old client
and a new server must not be mixed. The first build needs internet access for
Python build dependencies. A native Windows build and target-PC playtest are
still required; this guide does not claim either has already been completed.

1. In the working server installation, run **STOP_SERVER.bat** and wait for
   confirmed world and MySQL shutdown. Back up the complete stopped server
   folder and the client's `config` folder. Never copy a live database as a
   backup.
2. For the full release, download **both Full_Source_Part1_of2.zip and
   Full_Source_Part2_of2.zip** and extract both into the same writable parent
   folder, merging their `DigimonVenomNXT` directories. Both ZIPs are required.
   Alternatively, merge the patch's `DigimonVenomNXT` directory into a copy of
   the complete **v0.10.0 World DS source**, replacing the included files. The
   patch still requires that baseline's assets and bundled MySQL runtime.
   Keep the working server installation outside the source's `dist` directory.
3. Run **BUILD_ALL.bat**. Use both generated packages:
   `dist/Windows_Client_x64.zip` and `dist/Windows_Server_x64.zip`.
4. Extract the new client into a new folder. Copy the old client `config` folder
   into it, including `client.json` and its trusted `server-ca.pem`.
5. Work on a copy of the stopped server backup. Replace the application
   components from the new server package: `VenomWorldServer.exe`, `_internal`,
   `admin`, `assets`, `data`, `docs`, `mysql/manager`, launchers, build metadata
   and readme files. Replace application directories in full.
6. **Preserve** the complete server `config` folder, **`mysql/data`**,
   `mysql/instance.json`, `mysql/game-login.json`, private MySQL configuration
   and bundled `mysql/runtime`. The top-level `data` directory contains game
   content; **`mysql/data` is your saved database**. Do not run fresh database
   setup, reset accounts or replace existing save files with empty folders.
7. Start MySQL and the updated world server, then the updated client. Check
   the original account, partners, inventory, DigiFarm, Dawn Relay and Season
   progress. Open the campaign chooser, enter the peaceful DS hub, speak to
   Lyra, visit a service, then start the first field quest. Return to the MMO
   and reconnect to confirm your saved location and objective.

For a new server only, use the main README and
[../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md). Existing portable
installations require no fresh setup or database reset for this story update.

## v0.11.0 changes

- Added the campaign chooser and a second private story with 18 DS map layouts.
- Added a peaceful hub, regular service NPCs, local story dialogue, 17 quest
  sequences and separate authored tamer battles.
- Added 17 distinct Paradox guardians, permanent crest progression and the
  three-Mega level-100 Convergence finale.
- Added a permanent, non-stacking 20% increase to wild Paradox victory scan
  after the first final victory, with the existing scan cap retained.
- Kept Dawn Relay saves, ordinary character progression and shared-world
  activities connected through their existing systems.
- Updated release metadata, controls and client/server build documentation.

## Verification for this source release

The full automated suite passed **701 tests**, with **10 environment-specific
checks skipped**. After final dialogue polish, all **38 targeted checks** passed.
Both level-10 starter playthroughs completed all 17 crests and the final trio
through normal game actions. All **21,806 asset records** passed SHA-256
verification. Native campaign screens were reviewed at 1280×800 and 960×540.

See [WORLD_DS_STORY_VALIDATION_V0110.json](WORLD_DS_STORY_VALIDATION_V0110.json)
for scope and limitations, and `previews/world_ds_story` for actual client
screens. The supplied evidence covers source behavior and headless rendering;
build and smoke-test both Windows applications on the intended computer.
