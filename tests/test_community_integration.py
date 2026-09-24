"""Exercise rivals and authoritative arena results across actual encrypted sockets."""
import asyncio
import copy
import json
import math
from pathlib import Path
import ssl
import tempfile
import time
import unittest

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from tools.setup import create_certificates
from venom.common.game import GameEngine
from venom.common.paths import root_path
from venom.server.database import Database
from venom.server.main import WorldServer, tls_context


class CommunityWSSTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)
        ca, _ = create_certificates(path, 'localhost')
        tls = tls_context({'tls_cert':'config/server-cert.pem','tls_key':'config/server-key.pem'},path)
        self.client_tls = ssl.create_default_context(cafile=str(ca))
        self.db = Database({'driver':'sqlite','path':str(path/'community.sqlite3')},dev=True)
        self.db.initialize()
        self.engine = GameEngine(root_path(),seed=7)
        self.world = WorldServer(self.engine,self.db,{'rivals':{'count':8}})
        await self.world.initialize_community()
        self.listener = await serve(self.world.connection,'127.0.0.1',0,ssl=tls,max_size=65536)
        self.url = f'wss://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}'
        self.rid = 0

    async def asyncTearDown(self):
        self.world.stopping = True
        self.listener.close()
        await self.listener.wait_closed()
        await asyncio.to_thread(self.world.community.shutdown)
        self.db.close()
        self.temp.cleanup()

    def client(self):
        return connect(self.url,ssl=self.client_tls,server_hostname='localhost',max_size=8*1024*1024)

    async def receive(self, ws, op, rid=None):
        while True:
            message = json.loads(await asyncio.wait_for(ws.recv(),5))
            if message.get('op')==op and (rid is None or message.get('rid')==rid):
                return message

    async def request(self, ws, op='community', **fields):
        self.rid += 1
        await ws.send(json.dumps({'op':op,'rid':self.rid,**fields}))
        return await self.receive(ws,'result',self.rid)

    async def register(self, ws, name):
        hello = await self.receive(ws,'hello')
        self.assertIn('rivals',hello['features'])
        result = await self.request(ws,'register',username=name,password='rival-test-pass-123',
                                    tamer=next(iter(self.engine.tamers)),starter=self.engine.starters[0])
        self.assertTrue(result['ok'],result)
        # Community motion and local invitations are field scenarios.
        result = await self.request(ws, 'digifarm', action='return')
        self.assertTrue(result['ok'], result)
        return result['state']

    async def test_same_world_snapshot_for_two_players_and_actual_rival_motion(self):
        async with self.client() as alice, self.client() as bob:
            state = await self.register(alice,'RivalAlice')
            await self.register(bob,'RivalBob')
            now = time.monotonic()
            await asyncio.to_thread(self.world.community.step,now,.1)
            await self.world.broadcast_once()
            first = await self.receive(alice,'world')
            peer = await self.receive(bob,'world')
            self.assertEqual(first,peer,'Both players receive the exact same authoritative map snapshot')
            bots = [row for row in first['players'] if row.get('is_bot')]
            self.assertTrue(bots)
            self.assertLess(len(bots),8,'Rivals from other sectors are excluded')
            await asyncio.sleep(.15)
            await self.world.broadcast_once()
            later = await self.receive(alice,'world')
            for row in later['players']:
                if row.get('is_bot') and row['id']==bots[0]['id']:
                    elapsed = later['server_time']-first['server_time']
                    distance = math.dist((row['x'],row['y']),(bots[0]['x'],bots[0]['y']))
                    self.assertGreater(distance,0)
                    self.assertLessEqual(distance,180*elapsed+.5)
                    self.assertTrue(self.world._walkable(self.engine.maps[state['map_id']],row['x'],row['y']))
            profile = await self.request(alice,action='profile',bot_id=bots[0]['id'])
            self.assertTrue(profile['ok'],profile)
            self.assertEqual(bots[0]['id'],profile['community']['data']['id'])
            self.assertNotIn('runtime',profile['community']['data'])

    async def test_authoritative_ranked_outcome_ladders_history_and_unauthorized_payloads(self):
        async with self.client() as player:
            original = await self.register(player,'ArenaHuman')
            overview = await self.request(player,action='ranked')
            self.assertTrue(overview['ok'],overview)
            opponent = overview['community']['data']['opponents'][0]['id']
            battle = await self.request(player,action='match',opponent_id=opponent,
                                        winner_id='player:arenahuman',digirubies=999999)
            self.assertTrue(battle['ok'],battle)
            result = battle['community']['data']
            self.assertTrue(result['replay']['events'])
            self.assertEqual(0,self.world.community.ranked.overview('player:arenahuman')['own']['digirubies'])
            self.assertEqual(original['party'],self.world.sessions['arenahuman'].state['party'])
            profile = self.world.community.bots.profile(opponent)
            self.assertEqual(1,profile['stats']['ranked_wins']+profile['stats']['ranked_losses'])
            self.assertEqual(0,profile['stats']['rival_wins']+profile['stats']['rival_losses'])
            ladder = await self.request(player,action='ladder',scope='current')
            self.assertEqual(2,ladder['community']['data']['total'])
            hub = await self.request(player,action='rivals')
            self.assertEqual(1,len(hub['community']['data']['history']))
            self.assertEqual(8,hub['community']['data']['total'])
            bad = await self.request(player,action='accept',challenge_id='made-up')
            self.assertFalse(bad['ok'])
            activity = await self.request(player,action='activity')
            self.assertEqual(8,activity['community']['data']['population'])
            self.assertLessEqual(len(activity['community']['data']['events']),100)

    async def test_friendly_challenge_is_local_and_cannot_be_accepted_by_another_player(self):
        async with self.client() as alice, self.client() as bob:
            state = await self.register(alice,'ChallengeAlice')
            await self.register(bob,'ChallengeBob')
            hub = await self.request(alice,action='rivals')
            nearby = hub['community']['data']['nearby'][0]
            # Place the tester beside the actual rival: admission uses server state.
            session = self.world.sessions['challengealice']
            session.state.update(x=nearby['x'],y=nearby['y'])
            community = self.world.community
            community.next_invite['player:challengealice'] = 0
            with community.lock:
                community._offer(session.state,time.monotonic())
                challenges = community._pending('player:challengealice')
            self.assertTrue(challenges)
            ident = challenges[0]['id']
            denied = await self.request(bob,action='accept',challenge_id=ident)
            self.assertFalse(denied['ok'])
            accepted = await self.request(alice,action='accept',challenge_id=ident)
            self.assertTrue(accepted['ok'],accepted)
            self.assertFalse(accepted['community']['data']['ranked'])
            own = community.ranked.overview('player:challengealice')['own']
            self.assertEqual(0,own['career_wins']+own['career_losses'])
            history = community.store.rival_history('player:challengealice')
            self.assertEqual(1,history[0]['wins']+history[0]['losses'])
            # A completed invitation cannot award a second result even if replayed.
            replay = await self.request(alice,action='accept',challenge_id=ident)
            self.assertTrue(replay['ok'],replay)
            self.assertTrue(replay['community']['data']['duplicate'])
            self.assertEqual(1,sum(x['wins']+x['losses'] for x in community.store.rival_history('player:challengealice')))
