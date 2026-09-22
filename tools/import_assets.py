#!/usr/bin/env python3
"""Import user-owned sprite pack, x2 maps and authentic Dawn ROM human animation.
No network fetches or guessed sprites. Existing assets can regenerate catalog/manifest.
"""
from __future__ import annotations
import argparse, hashlib, json, re, struct, zipfile, sys
from pathlib import Path
from PIL import Image, ImageOps
ROOT=Path(__file__).resolve().parents[1]
STAGES={'1 Fresh':'fresh','2 In Training':'in_training','3 Rookie':'rookie','4 Champion':'champion','5 Ultimate':'ultimate','6 Armor':'armor','7 Mega':'mega','8 Ultra':'ultra'}
DIRECTIONS=['up','up_right','right','down_right','up_left','left','down_left','down']
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def relative(p):return p.relative_to(ROOT).as_posix()
def slug(s):return re.sub(r'[^a-z0-9]+','_',s.lower()).strip('_')
def save_json(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def rle30(b):
 if b[:1]!=b'\x30':raise ValueError('Expected Nintendo RLE30')
 length=int.from_bytes(b[1:4],'little');out=bytearray();pos=4
 while len(out)<length:
  command=b[pos];pos+=1
  if command&128:out.extend([b[pos]]*((command&127)+3));pos+=1
  else:out.extend(b[pos:pos+command+1]);pos+=command+1
 if len(out)!=length:raise ValueError('RLE output length mismatch')
 return bytes(out)
def pak_entries(b):
 count=struct.unpack_from('<I',b)[0];entries=[]
 for i in range(count):
  offset,sz=struct.unpack_from('<II',b,4+8*i);entries.append(rle30(b[offset:offset+(sz&0x7fffffff)]))
 return entries
def human_frame(raw,pal,index):
 count,size=struct.unpack_from('<II',raw)
 dimensions={128:(16,16),256:(16,32),512:(32,32),1024:(32,64),2048:(64,64)}
 w,h=dimensions[size]
 colors=[((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31,255 if n else 0) for n,v in enumerate(struct.unpack('<16H',pal[:32]))]
 out=Image.new('RGBA',(w,h));pixels=out.load()
 for p,value in enumerate(raw[8+index*size:8+(index+1)*size]):
  tile=p//32;x=tile%(w//8)*8+(p%4)*2;y=tile//(w//8)*8+(p%32)//4
  pixels[x,y]=colors[value&15];pixels[x+1,y]=colors[value>>4]
 return out
def animation_sequences(raw):
 # 10-byte MCHR header then seven u16 per frame; seven FFFF terminates sequence.
 sequences=[];seq=[]
 for p in range(10,len(raw)-13,14):
  record=struct.unpack_from('<7H',raw,p)
  if record==(65535,)*7:
   sequences.append(seq);seq=[]
  else:seq.append(record)
 if seq:sequences.append(seq)
 return sequences

def import_tamers(rom_path):
 import ndspy.rom
 rom=ndspy.rom.NintendoDSRom.fromFile(str(rom_path))
 chars=pak_entries(rom.getFileByName('dat/MCHR_CHR.PAK'))
 pals=pak_entries(rom.getFileByName('dat/MCHR_PAL.PAK'))
 animations=pak_entries(rom.getFileByName('dat/MCHR_ANM.PAK'))
 tamers=[]
 for i in [2,3,4,5,*range(14,40),*range(44,70),*range(82,90)]:
  tid=f'tamer_{i:03d}';directory=ROOT/'assets/tamers'/tid;directory.mkdir(parents=True,exist_ok=True)
  seq=animation_sequences(animations[i]);frames={};durations={};anchors={}
  for d,name in enumerate(DIRECTIONS):
   paths=[];ticks=[]
   # ROM groups first eight idle directions, then eight walking directions.
   walk=seq[8+d] if len(seq)>8+d else seq[d]
   for k,record in enumerate(walk):
    anchor_x,anchor_y,hit_w,hit_h,flip,frame_index,tick=record
    im=human_frame(chars[i],pals[i],frame_index)
    if flip&1:im=ImageOps.mirror(im)
    dest=directory/f'{name}_{k:02d}.png';im.save(dest)
    paths.append(relative(dest));ticks.append(tick/60)
   frames[name]=paths;durations[name]=ticks;anchors[name]=[walk[0][0],walk[0][1]]
  name={2:'Dawn Tamer · male',3:'Dawn Tamer · female',4:'Dusk Tamer · male',5:'Dusk Tamer · female'}.get(i,f'Digital World Tamer {i:03d}')
  tamers.append({'id':tid,'name':name,'frames':frames,'frame_seconds':durations,'anchors':anchors,'source_index':i,'native_size':[16,32],'display_scale':2,'provenance':'Dawn ROM MCHR_CHR/PAL/ANM; tile decoding, RLE decompression and per-direction animation-table flips; no redrawing'})
 save_json(ROOT/'data/tamers_catalog.json',tamers)
 return tamers

def import_zip(path):
 destination=ROOT/'assets/digimon'
 with zipfile.ZipFile(path) as archive:
  for info in archive.infolist():
   if info.is_dir():continue
   parts=Path(info.filename).parts[1:]
   if not parts or '..' in parts:raise ValueError('Invalid archive path')
   dest=destination.joinpath(*parts);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(archive.read(info))
def import_maps(path):
 import py7zr
 with py7zr.SevenZipFile(path) as archive:
  if any(Path(n).is_absolute() or '..' in Path(n).parts for n in archive.getnames()):raise ValueError('Invalid map archive path')
  archive.extractall(ROOT/'assets/maps')
def species_catalog():
 records=[];seen=set()
 for stage_dir in sorted((ROOT/'assets/digimon').iterdir()):
  if not stage_dir.is_dir():continue
  for base_dir in sorted(stage_dir.iterdir()):
   if not base_dir.is_dir():continue
   base_id=slug(base_dir.name);stage=STAGES.get(stage_dir.name,'unknown')
   if base_id in seen:base_id+='_'+stage
   for paradox,directory in [(False,base_dir),(True,base_dir/'Paradox')]:
    if not directory.is_dir():continue
    paths=sorted(directory.glob('*.png'));frame_paths=sorted((directory/'Frames').glob('*.png'))
    if not paths and not frame_paths:continue
    sid=base_id+('_paradox' if paradox else '')
    if sid in seen:raise ValueError(f'Duplicate species ID {sid}')
    seen.add(sid)
    def choose(suffix):return next((x for x in paths if x.stem.endswith('_'+suffix)),None)
    primary=choose('Primary') or choose('Idle') or (frame_paths[0] if frame_paths else paths[0])
    # Frame folders are sheet components, including small overworld art and credits.
    # Match only full-size combat poses; never animate every extracted component.
    battle_frames=[]
    if frame_paths:
     with Image.open(primary) as ref:rw,rh=ref.size
     for frame_path in frame_paths:
      with Image.open(frame_path) as image:fw,fh=image.size
      if .45*rw*rh<=fw*fh<=3*rw*rh and .6*rh<=fh<=1.7*rh and fw>=.35*rw:battle_frames.append(frame_path)
     battle_frames=battle_frames[:5]
    if battle_frames:primary=battle_frames[0]
    idle=relative(primary);walk_l=relative(battle_frames[1] if len(battle_frames)>1 else choose('LLegWalk') or primary);walk_r=relative(battle_frames[2] if len(battle_frames)>2 else choose('RLegWalk') or primary)
    attack1=relative(battle_frames[3] if len(battle_frames)>3 else choose('AttackPart1') or choose('Attack') or primary);attack2=relative(battle_frames[4] if len(battle_frames)>4 else choose('AttackPart2') or choose('Attack') or primary)
    h=hashlib.sha256(base_id.encode()).digest();rank={'fresh':0,'in_training':1,'rookie':2,'champion':3,'armor':3,'ultimate':4,'mega':5,'ultra':6}.get(stage,2)
    stats={'hp':120+rank*30+h[0]%35,'sp':24+rank*4+h[1]%10,'atk':18+rank*5+h[2]%12,'def':16+rank*5+h[3]%12,'int':18+rank*5+h[4]%12,'spd':18+rank*4+h[5]%12}
    # Non-CS species and Paradox fan variants do not have official CS statistics.
    records.append({'id':sid,'name':('Paradox ' if paradox else '')+base_dir.name,'stage':stage,'type':['vaccine','data','virus'][h[6]%3],'attribute':['fire','water','plant','earth','electric','wind','light','dark','neutral'][h[7]%9],'base_stats':stats,'sprites':{'idle':idle,'walk_left':walk_l,'walk_right':walk_r,'attack1':attack1,'attack2':attack2},'animations':{'idle':[idle,walk_l,idle,walk_r] if battle_frames else [idle],'walk':[idle,walk_l,idle,walk_r],'attack':[attack1,attack2]},'source_frame_count':len(frame_paths),'frame_selection':'combat-sized source poses; sheet credits and miniature overworld components excluded','paradox':paradox,'base_id':base_id,'provenance':'User-supplied v7 sprite pack; stage from source directory; provisional balance for non-curated mechanics','mechanics_status':'provisional_fan_balance','evolutions':[]})
 return records

def map_catalog():
 result=[]
 files=sorted((ROOT/'assets/maps').glob('*_a.png'))
 for i,path in enumerate(files):
  with Image.open(path) as im:width,height=im.size
  match=re.match(r'map_(\d+)_([ab])',path.stem);rom_id=int(match[1]) if match else i
  collision=ROOT/'assets/collision'/f'{path.stem}.png'
  result.append({'id':path.stem,'name':f'Dawn Sector {rom_id:03d}'+(' · lower' if match and match[2]=='b' else ''),'path':relative(path),'width':width,'height':height,'spawn':[width//2,height//2],'level':1+min(59,rom_id*60//265),'walkable':relative(collision) if collision.exists() else None,'foreground':relative(path.with_name(path.stem[:-1]+'b.png')) if path.with_name(path.stem[:-1]+'b.png').exists() else None,'rom_id':rom_id,'layer':match[2] if match else 'a','native_scale':2,'provenance':'User-supplied x2 Dawn map PNG; preserved dimensions, no resampling'})
 patches=ROOT/'data/collision.json'
 if patches.exists():
  patches=json.loads(patches.read_text(encoding='utf-8')).get('maps',{})
  for m in result:m.update(patches.get(m['id'],{}))
 return result

def manifest():
 files=[]
 for p in sorted((ROOT/'assets').rglob('*')):
  if p.is_file():files.append({'path':relative(p),'size':p.stat().st_size,'sha256':digest(p)})
 for p in sorted((ROOT/'data').glob('*.json')):
  if p.name!='asset_manifest.json':files.append({'path':relative(p),'size':p.stat().st_size,'sha256':digest(p)})
 result={'version':1,'files':files};save_json(ROOT/'data/asset_manifest.json',result);return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sprites',type=Path);p.add_argument('--maps',type=Path);p.add_argument('--rom',type=Path);p.add_argument('--manifest-only',action='store_true');p.add_argument('--verify-images',action='store_true');p.add_argument('--extract-media',action='store_true',help='With --rom, also regenerate authentic audio, effects and collision masks');args=p.parse_args()
 if args.manifest_only:
  print(f'Hashed {len(manifest()["files"])} files');return
 if args.sprites:import_zip(args.sprites)
 if args.maps:import_maps(args.maps)
 if args.rom:
  import_tamers(args.rom)
  if args.extract_media:
   sys.path.insert(0,str(ROOT))
   from tools.nds_audio import extract as extract_audio
   from tools.nds_effects import extract as extract_effects
   from tools.extract_collision import extract as extract_collision
   extract_audio(args.rom,ROOT);extract_effects(args.rom,ROOT);extract_collision(args.rom,ROOT)
 elif args.extract_media:p.error('--extract-media requires --rom')
 tamers_path=ROOT/'data/tamers_catalog.json';audio_path=ROOT/'data/audio_catalog.json'
 catalog={'version':'0.1.0','species':species_catalog(),'tamers':json.loads(tamers_path.read_text(encoding='utf-8')) if tamers_path.exists() else [],'maps':map_catalog(),'audio':json.loads(audio_path.read_text(encoding='utf-8')) if audio_path.exists() else {'music':[],'effects':[]},'mechanics_note':'Cyber Sleuth-inspired rules with curated type/attribute mappings where available; remaining species and all Paradox variants use explicitly provisional fan balancing.'}
 effects_path=ROOT/'data/effects_catalog.json'
 if effects_path.exists():catalog['battle_effects']=json.loads(effects_path.read_text(encoding='utf-8')).get('effects',[])
 save_json(ROOT/'data/catalog.json',catalog)
 if (ROOT/'venom/common/game.py').exists() and catalog['tamers']:
  sys.path.insert(0,str(ROOT))
  from venom.common.game import GameEngine
  catalog=GameEngine(ROOT,seed=0).catalog
  save_json(ROOT/'data/catalog.json',catalog)
 if args.verify_images:
  for f in (ROOT/'assets').rglob('*.png'):
   with Image.open(f) as im:im.verify()
 provenance=ROOT/'data/source_assets.json';sources=json.loads(provenance.read_text(encoding='utf-8')) if provenance.exists() else []
 for name,path in [('sprites',args.sprites),('maps',args.maps),('rom',args.rom)]:
  if path:
   sources=[s for s in sources if s['kind']!=name];sources.append({'kind':name,'filename':path.name,'size':path.stat().st_size,'sha256':digest(path)})
 save_json(provenance,sources)
 files=manifest();print(json.dumps({'species':len(catalog['species']),'tamers':len(catalog['tamers']),'maps':len(catalog['maps']),'manifest_files':len(files['files'])}))
if __name__=='__main__':main()
