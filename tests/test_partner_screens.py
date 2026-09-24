"""Action and data contracts for the native partner destinations."""
import copy
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import unittest
from unittest.mock import patch

import pygame

from tools.preview_ui_screens import ROOT, make_app
from venom.client.partners import PartnerScreen
from venom.client.render import NativeCanvas
from venom.client.display import effective_ui_scale
from venom.common.game import GameEngine


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class PartnerScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = GameEngine(ROOT)

    def setUp(self):
        self.app = make_app()
        self.addCleanup(pygame.quit)
        self.screen = PartnerScreen(self.app)
        self.app.menu = 'party'
        self.app.state['in_lab'] = True
        self.app.state['evolution_options'] = [self.game.evolution_options(mon) for mon in self.app.state['party']]
        self.controls = []
        original = self.app.ui.button
        def capture(rect, label, callback, **kwargs):
            self.controls.append((label, pygame.Rect(rect), kwargs))
            return original(rect, label, callback, **kwargs)
        self.button_patch = patch.object(self.app.ui, 'button', side_effect=capture)
        self.button_patch.start()
        self.addCleanup(self.button_patch.stop)

    def render(self, mode=None):
        if mode:
            self.screen.mode = mode
        self.app.ui.actions, self.app.ui.fields = [], []
        self.controls.clear()
        w, h = self.app.screen.get_size()
        self.screen.draw(pygame.Rect(20, 98, w-40, h-118))

    def control(self, label, index=0):
        found = [(rect, kwargs) for name, rect, kwargs in self.controls if name == label]
        self.assertGreater(len(found), index, label)
        return found[index]

    def click(self, label, index=0):
        rect, options = self.control(label, index)
        self.assertFalse(options.get('disabled'), label)
        self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                            pos=self.app.screen.to_physical_point(rect.center)))

    def test_roster_lead_and_storage_actions_respect_distinct_server_gates(self):
        self.app.selected_party = 1
        with patch.object(self.app, 'send') as send:
            self.render('roster')
            self.click('Make leader')
            send.assert_called_with('party', action='lead', index=1)
            self.click('Move to storage')
            send.assert_called_with('party', action='deposit', index=1)
            self.app.state['in_lab'] = False
            self.render()
            self.assertFalse(self.control('Make leader')[1]['disabled'])
            self.assertTrue(self.control('Move to storage')[1]['disabled'])
            self.app.state['battle'] = {'active': [0]}
            self.render()
            self.assertTrue(self.control('Make leader')[1]['disabled'])

    def test_evolution_uses_authoritative_eligibility_and_selected_slot(self):
        index = 1
        self.app.selected_party = index
        route = {'to': 'greymon', 'name': 'Greymon', 'level': 16, 'eligible': True,
                 'missing': [], 'devolve': False, 'stats': {'hp': 150}}
        self.app.state['evolution_options'][index] = [route]
        with patch.object(self.app, 'send') as send:
            self.render('evolution')
            # The first Digivolve is the filter; the second belongs to the route.
            self.click('Digivolve', index=1)
            send.assert_called_with('evolve', party_index=index, to='greymon')
            self.assertIn(('HP', self.app.state['party'][index]['max_hp'], 150),
                          self.screen.requirements(self.app.state['party'][index], route))
            route['eligible'] = False
            self.render()
            self.assertTrue(self.control('Digivolve', 1)[1]['disabled'])
            route['eligible'] = True
            self.app.state['in_lab'] = False
            self.render()
            self.assertTrue(self.control('Digivolve', 1)[1]['disabled'])
            self.app.state['in_lab'] = True
            self.app.action_pending = True
            self.render()
            self.assertTrue(self.control('Digivolve', 1)[1]['disabled'])

    def test_storage_search_retains_exact_indices_for_duplicate_records(self):
        mon = copy.deepcopy(self.app.state['party'][0])
        self.app.state['storage'] = [dict(mon, name='Other'), dict(mon, name='Twin'), dict(mon, name='Twin')]
        self.app.ui.values['bank_search'] = 'Twin'
        before = copy.deepcopy(self.app.state)
        with patch.object(self.app, 'send') as send:
            self.render('storage')
            self.click('Withdraw', index=1)
            send.assert_called_with('party', action='withdraw', index=2)
            self.assertEqual(self.app.state, before)

    def test_empty_party_can_withdraw_then_full_party_can_exchange(self):
        mon = copy.deepcopy(self.app.state['party'][0])
        self.app.state['party'] = []
        self.app.state['storage'] = [mon]
        self.render('roster')
        self.click('Open DigiBank')
        self.assertEqual(self.screen.mode, 'storage')
        self.assertEqual(self.app.menu, 'party')
        self.render()
        self.assertFalse(self.control('Withdraw')[1]['disabled'])
        self.app.state['party'] = [dict(mon) for _ in range(6)]
        self.render()
        self.assertFalse(self.control('Swap into slot 1')[1]['disabled'])

    def test_pagination_filters_and_native_bounds_across_sizes(self):
        mon = copy.deepcopy(self.app.state['party'][0])
        self.app.state['storage'] = [dict(mon, name=f'Partner {n}') for n in range(20)]
        self.render('storage')
        self.click('Next')
        self.assertGreater(self.app.scroll, 0)
        self.app.ui.values['bank_search'] = 'Partner 1'
        self.render()
        self.assertEqual(self.app.scroll, 0)
        self.assertEqual(len(self.screen.storage_entries()), 11)
        self.app.state['party'] = [dict(mon, uid=str(n)) for n in range(6)]
        self.app.state['evolution_options'] = [self.game.evolution_options(mon)]*6
        for size in ((1180, 800), (2048, 1152), (3840, 2160)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(size), effective_ui_scale(size))
            self.app.ui.screen = self.app.screen
            for mode in PartnerScreen.MODES:
                with self.subTest(size=size, mode=mode):
                    self.render(mode)
                    bounds = self.app.screen.get_rect()
                    for rect, _ in self.app.ui.actions:
                        self.assertTrue(bounds.contains(rect), (mode, rect, bounds))
                        self.assertGreater(rect.width, 0)
                        self.assertGreater(rect.height, 0)
        self.assertFalse(self.app.assets.errors, self.app.assets.errors)


if __name__ == '__main__':
    unittest.main()
