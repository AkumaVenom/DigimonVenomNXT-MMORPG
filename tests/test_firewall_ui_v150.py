"""FireWall discovery, real supplied sprites and server-authoritative UI flows."""
import copy
import unittest
from unittest.mock import patch
import pygame
import test_story_client as harness
from venom.client.varieties import (FIREWALL_ORANGE, VARIETIES, firewall_map_available,
                                    variety_of, normal_rookie, name_color, scan_hint)
from venom.client.widgets import WHITE
from venom.common import story


class FireWallNativeUITests(unittest.TestCase):
    setUp = harness.StoryClientTests.setUp
    resize = harness.StoryClientTests.resize
    draw = harness.StoryClientTests.draw
    click = harness.StoryClientTests.click

    def field(self):
        self.app.state.update(in_story=False, in_farm=False, in_lab=False)
        self.app.menu = None
        self.app.state['battle'] = None

    def mon(self, sid='agumon_firewall'):
        return self.engine._monster(sid, level=55, abi=100, cam=100)

    def text_capture(self, module):
        from importlib import import_module
        obj = import_module(module)
        original = obj.text
        rows = []
        self.enterContext(patch.object(obj, 'text', side_effect=lambda *a, **k:
            (rows.append((str(a[2]), a, k)), original(*a, **k))[1]))
        return rows

    def test_all_five_filters_cycle_and_502_firewall_scans_remain_separate(self):
        self.field()
        screen = self.app.scan_screen
        seen = []
        for _ in VARIETIES:
            seen.append(screen.variant)
            screen.cycle_variant()
        self.assertEqual(tuple(seen), ('all','normal','paradox','shiny','firewall'))
        screen.filter('variant','firewall')
        self.assertEqual(len(screen.entries()),502)
        self.assertTrue(all(row['id'].endswith('_firewall') for row in screen.entries()))
        self.app.state['scan'].update(agumon=200, agumon_shiny=150, agumon_paradox=100, agumon_firewall=95)
        screen.filter('ready_only',True)
        self.assertNotIn('agumon_firewall',[row['id'] for row in screen.entries()])
        self.app.state['scan']['agumon_firewall']+=5
        self.assertIn('agumon_firewall',[row['id'] for row in screen.entries()])
        self.assertEqual([self.app.state['scan'][sid] for sid in ('agumon','agumon_shiny','agumon_paradox')],[200,150,100])
        self.app.ui.values['search']='FireWall Agumon'
        self.assertEqual([row['id'] for row in screen.entries()],['agumon_firewall'])

    def test_classification_uses_species_for_renamed_partners_and_excludes_starters(self):
        record={'species_id':'agumon_firewall','name':'My friend'}
        self.assertEqual(variety_of(record,self.app.assets.species),'firewall')
        self.assertEqual(name_color(record,self.app.assets.species,WHITE),FIREWALL_ORANGE)
        self.assertFalse(normal_rookie(self.app.assets.species['agumon_firewall']))
        self.assertTrue(all(variety_of(self.engine.species[sid])=='normal' for sid in self.engine.starters))

    def test_all_500_maps_advertise_real_firewall_habitat_and_all_rare_rates(self):
        self.assertEqual(len(self.app.assets.maps),500)
        for area in self.app.assets.maps.values():
            self.assertTrue(firewall_map_available(area,self.app.assets.species),area['id'])
            self.assertEqual(self.app.world_screen.rare_label(area), 'FIREWALL 0.7%  ·  SHINY 1%  ·  PARADOX 2.5%')
        self.assertFalse(firewall_map_available({'encounters':[]},self.app.assets.species))
        self.assertFalse(firewall_map_available({'firewall_encounters':['missing']},self.app.assets.species))

    def test_mastery_hints_are_independent_and_do_not_inflate_encounter_rate(self):
        for active in ('firewall','shiny','paradox'):
            state={'permanent_rewards':{active+'_scan_mastery':True}}
            for variety, rate in (('firewall','0.7%'),('shiny','1%'),('paradox','2.5%')):
                hint=scan_hint(variety,state)
                self.assertIn(rate,hint)
                self.assertEqual('5% → 6%' in hint,active==variety)
        self.assertIn('3 scan masteries',scan_hint('all',{'permanent_rewards':{v+'_scan_mastery':True for v in ('firewall','shiny','paradox')}}))

    def test_materialize_buttons_keep_firewall_id_and_gates_at_both_resolutions(self):
        self.field();self.app.state['in_lab']=True;self.app.menu='scan'
        self.app.scan_screen.variant='firewall'
        self.app.ui.values['search']='FireWall Agumon'
        self.app.state['scan']['agumon_firewall']=100
        before=copy.deepcopy(self.app.state)
        rows=self.text_capture('venom.client.laboratory')
        for size in ((960,600),(1280,800)):
            self.resize(size);self.draw()
            self.assertIn('FireWall: 0.7% encounter chance · +5% scan / defeat',[r[0] for r in rows])
            for label,rect,_ in self.controls:
                self.assertTrue(self.app.screen.get_rect().contains(rect),(size,label,rect))
        self.click('Materialize')
        self.assertEqual(self.app.connection.sent[-1],('materialize',{'species_id':'agumon_firewall'}))
        self.assertEqual(self.app.state,before)
        self.app.action_pending=False
        self.app.state['scan']['agumon_firewall']=95
        self.draw()
        self.assertTrue(next(opts['disabled'] for label,_,opts in self.controls if label=='5% more data'))
        self.app.state['permanent_rewards']={'firewall_scan_mastery':True}
        self.draw()
        self.assertIn('FireWall Mastery: 0.7% chance · 5% → 6% on wild wins',[r[0] for r in rows])

    def test_firewall_battle_banner_orange_names_and_tokened_target_command(self):
        self.field();rows=self.text_capture('venom.client.app')
        self.app.state['battle']={'kind':'wild','id':'firewall-ui-battle','enemies':[self.mon()], 'active':[0], 'actor':0, 'turn':7}
        for size in ((960,600),(1280,800)):
            self.resize(size);self.draw()
            self.assertIn('FIREWALL ENCOUNTER',[r[0] for r in rows])
            self.assertIn('RAREST VARIETY  /  +5% FIREWALL SCAN PER DEFEAT',[r[0] for r in rows])
            names=[r for r in rows if r[0].startswith('FireWall')]
            self.assertTrue(names)
            self.assertTrue(all(r[1][5]==FIREWALL_ORANGE for r in names))
        self.click('Attack')
        self.assertEqual(self.app.connection.sent[-1],('battle',dict(action='attack',target=0,party_index=0)))
        self.app.action_pending=False
        self.app.state['permanent_rewards']={'firewall_scan_mastery':True};self.draw()
        self.assertIn('FIREWALL MASTERY  /  +5% SCAN PER DEFEAT · +1% ON VICTORY',[r[0] for r in rows])
        self.app.state['battle'].update(kind='story',story_training=False)
        rows.clear();self.draw()
        self.assertFalse(any('SCAN PER DEFEAT' in r[0] for r in rows))

    def test_padded_supplied_art_fits_cards_but_world_preserves_normal_body_size_and_feet(self):
        assets=self.app.assets
        for sid in ('agumon_firewall','imperialdramonpaladinmode_firewall','fanglongmon_firewall'):
            if sid not in assets.species:
                continue
            for motion in ('idle','walk','attack','attack1','attack2'):
                for flip in (False,True):
                    image=assets.sprite(sid,(100,86),motion,.25,flip)
                    self.assertIsNotNone(image)
                    self.assertLessEqual(image.get_width(),100)
                    self.assertLessEqual(image.get_height(),86)
                    world=assets.world_sprite(sid,(58,64),motion,.25,flip)
                    path=assets.sprite_path(sid,motion,.25)
                    if flip:
                        path=assets.species[sid].get('mirrored_frames',{}).get(path,path)
                    geo=assets.species[sid]['sprite_geometry'][path]
                    factor=min(58/geo['source_size'][0],64/geo['source_size'][1])
                    self.assertAlmostEqual(world.get_width()/geo['output_size'][0],factor,delta=.005)
                    foot=assets.sprite_anchor(sid,world,motion,.25,flip)
                    self.assertGreater(foot[0],0);self.assertLess(foot[0],world.get_width())
                    self.assertGreater(foot[1],0);self.assertLess(foot[1],world.get_height())
        self.assertFalse(assets.errors)

    def test_dawn_mastery_journal_survives_lost_title_and_results_distinguish_unlock(self):
        rows=[]
        original=self.app.story_screen.write
        self.enterContext(patch.object(self.app.story_screen,'write',side_effect=lambda value,*a,**k:(rows.append(str(value)),original(value,*a,**k))[1]))
        self.app.menu='story';self.app.story_screen.tab='league'
        view=self.app.state['story']['view']
        view.update(campaign_id='dawn_relay',firewall_scan_bonus=20,scan_bonus=20)
        view['champion'].update(holder='New challenger',status='former_champion',reigns=1,defenses=2)
        for size in ((960,600),(1280,800)):
            self.resize(size);self.draw()
            self.assertIn('+20% FIREWALL SCAN',rows)
            self.assertIn('PERMANENT · UNLOCKED',rows)
            self.assertIn('New challenger',rows)
        self.app.menu=None
        for unlocked in (True,False):
            self.app.story_screen.result={'id':'result','won':True,'role':'champion','credits':100,'opponent':'Astra','scan_mastery_unlocked':unlocked}
            rows.clear();self.draw()
            expected='PERMANENT REWARD UNLOCKED' if unlocked else 'PERMANENT MASTERY ACTIVE'
            self.assertTrue(any(r.startswith(expected) and 'FireWall scan: 5% → 6%' in r for r in rows))
        self.app.story_screen.result=None

    def test_partner_routes_and_storage_keep_exact_firewall_ids(self):
        self.field();self.app.state['in_lab']=True
        mon=self.mon();self.app.state['party']=[mon]+self.app.state['party']
        self.app.menu='party';self.app.partner_screen.mode='evolution'
        self.engine._refresh(self.app.state)
        rows=self.text_capture('venom.client.partners')
        self.draw()
        self.assertIn('FireWall variety stays through evolution.',[r[0] for r in rows])
        routes=self.app.partner_screen.routes()
        self.assertTrue(routes)
        self.assertTrue(all(row['to'].endswith('_firewall') for row in routes))
        available=[row for row in routes if row.get('eligible')]
        if available:
            with patch.object(self.app,'send') as send:
                button=next((rect for label,rect,opts in reversed(self.controls) if label=='Digivolve' and not opts.get('disabled')),None)
                self.assertIsNotNone(button)
                self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=self.app.screen.to_physical_point(button.center)))
                self.assertTrue(send.call_args.kwargs['to'].endswith('_firewall'))
        self.assertFalse(self.app.assets.errors)
