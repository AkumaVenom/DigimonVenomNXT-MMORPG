"""Complete sprite coverage, old-save IDs, exact supplied art and pose parity."""
from pathlib import Path, PurePosixPath
import copy
import json

import pytest

from tools import import_varieties_v120 as variants
from tools.import_assets import species_catalog

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'data/catalog.json').read_text('utf-8'))
BASELINE = json.loads((ROOT / variants.BASELINE).read_text('utf-8'))
SPECIES = {s['id']: s for s in CATALOG['species']}
NORMALS = [s for s in CATALOG['species'] if s.get('variety') == 'normal']


def test_complete_supplied_variety_installation_checksums_and_no_stale_files():
    result = variants.verify(ROOT)
    assert result == {'status': 'verified', 'normal_species': 502, 'paradox_species': 502,
                      'shiny_species': 502, 'total_species': 1506, 'source_pngs': 16040,
                      'installed_variety_files': 18051, 'animation_sidecars': 1004}


def test_all_existing_species_ids_and_normal_art_are_retained():
    old = {s['id']: s for s in BASELINE['species']}
    assert len(old) == 1004
    assert set(old) < set(SPECIES)
    assert len(SPECIES) == 2008
    assert len([s for s in SPECIES.values() if s.get("variety") != "firewall"]) == 1506
    assert len(NORMALS) == 502
    for sid, entry in old.items():
        if entry['paradox']:
            assert variants.retained_entry(SPECIES[sid], art=False) == variants.retained_entry(entry, art=False)
        else:
            assert variants.retained_entry(SPECIES[sid]) == entry
    assert CATALOG['version'] == '1.5.0'


@pytest.mark.parametrize('base', NORMALS, ids=lambda s: s['id'])
def test_both_varieties_preserve_every_selected_pose_sequence_and_direction(base):
    directory = variants.base_directory(base)
    for name in ('Paradox', 'Shiny'):
        entry = SPECIES[base['id'] + '_' + name.lower()]

        def normal_path(path):
            local = PurePosixPath(path).relative_to(directory / name)
            if name == 'Paradox':
                local = local.with_name(local.name.replace('_Paradox', '', 1))
            return (directory / local).as_posix()

        assert {k: normal_path(v) for k, v in entry['sprites'].items()} == base['sprites']
        assert {k: [normal_path(v) for v in seq] for k, seq in entry['animations'].items()} == base['animations']
        assert {normal_path(k): normal_path(v) for k, v in entry.get('mirrored_frames', {}).items()} == base.get('mirrored_frames', {})
        assert entry['source_frame_count'] == base.get('source_frame_count', 0)


def test_shiny_evolution_and_balance_preserve_the_selected_variety():
    for normal in NORMALS:
        shiny = SPECIES[normal['id'] + '_shiny']
        assert (shiny['base_id'], shiny['paradox'], shiny['shiny']) == (normal['id'], False, True)
        for key in ('base_stats', 'type', 'attribute', 'stage'):
            assert shiny[key] == normal[key]
        expected = [{**route, 'to': route['to'] + '_shiny'} for route in normal['evolutions']]
        assert shiny['evolutions'] == expected
        assert all(SPECIES[route['to']]['shiny'] for route in shiny['evolutions'])


def test_rebuild_preserves_all_current_species_without_reguessing_poses():
    assert species_catalog() == CATALOG['species']


def test_shoutmon_missing_champion_source_does_not_create_broken_duplicate():
    assert {'shoutmon', 'shoutmon_paradox', 'shoutmon_shiny'} <= SPECIES.keys()
    assert all(SPECIES[sid]['stage'] == 'rookie' for sid in SPECIES if sid.startswith('shoutmon'))
    assert not any(sid.startswith('shoutmon_champion') for sid in SPECIES)
