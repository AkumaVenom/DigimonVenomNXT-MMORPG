# Audio provenance

Audio is extracted from the supplied `Digimon World - Dawn (USA)(4).nds` ROM,
`dat/snd/sound_data.sdat`. The unchanged archive is preserved in `source/dawn.sdat`.

`tools/nds_audio.py` decodes the archive's PCM8, PCM16 and IMA ADPCM waveforms,
resolves its original instruments and note pitches, interprets track timing,
tempo, calls, loops, velocity, volume, pan and expression, and exports:

- `music/*.ogg`: all 46 music sequences, rendered through their first loop.
- `effects/*.wav`: all 183 sound-effect sequences, with a 12 second safety limit.
- `samples/*.wav`: all original individual decoded waveform samples.

The notes and sample sources are authentic. This is a portable software render,
not cycle-accurate Nintendo DS sound-hardware emulation. ADSR envelopes are
approximated; pitch modulation, sweep and portamento are not fully reproduced.
Music includes its introduction and a short ending fade when the file repeats.
Scene and event assignments are chosen for Venom NXT, not a verified reconstruction
of Dawn's original event assignments. The catalog exposes track IDs and provenance.

To regenerate, install `ndspy`, `numpy`, and `soundfile`, then run:

    python tools/nds_audio.py "path/to/Digimon World - Dawn (USA)(4).nds"

`data/audio_catalog.json` records exact outputs, decoded sample count, source
SHA-256, rendered durations, note counts, missing instrument notes, and failures.
