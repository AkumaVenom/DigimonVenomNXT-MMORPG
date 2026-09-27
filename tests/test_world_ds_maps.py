"""Asset import guarantees independent of the shared-world encounter integration."""
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from tools.import_world_ds_maps import collision_mask, disposition, safe_spawn

ROOT = Path(__file__).resolve().parents[1]


def metadata():
    return json.loads((ROOT / 'data/world_ds_maps.json').read_text(encoding='utf8'))


def test_complete_source_accounting_and_adventure_field_selection():
    report = metadata()
    playable = {30, *range(48, 133), *range(140, 204)}
    assert len(report['maps']) == 150
    assert {m['source_map_number'] for m in report['maps']} == playable
    assert len(report['source_maps']) == 204
    assert sum(len(m['files']) for m in report['source_maps']) == 1228
    assert len({m['zone_id'] for m in report['maps']}) == 21
    for source in report['source_maps']:
        assert source['status'] == disposition(source['source_map_number'])[0]
        assert source['reason']
        assert all(len(f['sha256']) == 64 and f['bytes'] > 0 for f in source['files'])
    assert {s['source_map_number'] for s in report['skipped']} == set(range(204)) - playable


def test_every_base_is_byte_identical_to_supplied_layer_and_dimensions_unchanged():
    report = metadata()
    originals = {s['source_map_number']: s for s in report['source_maps']}
    for area in report['maps']:
        source = originals[area['source_map_number']]
        filename = f"map_{area['source_map_number']:03}_layers_layer_a.png"
        source_hash = next(f['sha256'] for f in source['files'] if f['name'] == filename)
        assert hashlib.sha256((ROOT / area['path']).read_bytes()).hexdigest() == source_hash
        assert [area['width'], area['height']] == [source['width'], source['height']]
        for key in ('path', 'foreground', 'walkable'):
            if area[key]:
                with Image.open(ROOT / area[key]) as image:
                    assert image.size == (area['width'], area['height'])
        with Image.open(ROOT / area['walkable']) as image:
            assert {color for _, color in image.getcolors()} == {0, 255}
            x, y = area['spawn']
            assert image.crop((x - 4, y - 4, x + 5, y + 5)).getextrema() == (255, 255)
        assert area['geometry']['overlay_polarity_verified']
        assert area['geometry']['largest_component_pixels'] >= 4096
        assert area['geometry']['verified_patrol_points'] >= 12
        assert 1 <= area['level_min'] <= area['level'] <= area['level_max'] <= 99


def test_collision_polarity_is_verified_before_inverting(tmp_path):
    art = Image.new('RGBA', (128, 128), (70, 180, 90, 255))
    mask = Image.new('L', art.size, 255)
    ImageDraw.Draw(mask).rectangle((20, 20, 100, 100), fill=0)
    overlay = art.copy()
    red = Image.new('RGBA', art.size, (255, 0, 0, 255))
    overlay.paste(red, mask=mask)
    art.save(tmp_path / 'map_001_map_composite.png')
    mask.save(tmp_path / 'map_001_collision_mask.png')
    overlay.save(tmp_path / 'map_001_collision_overlay.png')
    imported = collision_mask(tmp_path, 1)
    assert ImageChops.difference(imported, ImageChops.invert(mask)).getbbox() is None
    # If exports change convention, fail instead of silently walking on walls.
    ImageChops.invert(mask).save(tmp_path / 'map_001_collision_mask.png')
    with pytest.raises(ValueError, match='black floor'):
        collision_mask(tmp_path, 1)


def test_spawn_uses_largest_component_not_a_nearby_isolated_island():
    mask = Image.new('L', (300, 220))
    draw = ImageDraw.Draw(mask)
    draw.rectangle((15, 15, 120, 200), fill=255)
    draw.rectangle((142, 100, 160, 120), fill=255)
    art = Image.new('RGBA', mask.size, 'white')
    before = mask.tobytes()
    spawn, geometry = safe_spawn(mask, art)
    assert 19 <= spawn[0] <= 116
    assert 19 <= spawn[1] <= 196
    assert geometry['largest_component_pixels'] == 106 * 186
    assert mask.tobytes() == before  # Arrival selection never redraws collision.


def test_spawn_rejects_tiny_or_invisible_floor():
    mask = Image.new('L', (128, 128))
    ImageDraw.Draw(mask).rectangle((60, 60, 65, 65), fill=255)
    with pytest.raises(ValueError, match='too small'):
        safe_spawn(mask, Image.new('RGBA', mask.size, 'white'))
    ImageDraw.Draw(mask).rectangle((16, 16, 110, 110), fill=255)
    with pytest.raises(ValueError, match='visible'):
        safe_spawn(mask, Image.new('RGBA', mask.size, (0, 0, 0, 0)))


def test_narrow_ledge_arrival_cloud_relocates_within_original_collision():
    from venom.server.navigation import Navigation
    from tools.import_world_ds_maps import arrival_spacing, ensure_arrival_space
    area = next(a for a in metadata()['maps'] if a['id'] == 'world_ds_058')
    # The center of the largest component can seed a locally trapped random
    # walk, despite having 33 nominal graph points. This was the actual ledge.
    area['spawn'] = [664, 340]
    navigation = Navigation(ROOT, {area['id']: area})
    assert arrival_spacing(navigation, area['id']) < 16
    original_mask = (ROOT / area['walkable']).read_bytes()
    with Image.open(ROOT / area['path']) as artwork:
        ensure_arrival_space(navigation, area, artwork)
    assert arrival_spacing(navigation, area['id']) >= 16
    assert (ROOT / area['walkable']).read_bytes() == original_mask
    assert area['geometry']['verified_arrival_count'] == 20
