"""v1.1.1 byte preservation, alias evidence, manifest routing and safe reapplication."""
from __future__ import annotations
import ast
import copy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from tools import fixed_sprites as legacy
from tools import fixed_sprites_v111 as fixed
from tools.build import catalog_paths
from tools.import_assets import species_catalog

ROOT = Path(__file__).resolve().parents[1]
RECORD = fixed.read_record(ROOT)
CATALOG = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
SPECIES = {e['id']: e for e in CATALOG['species']}
HAS_V120 = (ROOT / fixed.VARIETIES_RECORD).is_file()
HAS_V150 = (ROOT / "data/firewall_v150.json").is_file()


def test_complete_input_and_output_accounting():
    assert RECORD['counts'] == {'source_images': 68, 'canonical_replacements': 75,
        'direct_replacements': 68, 'pose_aliases': 7, 'animation_frames': 59,
        'primary_images': 12, 'labelled_poses': 4, 'species': 20,
        'new_sidecars': 15, 'superseded_v110_replacements': 14}
    assert len({r['source'] for r in RECORD['inputs']}) == 68
    assert len({r['path'] for r in RECORD['replacements']}) == 75
    assert {r['source'] for r in RECORD['replacements']} == {r['source'] for r in RECORD['inputs']}


@pytest.mark.parametrize('row', RECORD['replacements'], ids=lambda r: r['path'])
def test_every_png_is_byte_and_pixel_exact_and_changed_from_the_baseline(row):
    data = (ROOT / row['path']).read_bytes()
    legacy.validate_png(data, row)
    assert row['sha256'] != row['original_sha256']
    assert row['dimensions'] == row['original_dimensions']
    assert '-transparent' not in row['path']
    assert '/Paradox/' not in row['path']


def production_resolver():
    tree = ast.parse((ROOT / 'venom/client/assets.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Assets')
    method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'sprite_path'))
    scope = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 'venom/client/assets.py', 'exec'), scope)
    return scope['sprite_path']


@pytest.mark.parametrize('item', RECORD['species'], ids=lambda s: s['id'])
def test_every_fixed_pose_and_portrait_resolves_through_real_client_method(item):
    resolver = production_resolver()
    entry = SPECIES[item['id']]
    assets = SimpleNamespace(species=SPECIES)
    reached = set()
    for motion, sequence in entry['animations'].items():
        for i, expected in enumerate(sequence):
            assert resolver(assets, item['id'], motion, i / 8) == expected
            reached.add(expected)
        assert resolver(assets, item['id'], motion, len(sequence) / 8) == sequence[0]
    assert resolver(assets, item['id'], 'front', 0) == entry['sprites']['front']
    reached.add(entry['sprites']['front'])
    expected = {r['path'] for r in RECORD['replacements'] if r['species_id'] == item['id']}
    assert expected <= reached
    assert all((ROOT / path).is_file() for path in reached)
    assert entry['animations'] == item['before_art']['animations']
    assert entry['source_frame_count'] == item['before_art']['source_frame_count']


def test_typos_are_explicitly_canonicalized_not_left_as_duplicate_assets():
    row = next(r for r in RECORD['inputs'] if r['source'] == 'Barbamon_Frame_002-.png')
    assert row['path'].endswith('/Frames/Barbamon_Frame_002.png')
    assert RECORD['filename_normalization']['explicit_name_corrections'] == {'Barbamon_Frame_002-.png': 'Barbamon_Frame_002.png'}


def test_pose_aliases_have_independent_baseline_evidence_and_identical_new_bytes():
    old = {r['path']: r for r in legacy.read_record(ROOT)['replacements']}
    aliases = [r for r in RECORD['replacements'] if r['mapping'] == 'pose_alias']
    assert len(aliases) == 7
    assert sum(r['equivalence']['basis'] == 'v110_original_byte_identity' for r in aliases) == 2
    for row in aliases:
        assert (ROOT / row['path']).read_bytes() == (ROOT / row['equivalent_to']).read_bytes()
        evidence = row['equivalence']
        if evidence['basis'] == 'v110_original_byte_identity':
            assert old[row['path']]['original_sha256'] == evidence['original_sha256']
            assert old[row['equivalent_to']]['original_sha256'] == evidence['original_sha256']
        else:
            assert evidence['dimensions'] == row['original_dimensions']
            assert len(evidence['rgba_sha256']) == 64


def test_skullknightmon_fixed_primary_is_also_used_by_idle_frame_copy():
    e = SPECIES['skullknightmon']
    assert (ROOT / e['sprites']['front']).read_bytes() == (ROOT / e['sprites']['idle']).read_bytes()
    alias = next(r for r in RECORD['replacements'] if r['path'] == e['sprites']['idle'])
    assert alias['source'] == 'Skullknightmon_Primary.png'
    assert alias['mapping'] == 'pose_alias'


def test_all_catalog_paths_and_new_assets_are_present_in_the_manifest():
    manifest = json.loads((ROOT / 'data/asset_manifest.json').read_text(encoding='utf-8'))
    rows = {r['path']:r for r in manifest['files']}
    assert manifest['version'] == 1
    assert len(rows) == len(manifest['files'])
    assert len(rows) > 21970 if HAS_V120 else len(rows) == 21970
    assert set(catalog_paths(CATALOG)) <= rows.keys()
    for row in RECORD['replacements']:
        assert rows[row['path']] == {k:row[k] for k in ('path', 'size', 'sha256')}
    names = [r['sidecar'] for r in RECORD['species']] + [fixed.RECORD_PATH, 'data/catalog.json', 'data/source_assets.json']
    for name in names:
        data = (ROOT / name).read_bytes()
        assert rows[name] == {'path':name, 'size':len(data), 'sha256':legacy.sha256(data)}
    audio_paths = {path for path in rows if path.startswith('assets/audio/')}
    xros_audio = json.loads((ROOT / 'data/xros_audio.json').read_text())
    xros_paths = {track[key] for track in xros_audio['music']
                  for key in ('path', 'intro_path') if track.get(key)}
    assert len(xros_audio['music']) == 20
    assert len(xros_paths) == 39  # 20 main segments plus 19 supplied intros.
    assert xros_paths <= audio_paths
    assert len(audio_paths - xros_paths) == 985
    assert len(audio_paths) == 1024


def test_scoped_verifier_checks_both_generations_without_claiming_full_media_coverage():
    result = fixed.verify(ROOT, sprites_only=True)
    assert result['status'] == 'verified'
    assert result['scope'] == 'sprites-and-data-only'
    assert result['full_build_integrity_checked'] is False
    assert result['retained_v110_replacements'] == 695
    assert result['both_packs_effective_replacements'] == 770
    assert result['gameplay_unchanged'] is (not HAS_V120)
    assert result['original_species_mechanics_unchanged'] is True
    assert result['normal_species_unchanged'] == 502
    assert result['unaffected_species_unchanged'] == (482 if HAS_V120 else 984)


def test_full_species_rebuild_preserves_both_sprite_generations():
    rebuilt = {e['id']:e for e in species_catalog()}
    assert len(rebuilt) == len(SPECIES) == (2008 if (ROOT / "data/firewall_v150.json").is_file() else 1506 if HAS_V120 else 1004)
    affected = {r['id'] for r in RECORD['species']} | {r['id'] for r in legacy.read_record(ROOT)['species']}
    assert len(affected) == 148
    for sid in affected:
        for key in legacy.ART_KEYS:
            assert rebuilt[sid][key] == SPECIES[sid][key], (sid, key)


def test_historical_record_and_all_gameplay_data_are_preserved():
    assert legacy.sha256((ROOT / legacy.RECORD_PATH).read_bytes()) == RECORD['baseline']['v110_record_sha256']
    fixed.check_protected(ROOT, RECORD, CATALOG)
    old = legacy.read_record(ROOT)
    effective = fixed.effective_legacy_record(ROOT)
    assert old['inputs'] == effective['inputs']
    assert old['counts'] == effective['counts']
    changed = [a['path'] for a,b in zip(old['replacements'], effective['replacements']) if a['sha256'] != b['sha256']]
    assert sorted(changed) == RECORD['legacy_compatibility']['superseded_paths']
    assert sum(e['paradox'] for e in CATALOG['species']) == 502


def test_legacy_verification_dispatches_to_current_pack(monkeypatch):
    sentinel = {'status':'test sentinel'}
    monkeypatch.setattr(fixed, 'verify', lambda root: sentinel)
    assert legacy.verify(ROOT) is sentinel


def test_old_pack_reapplication_cannot_roll_back_the_newer_fixes(tmp_path):
    with pytest.raises(ValueError, match='Refusing to roll them back'):
        legacy.reapply(tmp_path, ROOT)


@pytest.fixture
def reapply_tree(tmp_path):
    """Minimal honest source fixture: only files touched/read by the reapply action.

    This fixture is not a complete game installation and never claims to pass
    full build/media verification. Input PNGs are recovered from installed,
    byte-identical direct destinations, not regenerated with an image encoder.
    """
    root, source = tmp_path / 'game', tmp_path / 'inputs'
    source.mkdir()
    names = {r['path'] for r in RECORD['baseline']['protected_data'] + RECORD['baseline']['runtime_python_files']}
    names.update(('data/catalog.json', 'data/asset_manifest.json', 'data/source_assets.json', fixed.RECORD_PATH))
    if HAS_V120:
        names.update((fixed.VARIETIES_RECORD, fixed.VARIETIES_BASELINE))
    if HAS_V150:
        names.add('data/firewall_v150.json')
    names.update(r['path'] for r in RECORD['replacements'])
    for item in RECORD['species']:
        names.add(item['sidecar'])
        art = legacy.absolute_art(item)
        names.update(art['sprites'].values())
        names.update(p for seq in art['animations'].values() for p in seq)
        names.update(art['mirrored_frames'].values())
    for name in names:
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    for row in RECORD['inputs']:
        shutil.copyfile(ROOT / row['path'], source / row['source'])
    # Non-image shell metadata is intentionally not imported into the game.
    (source / 'desktop.ini').write_text('not a sprite')
    return root, source


def file_hashes(root):
    return {p.relative_to(root).as_posix():legacy.sha256(p.read_bytes()) for p in root.rglob('*') if p.is_file()}


def test_reapplication_is_byte_idempotent_and_preserves_unrelated_manifest_records(reapply_tree):
    root, source = reapply_tree
    before = file_hashes(root)
    first = fixed.reapply(source, root)
    second = fixed.reapply(source, root)
    assert first == second
    assert first['updated_files'] == 99
    assert file_hashes(root) == before
    assert not (root / 'desktop.ini').exists()
    if HAS_V120:
        current = json.loads((root / 'data/catalog.json').read_text(encoding='utf-8'))
        assert current == CATALOG
        assert sum(entry.get('shiny', False) for entry in current['species']) == 502


@pytest.mark.parametrize('problem', ('missing', 'unexpected', 'corrupt', 'duplicate'))
def test_bad_input_pack_is_rejected_before_any_game_file_write(reapply_tree, problem):
    root, source = reapply_tree
    name = RECORD['inputs'][0]['source']
    if problem == 'missing':
        (source / name).unlink()
    elif problem == 'unexpected':
        shutil.copyfile(source / name, source / 'NotInThePack.png')
    elif problem == 'corrupt':
        with (source / name).open('ab') as stream:
            stream.write(b'altered')
    else:
        (source / 'duplicate').mkdir()
        shutil.copyfile(source / name, source / 'duplicate' / name)
    before = file_hashes(root)
    with pytest.raises(ValueError):
        fixed.reapply(source, root)
    assert file_hashes(root) == before


def test_unrecognized_target_bytes_are_not_overwritten(reapply_tree):
    root, source = reapply_tree
    (root / RECORD['replacements'][0]['path']).write_bytes(b'other local artwork')
    before = file_hashes(root)
    with pytest.raises(ValueError, match='Not the supplied'):
        fixed.reapply(source, root)
    assert file_hashes(root) == before


def test_gameplay_modification_is_reported_without_silently_resetting_it(reapply_tree):
    root, source = reapply_tree
    path = root / 'data/catalog.json'
    catalog = json.loads(path.read_text(encoding='utf-8'))
    catalog['species'][0]['base_stats']['hp'] += 10
    path.write_bytes(legacy.json_bytes(catalog))
    before = file_hashes(root)
    with pytest.raises(ValueError, match='Existing species changed' if HAS_V150 else 'Non-art catalog'):
        fixed.reapply(source, root)
    assert file_hashes(root) == before


@pytest.mark.skipif(not HAS_V120, reason='v1.2.0 upgrade is not installed')
@pytest.mark.parametrize('change', ('normal_art', 'paradox_mechanics', 'missing_shiny'))
def test_release_marker_does_not_disable_original_species_preservation(reapply_tree, change):
    root, source = reapply_tree
    path = root / 'data/catalog.json'
    catalog = json.loads(path.read_text(encoding='utf-8'))
    if change == 'normal_art':
        entry = next(e for e in catalog['species'] if e['variety'] == 'normal')
        entry['sprites']['idle'] = 'assets/digimon/unrelated.png'
    elif change == 'paradox_mechanics':
        entry = next(e for e in catalog['species'] if e['paradox'])
        entry['base_stats']['hp'] += 10
    else:
        catalog['species'].remove(next(e for e in catalog['species'] if e['shiny']))
    path.write_bytes(legacy.json_bytes(catalog))
    before = file_hashes(root)
    expected_error = ('FireWall roster does not preserve' if change == 'missing_shiny' else 'Existing species changed') if HAS_V150 else 'protected normal art|complete historical catalog'
    with pytest.raises(ValueError, match=expected_error):
        fixed.reapply(source, root)
    assert file_hashes(root) == before


@pytest.mark.skipif(not HAS_V120, reason='v1.2.0 upgrade is not installed')
def test_changed_historical_snapshot_is_rejected_even_with_recomputed_release_hashes(reapply_tree):
    root, source = reapply_tree
    historical_path = root / fixed.VARIETIES_BASELINE
    historical = json.loads(historical_path.read_text(encoding='utf-8'))
    entry = next(e for e in historical['species'] if not e['paradox'])
    entry['base_stats']['hp'] += 10
    historical_path.write_bytes(legacy.json_bytes(historical))
    catalog_path = root / 'data/catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    next(e for e in catalog['species'] if e['id'] == entry['id'])['base_stats']['hp'] += 10
    catalog_path.write_bytes(legacy.json_bytes(catalog))
    release_path = root / fixed.VARIETIES_RECORD
    release = json.loads(release_path.read_text(encoding='utf-8'))
    release['baseline_catalog_sha256'] = legacy.sha256(historical_path.read_bytes())
    release['baseline_normal_sha256'][entry['id']] = legacy.object_hash(entry)
    release_path.write_bytes(legacy.json_bytes(release))
    if HAS_V150:
        # Recompute the new additive preservation record too: the old immutable
        # v1.1.1 fingerprint must still reject this forged historical snapshot.
        altered = next(e for e in catalog['species'] if e['id'] == entry['id'])
        next(e for e in catalog['species'] if e['id'] == entry['id'] + '_firewall')['base_stats'] = copy.deepcopy(altered['base_stats'])
        catalog_path.write_bytes(legacy.json_bytes(catalog))
        firewall_path = root / 'data/firewall_v150.json'
        firewall = json.loads(firewall_path.read_text(encoding='utf-8'))
        firewall['baseline_species_sha256'][entry['id']] = legacy.object_hash(altered)
        firewall_path.write_bytes(legacy.json_bytes(firewall))
    before = file_hashes(root)
    with pytest.raises(ValueError, match='Non-art catalog fields differ'):
        fixed.reapply(source, root)
    assert file_hashes(root) == before


def test_symlinked_source_directory_is_rejected(reapply_tree, tmp_path):
    root, source = reapply_tree
    link = tmp_path / 'linked-inputs'
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip('Symlink creation is not permitted on this host.')
    before = file_hashes(root)
    with pytest.raises(ValueError, match='symlink'):
        fixed.reapply(link, root)
    assert file_hashes(root) == before


def test_record_rejects_duplicate_destinations(reapply_tree):
    root, _ = reapply_tree
    path = root / fixed.RECORD_PATH
    record = json.loads(path.read_text(encoding='utf-8'))
    record['replacements'].append(record['replacements'][0])
    path.write_bytes(legacy.json_bytes(record))
    with pytest.raises(ValueError, match='Duplicate'):
        fixed.read_record(root)


def test_manifest_merge_rejects_duplicate_records_without_writing(reapply_tree):
    root, _ = reapply_tree
    path = root / 'data/asset_manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest['files'].append(manifest['files'][0])
    path.write_bytes(legacy.json_bytes(manifest))
    before = file_hashes(root)
    with pytest.raises(ValueError, match='invalid asset manifest'):
        fixed.merge_manifest(root, {})
    assert file_hashes(root) == before
