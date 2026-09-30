# Digimon Venom NXT v1.3.0 — Super Xros Wars

Super Xros Wars adds 96 distinct playable world maps across 14 zones, with a
level 1–99 route and 20 supplied music recordings. Open **Worlds**, select
**Super Xros Wars**, and choose a field suited to your party. All three regions
share your existing partners, scans, inventory and progress.

The complete world now has **500 maps**: 254 Dawn, 150 World DS and 96 Super
Xros Wars. You can travel between them using the same world controls. The new
region uses shared world exploration and wild battles; the two existing private
story campaigns keep their own progress.

## Partners and progression

The new region gives every one of the 502 normal Digimon a habitat. Early
fields contain Fresh, In-Training and Rookie partners. Champion, Armor and
Hybrid encounters enter the middle route, followed by Ultimate, Mega and
Ultra encounters as the levels rise. Species placement is deterministic, so
restarting the server does not shuffle habitats.

All 502 Shiny and 502 Paradox counterparts are available in the same new
habitats as their normal forms. The v1.2.0 rules remain:

- **1% Shiny chance per wild battle**, with **+5 scan percentage points** for
  each defeated Shiny. Its own 100% scan record materializes that Shiny.
- **2.5% Paradox chance per wild battle**, with the existing Paradox scan and
  mastery rules. The updated Cyber Paradox artwork remains installed.
- A battle can receive at most one rare replacement. Scans and ownership stay
  separate for each variety, and evolution preserves the variety.

Existing Dawn and World DS habitats and all species identities are preserved.

## Music and map assets

The supplied archive contains 196 numbered map exports. The release includes
the 96 distinct playable adventure fields. Empty images, incomplete water-only
exports, duplicate fields, farm/service rooms and fixed cutscene backdrops are
documented in `data/xros_maps.json` instead of presented as broken wild maps.
Location names, level progression and soundtrack assignments are authored for
Venom NXT; the source map numbers remain recorded.

The archive provides 20 music recordings, all integrated into the regional
soundtrack. Exact available intro/loop metadata is preserved. Exploration music
changes with the selected field, battles use regional music, and leaving battle
returns to that field's soundtrack. Existing volume and mute controls apply.
The supplied music README lists additional tracks that are absent from the
upload; those are recorded as unavailable rather than referenced by the game.

## Persistent tamer rivals

The existing maximum of 3,000 rivals now targets six residents per map across
the 500-map world. Coverage reservations count rivals already travelling, so
several rivals do not all select the same underpopulated field. Coverage also
respects team strength: a new or underlevelled rival is not forced into a fight
it cannot handle.

Rivals use their existing gameplay routines on the new maps, including patrols,
wild battles, earned scans, materialization, training, evolution, shopping and
cross-region travel. Their private-mode and ranked activities remain available.
Existing saved rivals rebalance through normal travel; their progress and
ongoing battles are retained. Occupancy changes while rivals travel or perform
activities, so six per map is a balancing target, not a frozen display count.

## Install or upgrade

1. Download **every v1.3.0 Source Part ZIP**. Extract all parts into the same
   parent folder and merge their `DigimonVenomNXT` directories. They are normal
   ZIP archives containing different files, and all parts are required.
2. On Windows x64, run **BUILD_ALL.bat** with 64-bit Python 3.11 or newer. This
   source package does not contain newly built Windows client/server executables.
3. Stop the existing server cleanly and back up its complete installation.
4. Deploy **both** rebuilt v1.3.0 client and server. Keep the existing
   `mysql/data`, private MySQL settings, credentials, TLS certificates and
   `config` files. Do not run fresh database setup for this upgrade.
5. Start MySQL and the world server with the existing launchers. Connect using
   the rebuilt client and open **Worlds → Super Xros Wars**.

Keep live server installations outside the source tree's `dist` folder. The
builder refuses to overwrite a configured server there. No account reset,
species-ID migration or rival reset is required.

For a new installation only, follow `PORTABLE_SERVER_README.md`. For historical
variety details, see `docs/VARIETIES_V120.md`.

## Verification

Run **VERIFY_SUPER_XROS_WARS.bat** to verify all shipped asset checksums and the
new-region acceptance tests using the source environment. The tests require
`requirements-dev.txt`; the verifier prints the install command if those
dependencies are missing. Run
**VERIFY_VARIETIES.bat** to check the retained Shiny and Paradox art.

**Release validation: 2,978 tests passed, 10 host-specific checks skipped,
zero failures.** All 31,739 asset/data checksum records passed verification.

Release test results and native client previews are recorded under
`docs/validation/release_v130/`. Windows executable builds, interactive Windows
audio-device playback and a production MySQL deployment must be checked on the
target Windows host; they cannot be certified by this Linux source validation.
