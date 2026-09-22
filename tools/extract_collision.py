"""Extract original Dawn per-pixel walking masks, retaining source geometry at x2.

ROM .0t: Nintendo RLE compression; LE u32 width,height followed by one
LSB-first bit per pixel, 1=blocked. Visual validation against sloping platform
edges distinguishes bit order. No image-color guessing is used.
"""
from __future__ import annotations
import argparse
import json
import struct
from pathlib import Path
from PIL import Image, ImageFilter


def decompress_rle(data: bytes) -> bytes:
    if len(data) < 4 or data[0] != 0x30:
        raise ValueError('Expected Nintendo RLE 0x30 stream')
    size = int.from_bytes(data[1:4], 'little')
    if not 0 < size < 64*1024*1024:
        raise ValueError('Invalid decompressed length')
    out = bytearray()
    pos = 4
    while len(out) < size:
        if pos >= len(data):
            raise ValueError('Truncated RLE stream')
        control = data[pos]; pos += 1
        count = (control & 127) + (3 if control & 128 else 1)
        if control & 128:
            if pos >= len(data):
                raise ValueError('Truncated RLE repeat')
            out.extend(bytes([data[pos]]) * count); pos += 1
        else:
            if pos+count > len(data):
                raise ValueError('Truncated RLE literal')
            out.extend(data[pos:pos+count]); pos += count
        if len(out) > size:
            raise ValueError('RLE exceeds declared length')
    return bytes(out)


def decode_mask(data: bytes) -> Image.Image:
    raw = decompress_rle(data)
    w, h = struct.unpack_from('<II', raw)
    if w % 8 or not 0 < w <= 8192 or not 0 < h <= 8192 or len(raw) != 8+w*h//8:
        raise ValueError('Invalid walking-mask geometry')
    table = bytes(int(f'{b:08b}'[::-1], 2) ^ 255 for b in range(256))
    return Image.frombytes('1', (w, h), raw[8:].translate(table)).convert('L')


def safe_spawn(mask: Image.Image) -> list[int]:
    w, h = mask.size
    safe = mask.filter(ImageFilter.MinFilter(9))
    pixels = safe.load()
    candidates = ((x,y) for y in range(12,h-12,8) for x in range(12,w-12,8) if pixels[x,y] > 127)
    try:
        return list(min(candidates,key=lambda p:(p[0]-w/2)**2+(p[1]-h/2)**2))
    except ValueError:
        raise ValueError('Map has no safe walkable spawn') from None


def extract(rom_path: Path, root: Path) -> dict:
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom.fromFile(str(rom_path))
    dest=root/'assets/collision'; dest.mkdir(parents=True,exist_ok=True)
    entries={}; missing=[]
    for path in sorted((root/'assets/maps').glob('map_*_a.png')):
        map_id=path.stem; number=int(map_id.split('_')[1])
        try:
            mask=decode_mask(rom.getFileByName(f'dat/map/{number}.0t'))
            with Image.open(path) as artwork:
                native_x2 = (mask.width*2, mask.height*2)
                if artwork.size != native_x2 and not (map_id == 'map_088_a' and artwork.size == (1504,768) and native_x2 == (1536,768)):
                    raise ValueError(f'Artwork {artwork.size} does not match native x2 mask {mask.size}')
                # Supplied map 088 omits the rightmost 32 pixels; its top-left
                # and floor geometry align exactly with the original mask.
                mask=mask.resize(native_x2,Image.Resampling.NEAREST).crop((0,0,*artwork.size))
            spawn=safe_spawn(mask)
            relative=f'assets/collision/{map_id}.png';mask.save(root/relative,optimize=True)
            entries[map_id]={'walkable':relative,'spawn':spawn,'collision_provenance':f'NDS dat/map/{number}.0t; 1-bit collision scaled 2x nearest'}
        except (ValueError,KeyError) as exc:
            missing.append({'map_id':map_id,'error':str(exc)})
    report={'format':1,'maps':entries,'missing':missing}
    (root/'data/collision.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    catalog_path=root/'data/catalog.json'
    if catalog_path.exists():
        catalog=json.loads(catalog_path.read_text(encoding='utf8'))
        for record in catalog['maps']:
            if record['id'] in entries:record.update(entries[record['id']])
        catalog_path.write_text(json.dumps(catalog,indent=2)+'\n',encoding='utf8')
    print(f'Extracted {len(entries)} original collision masks; {len(missing)} missing.')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args(); extract(args.rom,args.root)

if __name__=='__main__':main()
