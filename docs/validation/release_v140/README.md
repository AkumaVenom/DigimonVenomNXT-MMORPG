# v1.4.0 Ghostline release evidence

This release adds the third private campaign to the confirmed v1.3.0 source
baseline. `release_summary.json` records the final suite result; `pytest.xml`
and `pytest.log` retain the complete test report.

The full run found one outdated simulated Windows-build fixture: it omitted
the v1.3.0/v1.4.0 evidence folders and still expected the old upgrade guide.
The fixture was corrected, and all three setup-launcher tests passed in
`setup_recheck.xml` / `setup_recheck.log`. The original report is retained
unchanged. The release summary counts unique passing tests after that recheck;
it does not count repeated setup tests twice. Two final dialogue-wording fixes
also passed the 13 content tests against the final content snapshot.

## Gameplay and persistence

The acceptance pilot begins with an established owned team, then uses normal
game commands for quest acceptance, collision-checked walking, tamer battles,
reports and portals. It does not insert completed quests, proofs or victories.
It completes all 31 maps, 30 assignments and 29 preliminary tamer battles,
loses the final battle deliberately, recovers and wins the retry. All 30
forward portals and the final return-to-hub uplink are used.

SQLite checkpoints reload the same character into a fresh game engine during
battle, before and after the revelation, and after completion. Checks cover
owned partner identity, ordinary battle rewards, all three independent saved
campaigns, DigiLab and DigiFarm visits, and free recovery. A separate early
fight verifies that an ordinary low-level team can lose and retry without
gaining evidence from the loss.

The nemesis is absent on every one of the 31 maps after completion and reload.
Stale dialogue, battle and portal requests cannot repeat the finale or reward.
A fresh account using the same engine retains its own ally and unopened case.

## Private multiplayer and scan rewards

Real WebSocket clients and a SQLite server verify per-account campaign
isolation, private chat, public-player/bot exclusion and restart persistence.
Forged progress fields, remote portal use and locked routes are rejected.

An eligible wild Shiny victory after earned completion grants 5 base scan
points plus 1 mastery point. Coverage also checks defeat/flee exclusions,
NPC-owned Digimon, fractional scan rates, the 200% cap, independent Paradox
mastery, pending battle rewards and reconnect/replay behavior. Private field
training uses the same eligible wild-victory rule. Encounter odds are unchanged.

## Content and native presentation

`layout/collision_report.json` checks every staged position against existing
walkability data. Its 31 map renders and four contact sheets show the supplied
artwork, unmodified spawns and connected routes. Actual content positions are
also checked for slot membership and overlap.

`ui/` contains native Pygame previews at 960×600 and 1280×800, with an accompanying
manifest identifying staged preview progress. Previewing later plot states
does not modify a production save. UI checks include the three-campaign chooser,
all 31 atlas entries, evidence paging, spoiler concealment, long-dialogue
pagination, the final battle, the secure epilogue and the completed hub.
Field and battle music use the existing Super Xros audio assets.

## Baseline and build integrity

`baseline_preservation.json` compares the existing Dawn and World DS campaign
definitions and catalog records. `v130_retention.json` records the comparison
of species, tamers, maps, audio metadata and original asset bytes against
v1.3.0, plus an actual first-chapter state-change audit.

`build_verify.log` records SHA-256 verification of the shipped asset manifest.
The split release archives are checked for CRC errors, duplicate or missing
members, manifest integrity and byte-for-byte agreement with the final source.

This environment runs Linux. Windows executable generation, native Windows
setup dialogs, a live production MySQL server and playback on the destination
audio device remain target-host checks. Use `BUILD_ALL.bat` on Windows to build
both applications, and preserve the existing server database and configuration.
