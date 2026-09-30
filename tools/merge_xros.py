"""Merge the Super Xros Wars expansion without replacing existing regions.

Map and music importers keep standalone reproducible catalogs. This merge is
idempotent, preserves stable identities and validates all regional music links.
It does not load or change player accounts or persistent rival progress.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REGION = 'xros_wars'


def merge_catalog(catalog: dict, root: Path = ROOT) -> dict:
    root = Path(root)
    result = copy.deepcopy(catalog)
    map_path = root / 'data/xros_maps.json'
    if not map_path.is_file():
        return result
    expansion = json.loads(map_path.read_text(encoding='utf-8'))
    maps = expansion['maps']
    if not maps:
        raise ValueError('The Super Xros Wars map catalog is empty.')
    identifiers = [row['id'] for row in maps]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Duplicate Super Xros Wars map identifiers.')
    if any(not row['id'].startswith('xros_') or row.get('region_id') != REGION for row in maps):
        raise ValueError('Super Xros Wars maps must use their own region and identifier namespace.')
    retained = [row for row in result['maps']
                if row.get('region_id') != REGION]
    if set(row['id'] for row in retained) & set(identifiers):
        raise ValueError('Super Xros Wars map identifier collides with another region.')
    result['maps'] = retained + copy.deepcopy(maps)
    region = copy.deepcopy(expansion.get('region', {}))
    region.update(id=REGION, name='Super Xros Wars', map_count=len(maps))
    region.setdefault('description', 'A new journey from beginner fields to level 99 endgame routes.')
    regions = [row for row in result.get('world_regions', []) if row.get('id') != REGION]
    result['world_regions'] = regions + [region]

    audio_path = root / 'data/xros_audio.json'
    if not audio_path.is_file():
        raise ValueError('Super Xros Wars music must be imported before merging its maps.')
    regional_audio = json.loads(audio_path.read_text(encoding='utf-8'))
    audio = result.setdefault('audio', {})
    for section in ('music', 'effects'):
        original = [row for row in audio.get(section, []) if row.get('region_id') != REGION]
        extra = regional_audio.get(section, [])
        if any(row.get('region_id') != REGION or not row['id'].startswith('xros_') for row in extra):
            raise ValueError(f'Invalid Super Xros Wars {section} namespace.')
        identifiers = [row['id'] for row in original + extra]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f'Duplicate audio identifiers in {section}.')
        audio[section] = original + copy.deepcopy(extra)
    audio.setdefault('region_tracks', {})[REGION] = copy.deepcopy(regional_audio.get('scene_tracks', {}))
    audio.setdefault('region_sources', {})[REGION] = copy.deepcopy(regional_audio.get('source', {}))
    available = {row['id'] for row in audio.get('music', []) if row.get('region_id') == REGION}
    for row in maps:
        for key in ('music_id', 'battle_music_id'):
            if not row.get(key) or row[key] not in available:
                raise ValueError(f"Unknown {key} {row.get(key)} for {row['id']}.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root))
    from venom.version import VERSION
    from venom.common.game import GameEngine
    catalog_path = root / 'data/catalog.json'
    catalog = merge_catalog(json.loads(catalog_path.read_text(encoding='utf-8')), root)
    catalog['version'] = VERSION
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    # Publish the exact pools consumed by authoritative wild battles and the UI.
    catalog = GameEngine(root, seed=0).catalog
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (root / 'data/audio_catalog.json').write_text(
        json.dumps(catalog['audio'], indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Merged {len(catalog['maps'])} maps and {len(catalog['audio']['music'])} music tracks for v{VERSION}.")


if __name__ == '__main__':
    main()
