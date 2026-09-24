"""Compose the original DigiFarm theme, ``A Place to Grow``.

Run from any directory: python tools/compose_digifarm_music.py
Build-only dependencies: numpy and ffmpeg (with libvorbis). The game streams the
shipped OGG and needs neither dependency. Every note, instrument, and rhythm is generated here;
no samples or existing melodies are used. Fixed seed, tempo, and wrapped tails
make the arrangement repeatable and the 32-bar loop seamless.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 32768
BPM = 96
BEAT = 60 / BPM
BARS = 32
LENGTH = round(BARS * 4 * BEAT * SAMPLE_RATE)


def compose() -> np.ndarray:
    """Render gentle rounded mallets, a soft synth pad, bass and brush rhythm."""
    mix = np.zeros((LENGTH, 2), dtype=np.float64)
    rng = np.random.default_rng(9624)

    def put(signal, beat, gain=1., pan=0.):
        start = round(beat * BEAT * SAMPLE_RATE) % LENGTH
        stereo = signal[:, None] * np.array([
            np.sqrt((1 - pan) / 2), np.sqrt((1 + pan) / 2)]) * gain
        first = min(len(signal), LENGTH - start)
        mix[start:start + first] += stereo[:first]
        if first < len(signal):
            mix[:len(signal) - first] += stereo[first:]

    def note(pitch, beat, duration, kind, gain, pan=0.):
        seconds = duration * BEAT
        release = {'pad': 1.0, 'bell': .95, 'pluck': .6, 'bass': .22}[kind]
        t = np.arange(round((seconds + release) * SAMPLE_RATE)) / SAMPLE_RATE
        frequency = 440 * 2 ** ((pitch - 69) / 12)
        phase = 2 * np.pi * frequency * t
        if kind == 'pad':
            # Slow attack, low harmonics and tiny detuning keep the bed soft.
            signal = (np.sin(phase) + .24 * np.sin(phase * 2)
                      + .16 * np.sin(phase * 1.0017)) / 1.4
            envelope = np.minimum(t / .32, 1) * np.minimum(
                np.maximum(seconds + release - t, 0) / release, 1)
        elif kind == 'bell':
            # Rounded glass/mallet voice: octave overtones decay ahead of body.
            signal = (np.sin(phase) * np.exp(-t / 1.25)
                      + .25 * np.sin(phase * 2) * np.exp(-t / .38)
                      + .11 * np.sin(phase * 3) * np.exp(-t / .19))
            envelope = np.minimum(t / .009, 1) * np.minimum(
                np.maximum(seconds + release - t, 0) / .35, 1)
        elif kind == 'pluck':
            signal = (np.sin(phase) + .24 * np.sin(phase * 2)
                      + .07 * np.sin(phase * 4)) * np.exp(-t / .28)
            envelope = np.minimum(t / .004, 1) * np.minimum(
                np.maximum(seconds + release - t, 0) / .12, 1)
        else:
            signal = np.sin(phase) + .16 * np.sin(phase * 2)
            envelope = np.minimum(t / .018, 1) * np.minimum(
                np.maximum(seconds + release - t, 0) / release, 1)
            envelope *= np.exp(-t / 1.0)
        put(signal * envelope, beat, gain, pan)

    # Gmaj9 / Em7 / Cmaj9 / Dadd9, with a B-section and a suspended turnaround.
    # Close pad voicings make each return home feel settled rather than dramatic.
    chords = [
        (43, (55, 59, 62, 69)), (43, (55, 59, 62, 66)),
        (40, (55, 59, 62, 67)), (40, (55, 59, 62, 66)),
        (36, (55, 59, 62, 64)), (36, (55, 59, 62, 67)),
        (38, (54, 57, 62, 64)), (38, (54, 57, 60, 64)),
        (45, (55, 60, 64, 67)), (38, (54, 57, 62, 66)),
        (43, (55, 59, 62, 67)), (40, (55, 59, 62, 66)),
        (36, (55, 59, 62, 64)), (45, (55, 60, 64, 67)),
        (38, (55, 57, 62, 64)), (38, (54, 57, 62, 64)),
    ]
    # An original conversational melody, with rests between short phrases.
    melodies = [
        [(0, 74, .75), (1, 71, .5), (1.75, 69, .5), (2.5, 67, 1)],
        [(.5, 69, .5), (1.5, 71, 1), (3, 74, .75)],
        [(0, 71, 1), (1.5, 67, .75), (2.5, 66, .5), (3.25, 67, .5)],
        [(0, 69, 1.5), (2, 66, 1)],
        [(.5, 67, .75), (1.5, 71, .5), (2.25, 74, 1)],
        [(0, 76, 1), (1.5, 74, .5), (2.5, 71, 1)],
        [(0, 69, .75), (1, 66, .5), (2, 69, .75), (3, 74, .5)],
        [(0, 72, 1), (1.5, 69, 1.5)],
        [(.5, 72, .5), (1.25, 76, 1), (2.75, 79, .75)],
        [(0, 78, 1), (1.5, 74, 1), (3, 69, .5)],
        [(0, 71, .5), (.75, 74, .75), (2, 79, 1.25)],
        [(.5, 78, .75), (1.5, 74, .75), (2.5, 71, 1)],
        [(0, 76, 1), (1.5, 74, .75), (2.5, 71, 1)],
        [(.5, 72, .75), (1.5, 71, .5), (2.5, 69, 1)],
        [(0, 67, .75), (1, 69, .75), (2.5, 74, .75)],
        [(0, 69, 1), (2, 66, 1)],
    ]
    for bar in range(BARS):
        root, voices = chords[bar % 16]
        beat = bar * 4
        for i, pitch in enumerate(voices):
            note(pitch, beat, 3.85, 'pad', .036, (i - 1.5) * .28)
        note(root, beat, 1.5, 'bass', .15)
        note(root + (7 if bar % 4 != 3 else 12), beat + 2.5, .85, 'bass', .10)
        # Eight-note accompaniment leaves small gaps for the tune to breathe.
        arpeggio = (0, 2, 1, 3, 2, 1)
        for index, voice in enumerate(arpeggio):
            if bar % 8 == 7 and index > 3:
                continue
            note(voices[voice] + 12, beat + .25 + index * .5, .35,
                 'pluck', .043 if bar < 16 else .050,
                 -.4 if index % 2 else .4)
        melody = melodies[bar % 16]
        for offset, pitch, duration in melody:
            # The last two phrases simplify, leaving space before the loop.
            if bar >= 30 and offset > 1.5:
                continue
            note(pitch, beat + offset, duration, 'bell', .12, .08)
        if 16 <= bar < 28 and bar % 2 == 1:
            note(voices[-1] + 12, beat + 3.5, .35, 'bell', .035, -.36)

        # Quiet brushed percussion adds life without turning home into battle.
        for offset in (0., 2.):
            t = np.arange(round(.19 * SAMPLE_RATE)) / SAMPLE_RATE
            kick = np.sin(2 * np.pi * (48 * t + 5 * (1 - np.exp(-t * 28))))
            put(kick * np.exp(-t * 25) * np.minimum(t / .003, 1),
                beat + offset, .050)
        for index in range(8):
            if bar % 8 == 7 and index >= 6:
                continue
            t = np.arange(round(.075 * SAMPLE_RATE)) / SAMPLE_RATE
            noise = rng.standard_normal(len(t))
            noise[1:] = noise[1:] - .88 * noise[:-1]
            brush = noise * np.exp(-t * 67) * np.minimum(t / .005, 1)
            put(brush, beat + index * .5 + (.026 if index % 2 else 0),
                .007 if index % 2 else .010, -.27 if index % 2 else .27)

    # Circular room/delay tails include preceding-loop ambience at time zero.
    dry = mix.copy()
    for delay, gain in ((.137, .13), (.229, .10), (.375, .08), (.563, .05)):
        mix += np.roll(dry[:, ::-1], round(delay * SAMPLE_RATE), axis=0) * gain
    mix -= mix.mean(axis=0)
    mix *= .72 / max(float(np.abs(mix).max()), 1e-9)
    return mix.astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT/'assets/audio/original/digifarm_home.ogg')
    parser.add_argument('--update-manifest', action='store_true')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    samples = compose()
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'f32le', '-ar', str(SAMPLE_RATE), '-ac', '2', '-i', 'pipe:0',
        '-c:a', 'libvorbis', '-q:a', '5', '-map_metadata', '-1',
        '-metadata', 'title=A Place to Grow',
        '-metadata', 'artist=Venom NXT original DigiFarm soundtrack',
        '-fflags', '+bitexact', str(args.output),
    ], input=samples.astype('<f4').tobytes(), check=True)
    print(f'{args.output}: {len(samples)/SAMPLE_RATE:.2f}s stereo, {BPM} BPM')
    if args.update_manifest:
        manifest_path = ROOT/'data/ui_audio.json'
        manifest = json.loads(manifest_path.read_text('utf-8'))
        path = args.output.relative_to(ROOT).as_posix()
        manifest['screen_tracks']['farm'] = path
        manifest.setdefault('original_assets', {})['digifarm_home'] = {
            'title': 'A Place to Grow', 'path': path,
            'source': 'Original synthesized composition; tools/compose_digifarm_music.py',
            'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
            'duration': len(samples)/SAMPLE_RATE, 'sample_rate': SAMPLE_RATE,
            'channels': 2, 'bpm': BPM, 'bars': BARS,
            'loop': 'Full stream; circular instrument and ambience tails',
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')


if __name__ == '__main__':
    main()
