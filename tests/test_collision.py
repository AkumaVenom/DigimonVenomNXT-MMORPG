import struct
import pytest
from tools.extract_collision import decompress_rle, decode_mask, safe_spawn
from PIL import Image


def packed(raw):
    # Independent literal-only encoder for testing imported source boundaries.
    payload=bytearray(b'\x30'+len(raw).to_bytes(3,'little'))
    for start in range(0,len(raw),128):
        block=raw[start:start+128];payload.append(len(block)-1);payload.extend(block)
    return bytes(payload)


def test_lsb_first_collision_blocks_matching_pixel():
    raw=struct.pack('<II',8,1)+b'\x05'
    mask=decode_mask(packed(raw))
    assert list(mask.tobytes())==[0,255,0,255,255,255,255,255]


def test_rle_repeat_and_truncation():
    assert decompress_rle(b'\x30\x06\x00\x00\x83\x42')==b'BBBBBB'
    with pytest.raises(ValueError,match='Truncated'):
        decompress_rle(b'\x30\x06\x00\x00\x83')
    with pytest.raises(ValueError,match='exceeds'):
        decompress_rle(b'\x30\x05\x00\x00\x83\x42')


def test_spawn_is_on_interior_walkable_ground():
    mask=Image.new('L',(64,64),0)
    for y in range(32,60):
        for x in range(8,56):mask.putpixel((x,y),255)
    x,y=safe_spawn(mask)
    assert 12 <= x <= 51 and 36 <= y <= 55
    with pytest.raises(ValueError,match='no safe'):
        safe_spawn(Image.new('L',(64,64),0))
