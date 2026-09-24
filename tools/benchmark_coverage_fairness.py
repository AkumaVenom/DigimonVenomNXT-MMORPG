"""Reproduce the scoped coverage-fairness check; output only, no injected progress.

GameEngine resolves all wild combat, scan conversion, XP, evolution and party
operations. RankedRecorder observes scheduling; it does not exercise RankedService.
The four map difficulty tiers and shortened timers are controlled test settings.
"""
import sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from test_bot_training_cycles import make_manager
m=make_manager(count=12,levels=(1,20,50,60))
covered={i:0 for i in m.bots};started={i:None for i in m.bots};longest={i:0 for i in m.bots};streak={i:0 for i in m.bots}
t=time.perf_counter()
for step in range(1,54001):
    m.tick(step/10,.1,budget=1000)
    if step%100==0:
        for ident,b in m.bots.items():
            if b['runtime'].get('coverage_duty'):
                covered[ident]+=1;streak[ident]+=1;longest[ident]=max(longest[ident],streak[ident])
            else:streak[ident]=0
            if b['runtime'].get('training_uids') and started[ident] is None:started[ident]=step/10
print(json.dumps({'elapsed':time.perf_counter()-t,'rows':[{'id':i,'initial_seed':b['runtime']['seed_level'],'started':started[i],'coverage_samples':covered[i],'longest_duty_samples':longest[i],'cycles':b['runtime']['cycle'],'round':b['runtime'].get('training_round'),'rotations':b['stats']['training_rotations'],'map_level':m.engine.maps[b['state']['map_id']]['level'],'party':[x['level'] for x in b['state']['party']],'stats':{k:b['stats'][k] for k in ('wild_wins','wild_losses','ranked_started','materialized','travels','errors')}} for i,b in m.bots.items()],'occupancy':{m.engine.maps[k]['level']:len(v) for k,v in m.by_map.items()}},indent=2))
