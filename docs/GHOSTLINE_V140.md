# Digimon Venom NXT v1.4.0 — Super Xros: Ghostline

**Ghostline** is the third private Story campaign. Open **Story Mode / F4** and
choose **Super Xros: Ghostline** to start or resume your own investigation.
Your existing Dawn Relay and Paradox Chronicle progress remain separate.

## Your investigation

The campaign uses **31 distinct Super Xros maps**: a safe service hub on map 1,
then thirty quest fields on maps 2–31. Most locations use cyber, mechanical and
science-fiction scenery. Story difficulty is authored independently of the
same maps' public-world encounter levels.

Follow an original cyber-hacking mystery through compromised tamer networks,
forged evidence and an increasingly personal hunt for the hacker behind them.
Meet recurring contacts, question local tamers and return to your intel broker
as the investigation develops. Future case details stay concealed until the
corresponding stage opens.

Each field has an assignment, an authored NPC tamer challenge and a report to
complete. Accept the assignment, win the marked battle, then return with the
evidence. Securing the field opens its forward portal. The final confrontation
takes place on **map 31**. After the finale, the defeated nemesis is permanently
absent from your campaign, including the hub; the finale cannot be replayed for
additional rewards.

The campaign tells an original Venom NXT cyber-detective story. The optional
design document contains major plot spoilers and is intended for maintainers.

## Your real partners and systems

Enter with your current owned partners at their real levels, stats and ABI.
There is no replacement story team and no entry-level normalization. Their UIDs,
evolutions, moves, farm bonuses, storage, inventory and earned progression
remain attached to your character.

Use the same DigiLab, DigiFarm, shop, healing, party management and combat
controls as elsewhere. The starting hub has service NPCs and no battles.
Field practice and free recovery help you prepare for later encounters. Quest
tamers and the final boss are NPC opponents, not the MMO's roaming bots, and
their owned Digimon do not award wild scan data.

Save & Return to World preserves your campaign location and completed cases.
You can revisit unlocked fields, leave for ordinary world activities and resume
later. Other players' campaign progress cannot change your quest tamers,
dialogue, portals or completion state.

## Permanent Shiny Scan Mastery

Completing Ghostline grants a permanent **20% increase to Shiny scan gain on
winning eligible wild battles**, following Paradox Chronicle's reward rule.

| Situation | Shiny scan gained |
|---|---:|
| Defeat a Shiny without mastery | 5 percentage points |
| Defeat a Shiny and win the battle with mastery | 5 base + 1 bonus = **6 points** |
| Defeat a Shiny, then flee or lose | 5 base points; no victory bonus |
| Defeat an NPC's owned Shiny | No wild scan data |

The bonus is a multiplier, not an additional twenty scan percentage points.
It does not change the **1% Shiny encounter chance**. It follows your character
outside the campaign, remains after reconnecting, and cannot stack through
repeat claims. Shiny and Paradox mastery affect their own varieties
independently. The existing scan cap is 200%.

## Install or upgrade from v1.3.0

1. Download **every v1.4.0 Source Part ZIP** and extract them into the same
   parent folder, merging the `DigimonVenomNXT` directories. All parts are
   required and each is an ordinary ZIP archive.
2. Run **BUILD_ALL.bat** on Windows x64 with 64-bit Python 3.11 or newer. The
   download contains source and assets, not newly built Windows executables.
3. Stop and back up your complete existing server installation.
4. Deploy **both** rebuilt v1.4.0 applications. Preserve your existing
   `mysql/data`, private MySQL settings, credentials, TLS certificates and
   `config` files. Do not run fresh database setup for this update.
5. Start your existing MySQL/world server and connect with the rebuilt client.
   Open **Story Mode / F4 → Super Xros: Ghostline**.

No character, rival, previous-campaign or inventory reset is required. The
existing 500 public maps, 3,000-rival maximum and all v1.3.0 assets are retained.
Keep configured server installations outside the source tree's `dist` folder.

## Verification

Use **VERIFY_GHOSTLINE.bat** for shipped asset checks and campaign acceptance
tests. Test dependencies are listed in `requirements-dev.txt`; the launcher
prints an installation command if they are missing. Release evidence and
native client previews are under `docs/validation/release_v140/`.

The automated checks cover real quest battles and portal progression, private
player isolation, save/reconnect behavior, old campaigns, the one-time reward
and permanent nemesis removal. Windows executable builds and interactive
playback on the target Windows audio device remain target-host checks.
