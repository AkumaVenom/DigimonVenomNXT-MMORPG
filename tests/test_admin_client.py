"""Server-owned notices, read-only titles and private detention presentation."""
import copy
import os
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from venom.client.app import App
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas
from venom.client.world import player_title

ROOT = Path(__file__).resolve().parents[1]


class Connection:
    connected = True

    def __init__(self):
        self.incoming, self.sent = queue.Queue(), []

    def send(self, op, **payload):
        self.sent.append((op, payload))
        return len(self.sent)


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class AdminClientTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(pygame.quit)
        args = SimpleNamespace(demo=True, demo_battle=False, dev=False, config=None,
                               size='1280x800', frames=0, screenshot=None, ui_scale='auto', show_fps=False)
        self.app = App(ROOT, args)
        self.resize((1280, 800))
        self.app.args.demo = False
        self.app.connection = Connection()
        self.app.now = 20
        self.app.state.update(username='CanonicalTamer', titles=['World Champion'], active_title='World Champion')
        self.controls = []
        original = self.app.ui.button
        def button(rect, label, callback, *args, **kwargs):
            self.controls.append((label, pygame.Rect(rect), callback, kwargs))
            return original(rect, label, callback, *args, **kwargs)
        self.enterContext(patch.object(self.app.ui, 'button', side_effect=button))

    def resize(self, size):
        self.app.screen = NativeCanvas(pygame.display.set_mode(size), effective_ui_scale(size, 'auto'))
        self.app.ui.screen = self.app.screen

    def packet(self, data):
        self.app.connection.incoming.put(data)
        self.app.poll()

    def draw(self):
        self.controls.clear()
        self.app.draw()

    def test_notices_arrive_in_private_modes_without_affecting_gameplay(self):
        for mode in ('in_farm', 'in_lab', 'in_season'):
            self.app.state[mode] = True
            before = copy.deepcopy(self.app.state)
            self.packet({'op': 'notice', 'kind': 'broadcast', 'text': 'The Digital World is online.'})
            self.assertEqual(self.app.state, before)
            self.assertEqual(self.app.server_notice['label'], 'SERVER BROADCAST')
            self.assertIn('[SERVER BROADCAST]', self.app.logs[-1][0])
            self.app.state[mode] = False
        self.assertFalse(self.app.connection.sent)

    def test_warning_and_shutdown_are_distinct_and_survive_chat_log_churn(self):
        for kind, label in (('warning', 'STAFF WARNING'), ('shutdown', 'SERVER SHUTDOWN')):
            self.packet({'op': 'notice', 'kind': kind, 'text': 'Please read this message.'})
            self.assertEqual(self.app.server_notice['label'], label)
            self.assertGreater(self.app.server_notice['until'], self.app.now)
        for i in range(150):
            self.packet({'op': 'chat', 'username': 'Tamer', 'text': f'Message {i}'})
        self.app.now += 60
        self.assertEqual(len(self.app.server_notices), 2)
        self.assertEqual(self.app.server_notices[0]['kind'], 'warning')

    def test_chat_cannot_create_a_trusted_banner_or_invoke_console_commands(self):
        self.packet({'op': 'chat', 'username': 'SERVER BROADCAST', 'text': '/giveitem CanonicalTamer hp_s 99'})
        self.assertIsNone(self.app.server_notice)
        self.assertFalse(self.app.server_notices)
        self.app.send('chat', text='/shutdown 10')
        self.assertEqual(self.app.connection.sent, [('chat', {'text': '/shutdown 10'})])
        self.assertTrue(self.app.running)

    def test_malformed_notices_are_ignored_and_controls_removed_from_display_text(self):
        for packet in ({'kind': 'player', 'text': 'Forged'}, {'kind': 'admin', 'text': []},
                       {'kind': 'warning', 'text': '\x00\n\t'}):
            self.packet({'op': 'notice', **packet})
        self.assertFalse(self.app.server_notices)
        self.packet({'op': 'notice', 'kind': 'admin', 'text': 'Hello\nworld\x00'+'Z'*2000})
        self.assertEqual(len(self.app.server_notice['text']), 1000)
        self.assertTrue(self.app.server_notice['text'].isprintable())

    def test_unsolicited_title_state_keeps_canonical_username_and_pending_request(self):
        state = copy.deepcopy(self.app.state)
        state.update(titles=['World Champion', 'Digital Guardian'], active_title='Digital Guardian')
        self.app.action_pending = True
        self.packet({'op': 'result', 'rid': 0, 'ok': True, 'state': state})
        self.assertEqual(self.app.state['username'], 'CanonicalTamer')
        self.assertEqual(self.app.state['titles'], ['World Champion', 'Digital Guardian'])
        self.assertTrue(self.app.action_pending)
        self.assertFalse(self.app.connection.sent)

    def test_title_lines_apply_to_self_and_real_players_but_not_ai_or_partner(self):
        self.packet({'op': 'world', 'scope': [self.app.state['map_id'], 'field', None], 'sequence': 1, 'players': [
            {'username': 'OtherTamer', 'name': 'NotTheAccountName', 'active_title': 'Digital Guardian',
             'map_id': self.app.state['map_id'], 'x': 200, 'y': 300, 'tamer': self.app.tamer},
            {'username': 'BotName', 'name': 'RivalName', 'is_bot': True, 'id': 'bot:1',
             'active_title': 'Should not appear', 'map_id': self.app.state['map_id'], 'x': 300, 'y': 300}]
        })
        actors = self.app.world._actors()
        own = next(a for a in actors if a[6] == 'CanonicalTamer')
        other = next(a for a in actors if a[6] == 'OtherTamer')
        bot = next(a for a in actors if a[-1] == 'bot:1')
        self.assertEqual(own[7], 'World Champion')
        self.assertEqual(other[7], 'Digital Guardian')
        self.assertEqual(bot[7], '')
        self.assertTrue(all(a[7] == '' for a in actors if a[1] == 'digimon'))

    def test_title_is_printable_bounded_and_separate_from_full_username(self):
        self.assertEqual(player_title(None), '')
        self.assertEqual(player_title(' World\n\tChampion '), 'World Champion')
        self.assertEqual(len(player_title('W'*100)), 32)
        for size in ((960, 600), (1280, 800), (1920, 1080)):
            self.resize(size)
            renderer = self.app.world
            view = pygame.Rect(10, 100, 750, 390)
            renderer.camera.configure((1536, 768), self.app.screen.to_physical_rect(view), (768, 384), snap=True)
            with patch('venom.client.world.text') as rendered, patch('venom.client.world.panel') as panels:
                renderer._draw_actor('tamer', (768, 384), self.app.tamer, False, 'down',
                                     'UsernameIsAllTwentyFourXX', title='W'*40)
                calls = rendered.call_args_list
                title_call = next(c for c in calls if c.args[2] == 'W'*32)
                name_call = next(c for c in calls if c.args[2] == 'UsernameIsAllTwentyFourXX')
                self.assertLess(title_call.args[3][1], name_call.args[3][1])
                self.assertNotIn('max_width', name_call.kwargs)
                self.assertTrue(view.contains(panels.call_args.args[1]))

    def test_farm_nameplate_keeps_title_above_the_full_username(self):
        from tools.preview_digifarm import farm_fixture
        farm_fixture(self.app, 2)
        self.app.state.update(username='CanonicalTamer', active_title='World Champion')
        self.app.position.update(836, 470)
        self.app.follower.update(790, 510)
        with patch('venom.client.digifarm.text') as rendered:
            self.draw()
        title = next(c for c in rendered.call_args_list if c.args[2] == 'World Champion')
        name = next(c for c in rendered.call_args_list if c.args[2] == 'YOU · CanonicalTamer')
        self.assertLess(title.args[3][1], name.args[3][1])
        self.assertNotIn('max_width', name.kwargs)

    def test_detention_blocks_gameplay_commands_but_allows_private_chat_and_ping(self):
        self.app.state['admin_jail'] = {'until': None, 'reason': 'Please contact the administrator.'}
        for op in ('move', 'encounter', 'battle', 'travel', 'season', 'digifarm', 'digilab',
                   'community', 'shop', 'evolve', 'materialize'):
            self.app.send(op)
        self.assertFalse(self.app.connection.sent)
        self.app.send('chat', text='Message in my cell')
        self.app.send('ping')
        self.assertEqual([op for op, _ in self.app.connection.sent], ['chat', 'ping'])
        self.app.enter_farm()
        self.app.enter_lab()
        self.app.set_menu('party')
        self.assertIsNone(self.app.menu)
        self.assertFalse(self.app.farm_screen.home_confirmation)

    def test_detention_activity_hotkeys_cannot_open_screens_and_enter_still_chats(self):
        self.app.state['admin_jail'] = {'until': None, 'reason': 'Review'}
        for key in (pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_b, pygame.K_m,
                    pygame.K_p, pygame.K_r, pygame.K_v, pygame.K_o, pygame.K_SPACE, pygame.K_e):
            self.app.key(pygame.event.Event(pygame.KEYDOWN, key=key))
        self.assertFalse(self.app.connection.sent)
        self.assertIsNone(self.app.menu)
        self.app.key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual(self.app.ui.focus, 'chat')

    def test_admin_detention_push_clears_stale_activity_controls(self):
        self.app.menu = 'party'
        self.app.farm_screen.home_confirmation = True
        self.app.farm_screen.manager_open = True
        self.app.partner_screen.pending_exchange = {'anything': True}
        state = copy.deepcopy(self.app.state)
        state.update(admin_jail={'until': None, 'reason': 'Review'}, x=0, y=0)
        self.packet({'op': 'result', 'rid': 0, 'ok': True, 'state': state})
        self.assertIsNone(self.app.menu)
        self.assertIsNone(self.app.partner_screen.pending_exchange)
        self.assertFalse(self.app.farm_screen.home_confirmation)
        self.assertFalse(self.app.farm_screen.manager_open)
        self.assertEqual(self.app.position, pygame.Vector2(0, 0))

    def test_expired_countdown_cannot_release_player_without_server_ack(self):
        self.app.state['admin_jail'] = {'until': 1, 'reason': 'Timed review'}
        before = copy.deepcopy(self.app.state)
        with patch('venom.client.hud.text') as rendered:
            self.draw()
        self.assertIn('Awaiting release from the server', [c.args[2] for c in rendered.call_args_list])
        self.assertEqual(self.app.state, before)
        self.assertFalse(self.app.connection.sent)
        state = copy.deepcopy(self.app.state)
        state.pop('admin_jail')
        self.packet({'op': 'result', 'rid': 0, 'ok': True, 'state': state})
        self.assertFalse(self.app.in_jail())

    def test_notice_archive_and_detention_fit_supported_native_sizes(self):
        self.app.receive_notice({'kind': 'warning', 'text': ('Long warning with details. '*50)[:1000]})
        for size in ((960, 600), (1180, 800), (1920, 1080)):
            self.resize(size)
            self.app.notice_history_open = True
            self.draw()
            self.assertEqual({label for label, _, _, _ in self.controls[-3:]}, {'Close', 'Newer', 'Older'})
            for rect, _ in self.app.ui.actions + self.app.ui.fields:
                self.assertTrue(self.app.screen.get_rect().contains(rect), (size, rect))
            self.app.notice_history_open = False
            self.app.server_notice = None
            self.app.state['admin_jail'] = {'until': None, 'reason': 'Review requested. '*30}
            self.draw()
            activities = ('Home · DigiFarm', 'DigiDex', 'Partners', 'Shop', 'Worlds', 'DigiLab  F1',
                          'Ranked Arena  R', 'Rivals Hub  V', 'Bot Activity  O', 'Season Mode  F3')
            for label, _, _, options in self.controls:
                if label in activities:
                    self.assertTrue(options.get('disabled'), label)
            self.assertIn('chat', [key for _, key in self.app.ui.fields])
            self.assertFalse(self.app.assets.errors, self.app.assets.errors)

    def test_long_unbroken_notice_wraps_within_width(self):
        lines = self.app.hud._lines('Z'*1000, 230, 14)
        font = self.app.assets.font(14)
        self.assertEqual(''.join(lines), 'Z'*1000)
        self.assertTrue(all(font.size(line)[0] <= 230 for line in lines))


if __name__ == '__main__':
    unittest.main()
