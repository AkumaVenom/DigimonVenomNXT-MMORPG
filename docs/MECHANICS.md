# Digimon Venom NXT — gameplay rules and data provenance

This game implements an original, server-authoritative Digimon collection RPG inside a shared multiplayer world. It is inspired by Cyber Sleuth's collection and party combat concepts. **It does not contain a verified complete Cyber Sleuth stat, move, support-skill, personality, evolution-requirement or progression database.** The supplied v7 pack contains artwork and stage folders; the Dawn ROM and maps are from a different game. They cannot establish Cyber Sleuth statistics for every imported species, particularly the custom Paradox variants.

All 1,004 imported normal and Paradox species are playable. Their sprite identity and stage come from the supplied pack. Their numerical base stats are deterministic original balance generated during import. The runtime applies hand-curated type/attribute choices for familiar species; other entries use explicitly provisional deterministic assignments. These choices are not represented as officially verified values. `data/mechanics.json` records overrides, family routes and the provenance statement; the catalog marks provisional records. Do not describe this release as a one-to-one recreation of every Cyber Sleuth system.

The official [Cyber Sleuth Complete Edition page](https://www.bandainamcoent.com/games/digimon-story-cyber-sleuth-complete-edition) documents collectible, raisable and digivolvable Digimon and turn-based party combat. It does not supply the complete numerical database required to certify exact parity. Exact imported statistics and canonical requirements need an independently verified, appropriately sourced dataset in a later content pass.

## Starting and exploring

Create a tamer from any of the imported tamer entries and choose one regular Rookie. Start at your private DigiFarm at level 1 with 650 credits, five Small HP Capsules, three Small SP Capsules and three Friendship DigiMeat. The first party member is the visible overworld follower. Party capacity is six, with the first three living slots forming the initial combat team. Reserve partners earn half XP. The game server owns movement, encounter and persistence rules; the client cannot supply HP, currency, damage, scan or rewards.

Every imported species has at least one assigned map encounter location. Maps expose their regular and Paradox pools in the runtime catalog. Pools are stable across restarts and matched to stage/progression: Rookie and baby stages near level 1, Champion near 15, Ultimate near 30, Mega near 45 and Ultra near 60. Map pools remain compact so repeated species can actually be scanned. All maps are available through travel; their displayed wild level warns of difficulty.

Manual Search and walking can start encounters. A solo tamer meets one, two or three enemies with weights 70/25/5; larger parties use 25/40/35. Wild levels follow the area's level with a ±2 variation, clamped to 1–99. Wild partners have 72% normal HP and deal 72% normal damage, an original onboarding balance adjustment.

## Scan and materialize

Scan data is awarded **on defeat**, as requested, rather than simply seeing an enemy. Regular species give 20%; Paradox species give 5%. Scan caps at 200%. Each defeated enemy awards once, and its scan data is retained even if the remaining enemies force a retreat or defeat.

The chance for an encounter to contain one Paradox is **2.5% per encounter**, not 2.5% independently per enemy slot. One slot is replaced by a variant from that area's eligible pool. Paradox species retain separate scan entries; normal scans cannot materialize them. Their evolution family retains the Paradox variant.

At the DigiFarm or DigiLab, 100% scan can materialize a level-1 partner. Materialization consumes the accumulated scan. Additional scan grants starting ABI: 120% grants 1, 140% grants 2, up to ABI 5 at 200%. A new partner joins the party if fewer than six members are present, otherwise DigiFarm storage. Farm capacity is 100 stored partners, separate from the six active party slots. Legacy collections above 100 are preserved without deletion; withdrawals remain available, but new deposits and materialization into full storage are blocked. A capacity-neutral party/storage exchange also works when both party and farm are full, including archived storage partners. The incoming party partner is restored; both retain their identity and progression, and counts stay unchanged. Deposit and withdraw work at the farm or lab; at least one partner must remain in the party.

## Types, attributes and damage

The type cycle is Vaccine → Virus → Data → Vaccine. Advantage multiplies damage by 2, disadvantage by 0.5; equal types and Free matchups use 1. Attributes are separate: Fire → Plant → Water → Fire; Electric → Wind → Earth → Electric; Light and Dark each beat the other. An attribute advantage grants 1.5×; other attribute matchups grant 1×. There is no invented 0.5× reverse elemental resistance. Both bonuses multiply, allowing 3× damage.

A basic Attack costs no SP and uses a neutral physical attack at full normal power, including when the partner has 0 SP. Every partner has two original moves: an elemental magic Burst costing `5 + stage rank` SP, and neutral physical Power Strike costing `4 + stage rank` SP. These are original generic moves, not claimed to be the creature's complete signature move list.

Damage uses the appropriate attacking stat (ATK physical; INT magic) against DEF or INT. Its original formula is:

`max(1, floor((8 + attack × 0.72 − defense × 0.28) × move_power × effectiveness × random(0.92, 1.08)))`

Wild damage then receives the balance adjustment above. Guard halves damage until the next action opportunity. With CAM at least 20 and a living active ally, an attack has `CAM / 500` chance to become a Cross Combo for 25% additional damage. Actual HP removed is used for floating damage numbers. Events identify attacker, defender, attribute, effectiveness, combo and defeat so the client can animate the correct combatants.

Battle actions include Attack, Skill, Item and Flee. The server also supports Guard and reserve Swap through the battle API. Swapping consumes the outgoing partner's action. Flee is guaranteed and gives no victory XP or credits. Recovery items consume the current actor's action in combat; using them through the out-of-battle operation during combat is rejected.

## Speed, XP, stats, ABI and CAM

Combat uses a persistent speed timeline, not alternating whole teams. Initial action time is `500 / SPD`; the next action is scheduled at current time plus `1000 / SPD`. Faster partners can act more often. Enemy turns automatically resolve until the next player decision. Reconnecting resumes the same battle queue.

Six battle stats are implemented: HP, SP, ATK, DEF, INT and SPD. Original per-level growth is stage-dependent: HP `18 + 2 × rank`, SP `2`, ATK/INT `3 + 0.3 × rank`, DEF `2.5 + 0.3 × rank`, SPD `2 + 0.2 × rank`. ABI adds `ABI / 1000` multiplicatively to these totals. Rank is 0 Fresh, 1 In-training, 2 Rookie, 3 Champion/Armor/Hybrid, 4 Ultimate, 5 Mega, 6 Ultra. The level cap is 99 and ABI cap 200.

XP needed for the next level is `35 + floor(12 × level^1.45)`. Victory awards XP from every defeated enemy: `24 + 12 × enemy level + 8 × enemy stage rank`; active partners receive full XP, reserves receive half. Level-up restores only newly gained HP/SP capacity; knocked-out partners stay knocked out. Victory also awards `25 + 7 × level` credits per enemy. CAM rises by 2 for active members and 1 for reserves, capped at 100.

Evolution requires the DigiFarm or DigiLab and checks the advertised level, ABI, CAM and stat thresholds on the server. Known family chains are curated routes with original balance requirements. Uncharted species have a stable, explicitly labelled **original data-splice route** into the next stage; these are not canon evolution claims. Paradox versions follow the corresponding Paradox target.

Evolution resets level to 1, preserves the individual UID and CAM, changes species/stats and increases ABI by `2 + floor(old level / 10)`. De-digivolution to a listed previous form requires level 5, resets level to 1, preserves identity/CAM, and grants `5 + floor(old level / 5)` ABI. De-digivolution only helps species with an available previous form. ABI DigiMeat provides an independent way to raise ABI when no backward route exists. The UI reads the server's `evolution_options`, including all unmet requirements and whether a route goes backwards.

**ABI DigiMeat** (`digimeat_abi`) costs **6,000 credits or 30 DigiRubies** in the regular shop and permanently adds **+1 ABI per owned item**, up to 200. Use it outside battle on a selected party partner at the DigiLab or DigiFarm, including the only party member, or feed a stored resident at the farm. It preserves level, XP, CAM, identity and permanent training bonuses; its ABI survives evolution and save/load. Normal ABI-based stats are recalculated immediately. It does not count toward the farm's +100-per-stat or +300-total training limits. At 200 ABI, or if the quantity would exceed that cap, the request is rejected without consuming items. All other evolution requirements still apply. See [ABI_DIGIMEAT_V101.md](ABI_DIGIMEAT_V101.md).

## DigiLab and shop

The DigiLab button outside battle instantly heals all party HP/SP and remembers map plus exact coordinates. Return places the tamer back at that point. Healing is free. Defeat also performs emergency lab recovery without taking currency, partners or collected scan data. Lab travel is blocked while battle is still active; Flee first if a safe retreat is needed.

| Capsule | Price | Restores |
| --- | ---: | ---: |
| Small HP | 60 | 250 HP |
| Medium HP | 180 | 650 HP |
| Large HP | 420 | 2,000 HP |
| Small SP | 90 | 25 SP |
| Medium SP | 260 | 65 SP |
| Large SP | 600 | 200 SP |

Purchases are available at the DigiFarm or DigiLab. Recovery is capped at the partner's maximum; full-resource use is rejected without consuming an item. Capsules cannot revive a defeated partner; the lab can. Purchase quantities must be integers 1–99, stocks cap at 999 each, and credit availability is checked before inventory changes.

## DigiFarm and optional feeding

Each account owns a private farm. The top-left Home button / F2 returns there;
confirming this action during a battle flees with no victory XP, credits or meat
reward. Scan already earned from defeated enemies is retained. The farm uses the
supplied island artwork and original music, and stored residents wander gently.
No hunger, deterioration or required feeding is implemented.

Friendship DigiMeat costs 150 credits and grants up to +5 CAM, capped at 100.
A PvE victory has an 18% chance to award one. Six training-meat families improve
HP, SP, ATK, DEF, INT or SPD: +1 costs 2,500 credits; rare +5 costs 25,000.
Permanent bonuses cap at +100 per stat and +300 combined per Digimon. These flat
bonuses are added after normal level/ABI stats, persist through level changes
and evolution, and participate in ranked snapshots. These CAM/stat treats require a stored
resident and an owned item and are checked on the server before consumption.
ABI DigiMeat can also be used directly on a party partner at the DigiLab or
DigiFarm, as described above.
See [DIGIFARM_V060.md](DIGIFARM_V060.md) for the complete item names and rules.

## Scope of this version

Implemented: shared-world movement, multiplayer presence, account persistence, species collection, wild turn-based battles, scan/materialize, party/bank, type/attribute effectiveness, HP/SP recovery, original stats/XP, ABI/CAM, evolution/devolution, shop, map travel, lab return, private DigiFarm and optional permanent training. Ranked battles, seasons and persistent AI tamers are documented in RIVALS_AND_RANKED.md. Administrative infrastructure lives in the server/setup documentation.

Not implemented as Cyber Sleuth parity: original story quests, complete signature/inherited move database, personality system, all statuses, support skills, DigiMemory, every canonical branch/jogress requirement, real-time command PvP, trading, raids or guilds. These require additional gameplay/content work. The runtime's generic animations and particles should likewise not be described as a full extraction of every original DS battle effect.

Run `python -m unittest tests.test_game -v` for the authoritative gameplay tests, including starter restrictions, all-species encounter coverage, speed turns, scan caps, zero-SP attacks, battle/lab boundaries, inventory exploits, materialization capacity, evolution stat gates, devolution identity, exact-coordinate recovery and defeat protection.
