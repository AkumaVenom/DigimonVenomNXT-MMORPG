#!/usr/bin/env python3
"""Install and verify the complete user-supplied FireWall variety.

The 502 normal species retain their exact pose selections, genuine mirrored
frames, stats, and evolution requirements. All supplied PNGs are copied byte
for byte; explicit source-canvas geometry accompanies the selected poses.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fixed_sprites import ART_KEYS, json_bytes, object_hash, safe_path
from tools.import_varieties_v120 import art_paths, base_directory, digest, load

RECORD = 'data/firewall_v150.json'
KIND = 'FireWall'
GEOMETRY_KEYS = ('source_size', 'output_size', 'padding')


def _geometry(directory: Path, *, decode_images=False) -> dict:
    """Validate the complete supplied frame geometry, including unused sheets."""
    manifest = load(directory / 'sprite_geometry.json')
    if manifest.get('version') != 1 or manifest.get('coordinate_space') != 'pixels':
        raise ValueError(f'Unsupported FireWall geometry: {directory}')
    files = manifest.get('files', {})
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*.png')}
    if set(files) != actual:
        raise ValueError(f'Incomplete FireWall geometry: {directory}')
    from PIL import Image
    for name, row in files.items():
        path = safe_path(directory, name)
        src, out, pad = row['source_size'], row['output_size'], row['padding']
        if (len(src) != 2 or len(out) != 2 or set(pad) != {'left', 'top', 'right', 'bottom'}
                or any(type(n) is not int or n < 1 for n in src + out)
                or any(type(n) is not int or n < 0 for n in pad.values())
                or out != [src[0] + pad['left'] + pad['right'], src[1] + pad['top'] + pad['bottom']]):
            raise ValueError(f'Invalid FireWall canvas dimensions: {name}')
        with Image.open(path) as image:
            if image.mode != 'RGBA' or list(image.size) != out:
                raise ValueError(f'PNG differs from FireWall geometry: {path}')
            if decode_images:
                image.load()
                if image.getbbox() is None:
                    raise ValueError(f'Empty FireWall image: {path}')
    return files


def mapped_art(normal: dict, directory: Path, root: Path) -> tuple[dict, dict]:
    """Build canonical pose routes without guessing from sprite-sheet contents."""
    original_dir = base_directory(normal)
    destination = original_dir / KIND
    geometry = _geometry(directory)

    def local(path: str) -> str:
        name = PurePosixPath(path).relative_to(original_dir).as_posix()
        if name not in geometry:
            raise ValueError(f'Missing FireWall replacement for {path}')
        from PIL import Image
        with Image.open(safe_path(root, path)) as image:
            if list(image.size) != geometry[name]['source_size']:
                raise ValueError(f'FireWall source geometry differs from normal: {path}')
        return name

    wanted = {
        'sprites': {k: local(p) for k, p in normal['sprites'].items()},
        'animations': {k: [local(p) for p in seq] for k, seq in normal['animations'].items()},
        'mirrored_frames': {local(p): local(m) for p, m in normal.get('mirrored_frames', {}).items()},
    }
    sidecar_path = directory / 'animation.json'
    if sidecar_path.exists():
        sidecar = load(sidecar_path)
        if sidecar.get('version') != 1 or any(sidecar.get(k, {}) != v for k, v in wanted.items()):
            raise ValueError(f'Supplied FireWall poses differ from normal: {normal["id"]}')
    else:
        sidecar = {
            'version': 1, **wanted,
            'source_frame_count': normal.get('source_frame_count', 0),
            'frame_selection': normal.get('frame_selection', 'Existing labeled pose selections retained'),
            'art_provenance': 'User-supplied FireWall PNG bytes preserved; normal pose selections and mirrors retained. Aura padding is recorded in sprite_geometry.json.',
        }
    def absolute(name):
        return (destination / name).as_posix()
    art = {
        'sprites': {k: absolute(p) for k, p in sidecar['sprites'].items()},
        'animations': {k: [absolute(p) for p in seq] for k, seq in sidecar['animations'].items()},
        'mirrored_frames': {absolute(p): absolute(m) for p, m in sidecar.get('mirrored_frames', {}).items()},
        **{k: sidecar[k] for k in ART_KEYS if k not in wanted and k in sidecar},
    }
    art['sprite_geometry'] = {p: {k: geometry[PurePosixPath(p).relative_to(destination).as_posix()][k]
                                    for k in GEOMETRY_KEYS} for p in sorted(art_paths(art))}
    return art, sidecar


def historical_catalog(root: Path, catalog: dict) -> dict:
    """Check the additive release and expose its immutable 1,506-entry baseline.

    Used by the historical art verifiers so accepting a fourth variety never
    weakens their normal, Paradox, or Shiny preservation guarantees.
    """
    root = root.resolve()
    record_path = root / RECORD
    if not record_path.exists():
        if catalog.get('version') == '1.5.0' or any(s.get('firewall') or s.get('variety') == 'firewall' for s in catalog['species']):
            raise ValueError('Missing FireWall preservation record.')
        return catalog
    record = load(record_path)
    if record.get('version') != 1 or record.get('release') != '1.5.0':
        raise ValueError('Unsupported FireWall preservation record.')
    entries = {s['id']: s for s in catalog['species']}
    normal_ids = set(record['normal_ids'])
    previous = set(record['baseline_species_sha256'])
    expected_old = normal_ids | {s + '_paradox' for s in normal_ids} | {s + '_shiny' for s in normal_ids}
    expected_new = {s + '_firewall' for s in normal_ids}
    if (len(normal_ids) != 502 or previous != expected_old or len(entries) != len(catalog['species'])
            or set(entries) != expected_old | expected_new):
        raise ValueError('FireWall roster does not preserve the complete 502-species baseline.')
    for sid in sorted(previous):
        if object_hash(entries[sid]) != record['baseline_species_sha256'][sid]:
            raise ValueError(f'Existing species changed during FireWall installation: {sid}')
    maps = catalog.get('maps', [])
    map_hashes = record['baseline_map_sha256']
    if len(maps) != 500 or len(map_hashes) != 500 or {m['id'] for m in maps} != set(map_hashes):
        raise ValueError('FireWall habitats do not cover all 500 preserved world maps.')
    for area in maps:
        retained = {k: v for k, v in area.items() if k != 'firewall_encounters'}
        if object_hash(retained) != map_hashes[area['id']]:
            raise ValueError(f'Existing world map fields changed: {area["id"]}')
        expected_habitat = [sid + '_firewall' for sid in area['encounters']]
        if area.get('firewall_encounters') != expected_habitat or any(sid not in expected_new for sid in expected_habitat):
            raise ValueError(f'FireWall encounter habitat differs from normal: {area["id"]}')
    for sid in sorted(normal_ids):
        normal, entry = entries[sid], entries[sid + '_firewall']
        if (entry.get('variety'), entry.get('firewall'), entry.get('shiny'), entry.get('paradox'), entry.get('base_id'), entry.get('name')) != (
                'firewall', True, False, False, sid, 'FireWall ' + normal['name']):
            raise ValueError(f'Invalid FireWall identity: {sid}')
        expected = copy.deepcopy(normal)
        expected.update(id=sid + '_firewall', name='FireWall ' + normal['name'], base_id=sid,
                        firewall=True, shiny=False, paradox=False, variety='firewall')
        expected['evolutions'] = [{**route, 'to': route['to'] + '_firewall'} for route in normal.get('evolutions', [])]
        excluded = set(ART_KEYS) | {'sprite_geometry'}
        if {k: v for k, v in entry.items() if k not in excluded} != {k: v for k, v in expected.items() if k not in excluded}:
            raise ValueError(f'FireWall stats or evolution requirements differ from normal: {sid}')
    return {**catalog, 'species': [s for s in catalog['species'] if s['id'] in previous]}


def verify(root: Path = ROOT, *, decode_images=False) -> dict:
    root = root.resolve()
    catalog, record = load(root / 'data/catalog.json'), load(root / RECORD)
    historical_catalog(root, catalog)
    entries = {s['id']: s for s in catalog['species']}
    rows = {row['path']: row for row in record['files']}
    actual = {p.relative_to(root).as_posix() for d in (root / 'assets/digimon').glob('*/*/FireWall')
              for p in d.rglob('*') if p.is_file() and not p.name.startswith('.rsync-tmp')}
    if len(rows) != len(record['files']) or set(rows) != actual:
        raise ValueError('Unrecorded, stale, or missing FireWall assets.')
    for name, row in rows.items():
        path = safe_path(root, name)
        if path.stat().st_size != row['size'] or digest(path) != row['sha256']:
            raise ValueError(f'FireWall file differs from the recorded installation: {name}')
    for row in record['source_files']:
        installed = rows.get('assets/digimon/' + row['path'])
        if not installed or any(installed[k] != row[k] for k in ('size', 'sha256')):
            raise ValueError(f'Supplied FireWall bytes changed: {row["path"]}')
    expected_files = {'assets/digimon/' + row['path'] for row in record['source_files']}
    expected_files.update((base_directory(entries[sid]) / KIND / 'animation.json').as_posix() for sid in record['normal_ids'])
    if set(rows) != expected_files:
        raise ValueError('Unrecognized files were included in the FireWall installation record.')
    from tools.import_assets import animation_override
    for sid in record['normal_ids']:
        normal, entry = entries[sid], entries[sid + '_firewall']
        directory = root / base_directory(normal) / KIND
        _geometry(directory, decode_images=decode_images)
        wanted, _ = mapped_art(normal, directory, root)
        if any(entry.get(k) != v for k, v in wanted.items()) or animation_override(directory, root) != wanted:
            raise ValueError(f'FireWall runtime pose/geometry mapping differs: {sid}')
        variant = load(directory / 'variant.json')
        if variant.get('status') != 'ready' or variant.get('materializable') is not True:
            raise ValueError(f'Incomplete supplied FireWall species: {sid}')
    counts = record['counts']
    expected_counts = {'normal_species': 502, 'paradox_species': 502, 'shiny_species': 502,
                       'firewall_species': 502, 'total_species': len(entries),
                       'source_pngs': sum(r['path'].endswith('.png') for r in record['source_files']),
                       'source_files': len(record['source_files']), 'installed_firewall_files': len(rows),
                       'animation_sidecars': 502,
                       'generated_animation_sidecars': sum(r['path'].endswith('/animation.json') for r in rows.values()) - sum(r['path'].endswith('/animation.json') for r in record['source_files'])}
    if counts != expected_counts:
        raise ValueError('FireWall installation counts differ from the record.')
    mechanics = load(root / 'data/mechanics.json')
    if mechanics.get('firewall_encounter_chance') != .007 or mechanics.get('firewall_scan_gain') != 5:
        raise ValueError('FireWall encounter or scan rate differs from the release specification.')
    return {'status': 'verified', **counts, 'decoded_images': bool(decode_images)}


def install(source: Path, root: Path = ROOT, *, volumes: Path | None = None) -> dict:
    source, root = source.resolve(), root.resolve()
    if source.is_relative_to(root / 'assets'):
        raise ValueError('Supply a separate extracted FireWall digimon directory.')
    catalog = load(root / 'data/catalog.json')
    old_record = load(root / RECORD) if (root / RECORD).exists() else None
    previous = historical_catalog(root, catalog) if old_record else catalog
    if len(previous['species']) != 1506:
        raise ValueError('FireWall requires the complete 1,506-entry v1.4 baseline.')
    normals = [s for s in previous['species'] if s.get('variety') == 'normal']
    directories = {d.relative_to(source).as_posix(): d for d in source.glob('*/*/FireWall') if d.is_dir()}
    expected_directories = {(base_directory(s).relative_to('assets/digimon') / KIND).as_posix() for s in normals}
    if len(normals) != 502 or set(directories) != expected_directories:
        raise ValueError('Supplied FireWall directories do not cover exactly all 502 normal species.')
    new_entries, sidecars = [], {}
    normal_ids = {s['id'] for s in normals}
    for normal in normals:
        directory = base_directory(normal).relative_to('assets/digimon') / KIND
        variant = load(source / directory / 'variant.json')
        if variant.get('status') != 'ready' or variant.get('materializable') is not True:
            raise ValueError(f'Incomplete supplied FireWall species: {normal["id"]}')
        if any(route['to'] not in normal_ids for route in normal.get('evolutions', [])):
            raise ValueError(f'Unknown normal evolution destination: {normal["id"]}')
        art, sidecar = mapped_art(normal, source / directory, root)
        entry = copy.deepcopy(normal)
        entry.update(id=normal['id'] + '_firewall', name='FireWall ' + normal['name'],
                     base_id=normal['id'], firewall=True, shiny=False, paradox=False, variety='firewall')
        entry['evolutions'] = [{**route, 'to': route['to'] + '_firewall'} for route in normal.get('evolutions', [])]
        entry.update(art)
        new_entries.append(entry)
        if not (source / directory / 'animation.json').exists():
            sidecars[(Path('assets/digimon') / directory / 'animation.json').as_posix()] = sidecar
    source_files = []
    for relative, directory in sorted(directories.items()):
        for path in sorted(directory.rglob('*')):
            if path.is_symlink():
                raise ValueError(f'Symlink in supplied FireWall assets: {path}')
            if path.is_file() and not path.name.startswith('.rsync-tmp'):
                source_files.append({'path': path.relative_to(source).as_posix(), 'size': path.stat().st_size, 'sha256': digest(path)})
    # All inputs and pose mappings have passed before the additive write starts.
    # No normal, Paradox, or Shiny directory is modified.
    for relative, directory in sorted(directories.items()):
        destination = root / 'assets/digimon' / relative
        shutil.copytree(directory, destination, dirs_exist_ok=True, copy_function=shutil.copy,
                        ignore=shutil.ignore_patterns('.rsync-tmp*'))
    for name, sidecar in sidecars.items():
        (root / name).write_bytes(json_bytes(sidecar))
    file_rows = [{'path': path.relative_to(root).as_posix(), 'size': path.stat().st_size, 'sha256': digest(path)}
                 for d in sorted((root / 'assets/digimon').glob('*/*/FireWall')) for path in sorted(d.rglob('*'))
                 if path.is_file() and not path.name.startswith('.rsync-tmp')]
    provenance = {'kind': 'firewall_v150', 'release': '1.5.0',
                  'use': 'Complete FireWall variety; every supplied PNG and metadata file preserved byte for byte',
                  'source_tree_sha256': object_hash(source_files)}
    if volumes:
        parts = sorted(volumes.glob('FireWall_Digimon_Complete.part*.rar'))
        if [p.name for p in parts] != [f'FireWall_Digimon_Complete.part{i}.rar' for i in range(1, 7)]:
            raise ValueError('Expected the six complete uploaded FireWall archive parts.')
        provenance['parts'] = [{'filename': p.name, 'size': p.stat().st_size, 'sha256': digest(p)} for p in parts]
    elif old_record:
        provenance = old_record['provenance']
    counts = {'normal_species': 502, 'paradox_species': 502, 'shiny_species': 502, 'firewall_species': 502,
              'total_species': 2008, 'source_pngs': sum(r['path'].endswith('.png') for r in source_files),
              'source_files': len(source_files), 'installed_firewall_files': len(file_rows),
              'animation_sidecars': 502, 'generated_animation_sidecars': len(sidecars)}
    record = {'version': 1, 'release': '1.5.0', 'normal_ids': sorted(normal_ids), 'counts': counts,
              'baseline_species_sha256': {s['id']: object_hash(s) for s in previous['species']},
              'baseline_map_sha256': {m['id']: object_hash({k: v for k, v in m.items() if k != 'firewall_encounters'}) for m in previous['maps']},
              'provenance': provenance, 'source_files': source_files, 'files': file_rows}
    catalog['species'] = previous['species'] + new_entries
    for area in catalog['maps']:
        area['firewall_encounters'] = [sid + '_firewall' for sid in area['encounters']]
    catalog['version'] = '1.5.0'
    mechanics = load(root / 'data/mechanics.json')
    mechanics.update(version='1.5.0', firewall_encounter_chance=.007, firewall_scan_gain=5)
    (root / 'data/catalog.json').write_bytes(json_bytes(catalog))
    (root / 'data/mechanics.json').write_bytes(json_bytes(mechanics))
    (root / RECORD).write_bytes(json_bytes(record))
    sources = [s for s in load(root / 'data/source_assets.json') if s.get('kind') != 'firewall_v150'] + [provenance]
    (root / 'data/source_assets.json').write_bytes(json_bytes(sources))
    verify(root)
    return {'status': 'installed', **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--volumes', type=Path)
    parser.add_argument('--decode-images', action='store_true')
    args = parser.parse_args()
    result = install(args.source, args.root, volumes=args.volumes) if args.source else verify(args.root, decode_images=args.decode_images)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
