from pathlib import Path
import json,struct,unittest
from PIL import Image
from tools.nds_effects import render_tiles
ROOT=Path(__file__).resolve().parents[1]
class EffectDecodeTests(unittest.TestCase):
    def test_tile_flips_palette_and_transparency(self):
        c=bytearray(80);c[:4]=b'RGCN';struct.pack_into('<I',c,28,3);struct.pack_into('<II',c,40,32,24);c[48]=1
        p=bytearray(72);p[:4]=b'RLCN';struct.pack_into('<II',p,32,32,16);struct.pack_into('<H',p,42,31)
        s=bytearray(38);s[:4]=b'RCSN';struct.pack_into('<HH',s,24,8,8)
        im=render_tiles(c,p,s);self.assertEqual(im.getpixel((0,0)),(255,0,0,255));self.assertEqual(im.getpixel((7,7))[3],0)
        struct.pack_into('<H',s,36,0x0c00)
        im=render_tiles(c,p,s);self.assertEqual(im.getpixel((7,7)),(255,0,0,255));self.assertEqual(im.getpixel((0,0))[3],0)
    def test_real_sequence_coverage_and_consistent_canvas(self):
        d=json.loads((ROOT/'data/effects_catalog.json').read_text());self.assertEqual(d['errors'],[]);self.assertEqual(len(d['effects']),96)
        self.assertEqual(sum(len(e['frames']) for e in d['effects']),1022)
        for e in d['effects']:
            visible=False
            for path in e['frames']:
                with Image.open(ROOT/path) as im:
                    self.assertEqual(list(im.size),e['size']);self.assertEqual(im.mode,'RGBA');visible|=im.getbbox() is not None
            self.assertTrue(visible,e['id'])
if __name__=='__main__':unittest.main()
