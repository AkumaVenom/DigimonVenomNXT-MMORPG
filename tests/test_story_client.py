"""Native Story inputs preserve server authority and existing player systems."""
import copy
import os
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import patch
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
import pygame
from venom.client.app import App
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas
from venom.common.game import GameEngine
ROOT=Path(__file__).resolve().parents[1]

class Connection:
    connected=True
    def __init__(self):
        self.incoming,self.sent=queue.Queue(),[]
    def send(self,op,**payload):
        self.sent.append((op,payload))
        return len(self.sent)

@unittest.skipUnless((ROOT/'data/catalog.json').exists(),'Imported assets required')
class StoryClientTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(pygame.quit)
        args=SimpleNamespace(demo=True,demo_battle=False,dev=False,config=None,size='1280x800',frames=0,screenshot=None,ui_scale='auto',show_fps=False)
        self.app=App(ROOT,args)
        self.resize((1280,800))
        self.app.args.demo=False
        self.app.connection=Connection()
        self.engine=GameEngine(ROOT,seed=94)
        self.app.state=self.engine.new_player('StoryTamer',self.app.tamer,self.engine.starters[0])
        self.app.state['in_farm']=False
        self.app.state['in_story']=True
        maps=list(self.app.assets.maps.values())
        self.app.state['story']={'view':{
            'chapter':0,'chapter_name':'The First Signal','objective':'Speak to the Dawn guide near the entrance.',
            'badges':[],'chapters':[{'index':i,'name':f'Region {i+1}','level':5+i*10,'unlocked':i==0,'complete':False,
                'map_id':maps[i]['id'],'maps':[{'id':maps[i]['id'],'name':maps[i].get('name','Dawn field'),'unlocked':i==0,'active':i==0}]} for i in range(9)],
            'npcs':[{'id':'guide','name':'Dawn Guide','tamer_id':self.app.tamer,'role':'mentor','map_id':self.app.state['map_id'],
                'x':self.app.state['x'],'y':self.app.state['y'],'status':'service'}],
            'dialogue':None,'champion':{'holder':'Astra','status':'Challenger','reigns':0,'defenses':0},
            'stats':{'wins':2,'losses':1},'recent':[],'training_level':5}}
        self.app.reset_scene_position()
        self.app.animations,self.app.toasts=[],[]
        self.app.now=5.
        self.controls=[]
        original=self.app.ui.button
        def button(rect,label,callback,*args,**kwargs):
            self.controls.append((label,pygame.Rect(rect),kwargs))
            return original(rect,label,callback,*args,**kwargs)
        self.enterContext(patch.object(self.app.ui,'button',side_effect=button))

    def resize(self,size):
        self.app.screen=NativeCanvas(pygame.display.set_mode(size),effective_ui_scale(size,'auto'))
        self.app.ui.screen=self.app.screen
    def draw(self):
        self.controls.clear()
        self.app.draw()
    def click(self,label):
        rect=next(rect for name,rect,options in self.controls if name==label and not options.get('disabled'))
        return self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=self.app.screen.to_physical_point(rect.center)))
    def key(self,key):
        self.app.key(pygame.event.Event(pygame.KEYDOWN,key=key))

    def test_top_left_toggle_uses_owned_team_and_only_server_enter_return(self):
        self.app.state['in_story']=False
        before=copy.deepcopy(self.app.state)
        self.draw();self.click('Story Mode  F4')
        self.assertEqual(self.app.menu,'story')
        self.assertFalse(self.app.connection.sent)
        self.draw();self.click('Continue Dawn Relay')
        self.assertEqual(self.app.connection.sent[-1],('story',{'action':'enter','campaign_id':'dawn_relay'}))
        self.assertEqual(self.app.state,before)
        self.app.action_pending=False;self.app.state['in_story']=True;self.app.menu=None
        self.draw();self.click('Return to MMO  F4')
        self.assertEqual(self.app.connection.sent[-1],('story',{'action':'return'}))

    def test_old_server_cannot_silently_open_dawn_for_a_ds_request(self):
        self.app.state['in_story'] = False
        self.app.server_features = {'story', 'digifarm'}
        before = copy.deepcopy(self.app.state)
        self.app.send('story', action='enter', campaign_id='world_ds_paradox')
        self.assertFalse(self.app.connection.sent)
        self.assertEqual(self.app.state, before)
        self.app.server_features.add('world_ds_story')
        self.app.send('story', action='enter', campaign_id='world_ds_paradox')
        self.assertEqual(self.app.connection.sent[-1], ('story', {'action': 'enter', 'campaign_id': 'world_ds_paradox'}))

    def test_owned_partner_shop_lab_and_farm_remain_available(self):
        for menu in ('party','shop','dex'):
            self.app.set_menu(menu);self.assertEqual(self.app.menu,menu);self.app.menu=None
        self.app.enter_lab()
        self.assertEqual(self.app.connection.sent[-1],('digilab',{'action':'enter'}))
        self.app.action_pending=False;self.app.enter_farm()
        self.assertEqual(self.app.connection.sent[-1],('digifarm',{'action':'enter'}))
        self.assertFalse(self.app.farm_screen.home_confirmation)

    def test_worlds_routes_to_story_atlas_and_shared_competitions_cannot_open(self):
        self.app.set_menu('maps')
        self.assertEqual((self.app.menu,self.app.story_screen.tab),('story','atlas'))
        self.app.menu=None
        for key in (pygame.K_r,pygame.K_v,pygame.K_o,pygame.K_F3): self.key(key)
        for op in ('travel','season','community','encounter'): self.app.send(op,action='enter')
        self.assertFalse(self.app.connection.sent);self.assertIsNone(self.app.menu)

    def test_nearby_interaction_and_dialogue_choices_are_tokened_and_modal(self):
        self.key(pygame.K_e)
        self.assertEqual(self.app.connection.sent[-1],('story',{'action':'talk','npc_id':'guide'}))
        self.app.action_pending=False
        view=self.app.state['story']['view']
        view['dialogue']={'npc_id':'guide','name':'Dawn Guide','tamer_id':self.app.tamer,
            'text':'Your team has travelled far. Our first trial begins here.','page':1,'pages':2,'token':'page-token',
            'choices':[{'id':'next','label':'Continue'},{'id':'leave','label':'Talk later'}]}
        before=copy.deepcopy(self.app.state)
        self.draw();self.assertEqual(len(self.app.ui.actions),2);self.assertFalse(self.app.field_visible())
        self.key(pygame.K_p);self.assertIsNone(self.app.menu)
        self.key(pygame.K_F10);self.assertTrue(self.app.settings_open)
        self.key(pygame.K_F10);self.assertFalse(self.app.settings_open)
        self.key(pygame.K_RETURN)
        self.assertEqual(self.app.connection.sent[-1],('story',{'action':'dialogue','token':'page-token','choice':'next'}))
        self.assertEqual(self.app.state,before)

    def test_story_battle_native_controls_tokens_and_no_flee_or_chat(self):
        mon=self.engine._monster(self.engine.starters[0],level=5)
        self.app.state['battle']={'kind':'story','id':'story-battle','story_role':'trainer','enemies':[mon],'active':[0],'actor':0,'turn':3}
        self.draw();labels=[label for label,_,_ in self.controls]
        for label in ('Attack','Skill · SP','Items'): self.assertIn(label,labels)
        self.assertNotIn('Flee',labels);self.assertNotIn('chat',[key for _,key in self.app.ui.fields])
        self.key(pygame.K_RETURN);self.assertIsNone(self.app.ui.focus)
        self.click('Attack')
        self.assertEqual(self.app.connection.sent[-1],('battle',{'action':'attack','target':0,'party_index':0,'battle_id':'story-battle','expected_turn':3}))
        self.app.action_pending=False;count=len(self.app.connection.sent)
        self.app.send('battle',action='flee');self.app.battle_action('flee');self.app.story_screen.toggle()
        self.assertEqual(len(self.app.connection.sent),count)

    def test_all_journal_tabs_fit_native_resolutions(self):
        for size in ((960,600),(1280,800),(1920,1080)):
            self.resize(size);self.app.menu='story'
            for tab,_ in self.app.story_screen.TABS:
                self.app.story_screen.tab=tab;self.draw()
                for label,rect,_ in self.controls: self.assertTrue(self.app.screen.get_rect().contains(rect),(size,tab,label,rect))
            self.app.menu=None;self.draw();labels=[row[0] for row in self.controls]
            self.assertIn('Story journal  J',labels);self.assertIn('Return to MMO  F4',labels)

    def test_training_recovery_and_atlas_commands_never_grant_local_progress(self):
        self.app.menu='story';before=copy.deepcopy(self.app.state)
        self.draw();self.click('Recover your team')
        self.assertEqual(self.app.connection.sent[-1],('story',{'action':'heal'}))
        self.app.action_pending=False;self.draw();self.click('Training battle · Lv.5')
        self.assertEqual(self.app.connection.sent[-1],('story',{'action':'train'}));self.assertEqual(self.app.state,before)
        self.app.action_pending=False;self.app.story_screen.tab='atlas';self.draw()
        locked=[options for label,rect,options in self.controls if label.startswith('→ ')]
        self.assertTrue(all(row.get('disabled') for row in locked))

    def test_training_allows_native_flee_but_farm_cannot_forfeit_npc_challenge(self):
        mon=self.engine._monster(self.engine.starters[0],level=3)
        self.app.state['battle']={'kind':'story','id':'training-battle','story_training':True,'enemies':[mon],'active':[0],'actor':0,'turn':2}
        self.draw();self.click('Flee')
        self.assertEqual(self.app.connection.sent[-1],('battle',{'action':'flee','target':0,'party_index':0,'battle_id':'training-battle','expected_turn':2}))
        self.app.action_pending=False;self.app.state['battle']['story_training']=False;count=len(self.app.connection.sent)
        self.app.enter_farm();self.app.send('digifarm',action='enter',forfeit=True)
        self.assertFalse(self.app.farm_screen.home_confirmation);self.assertEqual(len(self.app.connection.sent),count)

    def test_reward_journal_waits_for_result_dialogue_ack_without_trapping_input(self):
        view=self.app.state['story']['view']
        view['dialogue']={'npc_id':'guide','name':'Dawn Guide','tamer_id':self.app.tamer,'text':'The relay answers your team. Follow the new path.',
            'page':1,'pages':1,'token':'result-token','result_only':True,'choices':[{'id':'leave','label':'Continue the journey'}]}
        self.app.story_screen.result={'won':True,'opponent':'Dawn Guide','role':'trainer','credits':100}
        self.app.battle_until=0;self.draw();self.click('Journal after dialogue')
        self.assertIsNone(self.app.menu);self.assertTrue(self.app.story_screen.pending_journal);self.assertFalse(self.app.connection.sent)
        self.draw();self.click('Continue the journey')
        self.assertEqual(self.app.connection.sent[-1],('story',{'action':'dialogue','token':'result-token','choice':'leave'}))
        self.assertIsNone(self.app.menu)
        new_state=copy.deepcopy(self.app.state);new_state['story']['view']['dialogue']=None
        self.app.connection.incoming.put({'op':'result','rid':1,'ok':True,'state':new_state});self.app.poll()
        self.assertEqual(self.app.menu,'story');self.assertFalse(self.app.story_screen.modal)
        self.key(pygame.K_ESCAPE);self.assertIsNone(self.app.menu)

    def test_actual_story_view_counts_only_earned_badges_and_formats_dialogue_page(self):
        state=self.engine.new_player('ActualStory',self.app.tamer,self.engine.starters[0]);self.engine.handle(state,'story',{'action':'enter'})
        self.app.state=state
        self.assertEqual(len(self.app.story_screen.data['badges']),8);self.assertEqual(self.app.story_screen.badge_count,0)
        self.app.menu='story';self.app.story_screen.tab='badges';self.draw()
        self.app.story_screen.tab='league';self.draw()
        options=next(options for label,rect,options in self.controls if label=='Open championship region')
        self.assertTrue(options['disabled'])

    def test_world_gate_interaction_is_authoritative_and_blocked_by_dialogue(self):
        before=copy.deepcopy(self.app.state)
        self.app.story_screen.exit('lumen-forward')
        self.assertEqual(self.app.connection.sent[-1],('story',{'action':'exit','exit_id':'lumen-forward'}))
        self.assertEqual(self.app.state,before)
        self.app.action_pending=False
        self.app.state['story']['view']['dialogue']={'text':'Wait','choices':[],'token':'dialogue'}
        self.app.story_screen.exit('lumen-forward')
        self.assertEqual(len(self.app.connection.sent),1)

if __name__=='__main__': unittest.main()
