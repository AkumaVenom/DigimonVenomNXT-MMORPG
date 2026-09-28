#!/usr/bin/env python3
"""Install the supplied six-pose Fanglongmon artwork without changing gameplay.

Accepts the original RAR or an extracted directory. PNG files are copied byte for
byte; the per-species animation sidecars also survive a full catalog rebuild.
RAR import needs libarchive-c and system libarchive (import-only dependencies).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FORMS = {
    'fanglongmon': (
        'fanglongmon_01_idle.png', 'fanglongmon_02_idle_part_2.png',
        'fanglongmon_03_walk_r.png', 'fanglongmon_04_walk_l.png',
        'fanglongmon_05_attack_start.png', 'fanglongmon_06_attack_part_2.png',
    ),
    'fanglongmon_paradox': (
        'Fanglongmon_Paradox_01_Idle.png', 'Fanglongmon_Paradox_02_Idle_Part_2.png',
        'Fanglongmon_Paradox_03_Walk_R.png', 'Fanglongmon_Paradox_04_Walk_L.png',
        'Fanglongmon_Paradox_05_Attack_Start.png', 'Fanglongmon_Paradox_06_Attack_Part_2.png',
    ),
}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def extract_archive(source: Path, destination: Path) -> None:
    import libarchive
    expected = {name for names in FORMS.values() for name in names}
    seen = set()
    with libarchive.file_reader(str(source)) as archive:
        for entry in archive:
            path = Path(entry.pathname)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.pathname:
                raise ValueError('Unsafe Fanglongmon archive path.')
            if entry.isdir:
                continue
            if not entry.isfile or path.name not in expected or path.name in seen:
                raise ValueError(f'Unexpected or duplicate archive member: {path.name}')
            seen.add(path.name)
            if entry.size > 16 * 1024 * 1024:
                raise ValueError('Fanglongmon frame exceeds the expected source size.')
            with (destination / path.name).open('wb') as stream:
                for block in entry.get_blocks():
                    stream.write(block)
    if seen != expected:
        raise ValueError('Both forms require all six supplied animation frames.')


def import_frames(source: Path, root: Path = ROOT, *, archive_source: Path | None = None) -> dict:
    """Validate both complete forms before publishing any catalog changes."""
    catalog_path = root / 'data/catalog.json'
    catalog = json.loads(catalog_path.read_text('utf-8'))
    species = {entry['id']: entry for entry in catalog['species']}
    if any(sid not in species for sid in FORMS):
        raise ValueError('The existing normal and Paradox Fanglongmon records are required.')
    frames = {}
    for names in FORMS.values():
        for name in names:
            matches = list(source.rglob(name))
            if len(matches) != 1 or matches[0].is_symlink():
                raise ValueError(f'Expected one ordinary source file: {name}')
            path = matches[0]
            with Image.open(path) as image:
                if image.format != 'PNG' or image.mode != 'RGBA' or image.size != (1254, 1254):
                    raise ValueError(f'Unexpected supplied frame format: {name}')
                image.load()
                if image.getchannel('A').getextrema()[0] != 0:
                    raise ValueError(f'Source transparency is missing: {name}')
            frames[name] = path
    published = []
    for sid, names in FORMS.items():
        directory = root / 'assets/digimon/7 Mega/Fanglongmon'
        if sid.endswith('_paradox'):
            directory /= 'Paradox'
        (directory / 'Frames').mkdir(parents=True, exist_ok=True)
        prefix = 'Fanglongmon_Paradox' if sid.endswith('_paradox') else 'Fanglongmon'
        paths = [f'Frames/{prefix}_Frame_{index:03d}.png' for index in range(1, 7)]
        for name, relative in zip(names, paths):
            destination = directory / relative
            temporary = destination.with_suffix('.png.tmp')
            shutil.copyfile(frames[name], temporary)
            temporary.replace(destination)
            published.append({'source': name, 'path': destination.relative_to(root).as_posix(),
                              'size': destination.stat().st_size, 'sha256': digest(destination)})
        sidecar = {
            'version': 1,
            'sprites': dict(zip(('idle', 'idle2', 'walk_right', 'walk_left', 'attack1', 'attack2'), paths)),
            'animations': {'idle': paths[:2], 'walk': [paths[0], paths[2], paths[1], paths[2]],
                           'attack': paths[4:6]},
            # A left-facing source pose replaces only the right step. Mirrored
            # idle poses keep the walking cycle facing left between steps.
            'mirrored_frames': {paths[2]: paths[3], paths[3]: paths[2]},
            'source_frame_count': 6,
            'frame_selection': 'Six supplied labelled poses: two idle, right/left step, two attack; original PNG bytes preserved',
            'art_provenance': 'User-supplied Fanglongmon and Paradox six-frame pack; v1.0.0',
        }
        write_json(directory / 'animation.json', sidecar)
        from tools.import_assets import animation_override
        species[sid].update(animation_override(directory, root))
    write_json(catalog_path, catalog)
    provenance_path = root / 'data/source_assets.json'
    sources = json.loads(provenance_path.read_text('utf-8')) if provenance_path.exists() else []
    sources = [entry for entry in sources if entry.get('kind') != 'fanglongmon_v100']
    record = {'kind': 'fanglongmon_v100', 'use': 'Replacement art for existing normal and Paradox Fanglongmon IDs',
              'frames': published}
    if archive_source:
        record.update(filename=archive_source.name, size=archive_source.stat().st_size,
                      sha256=digest(archive_source))
    sources.append(record)
    write_json(provenance_path, sources)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    # Running as a direct script must make the sibling tools package importable.
    import sys
    sys.path.insert(0, str(ROOT))
    with tempfile.TemporaryDirectory(prefix='fanglongmon-') as temporary:
        source = args.source.resolve()
        archive = source if source.is_file() else None
        if archive:
            extract_archive(archive, Path(temporary))
            source = Path(temporary)
        record = import_frames(source, args.root.resolve(), archive_source=archive)
    print(json.dumps({'forms': list(FORMS), 'frames': len(record['frames']),
                      'note': 'Refresh the release asset manifest after all asset changes are complete.'}))


if __name__ == '__main__':
    main()
