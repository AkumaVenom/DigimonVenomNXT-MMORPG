# Story Mode v0.9.0 — Dawn Relay

A private, persistent adventure inside Digimon Venom NXT. Explore the supplied
Dawn maps with your own partners, meet NPC tamers, collect eight DigiBadges and
become the Dawn Champion. The championship continues through defenses and
comebacks after the main journey.

Dawn Relay is an original Venom NXT story using the game's imported Dawn maps,
tamer sprites, battle system and audio. It is not a retelling of the Nintendo DS
story. A protection protocol called HUSH is isolating the relay network; mentor
Mira and rival Nox accompany your journey to restore it.

## Your partners come with you

Story Mode uses your actual owned team. It does not create a replacement party,
reset your Digimon, scale them down or create a second wallet. A strong existing
team stays strong; a new tamer can begin with the normal starter.

| Shared with the MMO | Private to your Story Mode |
|---|---|
| Party and stored Digimon, levels, XP, ABI and CAM | Story location and current chapter |
| DigiLab, evolution and materialization | NPC conversations, prerequisites and victories |
| DigiFarm and its normal training systems | Eight DigiBadges |
| Inventory, shop purchases and ordinary credits | Dawn Champion, defenses, losses and reclaims |
| Permanent companion rewards and scan data | Story statistics and recent results |

Rewards and partner growth carry back to the world. Story victories do not award
Ranked Arena points or DigiRubies, advance a UTC season, or alter your private
Season league's calendar or championship. The Dawn Champion belongs to your own
story, independently of other players.

## Enter, explore and return

1. Click **Story Mode** in the top-left navigation, or press **F4**. Your first
   visit begins in Lumen Skyport; later visits resume the same journey.
2. Walk with the normal movement controls. NPC markers and the minimap help you
   find tamers and services. Approach an NPC and press **E**, or click them.
3. Read the conversation and choose its displayed action. **Enter / Space**
   advances dialogue; **Esc** closes a conversation when allowed.
4. Approach a marked exit and press **E**, or click it, to move through the region.
   The **Region atlas** also offers
   travel to unlocked locations. Later regions require the preceding DigiBadge.
5. Press **J** for the story journal. Review the current objective, atlas, badge
   collection and championship record. The normal Worlds button becomes the
   story atlas while you are in the adventure.
6. Click **Return to MMO**, press **F4**, or choose the journal's return action
   while outside combat. Your story position is saved and your previous world,
   DigiLab or DigiFarm location is restored.

Your normal Partners, Items, shop, DigiLab and DigiFarm remain available.
The story's camp action opens the real DigiLab. Return from those facilities to
continue exploring. You cannot switch activities during an NPC tamer battle.

Conversations pause movement locally so a key used to read cannot accidentally
walk you away. Server notices remain available. Other human players and shared
world rival bots do not enter your private story maps.

## Play every battle

NPC tamers use the existing live, server-authoritative combat system. Choose
attacks, skills, targets, items and party actions normally. The server controls
the opposing NPC team; it does not play your turns or substitute a replay.

**Fleeing and scanning are disabled in NPC tamer matches.** Win or lose the match
to resolve it. Logging out preserves the battle and current turn. Returning does
not silently award a result. Defeat lets you recover and try again without
losing an earned badge.

**Field Training** provides repeatable wild battles in the current region. These
retain normal wild-battle fleeing and scan rules. Training helps a new starter,
a newly evolved level-1 partner or a changed team prepare for the next trial.
Free recovery and the normal DigiLab/Farm prevent a weak party from becoming
stuck. Early training chooses an appropriate opponent for the actual party.

Healing NPCs provide free recovery, and resolved story fights restore the party.
Use services and the journal between matches. The visible objective identifies
the next required tamer and location, including training guidance when useful.

## Eight DigiBadges and the Dawn Champion

The journey contains nine regions across 18 supplied maps, with 54 placed NPCs
and 27 story tamer encounters before the repeatable championship cycle.
Each badge region has two preliminary trials and its own warden. Talk to local
NPCs for the story and services; complete the required trials before its warden.

| Region | Opponent levels | Reward / destination |
|---|---:|---|
| Lumen Skyport | 3–10 | Lumen DigiBadge |
| Verdant Circuit | 12–20 | Canopy DigiBadge |
| Tideglass Coast | 22–30 | Tide DigiBadge |
| Amber Archive | 32–40 | Strata DigiBadge |
| Aurora Shelf | 42–50 | Aurora DigiBadge |
| Alloy Foundry | 52–60 | Alloy DigiBadge |
| Cinder Caldera | 62–70 | Ember DigiBadge |
| Eclipse Sanctuary | 72–80 | Eclipse DigiBadge |
| Dawn Champion Citadel | 83–100 | Qualifiers, championship and defenses |

Collect all eight badges, clear the Citadel qualifiers and challenge Champion
Aster. Later defenses rotate through six high-level challengers, including a
level-100 opponent. The existing owned-partner level cap remains **99**; this
release does not change normal evolution or species rules.

After your first championship victory:

- **Win a defense:** keep the crown and extend your defense streak.
- **Lose a defense:** the winning NPC becomes champion. Your badges, progress and
  previous records remain, and you can challenge that holder to reclaim it.
- **Win it back:** begin another reign and continue defending.

There is no forced restart or designed final defense. Leaving the mode or being
offline pauses your progress; no real-time calendar removes the title. The
championship screen shows its holder, reigns, defenses and current/best streak.

## Rewards and records

Story victories grant ordinary credits, partner experience and CAM growth. First
victories also grant authored item rewards, ABI growth and selected permanent companion
rewards. These are saved into the existing inventory and roster. Milestone XP
helps a low-level team progress; it never reduces a higher-level partner.

A companion goes into an available party slot, then DigiFarm storage. If both
are full, its reward becomes enough scan data to materialize later. Clear space
through the normal systems when ready. Your current partners are never replaced.

First-clear rewards are recorded once. Friendly rematches grant reduced credits
without repeating the original companion or item package. Championship matches
continue to provide rewards as part of the endgame loop. Inventory and credit
limits remain enforced; the results display reports the rewards actually granted.

Story statistics retain wins, losses, training results, earned credits and
championship records. The recent-results view retains the latest 30 results;
older individual result cards are discarded while cumulative career statistics,
badges, completed trials and championship continuity persist.

## Persistence and isolation

The world server owns story state in the existing character save. No separate
offline executable, replacement account, or second save database is required.
Successful story actions save before publication to the client. Dialogues,
progress, location and active battles survive logout and a normal server restart.

The story uses a private instance key per player, even when two players visit
the same map. Story activity does not publish shared rival snapshots or ranked
records. Battle identifiers, turn checks, conversation tokens, proximity checks
and prerequisites are validated by the server.

Story Mode and Season Mode cannot be active together. Finish combat and return
to the world before changing modes. Local administrative gameplay edits are
refused while a player is in Story Mode; read-only inspection and moderation
remain available. Detention safely suspends the private activity and resumes it
when released. Existing host-only console permissions remain unchanged.

## Upgrade from Local Admin v0.8.0

This is a **source release**. Rebuild both the client and world server using
**64-bit Python 3.11 or newer on Windows x64**. Do not mix the old client with the
new server or the new client with an old server.

1. Run **STOP_SERVER.bat** in the working server installation. Wait for confirmed
   world and MySQL shutdown. Back up the complete stopped server folder and the
   client's `config` folder.
2. Extract the complete v0.9.0 source into a separate writable source folder, or
   merge the update's `DigimonVenomNXT` folder into a copy of the working
   **v0.8.0 Local Admin source**, replacing included files. The update requires
   that baseline's assets and bundled database runtime. Keep the live server
   installation outside the source's `dist` directory.
3. Run **BUILD_ALL.bat**. Use both resulting packages:
   `dist/Windows_Client_x64.zip` and `dist/Windows_Server_x64.zip`.
4. Extract the complete new client into a new folder. Copy in the existing client
   `config` folder, including `client.json` and `server-ca.pem`.
5. On a copy of the complete stopped server backup, replace application components
   from the new server package: `VenomWorldServer.exe`, `_internal`, `admin`,
   `assets`, `data`, `docs`, `mysql/manager`, launchers, build metadata and readme
   files. Replace application directories in full.
6. Preserve the server's entire `config` folder, `mysql/data`,
   `mysql/instance.json`, `mysql/game-login.json`, private MySQL configuration and
   bundled `mysql/runtime`. The top-level `data` folder is game content;
   **`mysql/data` is the saved database**. Do not run fresh database setup.
7. Start MySQL and the updated world server, then the updated client. Check your
   original party, inventory, DigiFarm and Season career. Enter Story Mode, talk
   to Mira, complete a fight, return to the MMO and reconnect to confirm your
   own character's saved journey.

Story progress is added lazily when each player first enters. Existing character
saves and Season archives remain in place. No fresh account or database reset is
needed. For a fresh installation, use the main README and portable server guide.

## Validation

See [STORY_MODE_VALIDATION_V090.json](STORY_MODE_VALIDATION_V090.json) for the
exact automated results, asset verification and preview coverage. Source tests
and native headless rendering do not replace a Windows executable build or an
interactive hardware playtest. Build and smoke-test both applications on the
intended Windows machine before replacing the working installation.
