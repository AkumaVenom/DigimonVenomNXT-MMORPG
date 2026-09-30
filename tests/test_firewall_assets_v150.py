"""Complete fourth-variety coverage, immutable originals, and supplied art."""
import copy
import json
from pathlib import Path, PurePosixPath

import pytest

from tools import import_firewall_v150 as firewall
from tools import import_varieties_v120 as legacy
from tools.import_assets import animation_override, species_catalog

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'data/catalog.json').read_text('utf-8'))
SPECIES = {s['id']: s for s in CATALOG['species']}
NORMALS = [s for s in CATALOG['species'] if s.get('variety') == 'normal']


def test_complete_supplied_pack_checksums_geometry_and_full_png_decode():
    result = firewall.verify(ROOT, decode_images=True)
    assert result == {
        'status': 'verified', 'normal_species': 502, 'paradox_species': 502,
        'shiny_species': 502, 'firewall_species': 502, 'total_species': 2008,
        'source_pngs': 7934, 'source_files': 9087, 'installed_firewall_files': 9440,
        'animation_sidecars': 502, 'generated_animation_sidecars': 353,
        'decoded_images': True,
    }


@pytest.mark.parametrize('normal', NORMALS, ids=lambda s: s['id'])
def test_each_species_keeps_exact_normal_poses_mirrors_stats_and_evolution_requirements(normal):
    variant = SPECIES[normal['id'] + '_firewall']
    directory = legacy.base_directory(normal)
    variant_dir = directory / 'FireWall'

    def original(path):
        return (directory / PurePosixPath(path).relative_to(variant_dir)).as_posix()

    assert {k: original(p) for k, p in variant['sprites'].items()} == normal['sprites']
    assert {k: [original(p) for p in seq] for k, seq in variant['animations'].items()} == normal['animations']
    assert {original(p): original(m) for p, m in variant['mirrored_frames'].items()} == normal.get('mirrored_frames', {})
    assert variant['source_frame_count'] == normal.get('source_frame_count', 0)
    assert set(variant['sprite_geometry']) == legacy.art_paths(variant)
    assert animation_override(ROOT / variant_dir, ROOT) == {
        k: variant[k] for k in (*firewall.ART_KEYS, 'sprite_geometry') if k in variant
    }
    assert (variant['base_id'], variant['variety'], variant['firewall'], variant['shiny'], variant['paradox']) == (
        normal['id'], 'firewall', True, False, False)
    for key in ('base_stats', 'type', 'attribute', 'stage', 'mechanics_status'):
        assert variant[key] == normal[key]
    assert variant['evolutions'] == [{**route, 'to': route['to'] + '_firewall'} for route in normal['evolutions']]
    assert all(SPECIES[route['to']]['firewall'] for route in variant['evolutions'])


def test_installed_asset_rebuild_preserves_all_four_varieties_and_geometry():
    assert len(CATALOG['species']) == 2008
    assert species_catalog() == CATALOG['species']


@pytest.mark.parametrize('case', ['old_stats', 'old_art', 'old_shiny', 'firewall_stats', 'firewall_evolution', 'firewall_identity', 'missing_firewall', 'duplicate', 'old_map', 'firewall_habitat'])
def test_preservation_guard_rejects_corrupt_or_incomplete_fourth_variety(case):
    changed = copy.deepcopy(CATALOG)
    entries = {s['id']: s for s in changed['species']}
    if case == 'old_stats':
        entries['agumon']['base_stats']['atk'] += 1
    elif case == 'old_art':
        entries['agumon']['sprites']['idle'] = entries['agumon_firewall']['sprites']['idle']
    elif case == 'old_shiny':
        entries['agumon_shiny']['evolutions'][0]['to'] = 'greymon'
    elif case == 'firewall_stats':
        entries['agumon_firewall']['base_stats']['atk'] += 1
    elif case == 'firewall_evolution':
        entries['agumon_firewall']['evolutions'][0]['to'] = 'greymon_shiny'
    elif case == 'firewall_identity':
        entries['agumon_firewall']['shiny'] = True
    elif case == 'missing_firewall':
        changed['species'].remove(entries['agumon_firewall'])
    elif case == 'duplicate':
        changed['species'].append(copy.deepcopy(entries['agumon_firewall']))
    elif case == 'old_map':
        changed['maps'][0]['name'] = 'Unexpected map change'
    else:
        changed['maps'][0]['firewall_encounters'] = ['agumon_shiny']
    with pytest.raises(ValueError):
        firewall.historical_catalog(ROOT, changed)


def test_historical_import_cannot_remove_the_installed_firewall_roster(tmp_path):
    with pytest.raises(ValueError, match='FireWall is installed'):
        legacy.install(tmp_path, ROOT)


def test_release_rates_leave_previous_rarities_unchanged():
    mechanics = json.loads((ROOT / 'data/mechanics.json').read_text('utf-8'))
    assert mechanics['firewall_encounter_chance'] == .007
    assert mechanics['shiny_encounter_chance'] == .01
    assert mechanics['paradox_encounter_chance'] == .025
    assert mechanics['firewall_scan_gain'] == mechanics['shiny_scan_gain'] == mechanics['paradox_scan_gain'] == 5
    record = json.loads((ROOT / firewall.RECORD).read_text('utf-8'))
    assert len(record['provenance']['parts']) == 6


def test_all_500_published_world_habitats_have_exactly_matching_firewall_species():
    assert len(CATALOG['maps']) == 500
    for area in CATALOG['maps']:
        assert area['firewall_encounters'] == [sid + '_firewall' for sid in area['encounters']]
        assert all(SPECIES[sid]['firewall'] for sid in area['firewall_encounters'])
