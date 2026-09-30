"""Import the supplied Super Xros Wars Blue adventure fields for Venom NXT.

Every source PNG is inventoried. Original flattened artwork is copied byte for
byte: several layer A exports omit their background color and layer B contains
walkable bridge decks, so blindly using A as ground/B as foreground is unsafe.
The optional foreground copies original composite pixels only on blocked ground
where the supplied B layer exists. It cannot hide an actor's walkable foot point.

Collision exports use black floor/white obstruction, confirmed against the
supplied art on every contact sheet and the explicit reference probes below.
No floor, ladder link or terrain pixel is invented. The authoritative navigation
implementation checks every arrival and patrol before the manifest is written.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
import sys

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.import_world_ds_maps import safe_spawn, ensure_arrival_space
from tools.import_xros_audio import soundtrack_for_map

# Authored Venom NXT zone names, not a claim of canonical source-game labels.
# Explicit lists retain stable source IDs while ordering a welcoming progression.
ZONES = (
    ('verdant_crossing', 'Verdant Crossing', 1, 6, (27, 28, 29)),
    ('sunlit_meadow', 'Sunlit Meadow', 5, 12, tuple(range(92, 97))),
    ('coral_causeway', 'Coral Causeway', 8, 20, (33, 34, 38, 39, 40, 106, 107)),
    ('mosswater_marsh', 'Mosswater Marsh', 18, 30, (42, 43, 44, 45, 49, 50)),
    ('sandglass_basin', 'Sandglass Basin', 28, 42, (80, 81, 82, 83, 88, 89, 90)),
    ('stonefall_outpost', 'Stonefall Outpost', 38, 52, (68, 69, 70, 71, 76, 77, 78)),
    ('frostline_shelf', 'Frostline Shelf', 45, 59, (58, 59, 60, 62, 63, 64)),
    ('cloudspire_cliffs', 'Cloudspire Cliffs', 52, 70, (23, 24, 25, 26, *range(138, 143), *range(145, 150))),
    ('duskmire_keep', 'Duskmire Keep', 60, 77, (72, 97, 98, 100, 133, 134)),
    ('crimson_causeway', 'Crimson Causeway', 70, 85, (51, 52, 54, 161, 180, 182, 188)),
    ('cinderfront_caldera', 'Cinderfront Caldera', 76, 89, (112, 113, 114, 115, 116, 119, 120, 121, 123, 124)),
    ('neon_bastion', 'Neon Bastion', 84, 93, tuple(range(126, 131))),
    ('overdrive_circuit', 'Overdrive Circuit', 90, 98, (152, 153, 154, 155, 156, 157, 160, 163, 164, 165)),
    ('xros_core', 'Xros Core', 97, 99, (175, 176, 177)),
)
PLAYABLE = {number for *_, numbers in ZONES for number in numbers}
BLANK = {0, 2, 3, 4, 131, 132, *range(166, 175)}
INCOMPLETE_WATER = {66, 101, 102, 103, 104, 108, 109, 110}
RESERVED = {*range(1, 23), 30, 31, 32, 151, 158}
# (source map, floor x/y, blocked x/y). Each floor is visibly on original terrain;
# blocked probes are sky/void. In particular the lava field floor is NOT its lava.
POLARITY_PROBES = (
    (27, (768, 700), (12, 12)),
    (58, (768, 512), (12, 12)),
    (92, (768, 512), (12, 12)),
    (112, (900, 512), (12, 12)),
    (126, (900, 512), (12, 12)),
    (138, (768, 700), (12, 12)),
    (152, (768, 700), (12, 12)),
    (175, (768, 512), (12, 12)),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collision_mask(path: Path, expected_size: tuple[int, int]) -> Image.Image:
    """Convert the authored antialiased threshold without changing its geometry."""
    with Image.open(path) as source:
        rgba = source.convert('RGBA')
        if rgba.size != expected_size:
            raise ValueError(f'{path.name}: artwork/collision dimensions disagree')
        red, green, blue, alpha = rgba.split()
        if ImageChops.difference(red, green).getbbox() or ImageChops.difference(red, blue).getbbox():
            raise ValueError(f'{path.name}: collision must be grayscale')
        if alpha.getextrema() != (255, 255):
            raise ValueError(f'{path.name}: transparent collision is ambiguous')
        return red.point(lambda value: 255 if value < 128 else 0)


def verify_polarity(source: Path) -> None:
    for number, floor, blocked in POLARITY_PROBES:
        with Image.open(source / f'map_{number:03}__collision.png') as mask:
            mask = mask.convert('L')
            if mask.getpixel(floor) != 0 or mask.getpixel(blocked) != 255:
                raise ValueError(f'{number:03}: supplied collision reference probe failed')


def make_foreground(art: Image.Image, layer: Image.Image, mask: Image.Image) -> Image.Image:
    """Keep original pixels and guarantee that supplied walkable decks stay below actors."""
    if art.size != layer.size or art.size != mask.size:
        raise ValueError('Foreground layer dimensions disagree')
    if art.getchannel('A').getextrema() != (255, 255):
        raise ValueError('Composite must contain its opaque original background')
    coverage = layer.convert('RGBA').getchannel('A').point(lambda value: 255 if value else 0)
    coverage = ImageChops.multiply(coverage, ImageChops.invert(mask))
    result = art.copy()
    result.putalpha(coverage)
    return result


def disposition(number: int, duplicate_of: int | None) -> tuple[str, str]:
    if number in PLAYABLE:
        if duplicate_of is not None:
            raise ValueError(f'Playable map {number:03} repeats {duplicate_of:03}')
        return 'playable', 'Distinct adventure field with supplied collision and verified navigation.'
    if number in BLANK:
        return 'incomplete', 'Black placeholder export contains no visible terrain.'
    if number in INCOMPLETE_WATER:
        return 'incomplete', 'Water-only export lacks the terrain described by its collision mask.'
    if duplicate_of is not None:
        return 'duplicate', f'Exact artwork and collision duplicate of source map {duplicate_of:03}.'
    if number == 1:
        return 'reserved', 'World overview illustration, not a playable field.'
    if 5 <= number <= 14:
        return 'reserved', 'Farm/arena layout or farm service room; existing DigiFarm remains authoritative.'
    if number in {151, 158}:
        return 'reserved', 'Small story/cutscene backdrop, with scenery or a baked-in boss covering the floor.'
    if number in RESERVED:
        return 'reserved', 'Town, transport or service location; not an adventure encounter field.'
    raise ValueError(f'Unreviewed source map {number:03}')


def import_maps(source: Path, root: Path = ROOT) -> dict:
    source, root = Path(source), Path(root)
    expected = {f'map_{n:03}.png' for n in range(196)}
    if {p.name for p in source.glob('map_???.png')} != expected:
        raise ValueError('All 196 numbered composite maps are required (000 through 195).')
    verify_polarity(source)
    destination = root / 'assets/maps/xros_wars'
    destination.mkdir(parents=True, exist_ok=True)
    sources, maps, seen = [], [], {}
    definitions = {}
    for zone_order, (zone_id, name, low, high, numbers) in enumerate(ZONES):
        for index, number in enumerate(numbers):
            definitions[number] = (zone_order, zone_id, name, low, high, index, len(numbers))
    for number in range(196):
        paths = sorted(source.glob(f'map_{number:03}*.png'))
        for suffix in ('', '__collision', '__layer_A'):
            if source / f'map_{number:03}{suffix}.png' not in paths:
                raise ValueError(f'Missing source map {number:03}{suffix}.png')
        with Image.open(source / f'map_{number:03}.png') as image:
            art = image.convert('RGBA')
        mask = collision_mask(source / f'map_{number:03}__collision.png', art.size)
        key = hashlib.sha256(art.tobytes() + mask.tobytes()).hexdigest()
        duplicate_of = seen.get(key)
        seen.setdefault(key, number)
        status, reason = disposition(number, duplicate_of)
        entry = {'source_map_number': number, 'id': f'xros_{number:03}', 'status': status,
                 'reason': reason, 'width': art.width, 'height': art.height,
                 'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': digest(p)} for p in paths]}
        if duplicate_of is not None:
            entry['duplicate_of'] = f'xros_{duplicate_of:03}'
        sources.append(entry)
        if status != 'playable':
            continue
        zone_order, zone_id, zone_name, low, high, index, count = definitions[number]
        level = low + (high - low) * index // max(1, count - 1)
        map_id = entry['id']
        base_path = f'assets/maps/xros_wars/{map_id}_base.png'
        mask_path = f'assets/maps/xros_wars/{map_id}_walkable.png'
        shutil.copyfile(source / f'map_{number:03}.png', root / base_path)
        mask.save(root / mask_path, optimize=True)
        foreground_path = None
        layer_path = source / f'map_{number:03}__layer_B.png'
        if layer_path.exists():
            with Image.open(layer_path) as layer:
                foreground = make_foreground(art, layer, mask)
            if foreground.getchannel('A').getbbox():
                foreground_path = f'assets/maps/xros_wars/{map_id}_foreground.png'
                foreground.save(root / foreground_path, optimize=True)
        spawn, geometry = safe_spawn(mask, art)
        geometry.pop('overlay_polarity_verified', None)
        geometry['reference_polarity_verified'] = True
        geometry['foreground_never_covers_walkable_floor'] = True
        area = {'id': map_id, 'name': f'{zone_name} {index + 1:02}',
                'region_id': 'xros_wars', 'region_name': 'Super Xros Wars',
                'zone_id': zone_id, 'zone_name': zone_name, 'zone_order': zone_order,
                'map_order': sum(len(z[-1]) for z in ZONES[:zone_order]) + index,
                'source_map_number': number, 'source_game': 'Digimon Super Xros Wars Blue',
                'path': base_path, 'foreground': foreground_path, 'walkable': mask_path,
                'width': art.width, 'height': art.height, 'spawn': spawn,
                'level': level, 'level_min': max(low, level - 2), 'level_max': min(high, level + 2),
                'native_scale': 1, 'layer': 'composite',
                'provenance': 'User-supplied full composite PNG copied byte for byte; original dimensions, no resampling.',
                'collision_provenance': f'Uploaded map_{number:03}__collision.png; source luminance <128 becomes runtime white floor; geometry unchanged.',
                'foreground_provenance': 'Original composite pixels within supplied B-layer coverage on blocked ground only; bridges and floor remain below actors.',
                'geometry': geometry}
        area.update(soundtrack_for_map(area))
        maps.append(area)
    from venom.server.navigation import Navigation
    navigation = Navigation(root, {m['id']: m for m in maps})
    for area in maps:
        map_id = area['id']
        with Image.open(root / area['path']) as art:
            ensure_arrival_space(navigation, area, art)
        navigation.spawn(map_id)
        points = navigation.spawn_points[map_id]
        if len(points) < 12:
            raise ValueError(f'{map_id}: insufficient connected patrol points ({len(points)})')
        patrol = navigation.patrol(map_id, *area['spawn'], random.Random(map_id), 0)
        if not patrol or len(patrol['segments']) < 4:
            raise ValueError(f'{map_id}: no useful authoritative patrol')
        geometry = area['geometry']
        geometry['verified_patrol_points'] = len(points)
        geometry['verified_patrol_segments'] = len(patrol['segments'])
    maps.sort(key=lambda area: area['map_order'])
    report = {'format': 1, 'region': {'id': 'xros_wars', 'name': 'Super Xros Wars',
              'map_count': len(maps), 'zone_count': len(ZONES), 'level_min': 1, 'level_max': 99},
              'source_archive': 'New folder.part01.rar through New folder.part20.rar',
              'source_map_count': len(sources), 'source_file_count': sum(len(s['files']) for s in sources),
              'naming_note': 'Zone names and progression are authored for Venom NXT; supplied map numbers remain stable.',
              'geometry_note': 'Original composite art unchanged; supplied collision threshold retained. Spawn uses largest connected floor. Disconnected ledges do not receive invented ladders or links.',
              'polarity_probes': [{'source_map_number': n, 'floor': floor, 'blocked': blocked} for n, floor, blocked in POLARITY_PROBES],
              'status_counts': dict(Counter(s['status'] for s in sources)), 'maps': maps, 'source_maps': sources,
              'skipped': [{k: s[k] for k in ('id', 'source_map_number', 'status', 'reason')} for s in sources if s['status'] != 'playable']}
    output = root / 'data/xros_maps.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(f'Imported {len(maps)} adventure fields in {len(ZONES)} zones; all 196 source maps accounted for.')
    print(json.dumps(report['status_counts'], sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Extracted Digimon_Super_Xros_Wars_Blue_Maps_Collision directory')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    import_maps(args.source, args.root)


if __name__ == '__main__':
    main()
