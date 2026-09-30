"""Expansion regeneration must retain all existing identities and regions."""
import copy
import json
from pathlib import Path

import pytest

from tools.merge_xros import merge_catalog
from tools.merge_world_ds import merge_catalog as merge_ds

ROOT = Path(__file__).resolve().parents[1]


def test_xros_merge_is_idempotent_and_preserves_existing_worlds():
    original = json.loads((ROOT / 'data/catalog.json').read_text())
    frozen = copy.deepcopy(original)
    once = merge_catalog(original, ROOT)
    assert once == merge_catalog(once, ROOT)
    assert original == frozen
    assert once['species'] == original['species']
    assert once['tamers'] == original['tamers']
    assert [m for m in once['maps'] if m.get('region_id') != 'xros_wars'] == [
        m for m in original['maps'] if m.get('region_id') != 'xros_wars']
    assert len(once['maps']) == len({m['id'] for m in once['maps']}) == 500
    assert {r['id'] for r in once['world_regions']} == {'dawn', 'world_ds', 'xros_wars'}
    assert once['audio']['scene_tracks'] == original['audio']['scene_tracks']
    assert once['audio']['event_sounds'] == original['audio']['event_sounds']
    assert once['audio']['region_tracks']['world_ds'] == original['audio']['region_tracks']['world_ds']
    # Regenerating DS afterward must not remove the third region's atlas entry.
    assert merge_ds(once, ROOT)['world_regions'] == once['world_regions']
    assert [m for m in merge_ds(once, ROOT)['maps'] if m.get('region_id') == 'xros_wars'] == [
        m for m in once['maps'] if m.get('region_id') == 'xros_wars']


def miniature(tmp_path, maps=None, music=None):
    (tmp_path / 'data').mkdir()
    maps = maps if maps is not None else [
        {'id': 'xros_001', 'region_id': 'xros_wars', 'music_id': 'xros_track', 'battle_music_id': 'xros_track'}]
    music = music if music is not None else [{'id': 'xros_track', 'region_id': 'xros_wars'}]
    (tmp_path / 'data/xros_maps.json').write_text(json.dumps({'maps': maps}))
    (tmp_path / 'data/xros_audio.json').write_text(json.dumps({'music': music}))
    return {'maps': [{'id': 'map_001', 'region_id': 'dawn'}], 'audio': {'music': []}}


def test_duplicate_maps_rejected_without_mutation(tmp_path):
    row = {'id': 'xros_001', 'region_id': 'xros_wars'}
    catalog = miniature(tmp_path, [row, row])
    before = copy.deepcopy(catalog)
    with pytest.raises(ValueError, match='Duplicate'):
        merge_catalog(catalog, tmp_path)
    assert catalog == before


def test_cross_region_identifier_collision_rejected(tmp_path):
    catalog = miniature(tmp_path)
    catalog['maps'].append({'id': 'xros_001', 'region_id': 'dawn'})
    with pytest.raises(ValueError, match='collides'):
        merge_catalog(catalog, tmp_path)


def test_missing_music_link_rejected(tmp_path):
    catalog = miniature(tmp_path, music=[])
    with pytest.raises(ValueError, match='Unknown music_id'):
        merge_catalog(catalog, tmp_path)


def test_wrong_region_audio_rejected(tmp_path):
    catalog = miniature(tmp_path, music=[{'id': 'xros_track', 'region_id': 'dawn'}])
    with pytest.raises(ValueError, match='namespace'):
        merge_catalog(catalog, tmp_path)
