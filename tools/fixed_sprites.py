#!/usr/bin/env python3
"""Verify or reapply the supplied v1.1.0 sprite fixes to the v1.0.1 source.

Normal installation is a file overlay: this tool is not needed to play or build.
Reapplication accepts an extracted copy of the original fixed-sprite archive.
All input PNGs are checked before writes. Selected PNG bytes are never re-encoded.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import os
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = 'data/fixed_sprites_v110.json'
ART_KEYS = ('sprites', 'animations', 'mirrored_frames', 'source_frame_count',
            'frame_selection', 'art_provenance')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def object_hash(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False).encode('utf-8'))


def non_art_catalog(catalog: dict) -> dict:
    """A fingerprint of every catalog field except the explicitly edited art."""
    return {**catalog, 'species': [
        {key: value for key, value in entry.items() if key not in ART_KEYS}
        for entry in catalog['species']
    ]}


def safe_path(root: Path, name: str) -> Path:
    """Resolve a canonical project path, rejecting traversal and symlink writes."""
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or '\x00' in name or PurePosixPath(name).is_absolute()
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError(f'Unsafe sprite path: {name!r}')
    root = root.resolve()
    result = root.joinpath(*PurePosixPath(name).parts)
    for part in (result, *result.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f'Symlink not allowed in sprite path: {name}')
    if not result.resolve().is_relative_to(root):
        raise ValueError(f'Sprite path escapes the source root: {name}')
    return result


def read_record(root: Path) -> dict:
    record = json.loads(safe_path(root, RECORD_PATH).read_text(encoding='utf-8'))
    if record.get('version') != 1 or record.get('patch_id') != 'fixed_sprites_v110_for_v101':
        raise ValueError('Unsupported fixed-sprite record.')
    inputs, replacements, species = (record[key] for key in ('inputs', 'replacements', 'species'))
    if len({row['source'] for row in inputs}) != len(inputs):
        raise ValueError('Duplicate input filename in fixed-sprite record.')
    if len({row['path'] for row in replacements}) != len(replacements):
        raise ValueError('Duplicate destination in fixed-sprite record.')
    if len({row['id'] for row in species}) != len(species):
        raise ValueError('Duplicate species in fixed-sprite record.')
    expected = {'source_images': len(inputs), 'canonical_replacements': len(replacements),
                'animation_frames': sum(row['kind'] == 'frame' for row in replacements),
                'primary_images': sum(row['kind'] == 'primary' for row in replacements),
                'species': len(species), 'duplicate_inputs': len(inputs) - len(replacements)}
    if record['counts'] != expected:
        raise ValueError('Fixed-sprite record counts are inconsistent.')
    selected = {row['path']: row for row in inputs if row['selected']}
    if len(selected) != len(replacements) or sum(bool(r['selected']) for r in inputs) != len(selected):
        raise ValueError('Each destination must have exactly one selected source.')
    for row in replacements:
        safe_path(root, row['path'])
        chosen = selected.get(row['path'])
        if not chosen or any(chosen[key] != row[key] for key in ('source', 'sha256', 'size', 'species_id')):
            raise ValueError(f'Inconsistent selected source: {row["path"]}')
    for row in inputs:
        if PurePosixPath(row['source']).name != row['source'] or '\\' in row['source']:
            raise ValueError('Source filenames must be basenames.')
        chosen = selected.get(row['path'])
        if not chosen or row['selected_source'] != chosen['source']:
            raise ValueError(f'Unaccounted source: {row["source"]}')
    return record


def absolute_art(species: dict) -> dict:
    """Expand the existing animation.json schema, without selecting new poses."""
    directory = PurePosixPath(species['directory'])
    sidecar = species['animation']

    def asset(local):
        if (not isinstance(local, str) or '\\' in local or ':' in local
                or PurePosixPath(local).is_absolute()
                or any(part in ('', '.', '..') for part in local.split('/'))):
            raise ValueError(f'Invalid local animation path: {local!r}')
        return (directory / local).as_posix()

    return {'sprites': {key: asset(path) for key, path in sidecar['sprites'].items()},
            'animations': {key: [asset(path) for path in paths]
                           for key, paths in sidecar['animations'].items()},
            'mirrored_frames': {asset(path): asset(mirror)
                                for path, mirror in sidecar.get('mirrored_frames', {}).items()},
            **{key: sidecar[key] for key in ('source_frame_count', 'frame_selection', 'art_provenance')}}


def validate_png(data: bytes, row: dict) -> None:
    from PIL import Image
    if len(data) != row['size'] or sha256(data) != row['sha256']:
        raise ValueError(f'Sprite checksum mismatch: {row.get("source", row.get("path"))}')
    with Image.open(BytesIO(data)) as image:
        if image.format != 'PNG' or image.mode != 'RGBA':
            raise ValueError(f'Expected an RGBA PNG: {row.get("source", row.get("path"))}')
        image.verify()
    with Image.open(BytesIO(data)) as image:
        image.load()
        if image.getchannel('A').getextrema() != (0, 255):
            raise ValueError(f'Missing transparent background or visible artwork: {row["source"]}')
        if 'dimensions' in row and list(image.size) != row['dimensions']:
            raise ValueError(f'Sprite dimensions changed: {row["path"]}')
        if 'rgba_sha256' in row and sha256(image.tobytes()) != row['rgba_sha256']:
            raise ValueError(f'Decoded sprite pixels changed: {row["path"]}')


def create_manifest(root: Path, updates: dict[str, bytes]) -> bytes:
    """The normal build manifest, calculated against the proposed file overlay."""
    names = {path.relative_to(root).as_posix() for path in (root / 'assets').rglob('*')
             if path.is_file() and not any(part.startswith('.rsync-tmp') for part in path.parts)}
    names.update(path.relative_to(root).as_posix() for path in (root / 'data').glob('*.json')
                 if path.name != 'asset_manifest.json')
    names.update(name for name in updates if name.startswith('assets/') or
                 (name.startswith('data/') and name.endswith('.json') and name != 'data/asset_manifest.json'))
    rows = []
    for name in sorted(names):
        path = safe_path(root, name)
        if name in updates:
            data = updates[name]
            size, checksum = len(data), sha256(data)
        else:
            with path.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            size = path.stat().st_size
        rows.append({'path': name, 'size': size, 'sha256': checksum})
    return json_bytes({'version': 1, 'files': rows})


def publish(root: Path, updates: dict[str, bytes]) -> None:
    """Stage the whole overlay, then publish with rollback on an I/O failure.

    Close the game before using this tool: multiple files are not one filesystem
    transaction. If interrupted by a power loss, restore the source backup.
    """
    paths = {name: safe_path(root, name) for name in updates}
    for path in paths.values():
        if path.exists() and not path.is_file():
            raise ValueError(f'Expected a regular destination file: {path}')
    with tempfile.TemporaryDirectory(prefix='.fixed-sprites-', dir=root) as work:
        staged, backups = {}, {}
        for index, (name, data) in enumerate(updates.items()):
            staged[name] = Path(work) / f'{index}.new'
            staged[name].write_bytes(data)
            if paths[name].exists():
                backups[name] = Path(work) / f'{index}.old'
                shutil.copy2(paths[name], backups[name])
        changed = []
        try:
            for name, path in paths.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged[name], path)
                changed.append(name)
        except BaseException:
            for name in reversed(changed):
                if name in backups:
                    os.replace(backups[name], paths[name])
                else:
                    paths[name].unlink(missing_ok=True)
            raise


def reapply(source: Path, root: Path = ROOT) -> dict:
    root = root.resolve()
    if (safe_path(root, 'data/fixed_sprites_v111.json').is_file()
            or safe_path(root, 'data/varieties_v120.json').is_file()):
        raise ValueError('v1.1.1 sprite fixes are installed. Refusing to roll them back with the older pack. '
                         'Use tools/fixed_sprites_v111.py --source with the v1.1.1 input folder instead.')
    if not source.is_dir():
        raise ValueError('Supply the extracted fixed-sprite folder, not the RAR file.')
    record = read_record(root)
    actual = defaultdict(list)
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError(f'Symlink in input folder: {path}')
        if path.is_file() and path.suffix.lower() == '.png':
            actual[path.name].append(path)
    expected_names = {row['source'] for row in record['inputs']}
    if set(actual) != expected_names or any(len(paths) != 1 for paths in actual.values()):
        missing, extra = sorted(expected_names - set(actual)), sorted(set(actual) - expected_names)
        raise ValueError(f'Expected all {len(expected_names)} original PNGs exactly once. '
                         f'Missing: {missing[:8]}; unexpected: {extra[:8]}; duplicate names are not allowed.')
    updates = {}
    # Verify rejected duplicate variants too: all supplied input bytes are accounted for.
    for row in record['inputs']:
        data = actual[row['source']][0].read_bytes()
        validate_png(data, row)
        if row['selected']:
            updates[row['path']] = data
    for row in record['replacements']:
        validate_png(updates[row['path']], row)
        current = safe_path(root, row['path'])
        if not current.is_file() or sha256(current.read_bytes()) not in (row['original_sha256'], row['sha256']):
            raise ValueError(f'Destination is not the supplied baseline or this installed patch: {row["path"]}')
    catalog = json.loads(safe_path(root, 'data/catalog.json').read_text(encoding='utf-8'))
    previous = copy.deepcopy(catalog)
    entries = {entry['id']: entry for entry in catalog['species']}
    for item in record['species']:
        sid = item['id']
        if sid not in entries or entries[sid].get('paradox'):
            raise ValueError(f'Expected the existing normal species: {sid}')
        art = absolute_art(item)
        for value in (*art['sprites'].values(), *(path for seq in art['animations'].values() for path in seq)):
            if value not in updates and not safe_path(root, value).is_file():
                raise ValueError(f'Missing retained animation frame: {value}')
        entries[sid].update(art)
        updates[item['sidecar']] = json_bytes(item['animation'])
    if non_art_catalog(previous) != non_art_catalog(catalog):
        raise ValueError('Refusing to change gameplay fields during an art update.')
    updates['data/catalog.json'] = json_bytes(catalog)
    sources = json.loads(safe_path(root, 'data/source_assets.json').read_text(encoding='utf-8'))
    kind = record['provenance']['kind']
    sources = [row for row in sources if row.get('kind') != kind] + [record['provenance']]
    updates['data/source_assets.json'] = json_bytes(sources)
    updates['data/asset_manifest.json'] = create_manifest(root, updates)
    publish(root, updates)
    return {'updated_files': len(updates), **record['counts']}


def verify(root: Path = ROOT) -> dict:
    root = root.resolve()
    if safe_path(root, 'data/fixed_sprites_v111.json').is_file():
        from tools.fixed_sprites_v111 import verify as verify_latest
        return verify_latest(root)
    record = read_record(root)
    catalog = json.loads(safe_path(root, 'data/catalog.json').read_text(encoding='utf-8'))
    entries = {entry['id']: entry for entry in catalog['species']}
    affected = {item['id'] for item in record['species']}
    reachable = set()
    from tools.import_assets import animation_override
    for item in record['species']:
        sidecar_path = safe_path(root, item['sidecar'])
        if json.loads(sidecar_path.read_text(encoding='utf-8')) != item['animation']:
            raise ValueError(f'Animation sidecar mismatch: {item["id"]}')
        art = absolute_art(item)
        if animation_override(safe_path(root, item['directory']), root) != art:
            raise ValueError(f'Catalog rebuild would change art: {item["id"]}')
        if item['id'] not in entries or any(entries[item['id']].get(key) != value for key, value in art.items()):
            raise ValueError(f'Catalog art mismatch: {item["id"]}')
        reachable.update(art['sprites'].values())
        reachable.update(path for seq in art['animations'].values() for path in seq)
    for row in record['replacements']:
        validate_png(safe_path(root, row['path']).read_bytes(), row)
        if row['path'] not in reachable:
            raise ValueError(f'Fixed sprite has no runtime reference: {row["path"]}')
    sources = json.loads(safe_path(root, 'data/source_assets.json').read_text(encoding='utf-8'))
    matching = [row for row in sources if row.get('kind') == record['provenance']['kind']]
    if matching != [record['provenance']]:
        raise ValueError('Fixed-sprite provenance record is missing or duplicated.')
    baseline = record['baseline']
    if object_hash(non_art_catalog(catalog)) != baseline['non_art_catalog_sha256']:
        raise ValueError('Non-art catalog data differs from the uploaded v1.0.1 baseline. '
                         'Review any intentional gameplay edits separately.')
    if object_hash([entry for entry in catalog['species'] if entry['id'] not in affected]) != baseline['unaffected_species_sha256']:
        raise ValueError('A species outside the supplied fixed-sprite pack changed.')
    from tools.build import verify_assets
    integrity = verify_assets(root)
    return {'status': 'verified', **record['counts'], 'catalog_species': len(entries),
            'gameplay_unchanged': True, 'unaffected_species_unchanged': len(entries) - len(affected),
            'manifest_files': integrity['files'], 'manifest_sha256': integrity['manifest_sha256']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--verify', action='store_true', help='Check every fixed PNG, animation, gameplay fingerprint and build manifest.')
    action.add_argument('--source', type=Path, help='Reapply from the extracted original folder containing all 711 PNGs.')
    parser.add_argument('--root', type=Path, default=ROOT, help='v1.0.1 source root (defaults to this script\'s project).')
    args = parser.parse_args(argv)
    try:
        result = verify(args.root) if args.verify else reapply(args.source, args.root)
    except (OSError, ValueError, KeyError, RuntimeError, ImportError) as exc:
        print(f'Fixed-sprite check failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
