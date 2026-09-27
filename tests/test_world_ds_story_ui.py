"""Native multi-campaign UI: travel coverage, safe-hub controls and reward clarity."""
import copy
import unittest
import pygame
import test_story_client as harness


class WorldDSStoryUITests(unittest.TestCase):
    setUp = harness.StoryClientTests.setUp
    resize = harness.StoryClientTests.resize
    draw = harness.StoryClientTests.draw
    click = harness.StoryClientTests.click
    key = harness.StoryClientTests.key

    def ds_view(self):
        view = self.app.state['story']['view']
        view.update(campaign_id='world_ds_paradox', title='World DS: Paradox Chronicle',
                    badge_total=17, badge_count=0, chapter=0, chapter_name='DigiCentral',
                    hub=True, training_available=False, completed=False, scan_bonus=0,
                    final_map_id='world_ds_001', final_npc_id='ds_convergence')
        view['chapters'] = [dict(index=i, name='DigiCentral' if i==0 else f'World DS Field {i}',
            level=10+i*5, unlocked=i<2, complete=False, map_id=f'world_ds_{i:03}',
            maps=[dict(id=f'world_ds_{i:03}', name=f'Explore field {i}', unlocked=i<2, active=i==0)]) for i in range(18)]
        view['badges'] = [dict(id=f'crest_{i}', name=f'Paradox Crest {i}', earned=False, chapter=i) for i in range(1,18)]
        view['final_team'] = [dict(species_id=ident, name=self.engine.species[ident]['name'], level=100) for ident in self.engine.starters[:3]]
        self.app.menu='story'
        return view

    def test_picker_selects_explicit_campaign_without_mutating_owned_resources(self):
        self.app.state['in_story']=False
        before=copy.deepcopy(self.app.state)
        self.key(pygame.K_F4); self.draw()
        self.assertEqual(self.app.menu,'story')
        self.assertFalse(self.app.connection.sent)
        self.click('Begin Paradox Chronicle')
        self.assertEqual(self.app.connection.sent[-1],('story',dict(action='enter',campaign_id='world_ds_paradox')))
        self.assertEqual(self.app.state,before)

    def test_every_map_and_crest_has_a_page_and_controls_fit_small_displays(self):
        self.ds_view()
        for size in ((960,540),(960,600),(1280,720),(1920,1080)):
            self.resize(size)
            for tab,_ in self.app.story_screen.tabs:
                for page in (0,1):
                    self.app.story_screen.tab=tab; self.app.story_screen.page=page; self.draw()
                    for label,rect,_ in self.controls:
                        self.assertTrue(self.app.screen.get_rect().contains(rect),(size,tab,page,label,rect))
        self.app.story_screen.select_tab('atlas'); self.draw()
        self.click('Next'); self.draw()
        labels=[row[0] for row in self.controls]
        self.assertIn('→ Explore field 17',labels)
        self.assertNotIn('● Explore field 0',labels)
        self.app.story_screen.select_tab('badges'); self.draw(); self.click('Next'); self.draw()
        self.assertEqual(self.app.story_screen.page,1)

    def test_safe_hub_has_all_services_and_no_training_battle(self):
        view=self.ds_view(); self.draw()
        labels=[row[0] for row in self.controls]
        for label in ('Partners & evolution  P','Shop & bag  B','Recover your team','DigiLab camp  F1','DigiFarm  F2'):
            self.assertIn(label,labels)
        self.assertFalse(any(label.startswith('Training battle') for label in labels))
        self.click('DigiFarm  F2')
        self.assertEqual(self.app.connection.sent[-1],('digifarm',dict(action='enter')))
        self.app.action_pending=False; view.update(hub=False,training_available=True,training_level=10)
        self.draw(); self.assertIn('Training battle · Lv.10',[row[0] for row in self.controls])

    def test_convergence_requires_all_crests_and_uses_authoritative_destination(self):
        view=self.ds_view(); self.app.story_screen.tab='league'; self.draw()
        self.assertTrue(next(options['disabled'] for label,_,options in self.controls if label=='Visit the Convergence'))
        view['badge_count']=17; self.draw(); self.click('Visit the Convergence')
        self.assertEqual(self.app.connection.sent[-1],('story',dict(action='travel',chapter=17,map_id='world_ds_001')))

    def test_quest_dialogue_choices_forward_authoritative_token(self):
        view=self.ds_view(); self.app.menu=None
        view['dialogue']=dict(name='Quest researcher',text='Help restore this field.',tamer_id=self.app.tamer,
            token='ds-token',page=1,pages=1,choices=[dict(id='accept_quest',label='Accept quest'),dict(id='leave',label='Talk later')])
        self.draw(); self.click('Accept quest')
        self.assertEqual(self.app.connection.sent[-1],('story',dict(action='dialogue',token='ds-token',choice='accept_quest')))

    def test_journal_talk_uses_npc_proximity_and_does_not_open_bot_profiles(self):
        self.ds_view(); self.draw(); self.click('Talk')
        self.assertEqual(self.app.connection.sent[-1],('story',dict(action='talk',npc_id='guide')))
        self.assertIsNone(self.app.menu)


if __name__=='__main__': unittest.main()
