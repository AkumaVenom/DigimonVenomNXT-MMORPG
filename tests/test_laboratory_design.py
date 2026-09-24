"""Interaction and data-gate checks for the real native laboratory screens."""
import copy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from tools.preview_ui_screens import ROOT, make_app
from venom.client.display import effective_ui_scale
from venom.client.laboratory import LaboratoryScreen, ScanScreen
from venom.client.render import NativeCanvas


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class LaboratoryDesignTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.addCleanup(pygame.quit)
        self.app.state['in_lab'] = True
        self.lab = LaboratoryScreen(self.app)
        self.scan = ScanScreen(self.app)
        self.controls = []
        original = self.app.ui.button
        def capture(rect, label, callback, *args, **kwargs):
            self.controls.append((str(label), pygame.Rect(rect), kwargs))
            return original(rect, label, callback, *args, **kwargs)
        self.button_patch = patch.object(self.app.ui, 'button', side_effect=capture)
        self.button_patch.start()
        self.addCleanup(self.button_patch.stop)

    def render(self, menu):
        self.app.menu = menu
        self.app.ui.begin()
        self.controls.clear()
        screen = self.app.screen
        destination = self.lab if menu == 'lab' else self.scan
        destination.draw(pygame.Rect(20, 98, screen.get_width()-40, screen.get_height()-118))

    def control(self, label):
        candidates = [(rect, options) for name, rect, options in self.controls if name == label]
        self.assertTrue(candidates, f'Missing {label}: {[item[0] for item in self.controls]}')
        return candidates[0]

    def click(self, label):
        rect, options = self.control(label)
        self.assertFalse(options.get('disabled'), f'{label} disabled')
        self.assertTrue(self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                        pos=self.app.screen.to_physical_point(rect.center))))

    def test_lab_clicks_keep_real_recovery_return_and_navigation_contracts(self):
        before = copy.deepcopy(self.app.state)
        with patch.object(self.app, 'send') as send:
            self.render('lab')
            self.click('Heal all partners')
            send.assert_called_with('digilab', action='heal')
            self.click('Return to field')
            send.assert_called_with('digilab', action='return')
        self.assertEqual(before, self.app.state)
        self.app.partner_screen = SimpleNamespace(open_mode=Mock())
        for label, mode in [('Digivolution', 'evolution'), ('DigiBank', 'storage'), ('Active team', 'roster')]:
            self.render('lab')
            self.click(label)
            self.app.partner_screen.open_mode.assert_called_with(mode)
        self.render('lab')
        self.click('Scan & materialize')
        self.assertEqual(self.app.menu, 'scan')

    def test_materialize_click_is_gated_by_scan_lab_busy_and_bank_capacity(self):
        ready_id = next(sid for sid, value in self.app.state['scan'].items() if value >= 100)
        with patch.object(self.app, 'send') as send:
            self.render('scan')
            self.click('Materialize')
            send.assert_called_once_with('materialize', species_id=ready_id)
            self.app.state['in_lab'] = False
            self.render('scan')
            self.assertTrue(self.control('Materialize')[1]['disabled'])
            self.click('Enter DigiLab')
            send.assert_called_with('digilab', action='enter')
            self.app.state['in_lab'] = True
            with patch.object(self.app, 'action_pending', True):
                self.render('scan')
                self.assertTrue(self.control('Materialize')[1]['disabled'])
            mon = self.app.state['party'][0]
            self.app.state = dict(self.app.state, party=[mon]*6, storage=[mon]*2000)
            self.render('scan')
            self.assertTrue(self.control('DigiBank full')[1]['disabled'])

    def test_filters_search_and_pagination_work_at_native_resolution(self):
        self.render('dex')
        all_ids = {entry['id'] for entry in self.scan.entries()}
        self.assertEqual(all_ids, set(self.app.assets.species))
        self.click('Next')
        self.assertEqual(self.app.scroll, 1)
        self.render('dex')
        self.click('Previous')
        self.assertEqual(self.app.scroll, 0)
        self.click('Ready 100%+')
        self.render('scan')
        self.assertTrue(self.scan.entries())
        self.assertTrue(all(self.app.state['scan'].get(entry['id'], 0) >= 100 for entry in self.scan.entries()))
        self.click('Ready 100%+')
        self.render('scan')
        self.click('All variants  ›')
        self.render('scan')
        self.assertTrue(all(not entry.get('paradox') for entry in self.scan.entries()))
        self.click('Normal  ›')
        self.render('scan')
        self.assertTrue(self.scan.entries())
        self.assertTrue(all(entry.get('paradox') for entry in self.scan.entries()))
        self.scan.filter('variant', 'all')
        self.app.ui.values['search'] = 'agumon'
        self.render('dex')
        self.assertTrue(self.scan.entries())
        self.assertTrue(all('agumon' in entry['name'].lower() for entry in self.scan.entries()))

    def test_gallery_cache_reuses_result_and_refreshes_for_new_server_scan(self):
        self.render('scan')
        first = self.scan.entries()
        self.assertIs(first, self.scan.entries())
        sid = first[-1]['id']
        self.app.state = dict(self.app.state, scan={sid: 200})
        refreshed = self.scan.entries()
        self.assertIsNot(first, refreshed)
        self.assertEqual(refreshed[0]['id'], sid)

    def test_populated_empty_and_filtered_views_keep_all_controls_inside_native_canvas(self):
        for physical in ((1180, 800), (1280, 800), (2048, 1152), (3840, 2160)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(physical), effective_ui_scale(physical))
            self.app.ui.screen = self.app.screen
            for empty in (False, True):
                state = self.app.state
                if empty:
                    self.app.state = dict(state, party=[], storage=[], scan={})
                    self.app.ui.values['search'] = 'no such signature exists'
                for menu in ('lab', 'scan', 'dex'):
                    with self.subTest(size=physical, empty=empty, menu=menu):
                        self.render(menu)
                        bounds = self.app.screen.get_rect()
                        for _, rect, _ in self.controls:
                            self.assertGreater(rect.width, 0)
                            self.assertGreater(rect.height, 0)
                            self.assertTrue(bounds.contains(rect), (menu, rect, bounds))
                        for rect, _ in self.app.ui.actions:
                            self.assertTrue(bounds.contains(rect), (menu, rect, bounds))
                self.app.state = state
                self.app.ui.values['search'] = ''
        self.assertFalse(self.app.assets.errors)
