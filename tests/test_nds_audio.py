"""Real-asset audio coverage and malformed stream regression tests."""
from pathlib import Path
from types import SimpleNamespace
import json
import struct
import unittest
import numpy as np
import soundfile as sf
from tools.nds_audio import decode_wave, read_notes, Renderer

ROOT = Path(__file__).resolve().parents[1]

class AudioDecoderTests(unittest.TestCase):
    def test_pcm_signedness_and_little_endian(self):
        wave = SimpleNamespace(waveType=0,data=b'\x80\x00\x7f')
        np.testing.assert_allclose(decode_wave(wave),[-1,0,127/128])
        wave = SimpleNamespace(waveType=1,data=struct.pack('<hhh',-32768,0,32767))
        np.testing.assert_allclose(decode_wave(wave),[-1,0,32767/32768])

    def test_adpcm_nibble_order_and_predictor(self):
        wave = SimpleNamespace(waveType=2,data=struct.pack('<hH',0,0)+bytes([0x07]))
        np.testing.assert_allclose(decode_wave(wave)*32768,[0,11,13])

    def test_truncated_sequence_and_unknown_opcode_are_rejected(self):
        for data in (b'\x81\x80',b'\x93\x01',b'\xe1\x20',b'\x01',b'\xab',b'\x94\xff\xff\xff'):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):read_notes(data)

    def test_self_jump_and_recursive_call_are_bounded(self):
        with self.assertRaisesRegex(ValueError,'budget'):
            read_notes(b'\x94\x00\x00\x00',max_events=64)
        with self.assertRaisesRegex(ValueError,'call depth'):
            read_notes(b'\x95\x00\x00\x00')

    def test_high_numbered_source_instrument_is_preserved(self):
        note=object()
        bank=SimpleNamespace(instruments=[None]*128+[SimpleNamespace(noteDefinition=note)])
        renderer=Renderer(None)
        self.assertIs(renderer.instrument_note(bank,128,60),note)

    def test_all_exported_music_and_effects_decode_and_are_audible(self):
        catalog=json.loads((ROOT/'data/audio_catalog.json').read_text())
        world_ds=json.loads((ROOT/'data/world_ds_audio.json').read_text())
        dawn_music=[entry for entry in catalog['music'] if entry.get('region_id')!='world_ds']
        ds_music=[entry for entry in catalog['music'] if entry.get('region_id')=='world_ds']
        self.assertEqual(len(dawn_music),46)
        self.assertEqual(len(ds_music),28)
        self.assertEqual(ds_music,world_ds['music'])
        self.assertEqual(len({entry['id'] for entry in catalog['music']}),74)
        self.assertEqual(len(catalog['effects']),183)
        self.assertEqual(catalog['errors'],[])
        for entry in catalog['music']+catalog['effects']:
            with self.subTest(sequence=entry['id']):
                data,rate=sf.read(ROOT/entry['path'],dtype='float32')
                # Existing synthesized Dawn exports retain their 22.05 kHz
                # format; supplied DS preview recordings retain native 32 kHz.
                self.assertEqual(rate,32000 if entry.get('region_id')=='world_ds' else 22050)
                self.assertGreater(len(data),100)
                self.assertTrue(np.isfinite(data).all())
                self.assertGreater(float(np.max(np.abs(data))),.0001)
        self.assertEqual(len(list((ROOT/'assets/audio/samples').glob('*.wav'))),703)

if __name__=='__main__':unittest.main()
