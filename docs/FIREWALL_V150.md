# Digimon Venom NXT v1.5.0 — FireWall

The FireWall update adds the supplied red-orange cyber-aura artwork as a complete
fourth Digimon variety. All 502 normal species have a FireWall counterpart, giving
2,008 catalog entries across Normal, Paradox, Shiny and FireWall.

## Finding and collecting FireWall Digimon

FireWall encounters are available across all 500 public maps: 254 Dawn maps,
150 World DS maps and 96 Super Xros maps. Each map uses FireWall counterparts
of its normal inhabitants, preserving the region's level and stage progression.

| Variety | Chance per eligible wild battle | Base scan per defeated Digimon |
|---|---:|---:|
| FireWall | **0.7%** | **5 percentage points** |
| Shiny | 1% | 5 percentage points |
| Paradox | 2.5% | 5 percentage points |

FireWall is the rarest variety. The roll follows the existing encounter system:
a successful rare roll replaces one opponent in the wild battle. Adding
FireWall does not reduce the Shiny or Paradox chance. Repeated battles remain
random; 0.7% is not a guarantee after a fixed number of encounters.

FireWall scan data belongs to its own species entry. Use the **FireWall** filter
in the DigiDex/DigiLab to find its scan progress, materialize it at the usual
threshold, manage your owned partners and plan evolutions. Evolution and
de-digivolution stay within the FireWall family, including saved evolution
history. Existing partner levels, ABI, CAM, moves and farm bonuses keep their
normal rules. FireWall partners can join your normal teams and core activities.

The supplied PNGs are preserved. Their aura padding is accounted for when
drawing battle sprites, walking partners, portraits and farm residents so the
body remains correctly scaled and aligned.

## Dawn Relay's permanent completion reward

Win Dawn Relay's championship for the first time to earn permanent **FireWall
Scan Mastery**. It increases scan earned from eligible FireWall wild victories
by 20%: **5 base points + 1 mastery point = 6 points**.

| Campaign completed | Permanent mastery | Normal scan → winning-battle total |
|---|---|---:|
| Dawn Relay | FireWall | 5% → **6%** |
| World DS: Paradox Chronicle | Paradox | 5% → **6%** |
| Super Xros: Ghostline | Shiny | 5% → **6%** |

Each reward applies only to its own variety and follows your character across
world regions and eligible private field training. They do not stack on one
another, increase encounter chances or award scans from NPC-owned opponents.
The existing scan cap remains 200%.

The base 5 scan points are earned when the wild Digimon is defeated. The extra
mastery point is awarded only if you win the battle; fleeing or losing does not
award the victory bonus. Pending bonuses survive a save/reconnect safely and
cannot be paid twice by replaying a request.

**Already completed Dawn Relay?** Your saved first championship victory grants
the reward automatically after upgrading and loading your character. This
includes a Dawn journey saved while another campaign is active, and former
champions who are currently reclaiming their title. No campaign reset or replay
is required. Normal title defenses and reclaim battles remain available;
losing the title never removes mastery. Repeat victories cannot stack it.

## Install or upgrade from v1.4.0

1. Download **every v1.5.0 Source Part ZIP** and extract them into the same
   parent folder, merging their `DigimonVenomNXT` directories. Every part is
   required; each is an ordinary ZIP archive.
2. Run **BUILD_ALL.bat** on Windows x64 with 64-bit Python 3.11 or newer.
   These downloads contain source and assets. Windows executables are built
   on your Windows machine.
3. Stop and back up your complete existing server installation.
4. Deploy **both** rebuilt v1.5.0 applications. Preserve `mysql/data`, private
   MySQL settings, credentials, TLS certificates and `config` files. Do not
   run fresh database setup for an existing installation.
5. Start the existing MySQL/world server, connect with the rebuilt client,
   and explore the world or resume Dawn Relay through **Story Mode / F4**.

No character, bot, inventory, scan or campaign reset is required. The three
private campaigns, 500 public maps, regional music, 3,000-rival maximum and
existing Normal/Paradox/Shiny assets remain in place. Keep configured server
installations outside the source tree's `dist` folder.

## Verification and release evidence

Run **VERIFY_FIREWALL.bat** for asset-integrity and FireWall integration checks.
Test dependencies are listed in `requirements-dev.txt`; the launcher prints
the installation command if they are missing.

Release reports and native client previews are under
`docs/validation/release_v150/`. Checks cover all species and maps, exact rarity
boundaries, scan/materialization/evolution, saved partner identity, Dawn mastery
and existing champions, other campaign rewards, multiplayer persistence,
supplied-art integrity and existing-system regressions.

Windows executable generation, native Windows setup dialogs, a production
MySQL connection and playback on the destination audio device remain checks
for the target machine.
