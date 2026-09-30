"""Byte-exact fixed art, complete routing, rebuild safety and patch isolation."""
from __future__ import annotations

import ast
import copy
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from tools import fixed_sprites as fixed
from tools.build import catalog_paths, verify_assets
from tools.import_assets import species_catalog

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / fixed.RECORD_PATH).read_text(encoding='utf-8'))
CATALOG = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
SPECIES = {entry['id']: entry for entry in CATALOG['species']}
HAS_V111 = (ROOT / 'data/fixed_sprites_v111.json').is_file()
HAS_V120 = (ROOT / 'data/varieties_v120.json').is_file()
if HAS_V111:
    from tools import fixed_sprites_v111 as latest
    LATEST = latest.read_record(ROOT)
    EFFECTIVE = latest.effective_legacy_record(ROOT)
else:
    EFFECTIVE = RECORD



def test_exact_input_accounting_and_duplicate_decisions():
    assert RECORD['counts'] == {'source_images': 711, 'canonical_replacements': 709,
                                'animation_frames': 584, 'primary_images': 125,
                                'species': 133, 'duplicate_inputs': 2}
    assert fixed.read_record(ROOT) == RECORD
    decisions = {row['selected']: row for row in RECORD['duplicate_resolutions']}
    assert decisions['Snimon_Frame_001-transparent.png']['pixel_identical'] is True
    assert decisions['CherubimonGood_Frame_002-transparent.png']['pixel_identical'] is False
    assert sum(row['selected'] for row in RECORD['inputs']) == 709
    assert len({row['source'] for row in RECORD['inputs']}) == 711


@pytest.mark.parametrize('row', EFFECTIVE['replacements'], ids=lambda row: row['source'])
def test_each_fixed_png_preserves_the_selected_supplied_bytes_and_pixels(row):
    data = (ROOT / row['path']).read_bytes()
    fixed.validate_png(data, row)
    assert fixed.sha256(data) != row['original_sha256']
    assert '-transparent' not in row['path']


def production_sprite_path():
    """Execute the actual pure resolver without importing unavailable SDL bindings.

    This is only a routing check. The separate runtime test module uses pygame
    itself and skips explicitly when that optional test environment is absent.
    """
    tree = ast.parse((ROOT / 'venom/client/assets.py').read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Assets')
    method = copy.deepcopy(next(node for node in cls.body
                                if isinstance(node, ast.FunctionDef) and node.name == 'sprite_path'))
    scope = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 'venom/client/assets.py', 'exec'), scope)
    return scope['sprite_path']


@pytest.fixture(scope='module')
def resolver():
    return production_sprite_path()


@pytest.mark.parametrize('item', RECORD['species'], ids=lambda item: item['id'])
def test_every_replacement_is_reachable_through_the_production_frame_resolver(item, resolver):
    entry = SPECIES[item['id']]
    selected = set()
    assets = SimpleNamespace(species=SPECIES)
    for motion, sequence in entry['animations'].items():
        for index, expected in enumerate(sequence):
            path = resolver(assets, item['id'], motion, index / 8)
            assert path == expected
            selected.add(path)
        assert resolver(assets, item['id'], motion, len(sequence) / 8) == sequence[0]
    for motion in entry['sprites']:
        for index in range(8):
            selected.add(resolver(assets, item['id'], motion, index / 8))
    assert {row['path'] for row in RECORD['replacements'] if row['species_id'] == item['id']} <= selected
    assert all((ROOT / path).is_file() for path in selected)


def test_daemon_uses_the_corrected_third_pose_and_real_attack():
    entry = SPECIES['daemon']
    prefix = 'assets/digimon/7 Mega/Daemon/Frames/'
    frames = [f'{prefix}Daemon_Frame_{index:03d}.png' for index in range(1, 5)]
    assert entry['sprites']['walk_right'] == frames[2]
    assert entry['animations']['walk'] == [frames[0], frames[1], frames[0], frames[2]]
    assert entry['animations']['idle'] == entry['animations']['walk']
    assert entry['animations']['attack'] == [frames[3], frames[0]]
    with Image.open(ROOT / frames[2]) as image:
        assert image.size == (201, 169)
    changed_dimensions = [row['source'] for row in RECORD['replacements']
                          if row['dimensions'] != row['original_dimensions']]
    assert changed_dimensions == ['Daemon_Frame_003-transparent.png']


def test_all_supplied_primary_images_have_explicit_front_portrait_routes():
    primaries = [row for row in RECORD['replacements'] if row['kind'] == 'primary']
    assert len(primaries) == 125
    for row in primaries:
        assert SPECIES[row['species_id']]['sprites']['front'] == row['path']


def test_full_species_catalog_rebuild_retains_all_fixed_pose_assignments():
    rebuilt = {entry['id']: entry for entry in species_catalog()}
    assert len(rebuilt) == len(SPECIES) == (2008 if (ROOT / "data/firewall_v150.json").is_file() else 1506 if HAS_V120 else 1004)
    for item in RECORD['species']:
        for key in fixed.ART_KEYS:
            assert rebuilt[item['id']][key] == SPECIES[item['id']][key], (item['id'], key)


def test_all_non_art_catalog_data_and_unaffected_species_are_unchanged():
    preserved = latest.release_baseline_catalog(ROOT, CATALOG) if HAS_V111 else CATALOG
    assert fixed.object_hash(fixed.non_art_catalog(preserved)) == RECORD['baseline']['non_art_catalog_sha256']
    affected = {item['id'] for item in RECORD['species']}
    expected_count = 871
    expected_hash = RECORD['baseline']['unaffected_species_sha256']
    if HAS_V111:
        affected.update(item['id'] for item in LATEST['species'])
        expected_count = LATEST['legacy_compatibility']['unaffected_by_either_pack_count']
        expected_hash = LATEST['legacy_compatibility']['unaffected_by_either_pack_sha256']
    untouched = [entry for entry in preserved['species'] if entry['id'] not in affected]
    assert len(untouched) == expected_count
    assert fixed.object_hash(untouched) == expected_hash
    assert sum(entry['paradox'] for entry in untouched) == 502


def test_fanglongmon_normal_custom_art_is_not_overwritten():
    sources = json.loads((ROOT / 'data/source_assets.json').read_text(encoding='utf-8'))
    fanglongmon = next(row for row in sources if row.get('kind') == 'fanglongmon_v100')
    assert len(fanglongmon['frames']) == 12
    for row in fanglongmon['frames']:
        if HAS_V120 and '/Paradox/' in row['path']:
            # v1.2.0 intentionally replaces Paradox artwork; normal art remains exact.
            continue
        assert fixed.sha256((ROOT / row['path']).read_bytes()) == row['sha256']


def test_manifest_contains_every_fixed_sprite_sidecar_and_catalog_reference():
    manifest = json.loads((ROOT / 'data/asset_manifest.json').read_text(encoding='utf-8'))
    entries = {row['path']: row for row in manifest['files']}
    assert len(entries) == len(manifest['files'])
    assert set(catalog_paths(CATALOG)) <= entries.keys()
    assert fixed.RECORD_PATH in entries
    for row in EFFECTIVE['replacements']:
        assert entries[row['path']]['sha256'] == row['sha256']
        assert entries[row['path']]['size'] == row['size']
    for item in RECORD['species']:
        assert item['sidecar'] in entries
    assert verify_assets(ROOT)['files'] == len(entries)
    assert len(entries) > 21970 if HAS_V120 else len(entries) == (21970 if HAS_V111 else 21954)


def test_verifier_checks_images_metadata_and_original_gameplay():
    result = fixed.verify(ROOT)
    assert result['status'] == 'verified'
    assert result['gameplay_unchanged'] is (not HAS_V120)
    if HAS_V120:
        assert result['original_species_mechanics_unchanged'] is True
        assert result['normal_species_unchanged'] == 502
    assert result['canonical_replacements'] == (75 if HAS_V111 else 709)


@pytest.mark.parametrize('name', ('../outside.png', '/outside.png', 'C:/outside.png',
                                  'assets/../../outside.png', 'assets\\outside.png',
                                  '', 'assets//image.png', 'assets/./image.png', 'a\x00b'))
def test_path_validation_rejects_unsafe_or_noncanonical_targets(tmp_path, name):
    with pytest.raises(ValueError, match='Unsafe'):
        fixed.safe_path(tmp_path, name)


def test_path_validation_rejects_symlinked_directories(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    root = tmp_path / 'source'
    root.mkdir()
    try:
        (root / 'assets').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Creating symlinks is not permitted on this test host.')
    with pytest.raises(ValueError, match='Symlink'):
        fixed.safe_path(root, 'assets/sprite.png')


def test_publish_rolls_back_completed_replacements_after_io_failure(tmp_path, monkeypatch):
    (tmp_path / 'old.txt').write_bytes(b'old value')
    original_replace = fixed.os.replace

    def failing_replace(source, destination):
        if Path(destination).name == 'fail.txt' and str(source).endswith('.new'):
            raise OSError('simulated disk error')
        return original_replace(source, destination)

    monkeypatch.setattr(fixed.os, 'replace', failing_replace)
    with pytest.raises(OSError, match='simulated'):
        fixed.publish(tmp_path, {'old.txt': b'new value', 'added.txt': b'new file', 'fail.txt': b'fail'})
    assert (tmp_path / 'old.txt').read_bytes() == b'old value'
    assert not (tmp_path / 'added.txt').exists()
    assert not (tmp_path / 'fail.txt').exists()


@pytest.fixture
def tiny_import(tmp_path):
    """A synthetic import fixture exercises safety without needing the user's RAR."""
    root, source = tmp_path / 'game', tmp_path / 'input'
    source.mkdir()
    directory = 'assets/digimon/4 Champion/Example'
    paths = [f'{directory}/Frames/Example_Frame_001.png', f'{directory}/Example_Primary.png']
    for name in ('data', directory + '/Frames'):
        (root / name).mkdir(parents=True, exist_ok=True)

    def png(color):
        image = Image.new('RGBA', (3, 3))
        image.putpixel((1, 1), color)
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()

    old, new = png((10, 20, 30, 255)), png((20, 40, 80, 255))
    inputs, replacements = [], []
    for path, name, kind in zip(paths, ('Example_Frame_001-transparent.png', 'Example_Primary-transparent.png'), ('frame', 'primary')):
        (source / name).write_bytes(new)
        (root / path).write_bytes(old)
        base = {'source': name, 'size': len(new), 'sha256': fixed.sha256(new), 'path': path, 'species_id': 'example'}
        inputs.append({**base, 'selected': True, 'selected_source': name})
        replacements.append({**base, 'original_sha256': fixed.sha256(old), 'kind': kind})
    animation = {'version': 1, 'sprites': {'idle': 'Frames/Example_Frame_001.png', 'front': 'Example_Primary.png'},
                 'animations': {'idle': ['Frames/Example_Frame_001.png'], 'walk': ['Frames/Example_Frame_001.png'],
                                'attack': ['Frames/Example_Frame_001.png']}, 'mirrored_frames': {},
                 'source_frame_count': 1, 'frame_selection': 'fixture', 'art_provenance': 'fixture'}
    catalog = {'version': '1.0.1', 'species': [{'id': 'example', 'paradox': False, 'base_stats': {'hp': 100},
                                             'sprites': {'idle': paths[0]}, 'evolutions': []}],
               'shop': {'do_not_change': 123}, 'maps': [], 'tamers': []}
    (root / 'data/catalog.json').write_bytes(fixed.json_bytes(catalog))
    (root / 'data/source_assets.json').write_bytes(fixed.json_bytes([{'kind': 'previous', 'value': 'keep'}]))
    record = {'version': 1, 'patch_id': 'fixed_sprites_v110_for_v101', 'inputs': inputs, 'replacements': replacements,
              'species': [{'id': 'example', 'directory': directory, 'sidecar': directory + '/animation.json', 'animation': animation}],
              'counts': {'source_images': 2, 'canonical_replacements': 2, 'animation_frames': 1, 'primary_images': 1,
                         'species': 1, 'duplicate_inputs': 0}, 'provenance': {'kind': 'fixed_sprites_v110', 'value': 'fixture'}}
    (root / fixed.RECORD_PATH).write_bytes(fixed.json_bytes(record))
    return root, source, catalog, paths, old


def test_reapply_is_idempotent_and_preserves_unrelated_gameplay_and_provenance(tiny_import):
    root, source, previous, paths, old = tiny_import
    fixed.reapply(source, root)
    first = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    fixed.reapply(source, root)
    second = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert second == first
    current = json.loads((root / 'data/catalog.json').read_text())
    assert fixed.non_art_catalog(previous) == fixed.non_art_catalog(current)
    sources = json.loads((root / 'data/source_assets.json').read_text())
    assert sources[0] == {'kind': 'previous', 'value': 'keep'}
    assert sum(row['kind'] == 'fixed_sprites_v110' for row in sources) == 1
    assert all((root / path).read_bytes() != old for path in paths)


@pytest.mark.parametrize('failure', ('missing', 'unexpected', 'corrupt', 'destination'))
def test_invalid_import_is_rejected_before_any_target_write(tiny_import, failure):
    root, source, previous, paths, old = tiny_import
    selected = source / 'Example_Frame_001-transparent.png'
    if failure == 'missing':
        selected.unlink()
    elif failure == 'unexpected':
        (source / 'Unexpected.png').write_bytes(selected.read_bytes())
    elif failure == 'corrupt':
        selected.write_bytes(b'not the supplied PNG')
    else:
        (root / paths[0]).write_bytes(b'unrelated local edit')
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):
        fixed.reapply(source, root)
    after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert after == before
