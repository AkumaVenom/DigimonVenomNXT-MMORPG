"""Expansion catalog regeneration must be repeatable and preserve owned assets."""
import copy
import json
from pathlib import Path

from tools.merge_world_ds import merge_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_regional_merge_is_idempotent_and_keeps_existing_species_tamers_and_scenes():
    original = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
    frozen = copy.deepcopy(original)
    once = merge_catalog(original, ROOT)
    twice = merge_catalog(once, ROOT)
    assert once == twice
    assert original == frozen
    assert once['species'] == original['species']
    assert once['tamers'] == original['tamers']
    assert once['audio']['scene_tracks'] == original['audio']['scene_tracks']
    assert once['audio']['event_sounds'] == original['audio']['event_sounds']
    assert len(once['maps']) == len({m['id'] for m in once['maps']}) == len(original['maps'])
    for region, count in (('dawn', 254), ('world_ds', 150)):
        assert sum(m.get('region_id', 'dawn') == region for m in once['maps']) == count
    assert [m for m in once['maps'] if m.get('region_id') == 'xros_wars'] == [
        m for m in original['maps'] if m.get('region_id') == 'xros_wars']
    assert len(once['tamers']) == 64  # Characters.rar deliberately remains unused.


def test_merging_into_unmarked_dawn_only_catalog_keeps_original_map_data():
    original = json.loads((ROOT / 'data/catalog.json').read_text(encoding='utf-8'))
    legacy = copy.deepcopy(original)
    legacy['maps'] = [m for m in legacy['maps'] if m.get('region_id', 'dawn') == 'dawn']
    for row in legacy['maps']:
        row.pop('region_id', None)
    before = copy.deepcopy(legacy['maps'])
    merged = merge_catalog(legacy, ROOT)
    after = [{k: v for k, v in m.items() if k != 'region_id'}
             for m in merged['maps'] if m.get('region_id') == 'dawn']
    assert before == after
    assert len(before) == 254
    music = merged['audio']['music']
    assert len(music) == len({m['id'] for m in music})
    assert all(m['music_id'].startswith('ds_') for m in merged['maps'] if m['region_id'] == 'world_ds')
