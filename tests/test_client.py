"""Native UI smoke checks plus a real TLS round-trip through the threaded transport."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import asyncio
import contextlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import pygame
from websockets.asyncio.server import serve
from tools.setup import create_certificates
from venom.common.game import GameEngine
from venom.common.paths import root_path
from venom.client.app import App
from venom.server.database import Database
from venom.server.main import WorldServer, tls_context


def args(**values):
    defaults = dict(dev=False, demo=True, demo_battle=False, config=None, frames=0, screenshot=None)
    defaults.update(values)
    return SimpleNamespace(**defaults)


@unittest.skipUnless((root_path()/'data/catalog.json').exists(), 'Imported game assets required')
class NativeViewsTests(unittest.TestCase):
    def setUp(self):
        self.app = App(root_path(),args())
        self.engine = GameEngine(root_path(),seed=8)
        self.app.state = self.engine.new_player('NativeTest',next(iter(self.engine.tamers)),self.engine.starters[0])
        self.engine.handle(self.app.state, 'digifarm', {'action': 'return'})
        self.app.position.update(self.app.state['x'],self.app.state['y'])

    def tearDown(self):
        pygame.quit()

    def test_every_gameplay_view_renders_real_assets_and_battle_effects(self):
        for menu in (None,'dex','party','shop','maps','lab'):
            self.app.menu = menu
            self.app.draw()
            self.assertTrue(self.app.ui.actions)
        self.engine.handle(self.app.state,'encounter',{})
        self.app.menu = None
        self.app.draw()
        self.app.animations=[{'kind':'damage','side':'enemy','index':0,'amount':37,'effectiveness':3,'start':self.app.now-.25,'duration':1.05}]
        self.app.draw()
        for menu in ('skills','battle_items'):
            self.app.menu=menu
            self.app.draw()
        self.assertFalse(self.app.assets.errors, self.app.assets.errors)

    def test_picker_excludes_clicks_on_covered_account_form_and_menu_covers_battle(self):
        self.app.state=None
        self.app.auth_tab='register'
        self.app.auth_picker='tamer'
        self.app.draw()
        self.assertEqual([key for _,key in self.app.ui.fields],['search'])
        self.app.auth_picker='starter'
        self.app.draw()
        self.assertEqual([key for _,key in self.app.ui.fields],['search'])


@unittest.skipUnless((root_path()/'data/catalog.json').exists(), 'Imported game assets required')
class NativeTLSClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.temp_root=Path(self.temp.name)
        ca,_=create_certificates(self.temp_root,'localhost')
        context=tls_context({'tls_cert':'config/server-cert.pem','tls_key':'config/server-key.pem'},self.temp_root)
        self.db=Database({'driver':'sqlite','path':str(self.temp_root/'client.sqlite3')},dev=True)
        self.db.initialize()
        self.engine=GameEngine(root_path(),seed=2)
        self.world=WorldServer(self.engine,self.db,{'allow_registration':True})
        self.listener=await serve(self.world.connection,'127.0.0.1',0,ssl=context,max_size=65536)
        self.port=self.listener.sockets[0].getsockname()[1]
        self.config=self.temp_root/'client.json'
        self.config.write_text(json.dumps({'host':'127.0.0.1','port':self.port,'server_name':'localhost','ca_file':str(ca),'tls':True}))
        self.app=App(root_path(),args(demo=False,config=str(self.config)))

    async def asyncTearDown(self):
        self.app.connection.close()
        await asyncio.sleep(.05)
        self.listener.close()
        await self.listener.wait_closed()
        self.db.close()
        pygame.quit()
        self.temp.cleanup()

    async def until(self,predicate):
        for _ in range(300):
            self.app.poll()
            if predicate(): return
            await asyncio.sleep(.01)
        self.fail(f'Client request timed out: {self.app.status}')

    async def test_native_registration_world_position_lab_and_encrypted_gameplay(self):
        await self.until(lambda:self.app.connection.connected)
        self.app.auth_tab='register'
        self.app.ui.values.update(username='NativeAlice',password='native-test-pass-123')
        self.app.auth()
        await self.until(lambda:self.app.state is not None)
        self.assertEqual(self.app.state['username'],'NativeAlice')
        self.assertEqual(len(self.app.state['party']),1)
        self.assertTrue(self.app.state['in_farm'])
        self.app.draw()
        self.app.send('digifarm', action='return')
        await self.until(lambda:not self.app.state.get('in_farm'))
        saved_party=self.app.state['party']
        self.app.send('move',dx=0,dy=0,dt=.05)
        await self.until(lambda:not self.app.requests)
        self.assertIs(self.app.state['party'],saved_party,'Compact position acknowledgement must preserve roster state')
        await asyncio.sleep(.2)
        self.app.enter_lab()
        await self.until(lambda:self.app.state.get('in_lab'))
        self.app.draw()
        self.assertEqual(self.app.menu,'lab')
        await asyncio.sleep(.2)
        self.app.send('digilab',action='return')
        await self.until(lambda:not self.app.state.get('in_lab'))
        self.assertIsNone(self.app.menu)
        await asyncio.sleep(.2)
        self.app.send('encounter')
        await self.until(lambda:self.app.state.get('battle'))
        self.app.draw()
        self.assertTrue(self.app.state['battle']['enemies'])
