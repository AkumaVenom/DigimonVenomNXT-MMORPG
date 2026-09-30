#!/usr/bin/env python3
"""Verify or reapply FixedSpritesPart2 v1.1.1 on the uploaded v1.1.0 art baseline.

Installation is an ordinary source-root file overlay. PNGs are never re-encoded.
The historical v1.1.0 record stays immutable; this record supersedes only its
explicitly listed paths. Full verification uses the normal build verifier.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import fixed_sprites as legacy

RECORD_PATH = 'data/fixed_sprites_v111.json'
PATCH_ID = 'fixed_sprites_v111_for_v110'
VARIETIES_RECORD = 'data/varieties_v120.json'
VARIETIES_BASELINE = 'data/varieties_v120_baseline.json'


def release_baseline_catalog(root: Path, catalog: dict) -> dict:
    """Validate v1.2.0 preservation against the archived, historical catalog.

    The v1.1.1 fingerprints describe the old release, including its old Paradox
    art and runtime. A new release may replace those deliberately, but every
    normal species must still have its original art routes and gameplay, and
    Paradox species must keep their original gameplay. The returned snapshot
    is also checked against the immutable v1.1.1 fingerprints by the caller.
    Simply adding a release marker cannot disable those historical checks.
    """
    from tools.import_firewall_v150 import historical_catalog
    catalog = historical_catalog(root, catalog)
    path = legacy.safe_path(root, VARIETIES_RECORD)
    if not path.is_file():
        if catalog.get('version') in {'1.2.0', '1.3.0', '1.4.0', '1.5.0'}:
            raise ValueError('Missing v1.2.0 variety preservation record.')
        return catalog
    release = json.loads(path.read_text(encoding='utf-8'))
    if (release.get('version') != 1 or release.get('release') != '1.2.0'
            or catalog.get('version') not in {'1.2.0', '1.3.0', '1.4.0', '1.5.0'}
            or release.get('baseline_catalog_path') != VARIETIES_BASELINE):
        raise ValueError('Unsupported v1.2.0 variety preservation record.')
    data = legacy.safe_path(root, VARIETIES_BASELINE).read_bytes()
    if legacy.sha256(data) != release.get('baseline_catalog_sha256'):
        raise ValueError('Historical v1.2.0 baseline catalog checksum differs.')
    historical = json.loads(data)
    original = {entry['id']: entry for entry in historical['species']}
    entries = {entry['id']: entry for entry in catalog['species']}
    if len(original) != len(historical['species']) or len(entries) != len(catalog['species']):
        raise ValueError('Duplicate species in the historical or current catalog.')
    normal_ids = {sid for sid, entry in original.items() if not entry.get('paradox')}
    paradox_ids = {sid + '_paradox' for sid in normal_ids}
    shiny_ids = {sid + '_shiny' for sid in normal_ids}
    if (set(original) != normal_ids | paradox_ids
            or set(entries) != normal_ids | paradox_ids | shiny_ids
            or release.get('normal_ids') != sorted(normal_ids)
            or set(release.get('baseline_normal_sha256', {})) != normal_ids
            or set(release.get('baseline_paradox_mechanics_sha256', {})) != paradox_ids):
        raise ValueError('v1.2.0 species do not match the complete historical catalog.')
    for sid in normal_ids | paradox_ids:
        is_paradox = sid in paradox_ids
        excluded = {'shiny', 'variety'} | (set(legacy.ART_KEYS) if is_paradox else set())
        before = {k: v for k, v in original[sid].items() if k not in excluded}
        current = {k: v for k, v in entries[sid].items() if k not in excluded}
        key = 'baseline_paradox_mechanics_sha256' if is_paradox else 'baseline_normal_sha256'
        if legacy.object_hash(before) != release[key][sid]:
            raise ValueError(f'v1.2.0 preservation hash is not historical: {sid}')
        if current != before:
            raise ValueError(f'Non-art catalog or protected normal art changed: {sid}')
        if (entries[sid].get('shiny') is not False
                or entries[sid].get('variety') != ('paradox' if is_paradox else 'normal')):
            raise ValueError(f'Invalid original species variety: {sid}')
    return historical


def read_record(root: Path = ROOT) -> dict:
    root = root.resolve()
    record = json.loads(legacy.safe_path(root, RECORD_PATH).read_text(encoding='utf-8'))
    if record.get('version') != 1 or record.get('patch_id') != PATCH_ID:
        raise ValueError('Unsupported v1.1.1 fixed-sprite record.')
    inputs = {r['source']: r for r in record['inputs']}
    targets = {r['path']: r for r in record['replacements']}
    species = {s['id']: s for s in record['species']}
    if (len(inputs) != len(record['inputs']) or len(targets) != len(record['replacements'])
            or len(species) != len(record['species'])):
        raise ValueError('Duplicate source, destination or species in v1.1.1 record.')
    for name, row in inputs.items():
        if PurePosixPath(name).name != name or any(c in name for c in ('\\', ':', '\x00')):
            raise ValueError(f'Unsafe source filename: {name!r}')
        selected = targets.get(row['path'])
        if not selected or selected['mapping'] != 'direct' or selected['source'] != name:
            raise ValueError(f'Input has no unique direct replacement: {name}')
    for name, row in targets.items():
        legacy.safe_path(root, name)
        item = species.get(row['species_id'])
        if not item or not name.startswith(item['directory'] + '/') or '/Paradox/' in name:
            raise ValueError(f'Destination is outside its normal species: {name}')
        supplied = inputs.get(row['source'])
        if not supplied or any(row[k] != supplied[k] for k in
                               ('size', 'sha256', 'dimensions', 'rgba_sha256', 'species_id')):
            raise ValueError(f'Replacement does not preserve its source PNG: {name}')
        expected_kind = 'frame' if '/Frames/' in name else 'primary' if name.endswith('_Primary.png') else 'pose'
        if row['kind'] != expected_kind:
            raise ValueError(f'Wrong replacement kind: {name}')
        if row['mapping'] == 'pose_alias':
            original = targets.get(row.get('equivalent_to'))
            if (not original or original['mapping'] != 'direct'
                    or original['source'] != row['source']
                    or row['equivalence']['basis'] not in
                    ('baseline_rgba_identity', 'v110_original_byte_identity')):
                raise ValueError(f'Unproven same-pose copy: {name}')
        elif row['mapping'] != 'direct':
            raise ValueError(f'Unknown replacement mapping: {name}')
    for item in species.values():
        legacy.safe_path(root, item['directory'])
        if item['sidecar'] != item['directory'] + '/animation.json':
            raise ValueError(f'Invalid animation sidecar: {item["id"]}')
        legacy.safe_path(root, item['sidecar'])
        # The shared helper validates every local animation and mirror path.
        legacy.absolute_art(item)
    compatibility = record['legacy_compatibility']
    superseded = compatibility['superseded_paths']
    if len(set(superseded)) != len(superseded) or not set(superseded) <= targets.keys():
        raise ValueError('Invalid superseded v1.1.0 path list.')
    expected = {'source_images': len(inputs), 'canonical_replacements': len(targets),
                'direct_replacements': sum(r['mapping'] == 'direct' for r in targets.values()),
                'pose_aliases': sum(r['mapping'] == 'pose_alias' for r in targets.values()),
                'animation_frames': sum(r['kind'] == 'frame' for r in targets.values()),
                'primary_images': sum(r['kind'] == 'primary' for r in targets.values()),
                'labelled_poses': sum(r['kind'] == 'pose' for r in targets.values()),
                'species': len(species), 'new_sidecars': sum(not s['had_sidecar'] for s in species.values()),
                'superseded_v110_replacements': len(superseded)}
    if expected != record['counts'] or expected['direct_replacements'] != len(inputs):
        raise ValueError('Inconsistent v1.1.1 replacement counts.')
    return record


def effective_legacy_record(root: Path = ROOT) -> dict:
    """An in-memory view for legacy tests; never rewrite historical input records."""
    original = copy.deepcopy(legacy.read_record(root))
    if not legacy.safe_path(root, RECORD_PATH).is_file():
        return original
    current = read_record(root)
    rows = {r['path']: r for r in current['replacements']}
    species = {s['id']: s for s in current['species']}
    for row in original['replacements']:
        newer = rows.get(row['path'])
        if newer:
            # Preserve v1.0.1 originals and its historical dimension-change audit.
            for key in ('source', 'size', 'sha256', 'rgba_sha256', 'dimensions'):
                row[key] = newer[key]
    original['species'] = [copy.deepcopy(species.get(s['id'], s)) for s in original['species']]
    return original


def check_protected(root: Path, record: dict, catalog: dict) -> None:
    baseline = record['baseline']
    preserved = release_baseline_catalog(root, catalog)
    if legacy.object_hash(legacy.non_art_catalog(preserved)) != baseline['non_art_catalog_sha256']:
        raise ValueError('Non-art catalog fields differ from the uploaded baseline. Review intentional gameplay edits separately.')
    affected = {s['id'] for s in record['species']}
    untouched = [e for e in preserved['species'] if e['id'] not in affected]
    if (len(untouched) != baseline['unaffected_species_count']
            or legacy.object_hash(untouched) != baseline['unaffected_species_sha256']):
        raise ValueError('An unaffected species record changed.')
    # Runtime and global data are intentionally upgraded in v1.2.0. The old
    # art-only release retains its original strict, whole-installation checks.
    if preserved is catalog:
        for row in baseline['protected_data'] + baseline['runtime_python_files']:
            if legacy.sha256(legacy.safe_path(root, row['path']).read_bytes()) != row['sha256']:
                raise ValueError(f'Unrelated baseline file changed: {row["path"]}')
    old_bytes = legacy.safe_path(root, 'data/fixed_sprites_v110.json').read_bytes()
    if legacy.sha256(old_bytes) != baseline['v110_record_sha256']:
        raise ValueError('The historical v1.1.0 sprite record was modified.')


def verify(root: Path = ROOT, *, sprites_only: bool = False) -> dict:
    root = root.resolve()
    record = read_record(root)
    catalog = json.loads(legacy.safe_path(root, 'data/catalog.json').read_text(encoding='utf-8'))
    entries = {e['id']: e for e in catalog['species']}
    check_protected(root, record, catalog)
    previous = legacy.read_record(root)
    oldrows = {r['path']: r for r in previous['replacements']}
    current_rows = {r['path']: r for r in record['replacements']}
    superseded = set(oldrows) & current_rows.keys()
    if superseded != set(record['legacy_compatibility']['superseded_paths']):
        raise ValueError('v1.1.0 supersession list does not match the installed fixes.')
    for name in superseded:
        if oldrows[name]['sha256'] != current_rows[name]['original_sha256']:
            raise ValueError(f'v1.1.1 is not based on the recorded v1.1.0 sprite: {name}')
    # Check both generations of artwork, with v1.1.1 taking precedence only where recorded.
    effective_rows = {**oldrows, **current_rows}
    effective_species = {s['id']: s for s in previous['species']}
    effective_species.update({s['id']: s for s in record['species']})
    from tools.import_assets import animation_override
    reachable = set()
    for sid, item in effective_species.items():
        art = legacy.absolute_art(item)
        actual = json.loads(legacy.safe_path(root, item['sidecar']).read_text(encoding='utf-8'))
        if actual != item['animation']:
            raise ValueError(f'Animation sidecar differs: {sid}')
        if animation_override(legacy.safe_path(root, item['directory']), root) != art:
            raise ValueError(f'A catalog rebuild would change sprite routes: {sid}')
        if sid not in entries or any(entries[sid].get(k) != value for k, value in art.items()):
            raise ValueError(f'Catalog and sidecar do not agree: {sid}')
        reachable.update(art['sprites'].values())
        reachable.update(p for seq in art['animations'].values() for p in seq)
        reachable.update(art['mirrored_frames'].values())
    for name, row in effective_rows.items():
        legacy.validate_png(legacy.safe_path(root, name).read_bytes(), row)
        if name not in reachable:
            raise ValueError(f'Corrected image has no runtime route: {name}')
    for item in record['species']:
        before, current = item['before_art'], legacy.absolute_art(item)
        if before['animations'] != current['animations']:
            raise ValueError(f'Existing animation sequence changed: {item["id"]}')
        if {k:v for k,v in before['sprites'].items() if k != 'front'} != {k:v for k,v in current['sprites'].items() if k != 'front'}:
            raise ValueError(f'Existing pose assignment changed: {item["id"]}')
    sources = json.loads(legacy.safe_path(root, 'data/source_assets.json').read_text(encoding='utf-8'))
    for generation in (previous, record):
        expected = generation['provenance']
        if [r for r in sources if r.get('kind') == expected['kind']] != [expected]:
            raise ValueError(f'Missing or duplicated provenance: {expected["kind"]}')
    union_ids = set(effective_species)
    compatibility = record['legacy_compatibility']
    preserved = release_baseline_catalog(root, catalog)
    upgraded = preserved is not catalog
    unchanged = [e for e in preserved['species'] if e['id'] not in union_ids]
    if (len(unchanged) != compatibility['unaffected_by_either_pack_count']
            or legacy.object_hash(unchanged) != compatibility['unaffected_by_either_pack_sha256']):
        raise ValueError('A species outside both fixed-sprite packs changed.')
    manifest_path = legacy.safe_path(root, 'data/asset_manifest.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    rows = {r['path']: r for r in manifest['files']}
    if manifest.get('version') != 1 or len(rows) != len(manifest['files']):
        raise ValueError('Invalid manifest schema or duplicate paths.')
    from tools.build import catalog_paths, verify_assets
    required = (set(catalog_paths(catalog)) | set(effective_rows) |
                {s['sidecar'] for s in effective_species.values()} |
                {RECORD_PATH, legacy.RECORD_PATH, 'data/catalog.json', 'data/source_assets.json'})
    if upgraded:
        required.update((VARIETIES_RECORD, VARIETIES_BASELINE))
    if not required <= rows.keys():
        raise ValueError(f'Missing manifest records: {sorted(required - rows.keys())[:5]}')
    checked = 0
    if sprites_only:
        # Explicitly scoped mode, never represented as full build/media verification.
        for name, row in rows.items():
            legacy.safe_path(root, name)
            if name.startswith(('assets/digimon/', 'data/')):
                data = legacy.safe_path(root, name).read_bytes()
                if len(data) != row['size'] or legacy.sha256(data) != row['sha256']:
                    raise ValueError(f'Manifest mismatch: {name}')
                checked += 1
        for p in (root / 'assets/digimon').rglob('*'):
            if (p.is_file() and not any(part.startswith('.rsync-tmp') for part in p.parts)
                    and p.relative_to(root).as_posix() not in rows):
                raise ValueError(f'Unmanifested Digimon asset: {p.relative_to(root)}')
    else:
        checked = verify_assets(root)['files']
    normal_count = sum(e.get('variety', 'paradox' if e.get('paradox') else 'normal') == 'normal'
                       and not e.get('shiny') and not e.get('firewall')
                       for e in preserved['species'])
    return {'status': 'verified', 'sprite_pack': '1.1.1', **record['counts'],
            'scope': 'sprites-and-data-only' if sprites_only else 'full-build-manifest',
            'full_build_integrity_checked': not sprites_only,
            'catalog_species': len(entries), 'gameplay_unchanged': not upgraded,
            'original_species_mechanics_unchanged': True,
            'normal_species_unchanged': normal_count,
            'unaffected_species_unchanged': (normal_count
                                             if upgraded else len(entries)) - len(record['species']),
            'retained_v110_replacements': len(oldrows) - len(superseded),
            'both_packs_effective_replacements': len(effective_rows),
            'manifest_files': len(rows), 'manifest_files_hashed': checked,
            'manifest_sha256': legacy.sha256(manifest_path.read_bytes())}


def merge_manifest(root: Path, updates: dict[str, bytes]) -> bytes:
    """Preserve untouched integrity records; never drop audio or other media."""
    manifest = json.loads(legacy.safe_path(root, 'data/asset_manifest.json').read_text(encoding='utf-8'))
    rows = {r['path']: r for r in manifest['files']}
    if manifest.get('version') != 1 or len(rows) != len(manifest['files']):
        raise ValueError('Cannot update an invalid asset manifest.')
    for name in rows:
        legacy.safe_path(root, name)
    for name, data in updates.items():
        if name.startswith('assets/') or (name.startswith('data/') and name.endswith('.json')
                                          and name != 'data/asset_manifest.json'):
            rows[name] = {'path': name, 'size': len(data), 'sha256': legacy.sha256(data)}
    return legacy.json_bytes({'version': 1, 'files': [rows[name] for name in sorted(rows)]})


def reapply(source: Path, root: Path = ROOT) -> dict:
    """Accept all 68 exact input PNGs and publish a validated, rollback-safe overlay."""
    root = root.resolve()
    if not source.is_dir() or source.is_symlink():
        raise ValueError('Supply an extracted fixed-sprite directory, not a RAR or symlink.')
    record = read_record(root)
    actual = {}
    for p in source.rglob('*'):
        if p.is_symlink():
            raise ValueError(f'Symlink in source folder: {p}')
        if p.is_file() and p.suffix.lower() == '.png':
            if p.name in actual:
                raise ValueError(f'Duplicate source filename: {p.name}')
            actual[p.name] = p
    expected = {r['source'] for r in record['inputs']}
    if set(actual) != expected:
        raise ValueError(f'Expected all {len(expected)} input PNGs exactly once. '
                         f'Missing: {sorted(expected - actual.keys())[:5]}; '
                         f'unexpected: {sorted(actual.keys() - expected)[:5]}')
    buffers = {}
    # Nothing is written before every supplied image has passed checksum/pixel checks.
    for row in record['inputs']:
        data = actual[row['source']].read_bytes()
        legacy.validate_png(data, row)
        buffers[row['source']] = data
    updates = {}
    for row in record['replacements']:
        target = legacy.safe_path(root, row['path'])
        if (not target.is_file() or legacy.sha256(target.read_bytes()) not in
                (row['original_sha256'], row['sha256'])):
            raise ValueError(f'Not the supplied v1.1.0 baseline or installed v1.1.1 fix: {row["path"]}')
        updates[row['path']] = buffers[row['source']]
    catalog = json.loads(legacy.safe_path(root, 'data/catalog.json').read_text(encoding='utf-8'))
    check_protected(root, record, catalog)
    before = copy.deepcopy(catalog)
    entries = {e['id']: e for e in catalog['species']}
    for item in record['species']:
        entry = entries.get(item['id'])
        if not entry or entry.get('paradox'):
            raise ValueError(f'Missing normal species: {item["id"]}')
        old_art = {k:entry[k] for k in legacy.ART_KEYS if k in entry}
        art = legacy.absolute_art(item)
        if old_art not in (item['before_art'], art):
            raise ValueError(f'Unrecognized sprite assignments: {item["id"]}')
        for path in (*art['sprites'].values(), *(p for seq in art['animations'].values() for p in seq),
                     *art['mirrored_frames'].values()):
            if path not in updates and not legacy.safe_path(root, path).is_file():
                raise ValueError(f'Missing retained pose: {path}')
        entry.update(art)
        updates[item['sidecar']] = legacy.json_bytes(item['animation'])
    if legacy.non_art_catalog(before) != legacy.non_art_catalog(catalog):
        raise ValueError('Refusing to modify gameplay fields in an art patch.')
    updates['data/catalog.json'] = legacy.json_bytes(catalog)
    sources = json.loads(legacy.safe_path(root, 'data/source_assets.json').read_text(encoding='utf-8'))
    kind = record['provenance']['kind']
    # Keep provenance order stable when a later release follows this patch.
    position = next((i for i, row in enumerate(sources) if row.get('kind') == kind), len(sources))
    sources = [r for r in sources if r.get('kind') != kind]
    sources.insert(position, record['provenance'])
    updates['data/source_assets.json'] = legacy.json_bytes(sources)
    updates[RECORD_PATH] = legacy.safe_path(root, RECORD_PATH).read_bytes()
    updates['data/asset_manifest.json'] = merge_manifest(root, updates)
    legacy.publish(root, updates)
    return {'status': 'reapplied', 'updated_files': len(updates), **record['counts']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--verify', action='store_true', help='Verify both sprite generations and the full build manifest.')
    action.add_argument('--source', type=Path, help='Reapply from the extracted folder containing all 68 supplied PNGs.')
    parser.add_argument('--root', type=Path, default=ROOT, help='Source root (defaults to this script\'s project).')
    parser.add_argument('--sprites-only', action='store_true', help='With --verify, check Digimon assets/data but not unrelated media.')
    args = parser.parse_args(argv)
    if args.sprites_only and not args.verify:
        parser.error('--sprites-only requires --verify')
    try:
        result = verify(args.root, sprites_only=args.sprites_only) if args.verify else reapply(args.source, args.root)
    except (OSError, ValueError, KeyError, RuntimeError, ImportError) as exc:
        print(f'v1.1.1 fixed-sprite check failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
