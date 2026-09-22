"""Decode unambiguous Dawn battle BG effect NCGR/NCLR/NSCR frame sets.
Original pixel art only. Frame cadence is chosen for this client because the
custom Dawn effect timing descriptor is not fully reverse engineered.
"""
from pathlib import Path
import argparse, json, re, struct, sys
from collections import defaultdict
from PIL import Image,ImageDraw
from ndspy.rom import NintendoDSRom
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.import_assets import rle30

def render_tiles(chars,palette,screen):
    if chars[:4]!=b'RGCN' or palette[:4]!=b'RLCN' or screen[:4]!=b'RCSN':raise ValueError('Invalid Nitro formats')
    depth=struct.unpack_from('<I',chars,28)[0]
    if depth!=3:raise ValueError(f'Unsupported indexed depth {depth}')
    data_length,data_offset=struct.unpack_from('<II',chars,40)
    tile_bytes=chars[24+data_offset:24+data_offset+data_length]
    palette_size,palette_offset=struct.unpack_from('<II',palette,32)
    colors=struct.unpack('<'+str(palette_size//2)+'H',palette[24+palette_offset:24+palette_offset+palette_size])
    rgba=[((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31,0 if i%16==0 else 255) for i,v in enumerate(colors)]
    width,height=struct.unpack_from('<HH',screen,24)
    if width>1024 or height>1024:raise ValueError('Effect dimensions too large')
    tilemap=struct.unpack('<'+str(width*height//64)+'H',screen[36:36+width*height//32])
    image=Image.new('RGBA',(width,height));pix=image.load()
    for index,cell in enumerate(tilemap):
        tile=cell&1023;flipx=bool(cell&1024);flipy=bool(cell&2048);bank=(cell>>12)&15
        x0=(index%(width//8))*8;y0=(index//(width//8))*8
        if (tile+1)*32>len(tile_bytes):continue
        for y in range(8):
            for x in range(8):
                xx=7-x if flipx else x;yy=7-y if flipy else y
                byte=tile_bytes[tile*32+yy*4+xx//2]
                color=((byte>>4) if xx&1 else byte&15)+16*bank
                if color<len(rgba):pix[x0+x,y0+y]=rgba[color]
    return image

def extract(rom_path,root):
    root=Path(root);out=root/'assets/effects';out.mkdir(parents=True,exist_ok=True)
    rom=NintendoDSRom.fromFile(str(rom_path));groups=defaultdict(lambda:defaultdict(list))
    for name in rom.filenames['dat/bgeff'].files:
        m=re.fullmatch(r'(\d+)([cpsd])(\d*)',name)
        if m:groups[m[1]][m[2]].append(name)
    catalog={'source':'Dawn ROM dat/bgeff NCGR/NCLR/NSCR','timing':'Frame order uses numeric source sequence; client cadence approximated at 12.5 fps. Compound c+s sequences omitted until custom descriptor mapping is verified.','effects':[],'errors':[]}
    sheet=[]
    for key,files in sorted(groups.items(),key=lambda kv:int(kv[0])):
        if not files['p'] or not files['s'] or not files['c']:continue
        if len(files['s'])!=1 and len(files['c'])!=1:continue
        def read(name):return rle30(rom.getFileByName('dat/bgeff/'+name))
        chars=sorted(files['c'],key=lambda n:int(n.split('c')[1] or 0))
        screens=sorted(files['s'],key=lambda n:int(n.split('s')[1] or 0))
        palette=read(files['p'][0]);images=[]
        try:
            for i in range(max(len(chars),len(screens))):
                images.append(render_tiles(read(chars[min(i,len(chars)-1)]),palette,read(screens[min(i,len(screens)-1)])))
        except Exception as exc:catalog['errors'].append({'id':key,'error':str(exc)});continue
        if not images:continue
        # Preserve a shared canvas across the sequence, crop only transparent margins.
        boxes=[im.getbbox() for im in images if im.getbbox()]
        if not boxes:continue
        box=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
        directory=out/f'dawn_{int(key):03d}';directory.mkdir(exist_ok=True);paths=[]
        for i,im in enumerate(images):
            path=directory/f'{i:03d}.png';im.crop(box).save(path);paths.append(path.relative_to(root).as_posix())
        catalog['effects'].append({'id':f'dawn_{int(key):03d}','frames':paths,'frame_seconds':.08,'size':[box[2]-box[0],box[3]-box[1]],'source_id':int(key),'provenance':'Original decoded Dawn battle-effect pixels; unambiguous single-screen or single-character-bank sequence.'})
        sample=images[min(3,len(images)-1)].crop(box);sample.thumbnail((116,116));sheet.append((key,sample))
    catalog['attribute_effects']={'fire':'dawn_012','water':'dawn_016','electric':'dawn_052','wind':'dawn_170','plant':'dawn_081','earth':'dawn_037','light':'dawn_084','dark':'dawn_033','neutral':'dawn_023'}
    catalog['event_effects']={'heal':'dawn_155','scan':'dawn_002'}
    (root/'data/effects_catalog.json').write_text(json.dumps(catalog,indent=2))
    contact=Image.new('RGB',(800,((len(sheet)+5)//6)*150),(20,27,43));draw=ImageDraw.Draw(contact)
    for i,(key,im) in enumerate(sheet):
        x=(i%6)*133;y=(i//6)*150;contact.paste(im,(x+(120-im.width)//2,y+20),im);draw.text((x+8,y+135),f'Effect {key}',fill='white')
    contact.save(out/'contact_sheet.jpg')
    print('Decoded effects',len(catalog['effects']),'frames',sum(len(e['frames']) for e in catalog['effects']),'errors',catalog['errors'])
    return catalog

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('rom');p.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));args=p.parse_args();extract(args.rom,args.root)
