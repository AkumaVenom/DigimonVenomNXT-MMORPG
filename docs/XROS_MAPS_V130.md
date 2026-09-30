# Super Xros Wars terrain import — v1.3.0

The supplied Super Xros Wars Blue archive contains **196 numbered maps and 764 PNG files**. This release publishes **96 distinct adventure fields in 14 zones**, spanning level 1–99. All 196 exports have per-file SHA-256 provenance and an explicit disposition in `data/xros_maps.json`.

## Progression

Zone names and levels below are authored for Venom NXT; they are not claims about canonical Super Xros Wars location names. Original source numbers remain stable in every map ID.

| Zone | Maps | Levels | Source map numbers |
|---|---:|---:|---|
| Verdant Crossing | 3 | 1–6 | 027, 028, 029 |
| Sunlit Meadow | 5 | 5–12 | 092, 093, 094, 095, 096 |
| Coral Causeway | 7 | 8–20 | 033, 034, 038, 039, 040, 106, 107 |
| Mosswater Marsh | 6 | 18–30 | 042, 043, 044, 045, 049, 050 |
| Sandglass Basin | 7 | 28–42 | 080, 081, 082, 083, 088, 089, 090 |
| Stonefall Outpost | 7 | 38–52 | 068, 069, 070, 071, 076, 077, 078 |
| Frostline Shelf | 6 | 45–59 | 058, 059, 060, 062, 063, 064 |
| Cloudspire Cliffs | 14 | 52–70 | 023, 024, 025, 026, 138, 139, 140, 141, 142, 145, 146, 147, 148, 149 |
| Duskmire Keep | 6 | 60–77 | 072, 097, 098, 100, 133, 134 |
| Crimson Causeway | 7 | 70–85 | 051, 052, 054, 161, 180, 182, 188 |
| Cinderfront Caldera | 10 | 76–89 | 112, 113, 114, 115, 116, 119, 120, 121, 123, 124 |
| Neon Bastion | 5 | 84–93 | 126, 127, 128, 129, 130 |
| Overdrive Circuit | 10 | 90–98 | 152, 153, 154, 155, 156, 157, 160, 163, 164, 165 |
| Xros Core | 3 | 97–99 | 175, 176, 177 |

## Artwork and movement

- Every playable base PNG is a byte-identical copy of the supplied complete composite, at its original dimensions. No terrain is redrawn or resampled.
- Source collision uses black for floor and white for obstruction. A strict luminance threshold below 128 converts the antialiased export into the existing runtime convention, white for floor. Grayscale, opacity and dimensions are validated; explicit reference probes on eight different biomes catch reversed masks.
- Some source layer A images omit the composite background color, while layer B includes walkable bridge decks. The importer therefore keeps the full composite as the base. Its foreground uses original composite pixels only where layer B covers blocked ground. It never draws a bridge deck over an actor standing on it, and recomposing the foreground preserves every original artwork pixel.
- Arrival points are chosen on the largest connected supplied floor component with at least a 9×9 clear neighborhood. The mask itself is never modified. Disconnected ledges remain disconnected; no fictional ladder or bridge links are inserted.
- Every field was checked using the actual authoritative `Navigation` implementation: twenty simultaneous arrivals at least 16 pixels apart, a connected patrol cloud, and a closed patrol with collision-safe segments. The smallest measured separation over all 96 maps was **24.749 pixels**.
- All 17 exploration recordings and all three combat difficulty tracks are assigned across these fields. See `data/xros_audio.json` for soundtrack provenance and loop details.

## Excluded source exports

| Disposition | Count | Reason |
|---|---:|---|
| Playable | 96 | Distinct adventure terrain with verified supplied collision |
| Duplicate | 53 | Exact repeated artwork and thresholded collision, including repeated service platforms |
| Incomplete | 23 | 15 empty black placeholders and 8 water-only exports with missing terrain |
| Reserved | 24 | World overview, farm layouts, service/hub rooms and small story backdrops |

The exclusions avoid presenting empty or repeated rooms as additional world content. Existing DigiFarm, service destinations and stories continue to supply their established functionality. The two story backdrops at source 151 and 158 are not used as encounter fields because one contains substantial foreground scenery and the other contains a baked-in boss over the nominal floor. Every excluded record has its individual reason and source hashes.

## Rebuild and verification

```bat
python tools/import_xros_audio.py --source path/to/Music_WAV
python tools/import_xros_maps.py --source path/to/Digimon_Super_Xros_Wars_Blue_Maps_Collision
python tools/merge_xros.py
python -m pytest -q tests/test_xros_maps.py
```

The map importer performs movement validation before publishing `data/xros_maps.json`. `test_xros_maps.py` independently checks source hashes, all collision dimensions, arrival spacing, complete patrol edges, every foreground layer and exact art reconstruction.

## Source contact sheets

The five sheets record the visual review of all source exports, including reserved and incomplete files.

- [Source maps 000–039](validation/release_v130/xros_source_contact_000.jpg)
- [Source maps 040–079](validation/release_v130/xros_source_contact_040.jpg)
- [Source maps 080–119](validation/release_v130/xros_source_contact_080.jpg)
- [Source maps 120–159](validation/release_v130/xros_source_contact_120.jpg)
- [Source maps 160–195](validation/release_v130/xros_source_contact_160.jpg)
