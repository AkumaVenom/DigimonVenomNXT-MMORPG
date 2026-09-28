# Fanglongmon artwork — v1.0.0

Fanglongmon and Paradox Fanglongmon now use the twelve supplied transparent PNG
poses, six per form. This upgrades the two existing species in place: owned
partners, scan percentages, identities, levels, trained bonuses and evolution
history continue to use `fanglongmon` and `fanglongmon_paradox`.

## Animation and presentation

Each form has two alternating idle poses, a right-facing walk cycle, the supplied
left-facing walking pose, and the two-part attack sequence. Leftward movement
uses the authored left step, with mirrored idle frames between steps; it never
cycles between opposed directions. Battle, partner previews, follower sprites,
DigiFarm residents, wild enemies and rival teams use the same shared assets.

All twelve 1254 × 1254 RGBA images are copied byte for byte. Their transparent
canvases, colours, authored glow, frame order and common registration are retained.
The existing nearest-neighbour renderer scales them into each UI's bounds and
caches the fitted frames within the established memory budgets. Artwork is
distributed with the client; it does not add per-frame network traffic.

## Gameplay and acquisition

The existing game balance is retained. Both forms are Mega, Virus, Electric in
this game's original fan balance. They use the established basic Attack and
Electric skill set. This release adds no duplicate species and changes no
encounter tables, rarity, combat statistics or rewards.

Both forms remain discoverable in the existing Dawn and World DS encounter
pools; Dawn Sector 190 is one location. Use the game's destination encounter
previews to find their other habitats. The Paradox form uses the normal rare
Paradox encounter roll for the same habitat.

Ordinary wild defeats give 20% Fanglongmon scan or 5% Paradox Fanglongmon scan.
The permanent World DS Paradox mastery reward adds 20% to the Paradox scan gain
when the entire wild battle is won (5% becomes 6%). Trainer and story boss
partners remain uncollectible through wild scan.

Materialize either form at a DigiLab or DigiFarm with at least 100% of that
form's scan data. 200% grants the existing ABI 5 bonus. A full party sends the
new partner to available DigiFarm storage.

The existing data-splice route remains Fanglongmon → Examon, with a separate
Paradox Fanglongmon → Paradox Examon route. Requirements are level 60, ABI 50,
CAM 40 and ATK 279. Examon can de-digivolve back at level 5. Evolution retains
identity, CAM and trained farm bonuses, and the Paradox route retains its
variant. No new incoming evolution family or fusion requirement was invented.

## Rebuild and provenance

Rebuild and distribute the v1.0.0 client to show the new art and directional
support. Use the matching v1.0.0 server release for its updated catalog/version;
no save reset or species migration is required.

`data/source_assets.json` records the archive and each published frame's SHA-256
digest. Per-form `animation.json` files preserve the authored pose roles when
`tools/import_assets.py` regenerates the catalog. The original placeholder art
remains in the source for compatibility, but these species no longer select it.

To reproduce just this artwork import from the supplied archive:

```sh
python tools/import_fanglongmon.py --source "fanglongmon&ParadoxVariety_6_png_frames_each.rar"
python tools/import_assets.py --manifest-only
```

An extracted directory is also accepted as `--source`. Archive extraction uses
the existing import-only libarchive dependency; players and servers require no
additional runtime packages.

Focused verification covers original frame checksums/transparency, both idle
and attack frames, left-facing art without a double flip, bounded real sprite
caches, catalog regeneration, legal encounter selection, combat scan rewards,
materialization, evolution/devolution and SQL save restoration.
