"""Persistent holding cells, login bans and hostile client escape attempts."""
import asyncio
import copy
import json
import time
import unittest
from unittest.mock import AsyncMock, patch

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from venom.server.database import Database, DatabaseError
from venom.server.main import GAME_OPS, Session, WorldServer
from venom.server.moderation import clear_jail, is_jailed, jail_expired, jail_state


class Engine:
    maps = {"test": {"id": "test", "level": 1, "width": 1000, "height": 1000, "spawn": [60, 70]}}
    def new_player(self, username, tamer=None, starter=None):
        return {"username": username, "tamer": "tamer", "map_id": "test", "x": 180., "y": 190.,
                "credits": 250, "party": [{"species_id": "rookie"}], "events": [], "battle": None,
                "in_farm": True, "in_lab": False, "in_season": False,
                "farm_position": {"x": 33, "y": 44}}
    def handle(self, state, op, payload):
        raise AssertionError("Jailed client reached game engine")


class JailStateTests(unittest.TestCase):
    def test_preserves_season_battle_and_exact_location_across_rejail(self):
        engine = Engine()
        state = engine.new_player("Tester")
        state.update(in_season=True, in_farm=False, battle={"kind": "season", "fixture_id": "year-10001-week-3", "turn": 7})
        state["season"] = {"elapsed_days": 3652500, "champion": "player", "week": 521786}
        before = copy.deepcopy(state)
        jail_state(engine, state, None, "Investigation")
        self.assertTrue(is_jailed(state))
        self.assertIsNone(state["battle"])
        self.assertFalse(state["in_season"])
        self.assertEqual((60., 70.), (state["x"], state["y"]))
        jail_state(engine, state, time.time() + 100, "Updated sentence")
        clear_jail(state)
        self.assertEqual(before, state)

    def test_expiry_uses_real_timestamp_and_preserves_absent_fields(self):
        state = Engine().new_player("Tester")
        state.pop("in_season")
        before = copy.deepcopy(state)
        jail_state(Engine(), state, 100, "Expired sentence")
        self.assertFalse(jail_expired(state, 99))
        self.assertTrue(jail_expired(state, 100))
        clear_jail(state)
        self.assertEqual(before, state)


class ModerationProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
        self.db.initialize()
        self.world = WorldServer(Engine(), self.db)
        self.listener = await serve(self.world.connection, "127.0.0.1", 0)
        self.url = f"ws://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}"
        self.next_rid = 0

    async def asyncTearDown(self):
        self.listener.close()
        await self.listener.wait_closed()
        self.db.close()

    async def request(self, ws, op, **fields):
        self.next_rid += 1
        rid = self.next_rid
        await ws.send(json.dumps({"op": op, "rid": rid, **fields}))
        while True:
            response = json.loads(await asyncio.wait_for(ws.recv(), 2))
            if response.get("op") == "result" and response.get("rid") == rid:
                return response

    async def register(self, ws, username="Tester"):
        await ws.recv()
        result = await self.request(ws, "register", username=username, password="correct-horse-123")
        self.assertTrue(result["ok"], result)
        return self.world.sessions[username.lower()]

    async def test_jail_blocks_all_gameplay_and_private_presence_then_restores(self):
        async with connect(self.url) as ws, connect(self.url) as other_ws:
            session = await self.register(ws)
            other = await self.register(other_ws, "Other")
            original = copy.deepcopy(session.state)
            async with session.lock:
                jail_state(self.world.engine, session.state, None, "Testing cell")
                await self.world.save(session)
            self.assertFalse(self.world.same_place(session, other))
            self.assertEqual("jail", self.world.place(session)[1])
            for op in sorted(GAME_OPS | {"community"}):
                result = await self.request(ws, op, action="history")
                self.assertFalse(result["ok"], (op, result))
                self.assertIn("holding cell", result["error"])
            moved = await self.request(ws, "move", dx=1, dy=0, dt=.1)
            self.assertTrue(moved["ok"])
            self.assertEqual((60., 70.), (session.state["x"], session.state["y"]))
            self.assertTrue((await self.request(ws, "chat", text="Ordinary text"))["ok"])
            command = await self.request(ws, "chat", text="/unjail Tester")
            self.assertFalse(command["ok"])
            self.assertIn("local world-server console", command["error"])
            for op in ("admin", "console", "setmoney"):
                self.assertFalse((await self.request(ws, op, amount=99999))["ok"])
            async with session.lock:
                session.state["admin_jail"]["until"] = time.time() - 1
                await self.world.expire_jail(session)
            self.assertEqual(original, session.state)
            saved, _ = self.db.load("Tester")
            self.assertEqual(original, saved)

    async def test_failed_jail_release_save_rolls_back_live_state(self):
        state = self.world.engine.new_player("Tester")
        jail_state(self.world.engine, state, time.time() - 10, "Expired")
        session = Session(None, "tester", "token", state, 0)
        before = copy.deepcopy(state)
        with patch.object(self.world, "save", AsyncMock(side_effect=DatabaseError("disk full"))):
            with self.assertRaises(DatabaseError):
                await self.world.expire_jail(session, notify=False)
        self.assertEqual(before, session.state)

    async def test_jail_release_is_not_broadcast_before_commit(self):
        for fail in (False, True):
            with self.subTest(save_failure=fail):
                state = self.world.engine.new_player("Tester")
                jail_state(self.world.engine, state, time.time() - 10, "Expired")
                session = Session(None, "tester", "token", state, 0)
                self.world.sessions["tester"] = session
                started, proceed = asyncio.Event(), asyncio.Event()
                async def slow_save(proposed):
                    self.assertIsNot(session, proposed)
                    self.assertFalse(is_jailed(proposed.state))
                    started.set()
                    await proceed.wait()
                    if fail:
                        raise DatabaseError("disk full")
                    proposed.revision = 1
                packets = []
                with patch.object(self.world, "save", slow_save), \
                     patch.object(self.world, "_queue_world", side_effect=lambda s, group, text: packets.append(json.loads(text))):
                    release = asyncio.create_task(self.world.expire_jail(session, notify=False))
                    try:
                        await asyncio.wait_for(started.wait(), 2)
                        self.assertTrue(is_jailed(session.state))
                        self.assertEqual(0, session.revision)
                        await self.world.broadcast_once()
                        self.assertTrue(packets[0]["players"][0]["in_jail"])
                    finally:
                        proceed.set()
                    if fail:
                        with self.assertRaises(DatabaseError):
                            await release
                        self.assertTrue(is_jailed(session.state))
                        self.assertEqual(0, session.revision)
                    else:
                        await release
                        self.assertFalse(is_jailed(session.state))
                        self.assertEqual(1, session.revision)
                self.world.sessions.clear()

    async def test_queued_request_cannot_mutate_after_moderation_marks_closing(self):
        async with connect(self.url) as ws:
            session = await self.register(ws)
            original = copy.deepcopy(session.state)
            await session.lock.acquire()
            pending = asyncio.create_task(self.request(ws, "shop", item="hp_s"))
            try:
                # Give the socket consumer the opportunity to queue behind the
                # same lock used by kick/ban, then mark it before releasing.
                await asyncio.sleep(.02)
                session.closing = True
            finally:
                session.lock.release()
            response = await asyncio.wait_for(pending, 2)
            self.assertFalse(response["ok"])
            self.assertIn("disconnecting", response["error"])
            self.assertEqual(original, session.state)

    async def test_login_releases_expired_jail_without_advancing_season(self):
        state = self.world.engine.new_player("Tester")
        state.update(in_season=True, battle={"kind": "season", "turn": 12})
        before = copy.deepcopy(state)
        jail_state(self.world.engine, state, time.time() - 10, "Expired")
        self.db.register("Tester", "correct-horse-123", state)
        async with connect(self.url) as ws:
            await ws.recv()
            result = await self.request(ws, "login", username="Tester", password="correct-horse-123")
            self.assertTrue(result["ok"], result)
            self.assertEqual(before, result["state"])

    async def test_ban_blocks_login_and_rechecks_before_session_acquisition(self):
        self.db.register("Tester", "correct-horse-123", self.world.engine.new_player("Tester"))
        ban = {"until": None, "reason": "Maintenance ban"}
        with patch.object(self.world.admin_store, "ban_status", side_effect=[None, ban]) as check, \
             patch.object(self.db, "acquire_session", wraps=self.db.acquire_session) as acquire:
            async with connect(self.url) as ws:
                await ws.recv()
                response = await self.request(ws, "login", username="Tester", password="correct-horse-123")
                self.assertFalse(response["ok"])
                self.assertIn("banned", response["error"])
            self.assertEqual(2, check.call_count)
            acquire.assert_not_called()
