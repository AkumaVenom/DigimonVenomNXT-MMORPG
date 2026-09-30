"""Supplied Xros terrain, foreground and authoritative route import guarantees."""
import hashlib
import json
import math
from pathlib import Path
import random

import pytest
from PIL import Image, ImageChops

from tools.import_xros_maps import PLAYABLE, POLARITY_PROBES, ZONES, collision_mask, make_foreground
from venom.server.navigation import Navigation

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def report():
    return json.loads((ROOT / 'data/xros_maps.json').read_text(encoding='utf8'))


@pytest.fixture(scope='module')
def navigation(report):
    return Navigation(ROOT, {area['id']: area for area in report['maps']})


def test_all_source_exports_accounted_for_and_distinct_fields_selected(report):
    assert len(report['source_maps']) == 196
    assert {s['source_map_number'] for s in report['source_maps']} == set(range(196))
    assert len(report['maps']) == len(PLAYABLE) == 96
    assert {area['source_map_number'] for area in report['maps']} == PLAYABLE
    assert {s['source_map_number'] for s in report['skipped']} == set(range(196)) - PLAYABLE
    assert sum(report['status_counts'].values()) == 196
    assert sum(len(s['files']) for s in report['source_maps']) == report['source_file_count']
    assert len({area['zone_id'] for area in report['maps']}) == len(ZONES) == 14
    assert min(area['level'] for area in report['maps']) == 1
    assert max(area['level'] for area in report['maps']) == 99
    assert [area['map_order'] for area in report['maps']] == list(range(96))
    assert len({(area['zone_id'], area['name']) for area in report['maps']}) == 96
    for source in report['source_maps']:
        assert source['reason']
        assert all(len(f['sha256']) == 64 and f['bytes'] > 0 for f in source['files'])


@pytest.mark.parametrize('number', sorted(PLAYABLE))
def test_original_art_exact_floor_safe_and_foreground_never_hides_ground(number, report):
    area = next(m for m in report['maps'] if m['source_map_number'] == number)
    original = next(s for s in report['source_maps'] if s['source_map_number'] == number)
    expected = next(f['sha256'] for f in original['files'] if f['name'] == f'map_{number:03}.png')
    assert hashlib.sha256((ROOT / area['path']).read_bytes()).hexdigest() == expected
    with Image.open(ROOT / area['path']) as source:
        art = source.convert('RGBA')
    with Image.open(ROOT / area['walkable']) as source:
        mask = source.convert('L')
    assert art.size == mask.size == (area['width'], area['height'])
    assert set(mask.tobytes()) == {0, 255}
    x, y = area['spawn']
    assert mask.crop((x - 4, y - 4, x + 5, y + 5)).getextrema() == (255, 255)
    if area['foreground']:
        with Image.open(ROOT / area['foreground']) as source:
            foreground = source.convert('RGBA')
        assert foreground.size == art.size
        assert ImageChops.multiply(foreground.getchannel('A'), mask).getbbox() is None
        # Layering the scenery back must preserve every original color channel.
        difference = ImageChops.difference(Image.alpha_composite(art, foreground), art)
        assert all(channel.getbbox() is None for channel in difference.split())
    assert 1 <= area['level_min'] <= area['level'] <= area['level_max'] <= 99
    assert area['music_id'].startswith('xros_') and area['battle_music_id'].startswith('xros_')
    assert area['geometry']['largest_component_pixels'] >= 4096
    assert area['geometry']['source_black_is_walkable']
    assert area['geometry']['reference_polarity_verified']


@pytest.mark.parametrize('number', sorted(PLAYABLE))
def test_every_field_accepts_twenty_spaced_arrivals_and_walkable_closed_patrol(number, report, navigation):
    area = next(m for m in report['maps'] if m['source_map_number'] == number)
    map_id = area['id']
    occupied = []
    for ordinal in range(20):
        point = navigation.arrival(map_id, occupied, ordinal)
        assert navigation.walkable(map_id, *point)
        assert all(math.dist(point, other) >= 16 for other in occupied)
        occupied.append(point)
    patrol = navigation.patrol(map_id, *area['spawn'], random.Random(map_id), 0)
    assert patrol['loop'] and patrol['from'] == patrol['to']
    assert len(patrol['segments']) >= 4
    for segment in patrol['segments']:
        assert segment['end'] > segment['start']
        traced = navigation.trace(map_id, segment['from'], segment['to'])
        assert math.dist(traced, segment['to']) < 0.01
    assert area['geometry']['verified_arrival_count'] == 20
    assert area['geometry']['minimum_arrival_spacing_pixels'] >= 16


def test_independent_original_terrain_polarity_probes(report):
    maps = {area['source_map_number']: area for area in report['maps']}
    for number, floor, blocked in POLARITY_PROBES:
        with Image.open(ROOT / maps[number]['walkable']) as mask:
            assert mask.getpixel(floor) == 255
            assert mask.getpixel(blocked) == 0


def test_antialias_threshold_and_invalid_collision_exports(tmp_path):
    path = tmp_path / 'mask.png'
    mask = Image.new('L', (6, 1))
    mask.putdata([0, 63, 127, 128, 191, 255])
    mask.save(path)
    assert list(collision_mask(path, (6, 1)).tobytes()) == [255, 255, 255, 0, 0, 0]
    with pytest.raises(ValueError, match='dimensions'):
        collision_mask(path, (8, 1))
    Image.new('RGBA', (6, 1), (255, 0, 0, 255)).save(path)
    with pytest.raises(ValueError, match='grayscale'):
        collision_mask(path, (6, 1))
    Image.new('RGBA', (6, 1), (0, 0, 0, 0)).save(path)
    with pytest.raises(ValueError, match='transparent'):
        collision_mask(path, (6, 1))


def test_foreground_bridge_decks_stay_below_actors():
    art = Image.new('RGBA', (4, 1), (170, 120, 80, 255))
    layer = Image.new('RGBA', (4, 1), (80, 70, 60, 255))
    layer.putpixel((3, 0), (0, 0, 0, 0))
    mask = Image.new('L', (4, 1))
    mask.putdata([255, 255, 0, 0])
    foreground = make_foreground(art, layer, mask)
    assert list(foreground.getchannel('A').tobytes()) == [0, 0, 255, 0]
    assert Image.alpha_composite(art, foreground).tobytes() == art.tobytes()
