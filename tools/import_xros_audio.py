#!/usr/bin/env python3
"""Import supplied Super Xros Wars WAV music with original intros and exact loops.

Usage: python tools/import_xros_audio.py --source /path/to/Music_WAV
Requires numpy, soundfile and ffmpeg only while rebuilding the assets. Runtime
uses pygame's streamed Ogg decoder and needs none of these import dependencies.
Numeric sequence names are preserved; map and combat assignments are original
Venom NXT arrangements, not claims about the source game's soundtrack names.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
REGION = 'xros_wars'
# All supplied full-length recordings receive a deliberate region role. The
# short nested SEQARC_SE recordings are sound effects, not background music.
WORLD_TRACKS = (
    'xros_bm009', 'xros_002_seq_n_01', 'xros_007_seq_n_07',
    'xros_008_seq_n_08', 'xros_012_seq_n_12', 'xros_014_seq_n_14',
    'xros_bm008', 'xros_bm010', 'xros_bm206', 'xros_020_seq_u_08',
    'xros_021_seq_u_10', 'xros_022_seq_u_11', 'xros_025_seq_u_15',
    'xros_026_seq_u_16', 'xros_027_seq_u_21', 'xros_bm219',
    'xros_013_seq_n_13',
)
SCENES = {'world': 'xros_002_seq_n_01', 'battle': 'xros_bm300',
          'advanced_battle': 'xros_bm307', 'endgame_battle': 'xros_bm608'}


def soundtrack_for_map(area):
    """Return stable exploration and difficulty-tier combat music for a map."""
    level = max(1, min(99, int(area.get('level', area.get('level_min', 1)))))
    index = min(len(WORLD_TRACKS) - 1, (level - 1) * len(WORLD_TRACKS) // 99)
    battle = ('endgame_battle' if level >= 75 else
              'advanced_battle' if level >= 35 else 'battle')
    return {'music_id': WORLD_TRACKS[index], 'battle_music_id': SCENES[battle]}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def wav_loop(path):
    """Read one RIFF forward loop, converting its inclusive end to exclusive."""
    with Path(path).open('rb') as stream:
        header = stream.read(12)
        if header[:4] != b'RIFF' or header[8:] != b'WAVE':
            raise ValueError(f'{path}: expected RIFF WAVE')
        loops = []
        while True:
            chunk = stream.read(8)
            if not chunk:
                break
            if len(chunk) != 8:
                raise ValueError(f'{path}: truncated RIFF chunk')
            tag, size = struct.unpack('<4sI', chunk)
            if tag == b'smpl':
                payload = stream.read(size)
                if len(payload) < 36:
                    raise ValueError(f'{path}: truncated smpl header')
                count = struct.unpack_from('<I', payload, 28)[0]
                if len(payload) < 36 + 24 * count:
                    raise ValueError(f'{path}: truncated smpl loops')
                for offset in range(count):
                    _, kind, start, inclusive_end, fraction, repeats = struct.unpack_from(
                        '<6I', payload, 36 + offset * 24)
                    if kind != 0 or fraction or repeats:
                        raise ValueError(f'{path}: unsupported finite/non-forward loop')
                    loops.append((start, inclusive_end + 1))
            else:
                stream.seek(size, 1)
            stream.seek(size % 2, 1)
    if len(loops) > 1:
        raise ValueError(f'{path}: multiple incompatible loops')
    return loops[0] if loops else None


def _encode(samples, rate, destination, scratch, gain, title):
    temporary = scratch / 'segment.wav'
    sf.write(temporary, samples * gain, rate, subtype='FLOAT')
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(temporary),
                    '-map_metadata', '-1', '-c:a', 'libvorbis', '-q:a', '6',
                    '-metadata', 'TITLE=Super Xros Wars upload ' + title,
                    '-metadata', 'COMMENT=Supplied recording; original Venom NXT scene assignment',
                    str(destination)], check=True)
    decoded, output_rate = sf.read(destination, dtype='float32', always_2d=True)
    if output_rate != rate or len(decoded) != len(samples) or decoded.shape[1] != 2:
        raise ValueError(f'{title}: encoded duration or format changed')
    if not np.isfinite(decoded).all():
        raise ValueError(f'{title}: non-finite decoded audio')
    return {'frames': len(decoded), 'sample_rate': rate, 'channels': 2,
            'duration': len(decoded) / rate,
            'peak': float(np.abs(decoded).max()),
            'rms': float(np.sqrt(np.mean(decoded ** 2)))}


def convert_track(source, metadata, root, scratch):
    samples, rate = sf.read(source, dtype='float32', always_2d=True)
    if rate != 44100 or samples.shape[1] != 2 or not len(samples) or not np.isfinite(samples).all():
        raise ValueError(f'{source.name}: invalid supplied stereo recording')
    digest = sha256(source)
    if metadata and metadata.get('sha256') != digest:
        raise ValueError(f'{source.name}: supplied manifest hash mismatch')
    if metadata and metadata.get('frames') != len(samples):
        raise ValueError(f'{source.name}: supplied frame count mismatch')
    loop = wav_loop(source)
    if loop and not 0 <= loop[0] < loop[1] <= len(samples):
        raise ValueError(f'{source.name}: loop outside source frames')
    if metadata:
        expected = ((metadata['loop_start_frame'], metadata['loop_end_frame_exclusive'])
                    if metadata.get('loop') else None)
        if loop != expected:
            raise ValueError(f'{source.name}: embedded loop differs from supplied manifest')
    identifier = 'xros_' + source.stem.lower()
    destination = root / 'assets/audio/xros_wars' / (identifier + '.ogg')
    destination.parent.mkdir(parents=True, exist_ok=True)
    segments = {'loop': samples[loop[0]:loop[1]] if loop else samples}
    if loop and loop[0]:
        segments['intro'] = samples[:loop[0]]
    peak = float(np.abs(samples).max())
    if peak < .0001:
        raise ValueError(f'{source.name}: silent recording')
    # Match the existing DS region's listening level with one constant gain,
    # preserving original mix dynamics and the intro/loop join. No compression,
    # replacement instruments, or added fades; leave headroom for Ogg decoding.
    rms = float(np.sqrt(np.mean(samples ** 2)))
    gain = min(10 ** (-18 / 20) / max(rms, .00001), 10 ** (-2 / 20) / peak)
    quality = {}
    for _ in range(3):
        for segment, recording in segments.items():
            output = destination if segment == 'loop' else destination.with_stem(identifier + '_intro')
            quality[segment] = _encode(recording, rate, output, scratch, gain, identifier + ' ' + segment)
        output_peak = max(value['peak'] for value in quality.values())
        if output_peak <= .98:
            break
        gain *= .94 / output_peak
    if output_peak > .98:
        raise ValueError(f'{source.name}: encoded output exceeds safe peak')
    track = {'id': identifier, 'region_id': REGION,
             'path': destination.relative_to(root).as_posix(),
             'sha256': sha256(destination), 'looped': bool(loop),
             'duration': quality['loop']['duration'],
             'source': {'file': source.name, 'sha256': digest,
                        'manifest_verified': bool(metadata),
                        'sequence': metadata.get('source_sequence', source.stem),
                        'frames': len(samples), 'sample_rate': rate,
                        'loop_start_frame': loop[0] if loop else None,
                        'loop_end_frame_exclusive': loop[1] if loop else None,
                        'loop_metadata': 'RIFF smpl; inclusive end converted to exclusive' if loop else 'one-shot',
                        'frames_after_loop_omitted': len(samples) - loop[1] if loop else 0},
             'quality': {'segments': quality, 'gain': gain, 'target_rms_dbfs': -18,
                         'encoding': 'Stereo Ogg Vorbis quality 6; source PCM timing retained'}}
    if 'intro' in segments:
        intro = destination.with_stem(identifier + '_intro')
        track.update(intro_path=intro.relative_to(root).as_posix(), intro_sha256=sha256(intro),
                     intro_duration=quality['intro']['duration'])
    if identifier == 'xros_bm009':
        # This supplied non-looping composition is arrival music. Let it finish
        # naturally, then continue a real exploration loop without silence.
        track['continuation_id'] = SCENES['world']
    return track


def import_audio(source, root):
    source, root = Path(source), Path(root)
    manifest_path = source / 'music_manifest.json'
    metadata = json.loads(manifest_path.read_text('utf-8'))
    supplied = {track['file']: track for track in metadata.get('tracks', [])}
    recordings = sorted(source.glob('*.wav'))
    if not recordings:
        raise ValueError('No root-level music WAV files were supplied.')
    music = []
    with tempfile.TemporaryDirectory(prefix='venom-xros-audio-') as folder:
        for path in recordings:
            music.append(convert_track(path, supplied.get(path.name, {}), root, Path(folder)))
            print(path.name + ' intro/loop encoded and decoded successfully', flush=True)
    seen = {track['id'] for track in music}
    if not (set(WORLD_TRACKS) | set(SCENES.values())) <= seen:
        raise ValueError('One or more assigned supplied music recordings is missing.')
    omitted_effects = [{'file': path.relative_to(source).as_posix(), 'sha256': sha256(path),
                        'reason': 'Supplied sound effect, not background music'}
                       for path in sorted(source.rglob('*.wav')) if path.parent != source]
    missing = [name for name in supplied if not (source / name).is_file()]
    result = {'version': 1, 'region_id': REGION,
              'source': {'manifest_sha256': sha256(manifest_path),
                         'source_sdat_sha256': metadata.get('source_sdat_sha256'),
                         'renderer': metadata.get('renderer'),
                         'assignment_note': 'Music and battle assignments are original Venom NXT choices; numeric IDs are preserved, not presented as official track or location titles.',
                         'coverage_note': 'The supplied manifest describes 62 bm recordings; this upload contains 8 of those and 12 additional SEQ recordings with valid embedded loop metadata. All 20 supplied music recordings are included.',
                         'manifest_recordings_not_supplied': missing,
                         'conversion': 'Source intro once, then exact embedded sample loop indefinitely; stereo Ogg Vorbis quality 6 with uniform -18 dBFS RMS gain bounded by -2 dBFS source peak. One-shot arrival composition queues a supplied exploration loop. All streams decoded and verified.'},
              'music': music, 'effects': [], 'scene_tracks': SCENES,
              'world_tracks': list(WORLD_TRACKS), 'skipped': omitted_effects}
    path = root / 'data/xros_audio.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(f'{len(music)} music recordings imported; {len(omitted_effects)} SFX left unchanged.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    import_audio(args.source.resolve(), args.root.resolve())


if __name__ == '__main__':
    main()
