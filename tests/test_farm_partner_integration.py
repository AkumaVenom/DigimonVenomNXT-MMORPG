"""Farm hub, resident capacity and authoritative destination UI contracts."""
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
from venom.client.destinations import WorldScreen
from venom.client.laboratory import ScanScreen
from venom.client.partners import PartnerScreen


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class FarmPartnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app('1180x800')
        self.addCleanup(pygame.quit)
        self.app.state.update(in_lab=False, in_farm=True, battle=None)
        self.partner = PartnerScreen(self.app)
        self.scan = ScanScreen(self.app)
        self.world = WorldScreen(self.app)
        self.controls = []
        original = self.app.ui.button

        def capture(rect, label, callback, **options):
            self.controls.append((label, pygame.Rect(rect), options))
            return original(rect, label, callback, **options)

        capture_patch = patch.object(self.app.ui, 'button', side_effect=capture)
        capture_patch.start()
        self.addCleanup(capture_patch.stop)

    def render(self, mode):
        self.app.ui.begin()
        self.controls.clear()
        rect = self.app.screen.get_rect().inflate(-40, -118)
        rect.top = 98
        if mode in PartnerScreen.MODES:
            self.app.menu = 'party'
            self.partner.mode = mode
            self.partner.draw(rect)
        else:
            self.app.menu = mode
            (self.scan if mode == 'scan' else self.world).draw(rect)

    def control(self, label):
        return next((rect, options) for name, rect, options in self.controls if name == label)

    def click(self, label):
        rect, options = self.control(label)
        self.assertFalse(options.get('disabled'), label)
        point = self.app.screen.to_physical_point(rect.center)
        self.assertTrue(self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point)))

    def test_farm_deposit_stops_at_100_without_blocking_withdrawal(self):
        mon = copy.deepcopy(self.app.state['party'][0])
        self.app.state['storage'] = [dict(mon, uid=f'resident-{n}') for n in range(99)]
        with patch.object(self.app, 'send') as send:
            self.render('roster')
            self.click('Move to storage')
            send.assert_called_once_with('party', action='deposit', index=0)
            self.app.state['storage'].append(dict(mon, uid='resident-99'))
            self.render('roster')
            self.assertTrue(self.control('Move to storage')[1]['disabled'])
            self.render('storage')
            self.click('Withdraw')
            send.assert_called_with('party', action='withdraw', index=0)
            self.app.state['battle'] = {'active': [0]}
            self.render('storage')
            self.assertTrue(self.control('Withdraw')[1]['disabled'])

    def test_filtered_resident_opens_correct_uid_and_legacy_partner_remains_accessible(self):
        mon = copy.deepcopy(self.app.state['party'][0])
        self.app.state['storage'] = [dict(mon, uid=f'resident-{n}', name=f'Resident {n:03}') for n in range(102)]
        self.app.state['in_farm'] = False
        self.app.ui.values['bank_search'] = 'Resident 042'
        self.app.farm_screen = SimpleNamespace(select=Mock())
        with patch.object(self.app, 'enter_farm') as enter:
            self.render('storage')
            self.click('Manage & feed')
            enter.assert_called_once_with()
            self.app.farm_screen.select.assert_called_once_with('resident-42')
        self.app.state['in_farm'] = True
        self.app.ui.values['bank_search'] = 'Resident 101'
        with patch.object(self.app, 'send') as send:
            self.render('storage')
            self.assertTrue(self.control('Legacy archive')[1]['disabled'])
            self.click('Withdraw')
            send.assert_called_once_with('party', action='withdraw', index=101)
            self.assertEqual(len(self.app.state['storage']), 102)

    def test_farm_materialization_respects_party_and_resident_capacity(self):
        mon = self.app.state['party'][0]
        self.app.state.update(party=[mon]*6, storage=[mon]*100)
        self.render('scan')
        self.assertTrue(self.control('DigiBank full')[1]['disabled'])
        self.app.state['party'] = [mon]*5
        with patch.object(self.app, 'send') as send:
            self.render('scan')
            self.click('Materialize')
            ready = next(sid for sid, scan in self.app.state['scan'].items() if scan >= 100)
            send.assert_called_once_with('materialize', species_id=ready)

    def test_full_party_exchange_confirms_named_pair_and_keeps_legacy_target_uid(self):
        mon = self.app.state['party'][0]
        self.app.state['party'] = [dict(mon, uid=f'party-{i}', name=f'Party {i}') for i in range(6)]
        self.app.state['storage'] = [dict(mon, uid=f'resident-{i}', name=f'Resident {i:03}') for i in range(103)]
        self.app.selected_party = 2
        self.app.ui.values['bank_search'] = 'Resident 102'
        before = copy.deepcopy(self.app.state)
        with patch.object(self.app, 'send') as send:
            self.render('storage')
            self.assertFalse(self.control('Slot 3: Party 2  ›')[1]['disabled'])
            self.click('Swap into slot 3')
            send.assert_not_called()
            self.render('storage')
            # Changing a highlight cannot replace the named, confirmed pair.
            self.app.selected_party = 5
            self.click('Confirm swap')
            send.assert_called_once_with('party', action='exchange', party_index=2, uid='resident-102')
            self.assertIsNone(self.partner.pending_exchange)
            self.assertEqual(before, self.app.state)

    def test_capacity_full_swap_can_be_cancelled_and_requires_safe_hub(self):
        mon = self.app.state['party'][0]
        self.app.state['party'] = [dict(mon, uid=f'party-{i}') for i in range(6)]
        self.app.state['storage'] = [dict(mon, uid=f'resident-{i}') for i in range(100)]
        with patch.object(self.app, 'send') as send:
            self.render('storage')
            self.click('Swap into slot 1')
            self.render('storage')
            self.click('Cancel')
            self.assertIsNone(self.partner.pending_exchange)
            self.app.state['in_farm'] = False
            self.render('storage')
            self.assertTrue(self.control('Swap into slot 1')[1]['disabled'])
            send.assert_not_called()

    def test_farm_can_travel_to_saved_sector_or_resume_exact_field_position(self):
        before = copy.deepcopy(self.app.state)
        with patch.object(self.app, 'send') as send:
            self.render('maps')
            self.world.transfer(self.app.state['map_id'])
            send.assert_called_once_with('travel', map_id=self.app.state['map_id'])
            self.click('Return to field position')
            send.assert_called_with('digifarm', action='return')
            self.assertEqual(before, self.app.state)
            self.app.action_pending = True
            self.world.transfer(self.app.state['map_id'])
            self.assertEqual(send.call_count, 2)


if __name__ == '__main__':
    unittest.main()
