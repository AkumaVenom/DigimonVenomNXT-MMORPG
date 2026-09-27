"""Private Story acceptance over real WebSockets, SQLite and native gameplay.

The story uses the owned MMO team, bag and credits; only the adventure's location,
NPC progress and championship are private. No client can supply an outcome.
"""
import asyncio
import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from venom.common.game import GameEngine
from venom.server.admin_commands import AdminConsole
from venom.server.database import Database, DatabaseError
from venom.server.main import GAME_OPS, WorldServer
from venom.server.moderation import clear_jail, jail_state

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "story-protocol-password-123"


class StoryProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.tmp.name) / "story.sqlite3")
        self.rid = 0
        self.buffer = {}
        await self.start_server()

    async def start_server(self):
        self.db = Database({"driver": "sqlite", "path": self.database_path}, dev=True)
        self.db.initialize()
        self.engine = GameEngine(ROOT, seed=971)
        self.world = WorldServer(self.engine, self.db, {
            "allow_registration": True, "rivals": {"enabled": False, "count": 0}})
        self.console = AdminConsole(self.world)
        self.listener = await serve(self.world.connection, "127.0.0.1", 0, max_size=65536)
        self.url = f"ws://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}"

    async def stop_server(self):
        await self.console.close()
        self.listener.close()
        await self.listener.wait_closed()
        if self.world.community:
            await asyncio.to_thread(self.world.community.shutdown)
        self.db.close()

    async def asyncTearDown(self):
        await self.stop_server()
        self.tmp.cleanup()

    def connection(self):
        return connect(self.url, max_size=8 * 1024 * 1024)

    async def receive(self, ws, op, rid=None):
        def matches(packet):
            return packet.get("op") == op and (rid is None or packet.get("rid") == rid)
        pending = self.buffer.setdefault(ws, [])
        for index, packet in enumerate(pending):
            if matches(packet):
                return pending.pop(index)
        while True:
            packet = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if matches(packet):
                return packet
            pending.append(packet)

    async def request(self, ws, op, **fields):
        # Real production limits remain active. Never accept a rate-limit error
        # as evidence that a forged progression payload was correctly rejected.
        if op in GAME_OPS:
            await asyncio.sleep(.175)
        self.rid += 1
        await ws.send(json.dumps({"op": op, "rid": self.rid, **fields}))
        return await self.receive(ws, "result", self.rid)

    async def action(self, ws, op, **fields):
        response = await self.request(ws, op, **fields)
        self.assertTrue(response["ok"], response)
        return response.get("state")

    async def register(self, ws, username):
        hello = await self.receive(ws, "hello")
        self.assertIn("story", hello["features"])
        return await self.action(ws, "register", username=username, password=PASSWORD,
                                 tamer=next(iter(self.engine.tamers)), starter=self.engine.starters[0])

    async def enter(self, ws, username):
        original = await self.register(ws, username)
        state = await self.action(ws, "story", action="enter")
        self.assertTrue(state["in_story"])
        self.assertEqual([], state["story"]["badges"])
        return original, state

    async def rejected(self, ws, key, op, **fields):
        before = self.db.load(key)
        response = await self.request(ws, op, **fields)
        self.assertFalse(response["ok"], response)
        self.assertNotIn("between actions", response.get("error", ""))
        self.assertEqual(before, self.db.load(key))
        return response

    async def wait_for_logout(self, key):
        for _ in range(100):
            if key not in self.world.sessions:
                return
            await asyncio.sleep(.01)
        self.fail("Disconnected player's session lease was not released")

    @staticmethod
    def battle_fields(state, action="guard", **fields):
        battle = state["battle"]
        return {"action": action, "battle_id": battle["id"], "expected_turn": battle["turn"], **fields}

    async def test_owned_team_native_hubs_and_wallet_continue_across_story_return(self):
        async with self.connection() as ws:
            original = await self.register(ws, "SharedHero")
            self.assertFalse((await self.console.execute("/setlevel SharedHero party:1 20")).startswith("ERROR:"))
            owned = copy.deepcopy(self.world.sessions["sharedhero"].state["party"])
            state = await self.action(ws, "story", action="enter")
            self.assertEqual(owned, state["party"])
            self.assertEqual(original["credits"], state["credits"])
            self.assertEqual(original["inventory"], state["inventory"])
            self.assertFalse(any(k in state["story_return_state"] for k in ("party", "inventory", "credits", "scan", "storage")))
            state = await self.action(ws, "digilab", action="enter")
            self.assertTrue(state["in_lab"])
            self.assertTrue(state["in_story"])
            before = state["credits"]
            count = state["inventory"]["hp_s"]
            state = await self.action(ws, "shop", item="hp_s", quantity=1)
            self.assertLess(state["credits"], before)
            self.assertEqual(count + 1, state["inventory"]["hp_s"])
            spent = state["credits"]
            state = await self.action(ws, "digilab", action="return")
            state = await self.action(ws, "digifarm", action="enter")
            self.assertTrue(state["in_farm"])
            self.assertTrue(state["in_story"])
            state = await self.action(ws, "digifarm", action="return")
            story = copy.deepcopy(state["story"])
            state = await self.action(ws, "story", action="return")
            self.assertFalse(state["in_story"])
            self.assertEqual(original["map_id"], state["map_id"])
            self.assertEqual(original["in_farm"], state["in_farm"])
            self.assertEqual(spent, state["credits"])
            self.assertEqual(count + 1, state["inventory"]["hp_s"])
            self.assertEqual(owned[0]["uid"], state["party"][0]["uid"])
            self.assertEqual(20, state["party"][0]["level"])
            resumed = await self.action(ws, "story", action="enter")
            self.assertEqual(story["badges"], resumed["story"]["badges"])
            self.assertEqual(spent, resumed["credits"])

    async def test_private_world_chat_collision_movement_and_forged_progress(self):
        async with self.connection() as alice, self.connection() as bob:
            _, state = await self.enter(alice, "StoryAlice")
            await self.enter(bob, "StoryBob")
            a, b = self.world.sessions["storyalice"], self.world.sessions["storybob"]
            self.assertFalse(self.world.same_place(a, b))
            self.assertEqual((state["map_id"], "story", "storyalice"), self.world.place(a))
            await self.world.broadcast_once()
            for ws, name in ((alice, "StoryAlice"), (bob, "StoryBob")):
                packet = await self.receive(ws, "world")
                self.assertEqual([name], [actor["username"] for actor in packet["players"]])
                self.assertTrue(packet["players"][0]["in_story"])
            self.assertTrue((await self.request(alice, "chat", text="Private Story text"))["ok"])
            own_chat = await self.receive(alice, "chat")
            self.assertEqual("StoryAlice", own_chat["username"])
            await self.request(bob, "ping")
            self.assertFalse(any(packet.get("op") == "chat" for packet in self.buffer.get(bob, [])))
            a.walked = a.next_encounter + 1000
            moved = False
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                a.move_credit = .1
                position_before = (a.state["x"], a.state["y"])
                response = await self.request(alice, "move", dx=dx, dy=dy, dt=.1)
                moved |= position_before != (a.state["x"], a.state["y"])
                self.assertTrue(response["ok"], response)
                self.assertIsNone(a.state["battle"])
                self.assertTrue(self.world._walkable(self.engine.maps[a.state["map_id"]], a.state["x"], a.state["y"]))
                self.assertEqual(0, a.walked)
            self.assertTrue(moved, "Private Story must preserve ordinary map walking")
            before_bob = self.db.load("storybob")
            for op, fields in (
                ("community", {"action": "overview"}),
                ("season", {"action": "history"}),
                ("season", {"action": "enter"}),
                ("encounter", {}),
                ("travel", {"map_id": state["map_id"]}),
                ("story", {"action": "travel", "chapter": 8}),
                ("story", {"action": "complete", "badges": list(range(8)), "winner": "player", "reward": 999999,
                           "username": "StoryBob"}),
                ("story", {"action": "challenge", "npc_id": "forged", "token": "forged"}),
            ):
                await self.rejected(alice, "storyalice", op, **fields)
            self.assertEqual(before_bob, self.db.load("storybob"))
            self.assertEqual([], a.state["story"]["badges"])
            blocked = await self.console.execute("/givemoney StoryAlice 100")
            self.assertTrue(blocked.startswith("ERROR:"), blocked)

    async def test_restart_restores_manual_training_turn_and_shared_owned_party(self):
        async with self.connection() as ws:
            _, state = await self.enter(ws, "StoryResume")
            await self.request(ws, "move", dx=1, dy=0, dt=.1)
            state = await self.action(ws, "story", action="train")
            self.assertEqual("story", state["battle"]["kind"])
            self.assertIsInstance(state["battle"]["actor"], int)
            expected = {key: copy.deepcopy(state[key]) for key in
                        ("party", "inventory", "credits", "battle", "story", "story_return_state", "in_story", "map_id", "x", "y", "in_lab", "in_farm")}
            await self.world.broadcast_once()
            await self.request(ws, "ping")
            self.assertEqual(expected["battle"], self.world.sessions["storyresume"].state["battle"])
            await self.rejected(ws, "storyresume", "battle", action="attack", target=0,
                                battle_id="foreign", expected_turn=0)
            await self.rejected(ws, "storyresume", "story", action="return")
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout("storyresume")
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            with patch("venom.server.main.time.time", return_value=time.time() + 3 * 365 * 86400):
                restored = await self.action(ws, "login", username="STORYRESUME", password=PASSWORD)
            self.assertEqual(expected, {key: restored[key] for key in expected})
            command = self.battle_fields(restored, "guard")
            changed = await self.action(ws, "battle", **command)
            self.assertTrue(any(event.get("kind") in ("guard", "damage", "message") for event in changed["events"]))
            await self.rejected(ws, "storyresume", "battle", **command)

    async def test_story_jail_roundtrip_and_legacy_v080_cell_release(self):
        async with self.connection() as ws:
            _, state = await self.enter(ws, "StoryJail")
            state = await self.action(ws, "story", action="train")
            expected = {key: copy.deepcopy(state[key]) for key in
                        ("party", "inventory", "credits", "battle", "story", "story_return_state", "in_story", "map_id", "x", "y")}
            result = await self.console.execute("/jail StoryJail permanent Inspection")
            self.assertFalse(result.startswith("ERROR:"), result)
            session = self.world.sessions["storyjail"]
            self.assertFalse(session.state["in_story"])
            self.assertFalse(self.world.shared_profile(session.state))
            self.assertEqual("jail", self.world.place(session)[1])
            await self.rejected(ws, "storyjail", "story", action="return")
            self.assertFalse((await self.console.execute("/unjail StoryJail")).startswith("ERROR:"))
            self.assertEqual(expected, {key: session.state[key] for key in expected})
            self.assertFalse(self.world.shared_profile(session.state))
        legacy = self.engine.new_player("LegacyCell", next(iter(self.engine.tamers)), self.engine.starters[0])
        legacy.pop("in_story", None)
        legacy["events"] = []
        original = copy.deepcopy(legacy)
        jail_state(self.engine, legacy, None, "Pre-upgrade holding cell")
        legacy["admin_jail"]["suspended"].pop("in_story", None)
        clear_jail(legacy)
        self.assertEqual(original, legacy)

    async def test_story_never_publishes_shared_competitor_profile(self):
        await self.world.initialize_community()
        community = self.world.community
        async with self.connection() as ws:
            await self.register(ws, "RankedIsolation")
            with patch.object(community, "register_player", wraps=community.register_player) as publish:
                await self.action(ws, "story", action="enter")
                self.assertFalse(self.world.shared_profile(self.world.sessions["rankedisolation"].state))
                await self.console.execute('/addtitle "Story Explorer"')
                await self.console.execute('/settitle RankedIsolation "Story Explorer"')
                publish.assert_not_called()
                await self.action(ws, "logout")
                await ws.wait_closed()
                await self.wait_for_logout("rankedisolation")
                publish.assert_not_called()
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            with patch.object(community, "register_player", wraps=community.register_player) as publish:
                restored = await self.action(ws, "login", username="RankedIsolation", password=PASSWORD)
                self.assertTrue(restored["in_story"])
                publish.assert_not_called()
                await self.action(ws, "story", action="return")
                self.assertTrue(self.world.shared_profile(self.world.sessions["rankedisolation"].state))

    async def test_failed_return_is_never_published_to_shared_world(self):
        async with self.connection() as ws:
            await self.enter(ws, "StoryCommit")
            session = self.world.sessions["storycommit"]
            original = copy.deepcopy(session.state)
            entered, release = asyncio.Event(), asyncio.Event()
            real_save = self.world.save
            async def delayed_save(proposed):
                if proposed is not session and not proposed.state.get("in_story"):
                    entered.set()
                    await release.wait()
                    raise DatabaseError("Injected unavailable save")
                return await real_save(proposed)
            with patch.object(self.world, "save", delayed_save):
                pending = asyncio.create_task(self.request(ws, "story", action="return"))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    self.assertEqual(original, session.state)
                    self.assertEqual("story", self.world.place(session)[1])
                    packets = []
                    with patch.object(self.world, "_queue_world", side_effect=lambda _session, _place, encoded:
                                      packets.append(json.loads(encoded))):
                        await self.world.broadcast_once()
                    self.assertTrue(packets[0]["players"][0]["in_story"])
                finally:
                    release.set()
                rejected = await pending
                self.assertFalse(rejected["ok"])
            self.assertEqual(original, session.state)
            await ws.wait_closed()


if __name__ == "__main__":
    unittest.main()
