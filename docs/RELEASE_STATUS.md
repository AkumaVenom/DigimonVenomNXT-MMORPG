# Release status — Digimon Venom NXT v1.2.0

The current release adds 502 Shiny varieties and replaces all 502 Paradox
art sets. Shiny scan-capture encounters have a 1% chance in both world-map
sets and give 5% scan per defeated Shiny. Variety-specific collection, scan
conversion, evolution, storage and persistence are integrated.

Use [VARIETIES_V120.md](VARIETIES_V120.md) for current upgrade instructions.
Build and deploy both applications; retain the database, credentials and config.
This is a source release. Native Windows builds and production playtests remain
host-side checks. Current automated and visual validation is recorded in
[validation/release_v120](validation/release_v120/README.md).

The release notes and counts below are historical evidence for prior versions.

## Historical v1.0.1

This source release adds **ABI DigiMeat**, a regular-shop item costing **6,000
credits or 30 DigiRubies**. Each owned item adds **+1 permanent ABI**, capped at
200, without resetting level or consuming the farm training-bonus allowance.
A selected party partner can use it at the DigiLab or DigiFarm, and stored
residents can be fed at the farm. Partners without a de-digivolution can now
raise ABI independently of evolution cycling, including a sole party member.
Level, CAM and stat requirements for each evolution still apply.

Read [ABI_DIGIMEAT_V101.md](ABI_DIGIMEAT_V101.md) for current instructions. Use
`BUILD_ALL.bat` and deploy **both rebuilt Windows applications**, including when
upgrading from v1.0.0. The server defines the item and validates consumption.
Preserve the complete stopped server's saved database, credentials and private
configuration. No fresh setup, database reset or progress deletion is required.

Current development evidence is recorded in
[validation/release_v101](validation/release_v101/README.md). The complete suite
finished with **938 passed and 10 skipped** in **236.43 seconds**, with no
failures or errors. The skips are one opt-in live-MySQL check and nine graphical
setup-wizard checks. Twelve native ABI interface captures cover 960×600 and
2047×1155, with no actions outside the displays. Native Windows
building and a playtest on the intended host are separate checks; this source
release does not claim those checks were performed here.

## Retained v1.0.0 battle presentation

The corrected cyber-blue arena and padded target cards retain full wrapped
names, metadata, sprites and HP bars. The selection outline and click area
stay anchored during attack movement. Normal and Paradox Fanglongmon keep
the supplied animation frames, stable species IDs and saved progression.
Both story campaigns, DigiLab, DigiFarm, DigiRuby economy, Season careers,
Ranked Arena, 3,000 persistent rivals, 12-hour activity retention and the prior
startup/network improvements remain part of the baseline.

The v1.0.0 complete suite recorded **873 passed and 10 skipped** in **240.66
seconds**. Its original visual and test evidence is retained in
[validation/release_v100](validation/release_v100/README.md), with the original
[release guide](RELEASE_V100.md) and [Fanglongmon guide](FANGLONGMON_V100.md).
These are historical results, not the v1.0.1 test count. The asset manifest
retains 21,820 records.

Earlier results below retain their original versions and measurement scope.

## Retained Rival Population v0.12.3

The live rival population is now **3,000 by default and at most**. Existing
configuration values above 3,000 are capped without requiring manual edits.
The extra rivals are removed through the startup migration; retained rivals
and human players keep their earned progress. The 12-hour activity retention
and startup loading without an overall deadline remain active. Negotiated
WebSocket compression reduces repeated map-update payloads without removing
actors or lowering the update rate.

Read [POPULATION_V0123.md](POPULATION_V0123.md) for that migration and its
original upgrade. That server-only update supported existing v0.12.2 clients,
which already offered WebSocket compression. For the current v1.0.1 release,
follow the guide above and deploy both rebuilt applications, preserving the
stopped server's saved database and private configuration. Native Windows
building and a target-host playtest are separate from development checks.

The complete automated suite passed with **818 passed, 10 skipped** in
228.94 seconds. The skips are one opt-in live-MySQL check and nine graphical
setup-wizard checks. Saved-fleet regressions verify exactly 5,000 → 3,000
persistent rivals, retained earned state/human history, repeat-safe migration,
disabled startup, stale-owner rejection and interrupted cleanup across a
season boundary. Native-client negotiation tests preserve complete decoded
snapshots and support uncompressed fallback.

The isolated moving-map benchmark measured 100 rivals plus one player at
**315,255 → 56,846 WebSocket bytes/second** and 160 rivals plus one player at
**502,677 → 88,684 bytes/second** with compression. These are Linux development
measurements of complete 10 Hz snapshots, excluding TLS/TCP/IP overhead and
other traffic, not a bandwidth guarantee for the user's host.

The v0.12.3 validation evidence is in
[validation/population_v0123](validation/population_v0123/README.md).
Historical release measurements below retain their original populations and
versions; they are not measurements of the current release.

## Retained Bot Activity v0.12.2

Global Bot Activity counters now cover the latest 12 hours. The feed retains
at most the latest 100 events inside that window. Compact minute totals and
expired activity receipt rows are cleaned up automatically at startup and
regularly while the server runs. Displayed results exclude expired activity.
The oldest partial minute of counters can expire less than one minute early so
the display does not include events older than 12 hours.

Old global lifetime totals had no timestamps and are not imported into the new
window. Global tracking begins with this upgrade. Small per-rival lifetime
career counters remain because they support individual records and training.
Earned partners, XP, scans, inventories, wallets, stories, Season progress and
ranked rewards are retained. Ranked outcome records remain available for
career and reward integrity.

The old counter integers themselves were small; the activity receipt table
was a source of unbounded activity metadata growth. Retention now bounds that
metadata. This does not promise that all database storage stops growing, and
MySQL may reuse freed pages without shrinking its files on disk.

The complete automated suite passed: **799 passed, 10 skipped** in 224.55
seconds. One opt-in live-MySQL check and nine graphical setup-wizard checks
were skipped. The [validation evidence](validation/activity_v0122/README.md)
includes the full log and XML results.

A 28-day simulated persistence check submitted **40,320 minute batches** using
all 27 counters, including fractional walking distance. The shared global
history remained bounded at **720 minute buckets** and **100 feed events**.
Retained counter JSON was **318,960 bytes** at days 1, 7 and 28, excluding SQL
overhead and other game data. Receipt counts depend on save frequency within
the retained 12 hours; they do not have a fixed 720-row cap. See the
[retention report](validation/activity_v0122/RETENTION_VALIDATION.md) and
[UI preview index](validation/activity_v0122/README.md).

The v0.12.1 restart repair remains in place: no overall startup deadline,
continuous ownership renewal during loading, batched saved-rival restoration
and visible progress. Read [BOT_ACTIVITY_V0122.md](BOT_ACTIVITY_V0122.md) for
the original activity upgrade and [the validation evidence](validation/activity_v0122/README.md)
for source checks. Rebuild and deploy **both Windows applications** with
`BUILD_ALL.bat`; preserve the existing database and private configuration.
This is a source release. Native Windows builds and target-machine playtests
remain separate checks.

## Retained persistent-rival restart repair v0.12.1

Saved-world loading has no overall deadline. The server renews its population
ownership throughout startup, restores saved rivals in bounded batches without
duplicating the full fleet in memory, and logs restoration progress. Startup
database reads and one-time history indexes can finish without the normal live
gameplay socket timeout. Ranked history, rewards and player saves are retained.

The complete automated suite passed: **785 passed, 10 skipped**. This includes
18 new restart, saved-progress, lease-ownership and startup-I/O regressions.
The full log and XML results are included in the validation evidence folder.

The v0.12.0 lease-expiry failure was reproduced using its archived source and a
durable saved population with a simulated long restore. Recovery and ownership
tests exercise the repaired path and still reject a stale server after another
server takes ownership. The affected installation's final traceback was not
provided, so its exact error remains unverified.

A Linux/SQLite before/after benchmark restored 5,000 grown rivals containing
30,000 party Digimon, 240,000 stored Digimon and 2,500 unfinished battles.
Community initialization measured **19.072 seconds → 8.216 seconds**; peak
process resident memory measured **1,821.9 MiB → 1,184.1 MiB**. The exact
saved-progress hash matched, the human fixture's 391 DigiRubies and 76,543
credits were retained, and loading performed zero offline simulation actions.
These single-run development measurements are not Windows/MySQL timings or a
performance guarantee. See [the benchmark evidence](validation/restart_v0121/README.md)
for original JSON results and measurement scope.

Read [RESTART_REPAIR_V0121.md](RESTART_REPAIR_V0121.md) for the original source
repair. The v0.12.1 server hotfix remained compatible with v0.12.0 clients.
For the current upgrade, follow the v1.0.1 guide above and deploy both rebuilt
applications while preserving the database and configuration.

## Retained DigiRuby Economy v0.12.0

All 19 shop items now offer credit and DigiRuby payment. Prices are shown before
purchase. A new **DigiRuby Exchange** tab in Ranked Arena converts earned
DigiRubies to ordinary credits at **100 credits per DigiRuby**. Shop ruby prices
are one DigiRuby per 200 credits of item value, rounded upward, with a minimum
of one. The complete price table and limits are documented in
[DIGIRUBY_ECONOMY_V0120.md](DIGIRUBY_ECONOMY_V0120.md).

The redundant Struggle action has been removed; the existing basic Attack
continues to cost zero SP. Existing wallets, inventories, partners, story saves,
Season careers and ranked records are preserved. Economy transactions validate
the balance and capacity on the server before committing the payment and grant.

The original v0.12.0 feature upgrade from v0.11.0 required rebuilding both
Windows x64 applications; its historical upgrade instructions are in the
DigiRuby guide. For the current update, follow the v1.0.1 guide above.
Preserve `mysql/data`, private database settings and all existing `config`
files; do not run fresh database setup. Native Windows builds and
target-machine playtests remain separate release checks.

## Retained Paradox Chronicle v0.11.0

The v0.11.0 source release added **World DS: Paradox Chronicle** as a second private
Story Mode campaign: 18 supplied DS maps, a peaceful service hub, 17 authored
quest and tamer sequences, 17 Paradox guardians and collectible Paradox Crests,
then a final team of three level-100 Paradox Megas. A first final victory grants
a permanent 20% increase to wild Paradox victory scan, from 5% to 6%, subject to
the existing 200% cap. Repeated clears do not multiply the benefit.

Campaign choice appears under **Story Mode / F4**. Dawn Relay progress and
championship records remain separate. Characters keep their existing partners,
inventory, credits and services. New story tamers use authored NPC teams and
private progression, independently of the shared AI rival population.

Read [WORLD_DS_STORY_V0110.md](WORLD_DS_STORY_V0110.md) for player guidance and
its historical upgrade from v0.10.0. Rebuild and update **both Windows x64
applications**. Preserve the stopped server's `mysql/data`, private MySQL
configuration and complete `config` folder; do not run fresh database setup.
This document makes no claim of a completed Windows native build or target-PC
playtest. Source validation and target-machine release checks are separate.

## Retained World DS region v0.10.0

The v0.10.0 release added the supplied World DS field maps and music as a shared
MMO region beside Dawn. Existing characters, wild battle/scan systems and saved
AI tamers continue across both regions. Story Mode, Season Mode and all prior
activities remain. The v0.10.0 NPC character archive was unused. Read
[WORLD_DS_V0100.md](WORLD_DS_V0100.md) for shared-region behavior and historical upgrade steps and
[WORLD_DS_VALIDATION_V0100.json](WORLD_DS_VALIDATION_V0100.json) for validation.
Rebuild and update both Windows applications together; preserve existing saves.

## Retained Story Mode v0.9.0

The v0.9.0 release added **Dawn Relay**, a private story journey that uses the
player's existing partners, items, credits, DigiLab and DigiFarm. It contains
18 supplied Dawn maps, 54 authored NPC placements, eight DigiBadges, live tamer
battles and a repeatable championship defense/reclaim cycle. NPC opponents reach
level 100; the existing owned-partner level cap remains 99.

Story progress and instances are private. Partner growth and rewards remain on
the ordinary character. Season careers, Ranked Arena, shared rivals and the
host-only local administration console remain available. Read
[STORY_MODE_V090.md](STORY_MODE_V090.md) for behavior and its historical upgrade
procedure; rebuild both Windows applications together. See
[STORY_MODE_VALIDATION_V090.json](STORY_MODE_VALIDATION_V090.json) for the checks
actually run. Windows executable building and an interactive target-machine
playtest remain required before deploying this source update.

The notes below describe retained features and historical release boundaries.

## Retained DigiFarm v0.6.0

The v0.6.0 release adds the player's private DigiFarm to the accepted UI2,
FPS1 and portable-MySQL baseline. Each account has its own home, up to 100
stored resident Digimon, optional feeding, a server-owned training economy,
and a dedicated original music loop. New accounts begin at home; existing
accounts retain their saved location and progress. See [DIGIFARM_V060.md](DIGIFARM_V060.md)
for exact limits, item prices, battle rewards and migration instructions.

**Both client and server must be rebuilt on Windows x64 and upgraded together.**
This is a source release; the Linux validation environment cannot build or
execute the Windows applications. Existing portable MySQL saves and credentials
are preserved. The new save fields are additive and require no database reset
or schema replacement. Historical UI2 instructions to update only the client
are superseded by the v0.6.0 guide.

For a **new installation only**, follow [SETUP.md](SETUP.md). The bundled MySQL
8.4.11 runs from `mysql/runtime`, with production saves under `mysql/data`.
Follow [../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md) for startup,
clean shutdown and complete-folder backups.

## Retained rival and portable-server systems

The walking interval starts when a rival's exploration job actually runs, so
startup or database delays cannot consume the interval before its first step.
Validated patrol paths continue looping between scheduled jobs, and snapshots
carry the same authoritative position and direction to all players. Arrival
spacing applies only when a rival actually changes maps; it does not teleport
walkers around their current sector to separate them. Wild battles and other
activities still have normal stationary periods.

Rivals retain training teams across activity cycles, bank experienced partners
through ordinary DigiLab party operations, and select eligible younger owned
partners for later rounds. The Lab selects and stores partners before checking
evolution, and a rival's only established partner is retained until earned scan
data can materialize another. Materialization still requires at least 100% earned
scan data. Evolution and de-evolution follow the existing eligibility rules and
retain the partner's identity. This update does not award invented XP, clear
collections or reset trained Digimon to manufacture new teams. Ranked battles,
healing, shopping and friendly challenges continue through their existing rules.

Travel considers quieter safe maps below a team's strength, rather than forcing
mature parties into a narrow high-level band. Banked veterans can make short
visits to underfilled higher-level sectors. Pending arrivals reserve space so
several rivals do not all claim the same apparent gap. These visits have a
bounded duration, followed by a protected stretch of ordinary team training;
other capable rivals can take later assignments. Experienced teams are not
permanently held in high-level sectors. This balances population opportunities
across level ranges; it is not a guarantee of identical visible headcounts on
every map at every instant. Residents can be
in battle, the DigiLab or travelling, and smaller configured populations cannot
occupy every map. Saved rivals adopt team selection during their normal Lab
visits instead of being replaced at startup.

## Fresh portable database setup

**01_SETUP_SERVER.bat** opens the native wizard. It prepares this folder's MySQL
process, generates private credentials, creates the fresh game database, and
configures local or public TLS connections. A failed step remains visible and can
be retried; sanitized diagnostics are stored in `logs/setup-latest.json`. No
existing administrator password, game login or player account is needed.

The database listens only at `127.0.0.1:3307`. Readiness checks authenticate and
verify that its data directory belongs to this server folder. The world launcher
starts or verifies MySQL before launching the game server. **STOP_SERVER.bat**
requests final world saves, waits for the world process and shuts MySQL down
cleanly. After successful shutdown, manually ZIP the complete server folder.
Keep both processes stopped until compression finishes.

The Windows MySQL engine and complete game content are included in this source
package. Build the application executables on Windows x64 first. A built server
needs the Microsoft Visual C++ x64 runtime, but no separate Python or MySQL
installation. Use the prerequisite helper only if that runtime is missing.
The engine's provenance records are in `mysql/provenance`.

This is a playable source release for a native desktop multiplayer RPG, with a Windows build pipeline. It is not a claim that every requested system has reached finished-MMO quality or exact Cyber Sleuth parity.

The v0.2.0 roaming rivals, ranked seasons and community screens remain, along
with the v0.1.1 display improvements and later movement/training fixes. This
release's fresh setup replaces the earlier external-database workflow; historical
feature guides do not provide a database migration procedure for it.

| Area | Delivered | Boundary |
|---|---|---|
| Native client | Native-resolution SDL desktop rendering, Windows DPI awareness, borderless fullscreen, saved UI/frame/audio preferences, continuous movement/camera, animated tamers and follower, account/party/collection/shop/world/lab/battle screens | Client and world-server EXEs must be generated with the supplied builder on Windows; the bundled MySQL engine alone does not make this source package a ready-to-run game server |
| Display/camera | Native-size text and shapes; nearest-neighbor artwork; whole-level 1× through close-up 8×; independent UI scale, fullscreen restoration and selectable frame caps | Fullscreen uses the current desktop resolution. Original artwork detail is unchanged. Fractional map-fit scales can sample source pixels unevenly; uniform pixel replication requires integer enlargement. No guaranteed hardware frame rate or Windows DPI acceptance result is claimed |
| Dedicated server | Authoritative WebSocket world, accounts, collision, battles and durable actions; shared players and chat | A single world process; no proven production human-connection capacity, clustering or operator dashboard |
| Tamer rivals | Default and maximum population of 3,000 persistent AI tamers, even initial map distribution, continuous collision-aware patrols, shared positions, spaced sector arrivals, clickable profiles, wild combat, earned XP/scan, materialization, persistent training teams, veteran storage, evolution, shop use, ranked participation and density-aware travel | Fresh rivals receive a clearly identified sector-appropriate seed level. Collection/evolution require eligibility and ranked attacks require energy. Existing partners retain their identities and earned progression; legal evolution can change levels under normal game rules. Population balancing does not promise equal visible occupancy. No simulated offline training while the world server is stopped |
| Population performance | Worker-driven scheduler, bounded work batches, map-local snapshots and shared navigation data; rivals do not open 3,000 player sockets | A configured population size is not a certified capacity for 3,000 human connections. Hardware, network and database performance must be measured on the target Windows host; see validation evidence for tests actually run |
| Battle Park | Asynchronous automatic battles using restored party snapshots, three active partners plus up to three reserves, weekly seasons, points, promotion battles, career rating, top-100 current/career/archive ladders and automatic DigiRuby rewards | ReArise-inspired structure with documented NXT numerical rules and SP combat, not verified exact ReArise parity. Earned DigiRubies can buy every shop item or convert to credits at the published rate. No real-time human-versus-human command exchange |
| Rivals Hub/activity | Nearby invitations, accept/decline, friendly challenges, head-to-head totals, bot directory, cumulative activity counters, latest 100 events and sector distribution | Global event detail is deliberately bounded to 100 recent events; cumulative totals remain. Head-to-head data persists, with the 100 most recent opponents exposed by the hub. Bots are explicitly identified as AI |
| Persistence | Bundled folder-owned MySQL 8.4.11, fresh native setup, authenticated readiness and data-directory checks, local game login, exact-database grants, transactional saves, password hashing, session leases and revisions; coordinated world/database shutdown for manual whole-folder backups | Physical portability requires a clean shutdown, the complete folder and the same engine on a compatible Windows x64 host. Native Windows execution and production performance remain target-host checks |
| Public hosting | CA-signed SAN server certificate, bundled client CA trust, hostname validation, private-key exclusion from public kit | Administrator supplies a reachable hostname/IP and network forwarding; hosting setup does not alter ISP/router/DNS |
| Maps | All 351 supplied PNG layers, composed into 254 playable map destinations at supplied x2 resolution; original per-pixel collision | Sector numbers are source IDs, not a restored named story world; travel menu replaces authored story/portal progression |
| Tamers | 64 original human appearances, eight directions, four movement frames per direction with ROM timing/flip metadata | Some appearances use descriptive/source-index labels; no complete story NPC behavior |
| Digimon artwork | All 16,028 supplied PNGs preserved; 1,004 normal/Paradox playable records | Automatic selection of battle poses is not hand-authored animation metadata for every form; sparse forms reuse supplied idle art |
| Battle visuals | Attack motion, hit reactions, fading damage and effectiveness, procedural particles and 96 decoded original effect sequences | 121 ambiguous compound ROM effect groups require further decoding; authentic exported pixels use approximate timing |
| Sound | All 46 music sequences and 183 effect sequences rendered from the actual ROM samples, with 703 sample exports | Envelopes/modulation are approximations, music loops have render/fade boundaries, and two undefined drum-note references in bgm00 are reported |
| Combat/collection | Speed turns, up to three active partners vs one to three enemies, six-member party, storage, scan/materialize, original move costs, free attacks, type/attribute modifiers, levels/ABI/CAM, evolution/devolution | Stats, growth, generic move lists and many routes are original balance, not a verified complete Cyber Sleuth dataset |
| Paradox | Separate artwork/scan records; 2.5% chance per encounter to contain a variant; 5% scan per defeat | Custom variants have custom balance; collecting them is deliberately substantially slower |
| Recovery/shop | Lab recovery and field return, six HP/SP capsule sizes, Friendship DigiMeat and +1 / +5 training meat for six stats | Feeding is optional and available for stored DigiFarm residents; permanent training caps are documented in DIGIFARM_V060.md |
| DigiFarm | Private home, supplied island artwork, up to 100 stored residents, gentle wandering, click-to-manage feeding, original music, optional CAM and permanent training meat | Active party slots are separate from storage; no hunger, offline farming or automated stat gain. Legacy over-cap saves are retained; withdrawals and capacity-neutral party swaps remain available |
| Other systems | Shared-world multiplayer foundation with persistent rival population and ranked seasons | Full Cyber Sleuth story, personalities, all statuses/support/moves, exact canonical evolution requirements and other advanced content remain unfinished |

## Validation interpretation

Automated gameplay, catalog, persistence, networking, setup/TLS, extraction and native rendering checks are shipped. Real local WSS tests use the actual imported catalog and two accounts. They verify the connection-kit trust path, wrong-certificate/hostname rejection, movement, collisions, scan rewards, lab/shop flow and saved relogin. Rival/ranked checks cover real battle outcomes, scheduled progression, persistence, season changes and reward delivery. See `VALIDATION.md` for the retained historical gameplay checks and results; no test count is implied by this feature table. See [PORTABLE_MYSQL_VALIDATION.md](PORTABLE_MYSQL_VALIDATION.md) for the new database checks actually run and [PORTABLE_MYSQL.md](PORTABLE_MYSQL.md) for its implementation boundary. Linux checks are not a substitute for a native Windows build and execution check with the bundled engine.

The content verifier checks SHA-256 and size for every runtime asset and gameplay metadata file, and checks catalog references before building. It detects corruption; it cannot certify that every source artwork component or provisional balance value matches the original games' intended semantics.
