"""Ghostline native UI preserves privacy, spoilers, real teams and readable text."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import pygame
import test_story_client as harness
from venom.client.assets import Audio
from venom.client.widgets import GOLD

ROOT = Path(__file__).resolve().parents[1]


class GhostlineStoryUITests(unittest.TestCase):
    setUp = harness.StoryClientTests.setUp
    resize = harness.StoryClientTests.resize
    draw = harness.StoryClientTests.draw
    click = harness.StoryClientTests.click
    key = harness.StoryClientTests.key

    def ghost_view(self):
        view = self.app.state['story']['view']
        view.update(campaign_id='xros_ghostline', title='Super Xros: Ghostline',
                    badge_count=0, badge_total=30, chapter=0, chapter_name='Switchboard',
                    objective='Speak to your intel contact to start tracing the Ghostline signal.',
                    hub=True, training_available=False, revealed=False, completed=False,
                    final_name=None, final_team=[], final_map_id=None, scan_bonus=0, shiny_scan_bonus=0)
        view['chapters'] = [dict(index=i,name='Switchboard' if i==0 else f'Encrypted node {i+1:02}',
            level=1+i*3,unlocked=i<2,complete=False,hub=i==0,map_id=f'xros_{i:03}',
            maps=[dict(id=f'xros_{i:03}',name=f'Node {i+1:02}',unlocked=i<2,active=i==0)]) for i in range(31)]
        view['badges'] = [dict(id=f'proof_{i}',name=f'Encrypted evidence {i+1:02}',earned=False,chapter=i+1) for i in range(30)]
        self.app.menu = 'story'
        return view

    def text_capture(self):
        texts = []
        original = self.app.story_screen.write
        self.enterContext(patch.object(self.app.story_screen,'write',side_effect=lambda value,*args,**kwargs:(texts.append(str(value)),original(value,*args,**kwargs))[1]))
        return texts

    def test_three_campaigns_choose_explicit_id_and_keep_owned_state(self):
        self.app.state['in_story'] = False
        self.app.menu='story'
        before = copy.deepcopy(self.app.state)
        for size in ((960,600),(1280,800)):
            self.resize(size);self.draw()
            labels = [row[0] for row in self.controls]
            for label in ('Continue Dawn Relay','Begin Paradox Chronicle','Begin Ghostline'):
                self.assertIn(label,labels)
            for label,rect,_ in self.controls:
                self.assertTrue(self.app.screen.get_rect().contains(rect),(size,label,rect))
        self.click('Begin Ghostline')
        self.assertEqual(self.app.connection.sent[-1],('story',dict(action='enter',campaign_id='xros_ghostline')))
        self.assertEqual(self.app.state,before)

    def test_old_server_cannot_open_dawn_when_ghostline_is_requested(self):
        self.app.state['in_story']=False
        self.app.server_features={'story','world_ds_story'}
        self.app.send('story',action='enter',campaign_id='xros_ghostline')
        self.assertFalse(self.app.connection.sent)
        self.app.server_features.add('ghostline_story')
        self.app.send('story',action='enter',campaign_id='xros_ghostline')
        self.assertEqual(self.app.connection.sent[-1],('story',dict(action='enter',campaign_id='xros_ghostline')))

    def test_all_31_maps_and_30_evidence_files_are_accessible_in_pages(self):
        self.ghost_view()
        for size in ((960,600),(1280,800),(1920,1080)):
            self.resize(size)
            for tab,_ in self.app.story_screen.tabs:
                for page in range(4):
                    self.app.story_screen.tab,self.app.story_screen.page=tab,page
                    self.draw()
                    for label,rect,_ in self.controls:
                        self.assertTrue(self.app.screen.get_rect().contains(rect),(size,tab,page,label,rect))
        self.app.story_screen.tab,self.app.story_screen.page='atlas',3
        self.draw()
        self.assertIn('→ Node 31',[label for label,_,_ in self.controls])
        self.assertTrue(next(options['disabled'] for label,_,options in self.controls if label=='→ Node 31'))
        self.app.story_screen.tab,self.app.story_screen.page='badges',3
        texts=self.text_capture();self.draw()
        self.assertTrue(any('Evidence 28–30 of 30' in text for text in texts))

    def test_future_case_details_remain_sealed_even_with_unexpected_final_data(self):
        view=self.ghost_view();self.app.story_screen.tab='league'
        view.update(final_name='Mara Vale / Null Regent',final_map_id='xros_095',final_team=[dict(name='SECRET BOSS',species_id=self.engine.starters[0])])
        texts=self.text_capture();self.draw()
        self.assertNotIn('Mara Vale / Null Regent',texts)
        self.assertNotIn('SECRET BOSS',texts)
        self.assertNotIn('Open final node',[label for label,_,_ in self.controls])
        view['revealed']=True;texts.clear();self.draw()
        self.assertIn('Mara Vale / Null Regent',texts)
        self.assertIn('SECRET BOSS',texts)
        self.assertTrue(next(options['disabled'] for label,_,options in self.controls if label=='Open final node'))
        view['chapters'][30]['unlocked']=True
        self.draw();self.click('Open final node')
        self.assertEqual(self.app.connection.sent[-1],('story',dict(action='travel',chapter=30,map_id='xros_095')))

    def test_completion_displays_permanent_shiny_reward_and_hub_return(self):
        view=self.ghost_view();view.update(revealed=True,completed=True,badge_count=30,shiny_scan_bonus=20,scan_bonus=20)
        self.app.story_screen.tab='league'
        texts=self.text_capture();self.draw()
        self.assertIn('+20% SHINY SCAN',texts)
        self.assertIn('UNLOCKED',texts)
        self.assertIn('Network secured',texts)
        self.assertNotIn('Open final node',[label for label,_,_ in self.controls])
        self.click('Return to the safe hub')
        self.assertEqual(self.app.connection.sent[-1],('story',dict(action='travel',chapter=0)))

    def test_private_hub_keeps_services_and_never_renders_stale_public_players(self):
        self.ghost_view();self.draw()
        for label in ('Partners & evolution  P','Shop & bag  B','DigiLab camp  F1','DigiFarm  F2'):
            self.assertIn(label,[row[0] for row in self.controls])
        self.assertFalse(any(label.startswith('Training battle') for label,_,_ in self.controls))
        self.app.players={'StalePublic':dict(map_id=self.app.state['map_id'],x=0,y=0,tamer=self.app.tamer),
                          'StaleBot':dict(map_id=self.app.state['map_id'],x=0,y=0,tamer=self.app.tamer,is_bot=True,id=1)}
        actors=self.app.world._actors()
        self.assertFalse(any(row[6] in ('StalePublic','StaleBot','AI RIVAL · StaleBot') for row in actors))
        self.app.state['story']['view']['npcs']=[]
        self.assertEqual(self.app.world._story_npcs(),[])

    def test_long_dialogue_keeps_every_word_and_only_sends_token_after_reading(self):
        view=self.ghost_view();self.app.menu=None
        phrase='Check the relay timestamp before opening the evidence vault. '
        dialogue=phrase*40+'The final word is UNTRUNCATED.'
        view['dialogue']=dict(name='Intel contact',text=dialogue,tamer_id=self.app.tamer,page=1,pages=2,
            token='long-ghost-token',choices=[dict(id='next',label='Continue'),dict(id='leave',label='Talk later')])
        before=copy.deepcopy(self.app.state)
        for size in ((960,600),(1280,800)):
            self.resize(size)
            self.app.story_screen.dialogue_key=None
            pages=self.app.story_screen.dialogue_text_pages()
            self.assertGreater(len(pages),1)
            self.assertEqual(' '.join(line for page in pages for line in page), ' '.join(dialogue.split()))
            self.draw();self.assertIn('Read more  →',[label for label,_,_ in self.controls])
            for page in range(len(pages)-1):
                self.key(pygame.K_RETURN);self.draw()
                self.assertFalse(self.app.connection.sent)
                for label,rect,_ in self.controls:
                    self.assertTrue(self.app.screen.get_rect().contains(rect),(size,page,label,rect))
            self.assertIn('Continue',[label for label,_,_ in self.controls])
        self.key(pygame.K_RETURN)
        self.assertEqual(self.app.connection.sent[-1],('story',dict(action='dialogue',token='long-ghost-token',choice='next')))
        self.assertEqual(self.app.state,before)

    def test_mastered_shiny_battle_explains_base_scan_and_victory_bonus(self):
        from venom.client.app import text as render_text
        self.app.state.update(in_story=False,in_farm=False,in_lab=False,permanent_rewards={'shiny_scan_mastery':True})
        species=next(row['id'] for row in self.engine.species.values() if row.get('shiny'))
        self.app.state['battle']={'id':'shiny-qa','kind':'wild','enemies':[self.engine._monster(species,5)],'active':[0],'actor':0,'turn':1}
        self.app.menu=None
        texts=[]
        def capture(screen,assets,value,*args,**kwargs):
            texts.append(str(value))
            return render_text(screen,assets,value,*args,**kwargs)
        with patch('venom.client.app.text',side_effect=capture):
            self.draw()
        self.assertIn('SHINY MASTERY  /  +5% SCAN PER DEFEAT · +1% ON VICTORY',texts)
        self.assertNotIn('RARE VARIETY  /  +5% SHINY SCAN PER DEFEAT',texts)

    def test_custom_portal_requirement_and_npc_role_do_not_claim_paradox_story(self):
        self.ghost_view()
        self.assertEqual(self.app.world._story_exit_requirement(dict(unlocked=False,requirement='Secure Relay Access Proof')), 'LOCKED  ·  Secure Relay Access Proof')
        self.assertIn('GHOSTLINE TARGET',self.app.world._story_role(dict(role='final',role_label='GHOSTLINE TARGET',level=100,status='ready')))
        self.assertNotIn('CONVERGENCE',self.app.world._story_role(dict(role='final',role_label='GHOSTLINE TARGET',level=100,status='ready')))
        hacked=dict(role='trainer',status='cleared',hacked=True)
        self.assertEqual(self.app.world._story_color(hacked),GOLD)
        self.assertIn('COMPROMISED',self.app.world._story_role(hacked))


class GhostlineMusicTests(unittest.TestCase):
    def test_regional_field_tamer_final_music_and_services_restore_without_blocking(self):
        pygame.init();self.addCleanup(pygame.quit)
        catalog=json.loads((ROOT/'data/catalog.json').read_text())
        maps={row['id']:row for row in catalog['maps']}
        area=next(row for row in maps.values() if row.get('region_id')=='xros_wars')
        data=json.loads((ROOT/'data/xros_audio.json').read_text())
        tracks={row['id']:row for row in data['music']}
        with patch.object(pygame.mixer.music,'load'),patch.object(pygame.mixer.music,'play'),patch.object(pygame.mixer.music,'queue'):
            audio=Audio(SimpleNamespace(root=ROOT,catalog=catalog,maps=maps));audio.enabled=False
            base=dict(map_id=area['id'],in_story=True,story_campaign='xros_ghostline')
            audio.music(**base,now=1)
            self.assertEqual(audio.track,tracks[area['music_id']]['path'])
            audio.music(**base,screen='story',now=1.5)
            self.assertEqual(audio.track,tracks[area['music_id']]['path'])
            audio.music(**base,battle=True,story_battle={'story_role':'trainer'},now=2)
            self.assertEqual(audio.track,tracks[area['battle_music_id']]['path'])
            audio.music(**base,battle=True,story_battle={'story_role':'final'},now=3)
            self.assertEqual(audio.track,tracks[data['scene_tracks']['endgame_battle']]['path'])
            for flag,scene in (('in_lab','digilab'),('in_farm','farm')):
                audio.music(**base,**{flag:True},now=4)
                self.assertEqual(audio.track,audio._screen_tracks[scene])
            audio.music(**base,now=5)
            self.assertEqual(audio.track,tracks[area['music_id']]['path'])
            audio.music(**base,screen='settings',now=6)
            self.assertEqual(audio.track,audio._screen_tracks['settings'])
            audio.music(**base,now=7)
            self.assertEqual(audio.track,tracks[area['music_id']]['path'])


if __name__=='__main__': unittest.main()
