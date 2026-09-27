"""Native Season screen inputs, authority boundaries, layouts, and audio routing."""
import copy
import os
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from venom.client.app import App
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas
from venom.common.game import GameEngine
from venom.common import season

ROOT = Path(__file__).resolve().parents[1]


class Connection:
    connected = True

    def __init__(self):
        self.incoming, self.sent = queue.Queue(), []

    def send(self, op, **payload):
        self.sent.append((op, payload))
        return len(self.sent)


def season_fixture(app):
    engine = GameEngine(ROOT, seed=95)
    state = engine.new_player('ShadowStar', app.tamer, engine.starters[0])
    state['in_farm'] = False
    state['party'] = [engine._monster(sid, level=24) for sid in engine.starters[:3]]
    engine.handle(state, 'season', {'action': 'enter'})
    app.state = copy.deepcopy(state)
    app.animations, app.toasts = [], []
    app.battle_old, app.menu = None, None
    app.now = 5.
    return engine, state


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class SeasonClientTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(pygame.quit)
        args = SimpleNamespace(demo=True, demo_battle=False, dev=False, config=None,
                               size='1280x800', frames=0, screenshot=None, ui_scale='auto',show_fps=False)
        self.app = App(ROOT,args)
        self.resize((1280,800))
        self.app.args.demo = False
        self.app.connection = Connection()
        self.engine, self.state = season_fixture(self.app)
        self.controls = []
        original = self.app.ui.button
        def button(rect,label,callback,*args,**kwargs):
            self.controls.append((label,pygame.Rect(rect),kwargs))
            return original(rect,label,callback,*args,**kwargs)
        self.enterContext(patch.object(self.app.ui,'button',side_effect=button))

    def resize(self, size):
        self.app.screen = NativeCanvas(pygame.display.set_mode(size),effective_ui_scale(size,'auto'))
        self.app.ui.screen = self.app.screen

    def draw(self):
        self.controls.clear()
        self.app.draw()

    def click(self,label):
        rect = next(rect for name,rect,options in self.controls if name == label and not options.get('disabled'))
        return self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,
                                pos=self.app.screen.to_physical_point(rect.center)))

    def reply(self,rid,state=None,**extra):
        packet={'op':'result','rid':rid,'ok':True,**extra}
        if state is not None:
            packet['state']=copy.deepcopy(state)
        self.app.connection.incoming.put(packet)
        self.app.poll()

    def test_fight_is_server_command_with_card_token_and_no_local_simulation(self):
        before=copy.deepcopy(self.app.state)
        self.draw()
        self.assertTrue(self.click('Continue Season  ·  Fight'))
        self.assertEqual(self.app.connection.sent[-1],('season',{'action':'start','token':before['season']['card']['token']}))
        self.assertEqual(self.app.state,before)
        self.engine.handle(self.state,'season',self.app.connection.sent[-1][1])
        self.reply(1,self.state)
        self.assertTrue(self.app.state['battle']['season'])
        self.assertIsNone(self.app.menu)
        self.draw()
        labels=[name for name,_,_ in self.controls]
        for label in ('Attack','Skill · SP','Items'):
            self.assertIn(label,labels)
        self.assertNotIn('Flee',labels)
        self.assertNotIn('chat',[key for _,key in self.app.ui.fields])
        self.app.key(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN))
        self.assertIsNone(self.app.ui.focus)

    def test_native_skill_and_item_buttons_send_live_actor_target_commands(self):
        self.engine.handle(self.state,'season',{'action':'start','token':self.state['season']['card']['token']})
        self.app.state=copy.deepcopy(self.state)
        battle=self.app.state['battle']
        self.draw()
        self.click('Skill · SP')
        self.assertEqual(self.app.menu,'skills')
        self.draw()
        self.click('Use skill')
        op,payload=self.app.connection.sent[-1]
        self.assertEqual(op,'battle')
        self.assertEqual(payload['action'],'skill')
        self.assertEqual(payload['party_index'],battle['actor'])
        self.assertEqual(payload['battle_id'],battle['id'])
        self.assertEqual(payload['expected_turn'],battle['turn'])
        self.assertEqual(payload['target'],self.app.target)
        self.app.action_pending=False
        self.app.state['inventory']['hp_s']=3
        self.draw()
        self.click('Items')
        self.app.selected_party=1
        self.draw()
        self.click('Use capsule')
        op,payload=self.app.connection.sent[-1]
        self.assertEqual((op,payload['action'],payload['item']),('battle','item','hp_s'))
        self.assertEqual(payload['party_index'],1)
        self.assertEqual(payload['battle_id'],battle['id'])
        self.assertEqual(payload['expected_turn'],battle['turn'])

    def test_all_live_commands_have_current_battle_identity_and_turn(self):
        self.engine.handle(self.state,'season',{'action':'start','token':self.state['season']['card']['token']})
        self.app.state=copy.deepcopy(self.state)
        battle=self.app.state['battle']
        for action in ('attack','skill','item'):
            self.app.send('battle',action=action,target=0)
            op,payload=self.app.connection.sent[-1]
            self.assertEqual(op,'battle')
            self.assertEqual(payload['battle_id'],battle['id'])
            self.assertEqual(payload['expected_turn'],battle['turn'])
        count=len(self.app.connection.sent)
        self.app.send('battle',action='flee')
        self.assertEqual(len(self.app.connection.sent),count)

    def test_home_farm_and_world_paths_cannot_forfeit_a_season_match(self):
        self.engine.handle(self.state,'season',{'action':'start','token':self.state['season']['card']['token']})
        self.app.state=copy.deepcopy(self.state)
        before=copy.deepcopy(self.app.state)
        self.app.enter_farm()
        self.app.enter_lab()
        self.app.season_screen.toggle()
        self.app.send('digifarm',action='enter',forfeit=True)
        self.app.battle_action('flee')
        self.app.key(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F2))
        self.app.key(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_F3))
        self.assertFalse(self.app.farm_screen.home_confirmation)
        self.assertFalse(self.app.connection.sent)
        self.assertEqual(self.app.state,before)

    def test_completed_card_advances_only_after_next_week_ack(self):
        season.begin_match(self.state['season'],self.state['season']['card']['token'])
        season.finish_human(self.state['season'],True,self.engine.species)
        self.app.state=copy.deepcopy(self.state)
        before=copy.deepcopy(self.app.state)
        self.draw()
        self.click('Next Week  →')
        self.assertEqual(self.app.state,before)
        self.assertEqual(self.app.connection.sent[-1],('season',{'action':'next','token':before['season']['card']['token']}))
        self.engine.handle(self.state,'season',self.app.connection.sent[-1][1])
        self.reply(1,self.state)
        self.assertEqual(self.app.state['season']['week'],2)
        self.assertEqual(self.app.state['season']['phase'],'ready')

    def test_history_pagination_and_detail_are_authoritative_read_only(self):
        self.draw()
        self.click('Career archive')
        self.assertEqual(self.app.connection.sent[-1],('season',{'action':'history','page':0,'page_size':8}))
        item={'week':1,'card':copy.deepcopy(self.state['season']['card'])}
        before=copy.deepcopy(self.app.state)
        self.reply(1,season_history={'items':[item],'page':0,'page_size':8,'has_more':True})
        self.draw()
        self.click('View match card')
        self.assertEqual(self.app.season_screen.archive_selection,1)
        self.assertEqual(self.app.state,before)
        self.draw()
        self.click('Back to archive')
        self.draw()
        self.click('Older')
        self.assertEqual(self.app.connection.sent[-1],('season',{'action':'history','page':1,'page_size':8}))

    def test_login_restores_saved_match_and_return_restores_world_after_ack(self):
        self.app.state=None
        self.app.requests[19]='login'
        self.reply(19,self.state)
        self.assertTrue(self.app.season_screen.visible)
        self.assertFalse(self.app.field_visible())
        self.draw()
        self.click('Save & Return to World')
        self.assertTrue(self.app.state['in_season'])
        self.engine.handle(self.state,'season',{'action':'return'})
        self.reply(1,self.state)
        self.assertFalse(self.app.state['in_season'])
        self.assertTrue(self.app.field_visible())

    def test_every_tab_fits_minimum_native_and_large_year(self):
        season.begin_match(self.state['season'],self.state['season']['card']['token'])
        season.finish_human(self.state['season'],True,self.engine.species)
        season.next_week(self.state,self.state['season']['card']['token'])
        self.app.state=copy.deepcopy(self.state)
        self.app.season_screen.history={'items':self.state['_season_archive_pending'],'page':0,'has_more':False}
        self.app.state['season']['calendar']=season.calendar_date(season.elapsed_for_date(10000,2,29))
        for size in ((960,600),(1180,800),(1920,1080)):
            self.resize(size)
            for tab,_ in self.app.season_screen.TABS:
                self.app.season_screen.tab=tab
                self.draw()
                for rect,_ in self.app.ui.actions+self.app.ui.fields:
                    self.assertTrue(self.app.screen.get_rect().contains(rect),(size,tab,rect))
                    self.assertGreater(rect.height,0)
                self.assertNotIn('chat',[key for _,key in self.app.ui.fields])
        self.assertFalse(self.app.assets.errors,self.app.assets.errors)

    def test_season_soundtracks_use_battle_family_and_normal_battle_has_priority(self):
        with patch.object(pygame.mixer.music,'load'), patch.object(pygame.mixer.music,'play'):
            self.app.audio.music_volume=0
            self.app.audio.music(screen='season',now=1)
            self.assertTrue(self.app.audio.track.endswith('bgm50.ogg'))
            self.app.audio.music(screen='season_results',now=2)
            self.assertTrue(self.app.audio.track.endswith('bgm51.ogg'))
            self.app.audio.music(battle=True,screen='season',now=3)
            self.assertTrue(self.app.audio.track.endswith('bgm40.ogg'))


if __name__ == '__main__':
    unittest.main()
