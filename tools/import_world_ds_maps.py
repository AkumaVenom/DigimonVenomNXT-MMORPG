"""Import supplied Digimon World DS fields without redrawing terrain or collision.

Input: an extracted upload directory, or all numbered RAR volumes. Artwork stays
at its supplied resolution. Source collision is black=walkable: the paired red
collision overlays provide a pixel-level polarity check before conversion.
Only adventure fields are published. Farm upgrades/service rooms are reserved;
duplicate clearings and water-only incomplete exports remain provenance records.

Pillow is the only import dependency. RAR extraction additionally needs
libarchive-c and a system libarchive supporting RAR. Neither is used at runtime.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
# Names are descriptive Venom NXT locations, not claims of canonical DS names.
ZONES = (
    (30, 30, 'forest_glade', 'Forest Glade', 1, 4, 7),
    (48, 52, 'green_valley', 'Green Valley', 1, 8, 10),
    (53, 58, 'sandstone_pass', 'Sandstone Pass', 8, 14, 19),
    (59, 65, 'drainage_tunnels', 'Drainage Tunnels', 14, 22, 13),
    (66, 72, 'canopy_ridge', 'Canopy Ridge', 22, 30, 8),
    (73, 79, 'sun_spire', 'Sun Spire', 30, 38, 0),
    (80, 88, 'crystal_mine', 'Crystal Mine', 38, 45, 24),
    (89, 96, 'mirage_marsh', 'Mirage Marsh', 45, 53, 11),
    (97, 105, 'silver_strand', 'Silver Strand', 53, 61, 12),
    (106, 114, 'amber_badlands', 'Amber Badlands', 61, 68, 2),
    (115, 124, 'clockwork_fort', 'Clockwork Fort', 68, 75, 16),
    (125, 132, 'frost_shelf', 'Frost Shelf', 75, 81, 21),
    (140, 148, 'radiant_citadel', 'Radiant Citadel', 81, 86, 1),
    (149, 160, 'coral_archipelago', 'Coral Archipelago', 86, 90, 5),
    (161, 172, 'magma_citadel', 'Magma Citadel', 90, 94, 15),
    (173, 184, 'shadow_grid', 'Shadow Grid', 94, 97, 25),
    (185, 187, 'core_terminal', 'Core Terminal', 97, 99, 28),
    (188, 191, 'emerald_spire', 'Emerald Spire', 84, 89, 6),
    (192, 195, 'dusk_highlands', 'Dusk Highlands', 88, 92, 14),
    (196, 199, 'void_isles', 'Void Isles', 92, 96, 23),
    (200, 203, 'eclipse_sanctum', 'Eclipse Sanctum', 96, 99, 29),
)
RUNS = re.compile(b'\xff+')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_volumes(first: Path, destination: Path) -> None:
    """Read numbered volumes together, refusing nested/unexpected filenames."""
    import libarchive.ffi as ffi
    from libarchive.read import ArchiveRead, new_archive_read
    files = sorted(first.parent.glob('DigimonWorldMapLevels.part*.rar'))
    expected = [f'DigimonWorldMapLevels.part{i:02}.rar' for i in range(1, 14)]
    if [p.name for p in files] != expected:
        raise ValueError('All 13 numbered map RAR volumes are required.')
    function = ffi.libarchive.archive_read_open_filenames
    function.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t]
    function.restype = ctypes.c_int
    names = (ctypes.c_char_p * (len(files) + 1))(*[str(p).encode() for p in files], None)
    destination.mkdir(parents=True, exist_ok=True)
    with new_archive_read() as pointer:
        if function(pointer, names, 65536) != 0:
            raise ValueError('Could not open multipart map archive.')
        for entry in ArchiveRead(pointer):
            if not re.fullmatch(r'map_\d{3}_(?:collision_mask|collision_overlay|layers_layer_[abc]|map_composite|tile_attributes_values)\.png', entry.pathname):
                raise ValueError(f'Unexpected archive entry: {entry.pathname}')
            with (destination / entry.pathname).open('wb') as stream:
                for block in entry.get_blocks():
                    stream.write(block)


def collision_mask(source: Path, number: int) -> Image.Image:
    """Verify source convention; invert its antialiased threshold, never guess."""
    prefix = source / f'map_{number:03}'
    with Image.open(f'{prefix}_collision_mask.png') as image:
        raw = image.convert('L')
    with Image.open(f'{prefix}_map_composite.png') as image:
        art = image.convert('RGBA')
    with Image.open(f'{prefix}_collision_overlay.png') as image:
        overlay = image.convert('RGBA')
    if raw.size != art.size or raw.size != overlay.size:
        raise ValueError(f'{number}: collision/overlay/art dimensions disagree')
    changed = Image.new('L', raw.size)
    for channel in ImageChops.difference(art, overlay).split():
        changed = ImageChops.lighter(changed, channel)
    black = raw.point(lambda value: 255 if value == 0 else 0)
    white = raw.point(lambda value: 255 if value == 255 else 0)
    if ImageChops.multiply(changed, black).getbbox():
        raise ValueError(f'{number}: source black floor does not match unchanged overlay')
    if not ImageChops.multiply(changed, white).getbbox():
        raise ValueError(f'{number}: source blocked ground has no collision overlay')
    return raw.point(lambda value: 255 if value < 128 else 0)


def safe_spawn(mask: Image.Image, art: Image.Image) -> tuple[list[int], dict]:
    """Find largest 4-connected floor using scanline union-find, not image color.

    The emitted mask stays untouched. Boundary restrictions match Navigation;
    spawn alone requires 9x9 clear ground and visible source artwork.
    """
    width, height = mask.size
    data = mask.tobytes()
    parents, spans, areas = [], [], []
    previous = []

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(a, b):
        a, b = find(a), find(b)
        if a == b:
            return
        if areas[a] < areas[b]:
            a, b = b, a
        parents[b] = a
        areas[a] += areas[b]

    for y in range(12, height - 11):
        row = data[y * width + 12:y * width + width - 11]
        current = []
        cursor = 0
        for match in RUNS.finditer(row):
            left, right = match.start() + 12, match.end() + 12
            index = len(parents)
            parents.append(index)
            areas.append(right - left)
            spans.append((y, left, right))
            while cursor < len(previous) and previous[cursor][1] <= left:
                cursor += 1
            other = cursor
            while other < len(previous) and previous[other][0] < right:
                union(index, previous[other][2])
                other += 1
            current.append((left, right, index))
        previous = current
    if not parents:
        raise ValueError('Map has no connected floor')
    largest = max(range(len(parents)), key=lambda index: areas[index] if parents[index] == index else -1)
    selected = [span for index, span in enumerate(spans) if find(index) == largest]
    size = areas[largest]
    if size < 4096:
        raise ValueError(f'Connected floor too small for player and bot activity: {size}')
    bounds = [min(s[1] for s in selected), min(s[0] for s in selected),
              max(s[2] for s in selected), max(s[0] for s in selected) + 1]
    safe = mask.filter(ImageFilter.MinFilter(9)).tobytes()
    alpha = art.convert('RGBA').getchannel('A').tobytes()
    center_x, center_y = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
    best = None
    best_distance = float('inf')
    for y, left, right in selected:
        for x in range(left, right, 4):
            offset = y * width + x
            if safe[offset] == 255 and alpha[offset] == 255:
                distance = (x - center_x) ** 2 + (y - center_y) ** 2
                if distance < best_distance:
                    best_distance, best = distance, [x, y]
    if best is None:
        raise ValueError('Largest connected floor has no safe visible arrival point')
    return best, {'largest_component_pixels': size, 'largest_component_bounds': bounds,
                  'spawn_clearance_pixels': 4, 'source_black_is_walkable': True,
                  'overlay_polarity_verified': True}



def arrival_spacing(navigation, map_id: str, count: int = 20) -> float:
    """Validate realistic simultaneous arrivals, not only graph node count."""
    occupied = []
    minimum = float('inf')
    for ordinal in range(count):
        point = navigation.arrival(map_id, occupied, ordinal)
        if not navigation.walkable(map_id, *point):
            raise ValueError(f'{map_id}: blocked authoritative arrival')
        if occupied:
            minimum = min(minimum, min(math.dist(point, other) for other in occupied))
        occupied.append(point)
    return minimum


def ensure_arrival_space(navigation, area: dict, artwork: Image.Image) -> None:
    """Keep the largest component, choosing a better origin if a local ledge
    traps the deterministic patrol cloud. No collision pixels are modified.
    """
    map_id = area['id']
    minimum = arrival_spacing(navigation, map_id)
    if minimum < 16:
        with Image.open(navigation.root / area['walkable']) as image:
            mask = image.convert('L')
        connected = mask.copy()
        ImageDraw.floodfill(connected, tuple(area['spawn']), 128)
        component = connected.point(lambda value: 255 if value == 128 else 0)
        safe = ImageChops.multiply(component, mask.filter(ImageFilter.MinFilter(9)))
        pixels, alpha = safe.load(), artwork.convert('RGBA').getchannel('A').load()
        bounds = component.getbbox()
        original = tuple(area['spawn'])
        candidates = [(x, y) for y in range(max(16, bounds[1]), min(mask.height - 16, bounds[3]), 8)
                      for x in range(max(16, bounds[0]), min(mask.width - 16, bounds[2]), 8)
                      if pixels[x, y] == 255 and alpha[x, y] == 255]
        candidates.sort(key=lambda point: (math.dist(point, original), point[1], point[0]))
        for candidate in candidates:
            area['spawn'] = list(candidate)
            navigation.spawn_points.pop(map_id, None)
            navigation.edges.pop(map_id, None)
            navigation.arrival_points.pop(map_id, None)
            minimum = arrival_spacing(navigation, map_id)
            if minimum >= 16:
                break
        else:
            raise ValueError(f'{map_id}: supplied floor cannot support twenty spaced arrivals')
    area['geometry']['verified_arrival_count'] = 20
    area['geometry']['minimum_arrival_spacing_pixels'] = math.floor(minimum * 1000) / 1000


def disposition(number: int) -> tuple[str, str]:
    if number < 30:
        return 'reserved', 'Farm upgrade layout; retained as source, existing DigiFarm unchanged.'
    if 31 <= number <= 34:
        return 'duplicate', 'Identical forest clearing artwork and collision; map 030 is playable.'
    if number == 35:
        return 'reserved', 'Real-world classroom with placeholder rectangular collision; not a wild field.'
    if 36 <= number <= 47:
        return 'reserved', 'Town/service interior reserved for future appropriate NPC features.'
    if 133 <= number <= 139:
        return 'incomplete', 'Export contains water texture only; collision refers to terrain absent from supplied art.'
    return 'playable', 'Adventure field with verified supplied collision.'


def import_maps(source: Path, root: Path = ROOT) -> dict:
    map_destination, collision_destination = root / 'assets/maps/world_ds', root / 'assets/collision/world_ds'
    map_destination.mkdir(parents=True, exist_ok=True)
    collision_destination.mkdir(parents=True, exist_ok=True)
    maps, sources = [], []
    for number in range(204):
        files = sorted(source.glob(f'map_{number:03}_*.png'))
        if len(files) not in (6, 7):
            raise ValueError(f'Incomplete source map {number}: {len(files)} files')
        status, reason = disposition(number)
        with Image.open(source / f'map_{number:03}_map_composite.png') as image:
            art = image.convert('RGBA')
        source_entry = {'source_map_number': number, 'id': f'world_ds_{number:03}',
                        'status': status, 'reason': reason, 'width': art.width, 'height': art.height,
                        'files': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': digest(p)} for p in files]}
        sources.append(source_entry)
        if status != 'playable':
            continue
        first, last, zone_id, zone_name, minimum, maximum, music = next(zone for zone in ZONES if zone[0] <= number <= zone[1])
        level = minimum + (maximum - minimum) * (number - first) // max(1, last - first)
        low, high = max(minimum, level - 2), min(maximum, level + 2)
        if first == last:
            low, high = minimum, maximum
        mask = collision_mask(source, number)
        spawn, geometry = safe_spawn(mask, art)
        map_id = f'world_ds_{number:03}'
        base_path = f'assets/maps/world_ds/{map_id}_base.png'
        mask_path = f'assets/collision/world_ds/{map_id}.png'
        original_base = source / f'map_{number:03}_layers_layer_a.png'
        with Image.open(original_base) as base:
            if base.size != art.size:
                raise ValueError(f'{number}: source base dimensions differ')
        shutil.copyfile(original_base, root / base_path)
        mask.save(root / mask_path, optimize=True)
        foreground = Image.new('RGBA', art.size)
        foreground_sources = []
        for layer in 'bc':
            path = source / f'map_{number:03}_layers_layer_{layer}.png'
            if path.exists():
                with Image.open(path) as image:
                    if image.size != art.size:
                        raise ValueError(f'{number}: source foreground dimensions differ')
                    if image.convert('RGBA').getchannel('A').getbbox():
                        foreground = Image.alpha_composite(foreground, image.convert('RGBA'))
                        foreground_sources.append(path)
        foreground_path = None
        if foreground_sources:
            foreground_path = f'assets/maps/world_ds/{map_id}_foreground.png'
            if len(foreground_sources) == 1:
                shutil.copyfile(foreground_sources[0], root / foreground_path)
            else:
                foreground.save(root / foreground_path, optimize=True)
        maps.append({'id': map_id, 'name': zone_name if first == last else f'{zone_name} {number - first + 1:02}',
                     'region_id': 'world_ds', 'region_name': 'Digimon World DS',
                     'zone_id': zone_id, 'zone_name': zone_name, 'zone_order': ZONES.index((first, last, zone_id, zone_name, minimum, maximum, music)),
                     'source_map_number': number, 'source_game': 'Digimon World DS',
                     'path': base_path, 'foreground': foreground_path, 'walkable': mask_path,
                     'width': art.width, 'height': art.height, 'spawn': spawn,
                     'level': level, 'level_min': low, 'level_max': high,
                     'music_id': f'ds_bgm{music:02}', 'battle_music_id': f'ds_bgm{17 if low >= 75 else 3:02}',
                     'native_scale': 1, 'layer': 'a',
                     'provenance': 'User-supplied Digimon World DS PNG layers; original pixel dimensions, no resampling.',
                     'collision_provenance': f'Uploaded map_{number:03}_collision_mask.png; verified overlay; source luminance <128 walkable, inverted to runtime white floor.',
                     'geometry': geometry})
    # Exercise the actual authoritative movement algorithm, including routes.
    sys.path.insert(0, str(root))
    from venom.server.navigation import Navigation
    import random
    navigation = Navigation(root, {m['id']: m for m in maps})
    for area in maps:
        map_id = area['id']
        with Image.open(source / f"map_{area['source_map_number']:03}_map_composite.png") as artwork:
            ensure_arrival_space(navigation, area, artwork)
        navigation.spawn(map_id)
        points = navigation.spawn_points[map_id]
        if len(points) < 12:
            raise ValueError(f'{map_id}: insufficient connected bot patrol space ({len(points)} points)')
        route = navigation.patrol(map_id, *area['spawn'], random.Random(map_id), 0)
        if not route or len(route['segments']) < 4:
            raise ValueError(f'{map_id}: no useful authoritative patrol')
        area['geometry']['verified_patrol_points'] = len(points)
    report = {'format': 1, 'region': {'id': 'world_ds', 'name': 'Digimon World DS', 'map_count': len(maps), 'level_min': 1, 'level_max': 99},
              'source_archive': 'DigimonWorldMapLevels.part01.rar through part13.rar',
              'source_map_count': 204, 'source_file_count': sum(len(s['files']) for s in sources),
              'naming_note': 'Zone names and level progression are authored for Venom NXT; supplied map numbers remain stable.',
              'geometry_note': 'Art dimensions unchanged. Supplied masks retain their thresholded geometry. Spawn selects largest connected floor; no terrain or ladder links are invented.',
              'maps': maps, 'source_maps': sources,
              'skipped': [{k: s[k] for k in ('id', 'source_map_number', 'status', 'reason')} for s in sources if s['status'] != 'playable']}
    destination = root / 'data/world_ds_maps.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(f'Imported {len(maps)} playable maps; indexed all {len(sources)} source maps; verified every bot patrol.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source', type=Path, help='Directory containing all extracted map PNGs')
    group.add_argument('--archive', type=Path, help='part01.rar beside the other 12 parts')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    if args.source:
        import_maps(args.source, args.root)
    else:
        with tempfile.TemporaryDirectory(prefix='venom-world-ds-') as folder:
            source = Path(folder)
            extract_volumes(args.archive, source)
            import_maps(source, args.root)


if __name__ == '__main__':
    main()
