"""Shiny discovery, separate scans and exact-species client commands in v1.2.0."""
import copy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame

from tools.preview_ui_screens import ROOT, make_app, select_ui2_view
from venom.client.laboratory import ScanScreen
from venom.client.varieties import (VARIETIES, SHINY_GOLD, name_color, normal_rookie,
                                    shiny_map_available, variety_of)
from venom.client.widgets import GOLD, WHITE


class ShinyClassificationTests(unittest.TestCase):
    def setUp(self):
        self.normal = dict(id='agumon', name='Agumon', stage='rookie')
        self.paradox = dict(self.normal, id='agumon_paradox', name='Paradox Agumon', paradox=True, base_id='agumon')
        self.shiny = dict(self.normal, id='agumon_shiny', name='Shiny Agumon', shiny=True, variety='shiny', base_id='agumon')
        self.catalog = {s['id']: s for s in (self.normal, self.paradox, self.shiny)}
        self.app = SimpleNamespace(assets=SimpleNamespace(species=self.catalog),
            state={'scan': {'agumon': 200, 'agumon_paradox': 150, 'agumon_shiny': 95}, 'party': [], 'storage': []},
            ui=SimpleNamespace(values={}), scroll=0)
        self.screen = ScanScreen(self.app)

    def test_all_four_filters_are_disjoint_and_keep_separate_scan_progress(self):
        self.assertEqual(len(self.screen.entries()), 3)
        for variant, expected in (('normal', 'agumon'), ('paradox', 'agumon_paradox'), ('shiny', 'agumon_shiny')):
            with self.subTest(variant=variant):
                self.screen.filter('variant', variant)
                self.assertEqual([s['id'] for s in self.screen.entries()], [expected])
        self.screen.filter('ready_only', True)
        self.assertEqual(self.screen.entries(), [])
        # A delta snapshot may update the scans dictionary without replacing it.
        self.app.state['scan']['agumon_shiny'] += 5
        self.assertEqual([s['id'] for s in self.screen.entries()], ['agumon_shiny'])
        self.assertEqual(self.app.state['scan']['agumon'], 200)
        self.assertEqual(self.app.state['scan']['agumon_paradox'], 150)

    def test_filter_cycle_search_and_snapshot_without_flags(self):
        observed=[]
        for _ in VARIETIES:
            observed.append(self.screen.variant)
            self.screen.cycle_variant()
        self.assertEqual(tuple(observed), VARIETIES)
        self.app.ui.values['search']='shiny'
        self.assertEqual([s['id'] for s in self.screen.entries()], ['agumon_shiny'])
        record = {'species_id': 'agumon_shiny', 'name': 'Custom partner name'}
        self.assertEqual(variety_of(record, self.catalog), 'shiny')
        self.assertEqual(name_color(record, self.catalog, WHITE), GOLD)
        self.assertEqual(SHINY_GOLD, GOLD)

    def test_starter_rules_and_map_guide_include_all_regions(self):
        self.assertTrue(normal_rookie(self.normal))
        self.assertFalse(normal_rookie(self.paradox))
        self.assertFalse(normal_rookie(self.shiny))
        self.assertFalse(normal_rookie(dict(self.normal, stage='mega')))
        for region in ('dawn', 'world_ds', 'xros_wars'):
            self.assertTrue(shiny_map_available({'region_id': region, 'encounters': ['agumon']}, self.catalog))
            self.assertTrue(shiny_map_available({'region_id': region, 'encounters': ['agumon_paradox']}, self.catalog))
        self.assertFalse(shiny_map_available({'encounters': []}, self.catalog))
        self.assertFalse(shiny_map_available({'encounters': ['unavailable']}, self.catalog))


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class ShinyNativeInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.app=make_app()
        self.addCleanup(pygame.quit)
        select_ui2_view(self.app, 'scan')
        base = copy.deepcopy(next(s for s in self.app.assets.species.values() if normal_rookie(s)))
        self.shiny = dict(base, id=base['id']+'_shiny', name='Shiny '+base['name'], shiny=True, paradox=False, variety='shiny')
        self.app.assets.species = dict(self.app.assets.species, **{self.shiny['id']: self.shiny})
        self.mon = dict(copy.deepcopy(self.app.state['party'][0]), species_id=self.shiny['id'], name=self.shiny['name'])
        self.app.state['scan'][self.shiny['id']]=100
        self.app.scan_screen.variant='shiny'
        self.app.ui.values['search']=self.shiny['name']
        self.buttons=[]
        original=self.app.ui.button
        def capture(rect, label, callback, *args, **kwargs):
            self.buttons.append((str(label), pygame.Rect(rect), callback, kwargs))
            return original(rect, label, callback, *args, **kwargs)
        patched=patch.object(self.app.ui,'button',side_effect=capture)
        patched.start();self.addCleanup(patched.stop)

    def render_scan(self):
        self.app.ui.begin();self.buttons.clear()
        w,h=self.app.screen.get_size()
        self.app.scan_screen.draw(pygame.Rect(20,98,w-40,h-118))

    def test_materialize_uses_shiny_id_and_shows_rarity_and_exact_rate(self):
        with patch('venom.client.laboratory.text', wraps=__import__('venom.client.laboratory', fromlist=['text']).text) as labels:
            self.render_scan()
        strings=[str(c.args[2]) for c in labels.call_args_list]
        self.assertIn('Shiny: 1% encounter chance · +5% scan / defeat', strings)
        materialize=next(c for c in self.buttons if c[0]=='Materialize')
        self.assertFalse(materialize[3].get('disabled'))
        with patch.object(self.app,'send') as send:
            materialize[2]()
        send.assert_called_once_with('materialize',species_id=self.shiny['id'])
        self.app.state['scan'][self.shiny['id']]=95
        self.render_scan()
        self.assertTrue(next(c[3]['disabled'] for c in self.buttons if c[0]=='5% more data'))

    def test_picker_and_demo_do_not_grant_shiny_starters(self):
        self.app.make_demo()
        self.assertTrue(all(variety_of(mon,self.app.assets.species)=='normal' for mon in self.app.state['party']))
        self.app.state=None
        self.app.auth_picker='starter'
        self.app.ui.values['search']=''
        self.app.ui.begin()
        with patch.object(self.app.presentation,'sprite',wraps=self.app.presentation.sprite) as sprites:
            self.app.entry_screen.draw_picker()
        self.assertTrue(sprites.call_args_list)
        for call in sprites.call_args_list:
            self.assertTrue(normal_rookie(self.app.assets.species[call.args[1]]))

    def test_shiny_battle_header_names_and_targeting_keep_server_contract(self):
        self.app.menu=None
        self.app.state['battle']={'kind':'wild','enemies':[self.mon], 'active':[0,1,2], 'actor':0,'turn':1}
        w,h=self.app.screen.get_size()
        self.app.viewport=pygame.Rect(20,94,w-352,h-262)
        self.app.ui.begin()
        import venom.client.app as app_module
        with patch.object(app_module,'text',wraps=app_module.text) as labels:
            self.app.draw_battle()
        strings=[str(c.args[2]) for c in labels.call_args_list]
        self.assertIn('SHINY ENCOUNTER',strings)
        self.assertIn('RARE VARIETY  /  +5% SHINY SCAN PER DEFEAT',strings)
        name_calls=[c for c in labels.call_args_list if str(c.args[2]).startswith('Shiny')]
        self.assertTrue(name_calls)
        self.assertTrue(all(c.args[5]==GOLD for c in name_calls))
        attack=next(c for c in self.buttons if c[0]=='Attack')
        with patch.object(self.app,'send') as send:
            attack[2]()
        send.assert_called_once_with('battle',action='attack',target=0,party_index=0)
        self.assertFalse(self.app.assets.errors)


if __name__=='__main__':
    unittest.main()
