"""Extract Dawn SDAT audio and render it from the ROM's actual notes and samples.

This is a portable sample renderer, not cycle-accurate DS sound hardware emulation.
Preserves the untouched SDAT; exports every interpretable music/effect sequence.
Required: ndspy, numpy, soundfile.  No synthetic replacement music is generated.
"""
from __future__ import annotations
import argparse, hashlib, json, math, struct
from pathlib import Path
from dataclasses import dataclass, field
import numpy as np
import soundfile as sf
from ndspy.soundArchive import SDAT
from ndspy.rom import NintendoDSRom

STEPS = (7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767)
INDEX = (-1,-1,-1,-1,2,4,6,8)

def decode_wave(w):
    """Decode Nintendo PCM8, PCM16 or IMA ADPCM; return signed float PCM."""
    if int(w.waveType) == 0:
        return np.frombuffer(w.data, np.int8).astype(np.float32) / 128
    if int(w.waveType) == 1:
        return np.frombuffer(w.data, '<i2').astype(np.float32) / 32768
    initial, index = struct.unpack_from('<hH', w.data)
    index &= 127
    index = min(88, index)
    out = np.empty(1 + (len(w.data)-4)*2, np.float32)
    out[0] = initial/32768
    pos = 1
    for byte in w.data[4:]:
        for code in (byte & 15, byte >> 4):
            step = STEPS[index]
            diff = step >> 3
            if code & 1: diff += step >> 2
            if code & 2: diff += step >> 1
            if code & 4: diff += step
            initial = max(-32768, min(32767, initial + (-diff if code & 8 else diff)))
            index = max(0, min(88, index+INDEX[code & 7]))
            out[pos] = initial / 32768
            pos += 1
    return out

def variable(d, p):
    n = 0
    for _ in range(5):
        if p >= len(d):raise ValueError('Truncated sequence variable integer')
        v = d[p]; p += 1
        n = (n << 7) | (v & 127)
        if v < 128: return n,p
    raise ValueError('Invalid sequence variable integer')

@dataclass
class Track:
    pc: int
    tick: int = 0
    instrument: int = 0
    volume: int = 127
    expression: int = 127
    pan: int = 64
    transpose: int = 0
    bend: int = 0
    bend_range: int = 2
    note_wait: bool = True
    attack: int | None = None
    decay: int | None = None
    sustain: int | None = None
    release: int | None = None
    calls: list = field(default_factory=list)
    loops: list = field(default_factory=list)
    visited_jumps: set = field(default_factory=set)
    automation: list = field(default_factory=list)

def read_notes(data, start=0, max_ticks=30000, max_events=100000):
    tracks = [Track(start)]
    notes, tempo, loops, controls = [], [(0,120)], [], []
    unknown = set()
    # Each track carries independent time; tempo is applied globally afterwards.
    for tr in tracks:
        for _ in range(max_events):
            if tr.pc >= len(data) or tr.tick > max_ticks: break
            at = tr.pc; op = data[tr.pc]; tr.pc += 1
            needed = (1 if op < 0x80 or 0xC0<=op<=0xD6 else 4 if op==0x93 else 3 if op in (0x94,0x95) else 2 if op in (0xE0,0xE1,0xE3,0xFE) else 0)
            if tr.pc+needed>len(data):raise ValueError(f'Truncated opcode {op:#x} at {at:#x}')
            if op < 0x80:
                velocity=data[tr.pc];tr.pc+=1
                length,tr.pc=variable(data,tr.pc)
                notes.append((tr.tick,max(1,length),op+tr.transpose,velocity,dict(vars(tr))))
                if tr.note_wait:tr.tick+=length
            elif op==0x80:
                value,tr.pc=variable(data,tr.pc);tr.tick+=value
            elif op==0x81:
                tr.instrument,tr.pc=variable(data,tr.pc)
            elif op==0x93:
                channel=data[tr.pc]; target=int.from_bytes(data[tr.pc+1:tr.pc+4],'little');tr.pc+=4
                if target>=len(data):raise ValueError('Track target outside sequence')
                if len(tracks)<16:tracks.append(Track(target,tick=tr.tick))
            elif op in (0x94,0x95):
                target=int.from_bytes(data[tr.pc:tr.pc+3],'little');tr.pc+=3
                if target>=len(data):raise ValueError('Jump target outside sequence')
                if op==0x95:
                    if len(tr.calls)>32:raise ValueError('Sequence call depth exceeded')
                    tr.calls.append(tr.pc)
                elif target < at:
                    loops.append((tr.tick,target));break
                tr.pc=target
            elif 0xC0<=op<=0xD6:
                value=data[tr.pc];tr.pc+=1
                if op in (0xC0,0xC1,0xD5):tr.automation.append((tr.tick,op,value))
                if op==0xC0:tr.pan=value
                elif op==0xC1:tr.volume=value
                elif op==0xC2:controls.append((tr.tick,value))
                elif op==0xC3:tr.transpose=value-256 if value>127 else value
                elif op==0xC4:tr.bend=value-256 if value>127 else value
                elif op==0xC5:tr.bend_range=value
                elif op==0xC7:tr.note_wait=bool(value)
                elif op==0xD0:tr.attack=value
                elif op==0xD1:tr.decay=value
                elif op==0xD2:tr.sustain=value
                elif op==0xD3:tr.release=value
                elif op==0xD4:tr.loops.append([tr.pc,value or 2])
                elif op==0xD5:tr.expression=value
            elif op in (0xE0,0xE1,0xE3):
                value=int.from_bytes(data[tr.pc:tr.pc+2],'little');tr.pc+=2
                if op==0xE1:tempo.append((tr.tick,max(1,value)))
            elif op==0xFE:tr.pc+=2
            elif op==0xFD:
                if not tr.calls:break
                tr.pc=tr.calls.pop()
            elif op==0xFC:
                if tr.loops:
                    tr.loops[-1][1]-=1
                    if tr.loops[-1][1]>0:tr.pc=tr.loops[-1][0]
                    else:tr.loops.pop()
            elif op==0xFF:break
            elif op==0xA2:
                # All supplied Dawn sequences currently avoid conditional branches.
                raise ValueError(f'Unsupported conditional at {at:#x}')
            else:
                unknown.add(op);raise ValueError(f'Unsupported opcode {op:#x} at {at:#x}')
        else:raise ValueError('Sequence instruction budget exceeded')
    # Last tempo event at one tick wins (initial default is replaced).
    tempos={t:v for t,v in tempo}
    return notes, sorted(tempos.items()), loops, controls

class Renderer:
    def __init__(self, archive, rate=22050):
        self.archive=archive;self.rate=rate;self.cache={}

    def instrument_note(self, bank, program, pitch):
        if not 0<=program<len(bank.instruments):return None
        inst=bank.instruments[program]
        if inst is None:return None
        if hasattr(inst,'noteDefinition'):return inst.noteDefinition
        if hasattr(inst,'noteDefinitions'):
            index=pitch-inst.firstPitch
            return inst.noteDefinitions[index] if 0<=index<len(inst.noteDefinitions) else None
        for region in inst.regions:
            if pitch<=region.lastPitch:return region.noteDefinition
        return None

    def waveform(self, bank, nd, pitch, seconds, state):
        count=max(1,int(seconds*self.rate))
        bend=state['bend']/128*state['bend_range']
        if int(nd.type)==1:
            if nd.waveArchiveIDID>=len(bank.waveArchiveIDs):return None
            key=(bank.waveArchiveIDs[nd.waveArchiveIDID],nd.waveID)
            swav=self.archive.waveArchives[key[0]][1].waves[key[1]]
            if key not in self.cache:self.cache[key]=decode_wave(swav)
            samples=self.cache[key]
            positions=np.arange(count,dtype=np.float64)*(swav.sampleRate/self.rate)*(2**((pitch-nd.pitch+bend)/12))
            if swav.isLooped:
                if int(swav.waveType)==2: loop=max(0,(swav.loopOffset*4-4)*2+1)
                elif int(swav.waveType)==1:loop=swav.loopOffset*2
                else:loop=swav.loopOffset*4
                loop=min(loop,len(samples)-1)
                idx=positions>=len(samples)
                positions[idx]=loop+(positions[idx]-loop)%(len(samples)-loop)
            out=np.interp(positions,np.arange(len(samples)),samples,left=0,right=0).astype(np.float32)
        elif int(nd.type)==2:
            frequency=440*2**((pitch-69+bend)/12)
            duty=(nd.waveID+1)/8
            out=np.where((np.arange(count)*frequency/self.rate)%1<duty,.22,-.22).astype(np.float32)
        elif int(nd.type)==3:
            # DS PSG noise uses a deterministic LFSR; only waveform, never invented notes.
            lfsr=0x7FFF; vals=np.empty(count,np.float32)
            for j in range(count):
                bit=(lfsr^(lfsr>>1))&1;lfsr=(lfsr>>1)|(bit<<14);vals[j]=.15 if lfsr&1 else -.15
            out=vals
        else:return None
        return out

    def render(self, data, sequence, start=0, max_seconds=190):
        notes,tempos,loops,controls=read_notes(data,start)
        if not notes:raise ValueError('Sequence has no playable notes')
        def seconds(tick):
            result=0
            for index,(t,bpm) in enumerate(tempos):
                if tick<=t:break
                end=tempos[index+1][0] if index+1<len(tempos) else tick
                result+=(min(tick,end)-t)*60/(48*bpm)
                if tick<=end:break
            return result
        end_tick=max(t+l for t,l,*_ in notes)
        musical_end=max([t for t,_ in loops]+[end_tick])
        duration=min(max_seconds,seconds(musical_end)+.22)
        out=np.zeros((int(duration*self.rate)+1,2),np.float32)
        bank=self.archive.banks[sequence.bankID][1]
        count=0;missing=0
        for tick,length,pitch,vel,state in notes:
            t=seconds(tick)
            if t>=duration:continue
            nd=self.instrument_note(bank,state['instrument'],pitch)
            if nd is None:missing+=1;continue
            sustain=state['sustain'] if state['sustain'] is not None else nd.sustain
            attack=state['attack'] if state['attack'] is not None else nd.attack
            decay=state['decay'] if state['decay'] is not None else nd.decay
            release=state['release'] if state['release'] is not None else nd.release
            note_secs=min(12,max(.005,seconds(tick+length)-t))
            rel=.006+(127-release)/127*.18
            wave=self.waveform(bank,nd,pitch,min(note_secs+rel,duration-t),state)
            if wave is None:missing+=1;continue
            n=len(wave);x=np.arange(n)/self.rate
            # Smooth approximation of hardware ADSR; source sample/pitch/note timing preserved.
            atk=max(.001,(127-attack)/127*.25)
            dec=max(.006,(127-decay)/127*.6)
            sus=(sustain/127)**1.5
            envelope=np.minimum(1,x/atk)*np.where(x>atk,sus+(1-sus)*np.maximum(0,1-(x-atk)/dec),1)
            envelope*=np.where(x>note_secs,np.maximum(0,1-(x-note_secs)/rel),1)
            volume=np.full(n,state['volume']/127,np.float32)
            expression=np.full(n,state['expression']/127,np.float32)
            pan_values=np.full(n,state['pan'],np.float32)
            for control_tick,control_op,control_value in state['automation']:
                if control_tick<=tick:continue
                offset=int((seconds(control_tick)-t)*self.rate)
                if offset>=n:break
                if control_op==0xC1:volume[offset:]=control_value/127
                elif control_op==0xD5:expression[offset:]=control_value/127
                elif control_op==0xC0:pan_values[offset:]=control_value
            gain=(vel/127)**1.3*volume*expression*(sequence.volume/127)
            global_volume=next((v for tt,v in reversed(controls) if tt<=tick),127)
            gain*=global_volume/127
            wave*=envelope*gain*.45
            pan=np.clip((pan_values+nd.pan-64)/127,0,1)
            start_sample=int(t*self.rate);n=min(n,len(out)-start_sample)
            out[start_sample:start_sample+n,0]+=wave[:n]*np.cos(pan[:n]*math.pi/2)
            out[start_sample:start_sample+n,1]+=wave[:n]*np.sin(pan[:n]*math.pi/2)
            count+=1
        peak=float(np.max(np.abs(out)))
        if peak>0:out*=min(1.5,.92/peak)
        fade=min(int(.12*self.rate),len(out))
        out[-fade:]*=np.linspace(1,0,fade)[:,None]
        return out,{'duration':round(len(out)/self.rate,3),'notes':count,'missing_notes':missing,'looped':bool(loops),'peak_before_normalization':round(peak,4)}

def extract(rom_path, root):
    root=Path(root); out=root/'assets'/'audio';out.mkdir(parents=True,exist_ok=True)
    rom=NintendoDSRom.fromFile(str(rom_path))
    sdat=rom.getFileByName('dat/snd/sound_data.sdat')
    source=out/'source';source.mkdir(exist_ok=True)
    (source/'dawn.sdat').write_bytes(sdat)
    archive=SDAT(sdat);renderer=Renderer(archive)
    catalog={'source':'Digimon World Dawn (USA), dat/snd/sound_data.sdat','sdat_sha256':hashlib.sha256(sdat).hexdigest(),
      'rendering':'Original sequence notes, instrument mapping and decoded PCM/ADPCM samples; portable ADSR and modulation approximation, not cycle-accurate DS emulation.',
      'music':[], 'effects':[], 'errors':[]}
    for category in ('music','effects'):(out/category).mkdir(exist_ok=True)
    for name,seq in archive.sequences:
        try:
            rendered,meta=renderer.render(seq._eventsData,seq)
            path=f'assets/audio/music/{name}.ogg'
            # Small writes avoid libsndfile/Vorbis large-buffer faults on some platforms.
            with sf.SoundFile(str(root/path),'w',samplerate=renderer.rate,channels=2,format='OGG',subtype='VORBIS') as handle:
                for offset in range(0,len(rendered),32768):handle.write(rendered[offset:offset+32768])
            catalog['music'].append({'id':name,'path':path,**meta})
            print(f'Music {name}: {meta}',flush=True)
        except Exception as exc:
            catalog['errors'].append({'id':name,'error':str(exc)});print(f'FAILED {name}: {exc}',flush=True)
    for _,ssar in archive.sequenceArchives:
        for name,seq in ssar.sequences:
            try:
                rendered,meta=renderer.render(ssar._eventsData,seq,start=seq._firstEventOffset,max_seconds=12)
                path=f'assets/audio/effects/{name}.wav';sf.write(str(root/path),rendered,renderer.rate,subtype='PCM_16')
                catalog['effects'].append({'id':name,'path':path,**meta})
            except Exception as exc:catalog['errors'].append({'id':name,'error':str(exc)})
    # Keep every wave sample available for precise effect substitution and auditing.
    raw=out/'samples';raw.mkdir(exist_ok=True)
    catalog['sample_count']=0
    for bank_index,(name,war) in enumerate(archive.waveArchives):
        for wave_index,wave in enumerate(war.waves):
            sf.write(str(raw/f'{bank_index:03}_{wave_index:03}.wav'),decode_wave(wave),wave.sampleRate,subtype='PCM_16')
            catalog['sample_count']+=1
    catalog['scene_tracks']={'title':'bgm00','world':'bgm10','battle':'bgm40','digilab':'bgm11','victory':'bgm60'}
    catalog['event_sounds']={'click':'se000','confirm':'se001','cancel':'se002','hit':'se014','heal':'se011','scan':'se009','evolve':'se030'}
    (root/'data').mkdir(exist_ok=True)
    (root/'data'/'audio_catalog.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in catalog.items() if k in ('music','effects','errors','sample_count')}),flush=True)
    return catalog

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom');parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    args=parser.parse_args();extract(args.rom,args.root)
