"""Merge the supplied World DS expansion without replacing Dawn game content.

The importers produce standalone region catalogs. This final merge is idempotent
and is also called by import_assets.py so a later Dawn re-import retains DS.
No ROM, archive, account save or existing character is read by this step.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def merge_catalog(catalog: dict, root: Path = ROOT) -> dict:
    root = Path(root)
    result = copy.deepcopy(catalog)
    map_path, audio_path = root / 'data/world_ds_maps.json', root / 'data/world_ds_audio.json'
    if not map_path.is_file():
        return result
    expansion = json.loads(map_path.read_text(encoding='utf-8'))
    maps = expansion['maps']
    if not maps:
        raise ValueError('The World DS map catalog is empty.')
    identifiers = [row['id'] for row in maps]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Duplicate World DS map identifiers.')
    if any(not ident.startswith('world_ds_') for ident in identifiers):
        raise ValueError('World DS maps must use their own identifier namespace.')
    retained = [row for row in result['maps']
                if row.get('region_id') != 'world_ds' and not row['id'].startswith('world_ds_')]
    if set(row['id'] for row in retained) & set(identifiers):
        raise ValueError('World DS map identifier collides with another region.')
    for row in retained:
        row.setdefault('region_id', 'dawn')
    result['maps'] = retained + copy.deepcopy(maps)
    region = expansion.get('region', {})
    other_regions = [row for row in result.get('world_regions', [])
                     if row.get('id') not in {'dawn', 'world_ds'}]
    result['world_regions'] = [
        {'id': 'dawn', 'name': 'Digimon World Dawn',
         'description': 'The original Dawn sectors and their established encounters.'},
        {'id': 'world_ds', 'name': 'Digimon World DS',
         'description': region.get('description', 'New field routes, wild partners and roaming tamers.')}] + other_regions
    if audio_path.is_file():
        ds_audio = json.loads(audio_path.read_text(encoding='utf-8'))
        audio = result.setdefault('audio', {})
        for section in ('music', 'effects'):
            original = [row for row in audio.get(section, [])
                        if row.get('region_id') != 'world_ds' and not row['id'].startswith('ds_')]
            extra = ds_audio.get(section, [])
            ids = [row['id'] for row in original + extra]
            if len(set(ids)) != len(ids):
                raise ValueError(f'Duplicate audio identifiers in {section}.')
            audio[section] = original + copy.deepcopy(extra)
        audio.setdefault('region_tracks', {})['world_ds'] = copy.deepcopy(ds_audio.get('scene_tracks', {}))
        audio.setdefault('region_sources', {})['world_ds'] = copy.deepcopy(ds_audio.get('source', {}))
        available = {row['id'] for row in audio.get('music', [])}
        for row in result['maps']:
            if row.get('region_id') == 'world_ds':
                for key in ('music_id', 'battle_music_id'):
                    if row.get(key) and row[key] not in available:
                        raise ValueError(f"Unknown {key} {row[key]} for {row['id']}.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    catalog_path = root / 'data/catalog.json'
    catalog = merge_catalog(json.loads(catalog_path.read_text(encoding='utf-8')), root)
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (root / 'data/audio_catalog.json').write_text(json.dumps(catalog['audio'], indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    # Publish the exact same derived encounter pools the authoritative engine uses.
    sys.path.insert(0, str(root))
    from venom.common.game import GameEngine
    catalog = GameEngine(root, seed=0).catalog
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Merged {len(catalog['maps'])} maps and {len(catalog['audio']['music'])} music tracks.")


if __name__ == '__main__':
    main()
