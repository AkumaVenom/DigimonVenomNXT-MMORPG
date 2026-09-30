# FireWall artwork integration

The v1.5.0 roster adds one FireWall version of every existing normal Digimon:
502 normal, 502 Paradox, 502 Shiny, and 502 FireWall entries (2,008 total).
Existing species IDs, stats, evolution routes, selected frames, and assets are
preserved. FireWall IDs use the suffix `_firewall`; their stats and evolution
requirements match the corresponding normal species, with all evolution routes
remaining within the FireWall variety.

Each of the 500 public world maps publishes a FireWall habitat list derived
from its existing normal encounters. Every pre-existing map field is retained;
the preservation record fingerprints those fields independently of the added
`firewall_encounters` list.

The six supplied archive volumes contain 502 complete FireWall directories,
7,934 PNGs, 502 variant records, 502 geometry records, and 149 animation records.
Every one of those 9,087 supplied files is retained byte for byte. The importer
adds 353 animation sidecars for species without one, using the exact existing
normal pose selection. It never guesses animation frames from a sheet or
recolors the uploaded art. Fanglongmon retains its explicit opposite-facing
frame pair. Repaired normal frame selections remain matched to their FireWall
equivalents.

The supplied aura margins are recorded in `sprite_geometry.json`. The runtime
catalog includes source size, output size, and padding for each selected pose,
allowing the renderer to preserve alignment while fitting the full effect
canvas. All source sizes match the corresponding installed normal PNGs.

`data/firewall_v150.json` records source volume checksums, every supplied and
installed file checksum, and immutable hashes for all 1,506 pre-existing
species. Historical sprite verifiers first validate that preserved baseline
before checking their original scope. The old three-variety installer rejects
attempts to overwrite an installation containing FireWall.

To verify the installed art, including full PNG decoding:

```text
python tools/import_firewall_v150.py --decode-images
```

To reproduce the additive import from the extracted uploaded `digimon` folder:

```text
python tools/import_firewall_v150.py --source PATH_TO_EXTRACTED_DIGIMON --volumes PATH_TO_SIX_RAR_PARTS
```

After an intentional import, the release maintainer regenerates the global
asset manifest with `python tools/import_assets.py --manifest-only`.
