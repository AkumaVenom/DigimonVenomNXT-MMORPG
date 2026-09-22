# Asset provenance and reproduction

This project imports the user's supplied artwork and Dawn ROM. No map, tamer or Digimon placeholder artwork is generated. The original uploaded ROM is not required to play the prepared build. See `data/source_assets.json` for the exact filenames, byte sizes and SHA-256 hashes used for this import.

## Included content

- **1,004 selectable/materializable Digimon records:** 502 normal artwork records and 502 matching Paradox variants. The source pack contains 16,028 PNGs. Agunimon and Shoutmon each appear in two stage directories; both artwork sets are preserved with distinct stage-suffixed IDs. A record is an artwork/form entry, not a claim that there are 502 distinct official Cyber Sleuth species.
- **64 selectable human tamer appearances:** four protagonist appearances and 60 additional human NPC/guest appearances extracted from the ROM. These contain **2,048 RGBA PNG frames**, eight directions with four-frame walking cycles. Some NPCs reuse diagonal views for cardinal motion, exactly as their original animation tables do. Generic display names are used when identity was not verified.
- **254 traversable base maps** and **97 foreground overlays**, using all 351 supplied PNGs at their original x2 dimensions. Foreground images are composited over the matching base map and are not selectable empty maps. The map labels identify source indices; canonical location names are not yet mapped.
- **254 original collision masks**, decoded from the ROM and scaled to the supplied x2 maps. `data/collision.json` preserves each collision reference and verified walkable spawn. See `tools/extract_collision.py` for decoding details.
- **96 authentic battle-effect sequences:** 1,022 transparent effect PNGs decoded from the ROM NCGR/NCLR/NSCR resources. Compound effect mappings that could not be established unambiguously are excluded; playback cadence is chosen for this client rather than claimed to match the original descriptor exactly.
- **46 music sequences, 183 sound effects and 703 decoded sample WAVs** from the original SDAT, plus the original SDAT. The portable renderer uses authentic sequence notes and instrument samples, with approximate ADSR/modulation rather than DS-hardware-identical synthesis. See `assets/audio/README.md` and `tools/nds_audio.py`.

The numbered visual roster is in `docs/TAMER_ROSTER.png`.

## Sprites and animation

The MCHR PAK files use Nintendo RLE30 compression. `tools/import_assets.py` decodes indexed 4-bpp 8x8 tiles with the matching RGB555 palette. Each `MCHR_ANM` frame supplies its image index, horizontal flip, anchor and timing. The exported tamer frames bake in the ROM direction flip; the client must not apply another left/right mirror. Native tamer frames are 16x32 pixels and display at 2x beside the x2 maps. The usual walking cycle is standing, step one, standing, step two at eight DS ticks per image.

Digimon `LLegWalk` and `RLegWalk` mean alternating legs, not left-facing/right-facing directions. Front sprites are used for overworld followers, as requested. All named original PNGs are retained.

The pack's `Frames` directories contain components cut from sprite sheets: large battle poses, miniature overworld poses, occasional effects and credit text. They are **not** a ready-to-play animation sequence. The importer selects the combat-sized group relative to each `Primary` image and excludes miniature components, merged oversized components and credit labels. The first three combat poses supply standing/step motion; the fourth/fifth, when present, supply attack motion. The client adds continuous attack lunges and particle effects. For sparse forms, movement/attack poses fall back to the actual standing art rather than inventing missing frames. All source components remain available for future hand-authored animation metadata.

The base stats, evolution thresholds and uncommon species assignments are explicitly original/provisional balance. A sprite pack and a Dawn ROM do not contain the complete Cyber Sleuth rules/stat tables. The importer applies `GameEngine`'s curated type/attribute overrides, evolution routes and encounter pools before writing the final catalog, keeping the client display consistent with server logic. See `docs/MECHANICS.md`.

## Reimport the user-owned inputs

Run from the project root with the builder's Python environment (Python 3.11+):

```bat
.venv\Scripts\python tools\import_assets.py --sprites "C:\Assets\2D Digimon Assets v7 With Paradox Variants(1).zip" --maps "C:\Assets\DigimonDawnAllLevelMaps(1).7z" --rom "C:\Assets\Digimon World - Dawn (USA)(4).nds" --verify-images
.venv\Scripts\python tools\extract_collision.py --rom "C:\Assets\Digimon World - Dawn (USA)(4).nds"
.venv\Scripts\python tools\nds_audio.py "C:\Assets\Digimon World - Dawn (USA)(4).nds"
.venv\Scripts\python -m tools.nds_effects "C:\Assets\Digimon World - Dawn (USA)(4).nds"
.venv\Scripts\python tools\import_assets.py --verify-images
```

For a single full ROM pass, add `--extract-media` to the first import command; this calls the audio, effect and collision extractors automatically. It can take a few minutes.

The prepared source already includes the complete imported content. Collision, effects and audio extraction also have separate commands because they are unnecessary for normal builds; the commands above supply the input paths. After regenerating either, run `python tools/import_assets.py` to merge their metadata and rebuild checksums. This preserves safe spawns from `data/collision.json` and incorporates `data/audio_catalog.json`.

To regenerate only the integrity manifest after an intentional asset/catalog edit:

```bat
.venv\Scripts\python tools\import_assets.py --manifest-only
```

`data/asset_manifest.json` records SHA-256 and byte size for every asset plus the catalog and provenance metadata. The one-click builder verifies it before compiling. `--verify-images` additionally decodes every PNG to catch corrupt images. Re-running the importer with the same files and mechanics produces the same asset and catalog content.
