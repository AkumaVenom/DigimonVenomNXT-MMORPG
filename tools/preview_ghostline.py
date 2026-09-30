"""Render Ghostline in the native client using disposable, staged QA profiles.

Uses release maps, authored NPCs/dialogue and server story views. Progression is
staged in memory solely to inspect later story layouts; final settlement is an
isolated QA fixture, not a gameplay walkthrough. No accounts, saves, databases,
network connections or persistent rewards are changed.

python -m tools.preview_ghostline --output docs/validation/release_v140/ui
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
from venom.client.widgets import text, GOLD
from venom.common.game import GameEngine
from venom.common import story

ROOT=Path(__file__).resolve().parents[1]


def render(output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    records=[]
    for resolution in ((960,600),(1280,800)):
        args=SimpleNamespace(demo=True,demo_battle=False,dev=False,config=None,size='1280x800',frames=0,screenshot=None,ui_scale='auto',show_fps=False)
        app=App(ROOT,args)
        try:
            app.screen=NativeCanvas(pygame.display.set_mode(resolution),effective_ui_scale(resolution,'auto'))
            app.ui.screen=app.screen
            engine=GameEngine(ROOT,seed=6140)
            app.state=engine.new_player('GhostlineQA',app.tamer,engine.starters[0])
            app.now=5.0
            app.animations,app.toasts,app.players,app.player_render=[],[],{},{}
            app.logs=[('OFFLINE QA / Staged private profile. No account or save changed.',GOLD)]
            app.menu='story'
            def capture(name):
                app.reset_scene_position()
                app.draw()
                text(app.screen,app.assets,'OFFLINE QA / STAGED IN-MEMORY STORY PROGRESS',
                     (app.screen.get_width()//2,app.screen.get_height()-7),8,GOLD,center=True)
                filename=f'ghostline_{name}_{resolution[0]}x{resolution[1]}.png'
                pygame.image.save(app.screen.surface,output/filename)
                view=app.story_screen.data
                records.append(dict(file=filename,resolution=list(resolution),phase=name,map_id=app.state['map_id'],
                                    chapter=view.get('chapter'),revealed=view.get('revealed'),completed=view.get('completed'),
                                    staged_qa_progress=True,asset_errors=list(app.assets.errors)))
                if app.assets.errors:
                    raise RuntimeError(str(app.assets.errors))
            capture('01_campaign_chooser')
            engine.handle(app.state,'story',dict(action='enter',campaign_id=story.XROS_CAMPAIGN))
            data=story.content(engine,story.XROS_CAMPAIGN)
            regions=story._regions(data)
            fresh=copy.deepcopy(app.state)
            app.story_screen.tab='quest';capture('02_hub_journal')
            app.menu=None;capture('03_private_hub')
            broker=next(npc for npc in app.state['story']['view']['npcs'] if npc['name']=='Mara Vale')
            app.state.update(x=broker['x'],y=broker['y'])
            engine.handle(app.state,'story',dict(action='talk',npc_id=broker['id']))
            capture('04_trusted_contact')
            app.state=copy.deepcopy(fresh)
            app.menu='story';app.story_screen.tab='league';capture('05_sealed_case_file')
            app.story_screen.tab='atlas';app.story_screen.page=3;capture('06_locked_final_routes')
            app.story_screen.tab='badges';app.story_screen.page=3;capture('07_sealed_evidence')
            app.menu=None
            engine.handle(app.state,'story',dict(action='travel',chapter=1))
            quest=next(npc for npc in app.state['story']['view']['npcs'] if npc['role']=='quest')
            app.state.update(x=quest['x'],y=quest['y'])
            engine.handle(app.state,'story',dict(action='talk',npc_id=quest['id']))
            capture('08_first_assignment_dialogue')

            def stage(index,revealed=False):
                app.state=copy.deepcopy(fresh)
                profile=app.state['story']
                preceding=regions[:index]
                maps={map_id for region in preceding for map_id in region['maps']}
                profile['badges']=[row['badge']['id'] for row in preceding if row.get('badge')]
                profile['completed']=[row['id'] for row in data['npcs'].values() if row['map_id'] in maps and row['role'] in ('quest','trainer')]
                profile['quest_accepted']=[row['id'] for row in data['npcs'].values() if row['map_id'] in maps and row['role']=='quest']
                profile['hacked']=[row['id'] for row in data['npcs'].values() if row['id'] in profile['completed'] and row.get('hacked_after_victory')]
                profile['revealed']=revealed
                story.update_view(engine,app.state)
                engine.handle(app.state,'story',dict(action='travel',chapter=index))
                app.story_screen.reset()

            reveal=next(row for row in data['npcs'].values() if row.get('reveal_on_complete'))
            reveal_index=next(region['index'] for region in regions if reveal['map_id'] in region['maps'])
            stage(reveal_index)
            profile=app.state['story']
            profile['quest_accepted'].append(reveal['id'])
            profile['completed'].extend(row for row in reveal.get('quest_requires',[]) if row not in profile['completed'])
            story.update_view(engine,app.state)
            app.state.update(x=reveal['x'],y=reveal['y'])
            engine.handle(app.state,'story',dict(action='talk',npc_id=reveal['id']))
            while any(row['id']=='next' for row in app.story_screen.dialogue['choices']):
                engine.handle(app.state,'story',dict(action='dialogue',token=app.story_screen.dialogue['token'],choice='next'))
            engine.handle(app.state,'story',dict(action='dialogue',token=app.story_screen.dialogue['token'],choice='complete_quest'))
            app.menu=None;capture('09_reveal_dialogue')
            app.state['story']['dialogue']=None;story.update_view(engine,app.state)
            app.menu='story';app.story_screen.tab='league';capture('10_revealed_case_file')

            stage(30,True)
            profile=app.state['story']
            profile['badges']=[row['badge']['id'] for row in regions if row.get('badge')]
            profile['completed'] += [row['id'] for row in data['npcs'].values() if row['map_id']==app.state['map_id'] and row['role']=='quest']
            story.update_view(engine,app.state)
            final=data['npcs'][data['champion_id']]
            # Give this disposable final-layout fixture a viable real-stat team.
            app.state['party']=[engine._monster(member['species'],member['level'],abi=50,cam=100) for member in final['team']]
            app.state.update(x=final['x'],y=final['y'])
            engine.handle(app.state,'story',dict(action='talk',npc_id=final['id']))
            app.menu=None;capture('11_final_confrontation')
            while any(row['id']=='next' for row in app.story_screen.dialogue['choices']):
                engine.handle(app.state,'story',dict(action='dialogue',token=app.story_screen.dialogue['token'],choice='next'))
            engine.handle(app.state,'story',dict(action='dialogue',token=app.story_screen.dialogue['token'],choice='challenge'))
            capture('12_final_battle')
            # Staged settlement solely for inspecting the post-campaign UI.
            previous=copy.deepcopy(app.state)
            story.settle(engine,app.state,True)
            app.state['battle']=None;story.update_view(engine,app.state)
            app.story_screen.confirmed(previous,app.state)
            app.battle_until=0
            capture('13a_final_victory')
            app.story_screen.dismiss_result()
            capture('13b_secure_epilogue')
            while app.story_screen.dialogue:
                dialogue=app.story_screen.dialogue
                choice='next' if any(row['id']=='next' for row in dialogue['choices']) else 'leave'
                engine.handle(app.state,'story',dict(action='dialogue',token=dialogue['token'],choice=choice))
            app.story_screen.reset();app.menu='story';app.story_screen.tab='league';capture('13_case_complete')
            engine.handle(app.state,'story',dict(action='travel',chapter=0))
            assert not any('Mara' in row['name'] for row in app.state['story']['view']['npcs'])
            app.menu=None;capture('14_hub_after_completion')
        finally:
            pygame.quit()
    (output/'ghostline_previews.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    return records


def render_played_completion(profile_path, output):
    """Render a disposable profile earned by the normal-control acceptance run."""
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    state=json.loads(Path(profile_path).read_text())
    assert state['story']['campaign_id']==story.XROS_CAMPAIGN
    assert state['story']['champion']['first_victory'] and len(state['story']['badges'])==30
    assert state.get('permanent_rewards',{}).get('shiny_scan_mastery')
    args=SimpleNamespace(demo=True,demo_battle=False,dev=False,config=None,size='1280x800',frames=0,screenshot=None,ui_scale='auto',show_fps=False)
    app=App(ROOT,args)
    try:
        app.screen=NativeCanvas(pygame.display.set_mode((1280,800)),effective_ui_scale((1280,800),'auto'))
        app.ui.screen=app.screen
        app.state=state
        app.now=5.0
        app.animations,app.toasts,app.players,app.player_render=[],[],{},{}
        app.menu=None
        story.update_view(GameEngine(ROOT),app.state)
        assert not any('Mara' in row['name'] for row in app.story_screen.data['npcs'])
        app.reset_scene_position()
        app.draw()
        text(app.screen,app.assets,'OFFLINE QA / COMPLETED THROUGH NORMAL STORY AND BATTLE CONTROLS',
             (app.screen.get_width()//2,app.screen.get_height()-7),8,GOLD,center=True)
        filename='ghostline_15_played_completion_hub_1280x800.png'
        pygame.image.save(app.screen.surface,output/filename)
        record=dict(file=filename,resolution=[1280,800],map_id=state['map_id'],
                    completed=True,staged_qa_progress=False,disposable_acceptance_profile=True,
                    original_owned_party=True,asset_errors=list(app.assets.errors))
        (output/'ghostline_played_preview.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        return record
    finally:
        pygame.quit()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/validation/release_v140/ui')
    parser.add_argument('--played-profile',type=Path,help='Optional completed disposable acceptance profile for an additional real-playthrough preview.')
    options=parser.parse_args()
    if options.played_profile:
        print(json.dumps(render_played_completion(options.played_profile,options.output)))
    print(json.dumps(dict(output=str(options.output),previews=len(render(options.output)))))
