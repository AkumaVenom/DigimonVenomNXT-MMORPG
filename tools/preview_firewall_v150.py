"""Export the actual native FireWall interface with disposable offline QA state.

Only images and a validation report are written. All accounts, progress and
rewards in the previews are staged in memory; no server is contacted.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
import pygame
from venom.client.app import App
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas
from venom.client.widgets import text
from venom.client.varieties import FIREWALL_ORANGE
from venom.common.game import GameEngine
from venom.common import story

ROOT=Path(__file__).resolve().parents[1]

def render(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    records=[]
    for resolution in ((960,600),(1280,800)):
        args=SimpleNamespace(demo=True,demo_battle=False,dev=False,config=None,size='1280x800',frames=0,screenshot=None,ui_scale='auto',show_fps=False)
        app=App(ROOT,args)
        try:
            app.screen=NativeCanvas(pygame.display.set_mode(resolution),effective_ui_scale(resolution,'auto'))
            app.ui.screen=app.screen
            engine=GameEngine(ROOT,seed=150)
            state=engine.new_player('FireWallQA',app.tamer,engine.starters[0])
            state.update(in_farm=False,in_story=False,in_lab=False)
            ids=[row['id'] for row in engine.species.values() if row.get('firewall')]
            assert len(ids)==502
            long_ids=sorted(ids,key=lambda sid:len(engine.species[sid]['name']),reverse=True)
            preferred=['agumon_firewall','gabumon_firewall','fanglongmon_firewall']
            preferred=[sid for sid in preferred if sid in ids]
            chosen=preferred+[sid for sid in long_ids if sid not in preferred]
            state['party']=[engine._monster(sid,65,abi=100,cam=100) for sid in chosen[:6]]
            state['storage']=[engine._monster(sid,25+i,abi=40,cam=70) for i,sid in enumerate(chosen[6:24])]
            state['scan']={sid:(100 if i%3 else 95) for i,sid in enumerate(ids)}
            state['scan']['agumon_firewall']=100
            engine._refresh(state)
            app.state=state;app.now=5.;app.menu=None
            app.animations,app.toasts,app.players,app.player_render=[],[],{},{}
            app.logs=[('Offline preview: disposable in-memory profile.',FIREWALL_ORANGE)]
            def capture(phase):
                app.reset_scene_position();app.draw()
                text(app.screen,app.assets,'OFFLINE QA / STAGED IN-MEMORY PROFILE',
                     (app.screen.get_width()//2,app.screen.get_height()-7),8,FIREWALL_ORANGE,center=True)
                filename=f'firewall_{phase}_{resolution[0]}x{resolution[1]}.png'
                pygame.image.save(app.screen.surface,output/filename)
                records.append(dict(file=filename,resolution=list(resolution),phase=phase,
                    asset_errors=list(app.assets.errors),staged_qa_profile=True))
                if app.assets.errors: raise RuntimeError(str(app.assets.errors))
            app.menu='scan';app.scan_screen.variant='firewall';app.state['in_lab']=True
            capture('01_scan_gallery')
            app.state['permanent_rewards']={'firewall_scan_mastery':True};capture('02_scan_mastery')
            app.menu='dex';app.ui.values['search']='Sistermon';capture('03_large_art_dex')
            app.ui.values['search']='';app.state['in_lab']=False
            app.menu='maps';app.world_screen.on_open();capture('04_atlas')
            app.menu=None;capture('05_world_idle')
            app.moving=True;app.direction='left';app.now=5.2;capture('06_world_walk')
            app.moving=False;app.now=5.
            app.state['battle']={'kind':'wild','id':'preview-wild','enemies':[engine._monster(sid,70) for sid in long_ids[:3]],'active':[0,1,2],'actor':0,'turn':1}
            capture('07_battle_long_names')
            app.state['permanent_rewards']={};capture('08_battle_base_scan')
            app.state['battle']=None;app.state['in_lab']=True;app.menu='party';app.partner_screen.mode='roster'
            capture('09_partner_roster')
            app.partner_screen.mode='evolution';capture('10_evolution')
            app.partner_screen.mode='storage';capture('11_storage')
            app.state['in_lab']=False;app.menu=None
            engine.handle(app.state,'digifarm',dict(action='enter'))
            capture('12_farm')
            engine.handle(app.state,'digifarm',dict(action='return'))
            app.menu='story';capture('13_campaign_chooser')
            engine.handle(app.state,'story',dict(action='enter',campaign_id=story.DAWN_CAMPAIGN))
            app.story_screen.tab='league';capture('14_dawn_reward_locked')
            profile=app.state['story']
            profile['champion'].update(first_victory=True,holder='FireWallQA',reigns=1,defenses=0)
            story.update_view(engine,app.state);capture('15_dawn_mastery')
            profile['champion'].update(holder='A new challenger',status='former_champion')
            story.update_view(engine,app.state);capture('16_mastery_after_title_loss')
            app.menu=None
            app.story_screen.result=dict(won=True,role='champion',credits=2500,opponent='Astra',scan_mastery_unlocked=True)
            capture('17_first_championship_reward')
        finally:
            pygame.quit()
    (output/'firewall_previews.json').write_text(json.dumps(records,indent=2)+'\n')
    return records

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/validation/release_v150/ui')
    args=parser.parse_args()
    print(json.dumps(dict(output=str(args.output),previews=len(render(args.output)))))
