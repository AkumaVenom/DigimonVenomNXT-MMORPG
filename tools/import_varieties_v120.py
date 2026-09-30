#!/usr/bin/env python3
"""Install or verify the supplied Cyber Paradox and Shiny sprite varieties.

Use --source with the extracted pack's ``digimon`` directory. PNG bytes are
copied unchanged. Current normal pose selections, including repaired frames and
mirrors, are mapped to each variety; sheets are never guessed or auto-cycled.
The existing catalog is retained, including maps, rules and existing species IDs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fixed_sprites import ART_KEYS, create_manifest, json_bytes, object_hash, safe_path

RECORD = 'data/varieties_v120.json'
BASELINE = 'data/varieties_v120_baseline.json'
KINDS = ('Paradox', 'Shiny')
ADDED_KEYS = {'shiny', 'variety'}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def is_sync_temp(path: Path) -> bool:
    return any(part.startswith('.rsync-tmp') for part in path.parts)


def art_paths(entry: dict) -> set[str]:
    return (set(entry['sprites'].values()) |
            {path for seq in entry['animations'].values() for path in seq} |
            set(entry.get('mirrored_frames', {})) |
            set(entry.get('mirrored_frames', {}).values()))


def base_directory(entry: dict) -> PurePosixPath:
    parts = PurePosixPath(entry['sprites']['idle']).parts
    if len(parts) < 5 or parts[:2] != ('assets', 'digimon'):
        raise ValueError(f'Unexpected species directory: {entry["id"]}')
    directory = PurePosixPath(*parts[:4])
    if any(not PurePosixPath(p).is_relative_to(directory) for p in art_paths(entry)):
        raise ValueError(f'Species art escapes its directory: {entry["id"]}')
    return directory


def retained_entry(entry: dict, art: bool = True) -> dict:
    return {key: value for key, value in entry.items()
            if key not in ADDED_KEYS and (art or key not in ART_KEYS)}


def mapped_art(normal: dict, source: Path, kind: str) -> tuple[dict, dict]:
    directory = base_directory(normal)
    source_dir = source / directory.relative_to('assets/digimon') / kind
    if not source_dir.is_dir():
        raise ValueError(f'Missing {kind} sprite folder: {normal["id"]}')

    # Normalize only the explicit Paradox filename marker, including species
    # such as JustimonBlitz_Arm whose own name contains an underscore.
    lookup = {}
    for path in source_dir.rglob('*.png'):
        local = path.relative_to(source_dir)
        filename = local.name.replace('_Paradox', '', 1) if kind == 'Paradox' else local.name
        key = local.with_name(filename).as_posix()
        if key in lookup:
            raise ValueError(f'Ambiguous variant frame: {source_dir}/{key}')
        lookup[key] = local.as_posix()

    def frame(path: str) -> str:
        local = PurePosixPath(path).relative_to(directory).as_posix()
        if local not in lookup:
            raise ValueError(f'Missing {kind} replacement for {path}')
        return lookup[local]

    sidecar_path = source_dir / 'animation.json'
    sidecar = load(sidecar_path) if sidecar_path.is_file() else {'version': 1}
    sidecar.update({
        'sprites': {key: frame(path) for key, path in normal['sprites'].items()},
        'animations': {key: [frame(path) for path in paths]
                       for key, paths in normal['animations'].items()},
        'mirrored_frames': {frame(path): frame(mirror)
                            for path, mirror in normal.get('mirrored_frames', {}).items()},
        'source_frame_count': normal.get('source_frame_count', 0),
        'frame_selection': normal.get('frame_selection', 'Existing labeled pose selections retained'),
        'art_provenance': (
            f'User-supplied v1.2.0 {kind} PNG bytes preserved. Existing normal '
            'pose sequences and repaired-frame/mirror assignments retained.'),
    })
    variant_dir = directory / kind

    def absolute(path):
        return (variant_dir / path).as_posix()

    art = {
        'sprites': {key: absolute(path) for key, path in sidecar['sprites'].items()},
        'animations': {key: [absolute(path) for path in paths]
                       for key, paths in sidecar['animations'].items()},
        'mirrored_frames': {absolute(path): absolute(mirror)
                            for path, mirror in sidecar['mirrored_frames'].items()},
        **{key: sidecar[key] for key in ART_KEYS if key in sidecar and
           key not in ('sprites', 'animations', 'mirrored_frames')},
    }
    return art, sidecar


def verify(root: Path = ROOT, *, decode_images: bool = False) -> dict:
    root = root.resolve()
    catalog, record = load(root / 'data/catalog.json'), load(root / RECORD)
    # A later additive variety must prove that every installed v1.2 entry is
    # unchanged before this historical three-family verifier narrows its scope.
    from tools.import_firewall_v150 import historical_catalog
    catalog = historical_catalog(root, catalog)
    baseline_path = safe_path(root, record['baseline_catalog_path'])
    if digest(baseline_path) != record['baseline_catalog_sha256']:
        raise ValueError('Historical baseline catalog has changed.')
    entries = {entry['id']: entry for entry in catalog['species']}
    if len(entries) != len(catalog['species']):
        raise ValueError('Duplicate catalog species IDs.')
    normal_ids = set(record['normal_ids'])
    expected = normal_ids | {sid + '_paradox' for sid in normal_ids} | {sid + '_shiny' for sid in normal_ids}
    if set(entries) != expected:
        raise ValueError('Normal/Paradox/Shiny catalog coverage differs from the installed pack.')
    files = {row['path']: row for row in record['files']}
    for row in record['files']:
        path = safe_path(root, row['path'])
        if not path.is_file() or path.stat().st_size != row['size'] or digest(path) != row['sha256']:
            raise ValueError(f'Variety asset differs from the recorded installation: {row["path"]}')
        if decode_images and path.suffix.lower() == '.png':
            from PIL import Image
            with Image.open(path) as image:
                if image.mode != 'RGBA':
                    raise ValueError(f'Expected RGBA sprite: {row["path"]}')
                image.verify()
    actual = {p.relative_to(root).as_posix()
              for kind in KINDS for d in (root / 'assets/digimon').glob(f'*/*/{kind}')
              for p in d.rglob('*') if p.is_file() and not is_sync_temp(p)}
    if actual != set(files):
        raise ValueError('Unrecorded/stale or missing files in a variety directory: '
                         f'extra={sorted(actual-set(files))[:5]}, missing={sorted(set(files)-actual)[:5]}')
    for sid in sorted(normal_ids):
        normal = entries[sid]
        if object_hash(retained_entry(normal)) != record['baseline_normal_sha256'][sid]:
            raise ValueError(f'Normal art/mechanics changed while importing varieties: {sid}')
        for kind in ('normal', 'paradox', 'shiny'):
            entry = entries[sid if kind == 'normal' else sid + '_' + kind]
            if (entry.get('variety'), entry.get('paradox'), entry.get('shiny'), entry.get('base_id')) != (
                    kind, kind == 'paradox', kind == 'shiny', sid):
                raise ValueError(f'Invalid variety flags for {entry["id"]}')
            for path in art_paths(entry):
                if not safe_path(root, path).is_file():
                    raise ValueError(f'Missing runtime sprite: {path}')
                if kind != 'normal' and (path not in files or f'/{kind.title()}/' not in path):
                    raise ValueError(f'Wrong variety runtime sprite: {path}')
        paradox, shiny = entries[sid + '_paradox'], entries[sid + '_shiny']
        if object_hash(retained_entry(paradox, art=False)) != record['baseline_paradox_mechanics_sha256'][paradox['id']]:
            raise ValueError(f'Existing Paradox mechanics changed: {sid}')
        for key in ('base_stats', 'stage', 'type', 'attribute', 'mechanics_status'):
            if shiny.get(key) != normal.get(key):
                raise ValueError(f'Shiny balance differs from normal: {sid}/{key}')
        expected_routes = [{**route, 'to': route['to'] + '_shiny'} for route in normal.get('evolutions', [])]
        if shiny.get('evolutions', []) != expected_routes:
            raise ValueError(f'Shiny evolution changes variety: {sid}')
        for kind, entry in [('Paradox', paradox), ('Shiny', shiny)]:
            directory = base_directory(normal) / kind
            from tools.import_assets import animation_override
            if any(entry.get(key) != value for key, value in
                   animation_override(root / directory, root).items()):
                raise ValueError(f'Animation sidecar differs from runtime catalog: {entry["id"]}')
    return {'status': 'verified', **record['counts']}


def install(source: Path, root: Path = ROOT, *, volumes: Path | None = None) -> dict:
    source, root = source.resolve(), root.resolve()
    if not source.is_dir():
        raise ValueError('Supply the extracted sprite pack digimon directory.')
    if source.is_relative_to(root / 'assets'):
        raise ValueError('Use a separate extracted source directory, not installed game assets.')
    catalog = load(root / 'data/catalog.json')
    if (root / 'data/firewall_v150.json').is_file():
        raise ValueError('FireWall is installed. Use the current FireWall importer; this historical three-variety installer would remove the fourth variety.')
    old_record = load(root / RECORD) if (root / RECORD).is_file() else None
    baseline_bytes = (root / BASELINE).read_bytes() if old_record else (root / 'data/catalog.json').read_bytes()
    entries = {entry['id']: entry for entry in catalog['species']}
    normals = [entry for entry in catalog['species'] if not entry.get('paradox') and not entry.get('shiny')]
    if len(normals) != 502:
        raise ValueError(f'This pack requires the 502-species baseline; found {len(normals)}.')
    baseline_normal = {s['id']: object_hash(retained_entry(s)) for s in normals}
    baseline_paradox = {s['id'] + '_paradox': object_hash(retained_entry(entries[s['id'] + '_paradox'], art=False))
                        for s in normals}
    if old_record and (baseline_normal != old_record['baseline_normal_sha256'] or
                       baseline_paradox != old_record['baseline_paradox_mechanics_sha256']):
        raise ValueError('Baseline species mechanics/art changed since v1.2.0 installation.')

    new_species, sidecars = [], {}
    normal_ids = {s['id'] for s in normals}
    for normal in normals:
        normal = copy.deepcopy(normal)
        sid = normal['id']
        normal.update(shiny=False, variety='normal')
        new_species.append(normal)
        for kind in KINDS:
            entry = copy.deepcopy(entries[sid + '_paradox'] if kind == 'Paradox' else normal)
            entry.update(id=sid + '_' + kind.lower(), name=kind + ' ' + normal['name'],
                         base_id=sid, shiny=kind == 'Shiny', paradox=kind == 'Paradox', variety=kind.lower())
            if kind == 'Shiny':
                if any(route['to'] not in normal_ids for route in normal.get('evolutions', [])):
                    raise ValueError(f'Unknown normal evolution destination for {sid}')
                entry['evolutions'] = [{**route, 'to': route['to'] + '_shiny'}
                                       for route in normal.get('evolutions', [])]
            art, sidecar = mapped_art(normal, source, kind)
            entry.update(art)
            new_species.append(entry)
            sidecars[(base_directory(normal) / kind / 'animation.json').as_posix()] = sidecar
    catalog['species'] = new_species
    # Reapplying the artwork on a later release must not downgrade its identity.
    from venom.version import VERSION
    catalog['version'] = VERSION

    source_dirs = sorted(source.glob('*/*/Paradox')) + sorted(source.glob('*/*/Shiny'))
    if len(source_dirs) != 1006:
        raise ValueError(f'Expected 1006 supplied variety directories, found {len(source_dirs)}.')
    # Stage complete replacements before touching the installed copy. Remove
    # every superseded file, then write canonical paths in place so filesystem
    # sync services observe fresh file modifications rather than stale renames.
    with tempfile.TemporaryDirectory(prefix='.varieties-v120-tmp-', dir=root) as work_name:
        work = Path(work_name)
        staged, source_files = work / 'new', []
        for directory in source_dirs:
            relative = directory.relative_to(source)
            target = staged / 'assets/digimon' / relative
            for path in directory.rglob('*'):
                if is_sync_temp(path):
                    continue
                if path.is_symlink():
                    raise ValueError(f'Symlink in supplied source: {path}')
                if path.is_file():
                    source_files.append({'path': path.relative_to(source).as_posix(),
                                         'size': path.stat().st_size, 'sha256': digest(path)})
            # Fresh modification times make these replacements unambiguous to
            # file-sync services, while copying the supplied bytes unchanged.
            shutil.copytree(directory, target, copy_function=shutil.copy,
                            ignore=shutil.ignore_patterns('.rsync-tmp*'))
        for name, value in sidecars.items():
            (staged / name).write_bytes(json_bytes(value))
        file_rows = [{'path': path.relative_to(staged).as_posix(), 'size': path.stat().st_size,
                      'sha256': digest(path)} for path in sorted(staged.rglob('*'))
                     if path.is_file() and not is_sync_temp(path)]
        provenance = {'kind': 'varieties_v120', 'release': '1.2.0',
                      'use': 'Complete Cyber Paradox replacement and new Shiny varieties; supplied PNG bytes unchanged',
                      'source_file_count': len(source_files),
                      'source_tree_sha256': object_hash(sorted(source_files, key=lambda x: x['path']))}
        if volumes:
            provenance['parts'] = [{'filename': path.name, 'size': path.stat().st_size, 'sha256': digest(path)}
                                   for path in sorted(volumes.glob('Digimon_Cyber_Paradox&Shiny_Varieties_Sprites.part*.rar'))]
        elif old_record:
            provenance = old_record['provenance']
        counts = {'normal_species': len(normals), 'paradox_species': len(normals), 'shiny_species': len(normals),
                  'total_species': len(new_species), 'source_pngs': sum(r['path'].endswith('.png') for r in source_files),
                  'installed_variety_files': len(file_rows), 'animation_sidecars': len(sidecars)}
        record = {'version': 1, 'release': '1.2.0', 'normal_ids': sorted(normal_ids), 'counts': counts,
                  'baseline_catalog_path': BASELINE,
                  'baseline_catalog_sha256': hashlib.sha256(baseline_bytes).hexdigest(),
                  'baseline_normal_sha256': baseline_normal,
                  'baseline_paradox_mechanics_sha256': baseline_paradox,
                  'provenance': provenance, 'files': file_rows,
                  'exceptions': [{'directory': '4 Champion/Shoutmon', 'status': 'missing_2d_source',
                                  'impact': 'None: baseline roster uses supplied Rookie Shoutmon. No Champion duplicate is added.'}]}
        sources = [s for s in load(root / 'data/source_assets.json') if s.get('kind') != 'varieties_v120'] + [provenance]
        updates = {'data/catalog.json': json_bytes(catalog), RECORD: json_bytes(record), BASELINE: baseline_bytes,
                   'data/source_assets.json': json_bytes(sources)}
        destinations = sorted({(PurePosixPath('assets/digimon') / p.relative_to(source)).as_posix() for p in source_dirs} |
                              {p.relative_to(root).as_posix() for kind in KINDS
                               for p in (root / 'assets/digimon').glob(f'*/*/{kind}')})
        changed = []
        try:
            for name in destinations:
                destination, replacement, backup = safe_path(root, name), staged / name, work / 'old' / name
                if destination.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(destination, backup, ignore=shutil.ignore_patterns('.rsync-tmp*'))
                changed.append((destination, backup))
                if replacement.exists():
                    desired = {p.relative_to(replacement) for p in replacement.rglob('*') if p.is_file()}
                    if destination.exists():
                        for path in destination.rglob('*'):
                            if path.is_file() and not is_sync_temp(path) and path.relative_to(destination) not in desired:
                                path.unlink()
                    shutil.copytree(replacement, destination, dirs_exist_ok=True, copy_function=shutil.copy,
                                    ignore=shutil.ignore_patterns('.rsync-tmp*'))
                elif destination.exists():
                    shutil.rmtree(destination)
            for name, data in updates.items():
                destination, backup = safe_path(root, name), work / 'old' / name
                if destination.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, backup)
                changed.append((destination, backup))
                destination.write_bytes(data)
            verify(root)
            (root / 'data/asset_manifest.json').write_bytes(create_manifest(root, {}))
        except BaseException:
            for destination, backup in reversed(changed):
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink(missing_ok=True)
                if backup.exists():
                    os.replace(backup, destination)
            raise
    return {'status': 'installed', **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--source', type=Path, help='Extracted sprite pack digimon directory')
    action.add_argument('--verify', action='store_true')
    parser.add_argument('--decode-images', action='store_true', help='Decode every PNG during verification')
    parser.add_argument('--volumes', type=Path, help='Optional original-volume directory for provenance hashes')
    args = parser.parse_args()
    result = (verify(args.root, decode_images=args.decode_images) if args.verify else
              install(args.source, args.root, volumes=args.volumes))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
