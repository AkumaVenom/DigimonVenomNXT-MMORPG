#!/usr/bin/env python3
"""Import supplied Digimon World DS preview recordings, never synthesize MIDI.

Usage: python tools/import_world_ds_audio.py --source /path/to/part1.rar
An extracted folder containing tracks/bgmNN/* is also accepted. Multipart RAR
reading requires libarchive-c and system libarchive; encoding requires ffmpeg,
numpy and soundfile. These are build-time dependencies only.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
TARGET_RMS = 10 ** (-18 / 20)
PEAK_LIMIT = 10 ** (-2 / 20)
SCENES = {'world': 'ds_bgm10', 'battle': 'ds_bgm03',
          'endgame_battle': 'ds_bgm17', 'victory': 'ds_bgm30'}


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def extract_previews(source: Path, output: Path):
    """Read ordered volumes with libarchive, keeping only recordings/metadata."""
    import libarchive.ffi as ffi
    from libarchive.read import ArchiveRead, new_archive_read
    paths = sorted(source.parent.glob(source.name.split('.part')[0] + '.part*.rar'))
    if not paths:
        paths = [source]
    encoded = [str(path.resolve()).encode() for path in paths]
    names = (ctypes.c_char_p * (len(encoded) + 1))(*encoded, None)
    open_volumes = ffi.libarchive.archive_read_open_filenames
    open_volumes.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t]
    open_volumes.restype = ctypes.c_int
    with new_archive_read() as pointer:
        if open_volumes(pointer, names, 65536) != 0:
            raise RuntimeError('Cannot open all source archive volumes.')
        for entry in ArchiveRead(pointer):
            relative = Path(entry.pathname)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe archive path: ' + str(relative))
            if (entry.isdir or relative.parts[0] != 'tracks' or
                    not (relative.name.endswith('_preview.flac') or
                         relative.name in ('track.json', 'sequence_events.json'))):
                continue
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('wb') as stream:
                for block in entry.get_blocks():
                    stream.write(block)
    return [{'name': path.name, 'sha256': sha256(path)} for path in paths]


def convert_track(metadata_path: Path, root: Path, scratch: Path):
    metadata = json.loads(metadata_path.read_text('utf-8'))
    name = metadata['name']
    preview = metadata_path.with_name(name + '_preview.flac')
    samples, rate = sf.read(preview, dtype='float32', always_2d=True)
    if not len(samples) or samples.shape[1] != 2 or not np.isfinite(samples).all():
        raise ValueError(f'{name}: invalid stereo source recording')
    loops = {(round(loop['start_seconds'], 9), round(loop['end_seconds'], 9))
             for loop in metadata.get('loops', [])}
    if len(loops) > 1:
        raise ValueError(f'{name}: inconsistent track loop ranges')
    start, end = next(iter(loops)) if loops else (0., len(samples) / rate)
    first, last = round(start * rate), round(end * rate)
    if not (0 <= first < last <= len(samples)):
        raise ValueError(f'{name}: loop lies outside the supplied recording')
    samples = samples[first:last].copy()
    # A two-millisecond endpoint taper prevents a sample discontinuity when SDL
    # repeats the exact original sequence loop. It neither adds a silence tail
    # nor changes the musical bar length.
    edge = min(round(rate * .002), len(samples) // 2)
    ramp = np.linspace(0., 1., edge, dtype=np.float32)[:, None]
    samples[:edge] *= ramp
    samples[-edge:] *= ramp[::-1]
    peak, rms = float(np.abs(samples).max()), float(np.sqrt(np.mean(samples ** 2)))
    if peak <= .0001 or rms <= .00001:
        raise ValueError(f'{name}: silent source recording')
    gain = min(TARGET_RMS / rms, PEAK_LIMIT / peak)
    destination = root / 'assets/audio/world_ds' / ('ds_' + name + '.ogg')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = scratch / (name + '.wav')
    encoded = scratch / (name + '.ogg')
    for _ in range(3):
        sf.write(temporary, samples * gain, rate, subtype='FLOAT')
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(temporary),
                        '-map_metadata', '-1', '-c:a', 'libvorbis', '-q:a', '6',
                        '-metadata', 'TITLE=Digimon World DS ' + name,
                        '-metadata', 'COMMENT=Supplied preview recording; original Venom NXT scene assignment',
                        str(encoded)], check=True)
        decoded, output_rate = sf.read(encoded, dtype='float32', always_2d=True)
        output_peak = float(np.abs(decoded).max())
        if output_peak <= .98:
            break
        gain *= .94 / output_peak
    if output_peak > .98 or not np.isfinite(decoded).all():
        raise ValueError(f'{name}: encoded output exceeds safe peak')
    if len(decoded) != len(samples):
        raise ValueError(f'{name}: encoded output was truncated')
    # Publish a complete file so asset indexers cannot see a partial recording.
    import shutil
    staging = destination.with_suffix('.ogg.tmp')
    shutil.copyfile(encoded, staging)
    staging.replace(destination)
    events_path = metadata_path.with_name('sequence_events.json')
    events = json.loads(events_path.read_text('utf-8')) if events_path.exists() else {}
    return {'id': 'ds_' + name, 'region_id': 'world_ds',
            'path': destination.relative_to(root).as_posix(),
            'duration': round(len(decoded) / output_rate, 6), 'looped': bool(loops),
            'sha256': sha256(destination),
            'source': {'preview_path': 'tracks/' + name + '/' + preview.name,
                       'preview_sha256': sha256(preview),
                       'sequence_sha256': metadata['source_sseq_sha256'],
                       'loop_start_seconds': start, 'loop_end_seconds': end,
                       'tempo': events.get('tempos', []),
                       'preview_accuracy': metadata.get('preview_accuracy', '')},
            'quality': {'sample_rate': output_rate, 'channels': int(decoded.shape[1]),
                        'frames': len(decoded), 'peak': round(output_peak, 6),
                        'rms': round(float(np.sqrt(np.mean(decoded ** 2))), 6),
                        'gain_db': round(20 * math.log10(gain), 4),
                        'endpoint_taper_ms': 2, 'missing_instruments': []}}


def import_audio(source: Path, root: Path):
    with tempfile.TemporaryDirectory(prefix='venom-ds-audio-') as folder:
        scratch = Path(folder)
        archives = []
        if source.is_dir():
            extracted = source
        else:
            extracted = scratch / 'source'
            archives = extract_previews(source, extracted)
        music, skipped = [], []
        for path in sorted(extracted.glob('tracks/*/track.json')):
            metadata = json.loads(path.read_text('utf-8'))
            identifier = 'ds_' + metadata['name']
            missing = metadata.get('preview', {}).get('missing_instruments', [])
            if metadata.get('duplicate_of_sequence_id') is not None:
                skipped.append({'id': identifier, 'reason': 'Duplicate source sequence',
                                'duplicate_of': f"ds_bgm{metadata['duplicate_of_sequence_id']:02d}"})
            elif missing or metadata.get('trace_errors'):
                skipped.append({'id': identifier, 'reason': 'Incomplete supplied preview',
                                'missing_instruments': missing,
                                'trace_errors': metadata.get('trace_errors', [])})
            else:
                music.append(convert_track(path, root, scratch))
                print(identifier + ' encoded and decoded successfully', flush=True)
        if not music or not set(SCENES.values()) <= {track['id'] for track in music}:
            raise ValueError('Source is missing one or more required scene recordings.')
        for track in music:
            destination = root / track['path']
            if (sha256(destination) != track['sha256'] or
                    sf.info(destination).frames != track['quality']['frames']):
                raise ValueError(f"{track['id']}: output changed before manifest publication")
        result = {'version': 1, 'region_id': 'world_ds',
                  'source': {'archives': archives,
                             'preview_accuracy': 'Uses supplied approximate software mixes of original samples; no new synthesis. Source previews are not hardware-bit-exact.',
                             'assignment_note': 'Region, battle and victory assignments are original Venom NXT choices; numeric source names do not identify official map music.',
                             'conversion': 'Original sequence loop range, 2 ms click-prevention taper, RMS target -18 dBFS bounded by -2 dBFS source peak, stereo Ogg Vorbis quality 6. All outputs decoded and checked for clipping.'},
                  'music': music, 'effects': [], 'scene_tracks': SCENES, 'skipped': skipped}
        target = root / 'data/world_ds_audio.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
        print(f'{len(music)} recordings imported; {len(skipped)} duplicates/incomplete previews omitted.')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    options = parser.parse_args()
    import_audio(options.source.resolve(), options.root.resolve())


if __name__ == '__main__':
    main()
