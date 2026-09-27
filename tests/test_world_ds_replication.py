"""World DS replication through real sockets, saves, collision and bot routes.

Only the delayed-frame case injects a send barrier; it still transmits the real
server payload over the real connection and feeds it to the native client.
"""
import asyncio
import copy
import json
import math
import os
from pathlib import Path
import queue
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from venom.common.game import GameEngine
from venom.common.replication import snapshot_matches, world_scope
from venom.server.database import Database
from venom.server.main import WorldServer

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "ds-replication-password-123"


class WorldDSReplicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database({"driver": "sqlite", "path": str(Path(self.tmp.name) / "world.sqlite3")}, dev=True)
        self.db.initialize()
        self.engine = GameEngine(ROOT, seed=823)
        self.world = WorldServer(self.engine, self.db, {"rivals": {"count": 2, "seed": 217}})
        self.listener = await serve(self.world.connection, "127.0.0.1", 0, max_size=65536)
        self.url = f"ws://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}"
        self.rid = 0
        self.pending = {}
        self.entry = self.engine.maps["world_ds_030"]
        self.other = self.engine.maps["world_ds_048"]
        self.large = max((area for area in self.engine.maps.values() if area.get("region_id") == "world_ds"),
                         key=lambda area: area["width"] * area["height"])

    async def asyncTearDown(self):
        self.listener.close()
        await self.listener.wait_closed()
        if self.world.community:
            await asyncio.to_thread(self.world.community.shutdown)
        self.db.close()
        self.tmp.cleanup()

    def client(self):
        return connect(self.url, max_size=8 * 1024 * 1024)

    async def receive(self, ws, op, rid=None):
        def matches(packet):
            return packet.get("op") == op and (rid is None or packet.get("rid") == rid)
        pending = self.pending.setdefault(ws, [])
        for index, packet in enumerate(pending):
            if matches(packet):
                return pending.pop(index)
        while True:
            packet = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if matches(packet):
                return packet
            pending.append(packet)

    async def request(self, ws, op, **fields):
        self.rid += 1
        await ws.send(json.dumps({"op": op, "rid": self.rid, **fields}))
        return await self.receive(ws, "result", self.rid)

    async def action(self, ws, op, **fields):
        packet = await self.request(ws, op, **fields)
        self.assertTrue(packet["ok"], packet)
        return packet

    async def register(self, ws, name):
        await self.receive(ws, "hello")
        await self.action(ws, "register", username=name, password=PASSWORD,
                          tamer=next(iter(self.engine.tamers)), starter=self.engine.starters[0])
        return (await self.action(ws, "travel", map_id=self.entry["id"]))["state"]

    async def snapshot(self, *clients):
        await self.world.broadcast_once()
        return await asyncio.gather(*(self.receive(ws, "world") for ws in clients))

    def humans(self, packet):
        return {row["username"]: row for row in packet["players"] if not row.get("is_bot")}

    async def wait_logout(self, key):
        for _ in range(100):
            if key not in self.world.sessions:
                return
            await asyncio.sleep(.01)
        self.fail("The departed player's lease was not released")

    async def test_two_humans_share_authoritative_movement_and_collision_on_entry_and_largest_map(self):
        async with self.client() as alice, self.client() as bob:
            await self.register(alice, "DSMoveAlice")
            await self.register(bob, "DSMoveBob")
            for area in (self.entry, self.large):
                for ws in (alice, bob):
                    await self.action(ws, "travel", map_id=area["id"])
                first, peer = await self.snapshot(alice, bob)
                self.assertEqual(first, peer)
                self.assertEqual([area["id"], "field", None], first["scope"])
                self.assertEqual({"DSMoveAlice", "DSMoveBob"}, set(self.humans(first)))
                # Choose the nearest real wall from the catalog's real spawn.
                x, y = area["spawn"]
                walls = []
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    for distance in range(1, max(area["width"], area["height"])):
                        px, py = x + dx * distance, y + dy * distance
                        if not (12 <= px <= area["width"] - 12 and 12 <= py <= area["height"] - 12
                                and self.world._walkable(area, px, py)):
                            walls.append((distance, dx, dy))
                            break
                distance, dx, dy = min(walls)
                blocked = False
                previous = (x, y)
                for _ in range(math.ceil(distance / 18) + 2):
                    # Real production time budgets stay active.
                    await asyncio.sleep(.105)
                    response = await self.action(alice, "move", dx=dx, dy=dy, dt=.1,
                                                 x=-99999, y=99999, map_id="forged", space="field")
                    position = response["position"]
                    point = (position["x"], position["y"])
                    self.assertEqual(area["id"], position["map_id"])
                    self.assertLessEqual(math.dist(previous, point), 18.002)
                    self.assertTrue(self.world._walkable(area, *point))
                    blocked |= point == previous
                    previous = point
                    local, remote = await self.snapshot(alice, bob)
                    self.assertEqual(local, remote)
                    row = self.humans(remote)["DSMoveAlice"]
                    self.assertEqual(point, (row["x"], row["y"]))
                self.assertTrue(blocked, f"{area['id']}: walking into supplied collision never stopped")
                self.assertNotEqual((x, y), previous)
                # Another player's diagonal input also remains speed-limited
                # and replicates from the same server-owned state.
                response = await self.action(bob, "move", dx=1, dy=1, dt=.1)
                bp = response["position"]
                local, remote = await self.snapshot(alice, bob)
                self.assertEqual(local, remote)
                row = self.humans(local)["DSMoveBob"]
                self.assertEqual((bp["x"], bp["y"]), (row["x"], row["y"]))
                self.assertLessEqual(math.dist((x, y), (bp["x"], bp["y"])), 18.002)

    async def test_cross_region_travel_departures_and_reconnect_have_no_ghosts(self):
        async with self.client() as alice, self.client() as bob:
            await self.register(alice, "DSRouteAlice")
            await self.register(bob, "DSRouteBob")
            await self.action(alice, "travel", map_id=self.other["id"])
            a, b = await self.snapshot(alice, bob)
            self.assertEqual({"DSRouteAlice"}, set(self.humans(a)))
            self.assertEqual({"DSRouteBob"}, set(self.humans(b)))
            self.assertEqual(self.other["id"], a["scope"][0])
            self.assertEqual(self.entry["id"], b["scope"][0])
            await self.action(bob, "travel", map_id=self.other["id"])
            a, b = await self.snapshot(alice, bob)
            self.assertEqual(a, b)
            self.assertEqual({"DSRouteAlice", "DSRouteBob"}, set(self.humans(a)))
            dawn = next(area for area in self.engine.maps.values() if area["id"].startswith("map_"))
            state = (await self.action(alice, "travel", map_id=dawn["id"]))["state"]
            a, b = await self.snapshot(alice, bob)
            self.assertEqual({"DSRouteAlice"}, set(self.humans(a)))
            self.assertEqual({"DSRouteBob"}, set(self.humans(b)))
            await self.action(alice, "logout")
            await alice.wait_closed()
            await self.wait_logout("dsroutealice")
            (b,) = await self.snapshot(bob)
            self.assertEqual({"DSRouteBob"}, set(self.humans(b)))
            async with self.client() as reconnected:
                await self.receive(reconnected, "hello")
                restored = (await self.action(reconnected, "login", username="DSRouteAlice", password=PASSWORD))["state"]
                self.assertEqual((state["map_id"], state["x"], state["y"]),
                                 (restored["map_id"], restored["x"], restored["y"]))
                a, b = await self.snapshot(reconnected, bob)
                self.assertEqual({"DSRouteAlice"}, set(self.humans(a)))
                self.assertEqual({"DSRouteBob"}, set(self.humans(b)))
                await self.action(reconnected, "travel", map_id=self.other["id"])
                a, b = await self.snapshot(reconnected, bob)
                self.assertEqual(a, b)
                self.assertEqual({"DSRouteAlice", "DSRouteBob"}, set(self.humans(a)))

    async def test_shared_bot_patrol_battle_and_transfer_are_identical_for_both_humans(self):
        await self.world.initialize_community()
        manager = self.world.community.bots
        # Assign ordinary low-level coverage work, then let the real population
        # manager travel, maintain membership and create actual collision paths.
        now = time.monotonic()
        with self.world.community.lock, manager.lock:
            for bot in manager.bots.values():
                bot["runtime"]["coverage_target"] = self.entry["id"]
                manager._relocate(bot, now)
                manager._explore(bot, now)
                self.assertEqual(self.entry["id"], bot["state"]["map_id"])
                self.assertTrue(bot["runtime"]["path"])
        async with self.client() as alice, self.client() as bob:
            await self.register(alice, "DSBotAlice")
            await self.register(bob, "DSBotBob")
            first, peer = await self.snapshot(alice, bob)
            self.assertEqual(first, peer)
            original = {row["id"]: row for row in first["players"] if row.get("is_bot")}
            self.assertEqual(2, len(original))
            await asyncio.sleep(.14)
            later, peer = await self.snapshot(alice, bob)
            self.assertEqual(later, peer)
            elapsed = later["server_time"] - first["server_time"]
            for row in later["players"]:
                if row.get("is_bot"):
                    before = original[row["id"]]
                    distance = math.dist((before["x"], before["y"]), (row["x"], row["y"]))
                    self.assertGreater(distance, 0)
                    self.assertLessEqual(distance, 180 * elapsed + .5)
                    self.assertTrue(self.world._walkable(self.entry, row["x"], row["y"]))
            battle_bot, traveler = list(manager.bots.values())
            with self.world.community.lock, manager.lock:
                now = time.monotonic()
                battle_bot["runtime"]["phase_until"] = now - 1
                manager._explore(battle_bot, now)
                self.assertIsNotNone(battle_bot["state"]["battle"])
                manager._stop(traveler, now)
                traveler["runtime"]["coverage_target"] = self.other["id"]
                manager._relocate(traveler, now)
                manager._explore(traveler, now)
            a, b = await self.snapshot(alice, bob)
            self.assertEqual(a, b)
            bots = {row["id"]: row for row in a["players"] if row.get("is_bot")}
            self.assertEqual({battle_bot["id"]}, set(bots))
            self.assertTrue(bots[battle_bot["id"]]["battle"])
            self.assertEqual((0, 0), (bots[battle_bot["id"]]["dx"], bots[battle_bot["id"]]["dy"]))
            await self.action(alice, "travel", map_id=self.other["id"])
            a, b = await self.snapshot(alice, bob)
            self.assertEqual({traveler["id"]}, {row["id"] for row in a["players"] if row.get("is_bot")})
            self.assertEqual({battle_bot["id"]}, {row["id"] for row in b["players"] if row.get("is_bot")})

    async def test_in_flight_departed_map_frame_is_rejected_by_native_client_after_travel(self):
        from tools.preview_ui_screens import make_app
        import pygame
        app = make_app("960x600")
        self.addCleanup(pygame.quit)
        app.args.demo = False
        app.connection = SimpleNamespace(incoming=queue.Queue())
        app.now = 10.0
        async with self.client() as alice, self.client() as bob:
            app.state = await self.register(alice, "DSDelayAlice")
            await self.register(bob, "DSDelayBob")
            initial, _ = await self.snapshot(alice, bob)
            app.connection.incoming.put(initial)
            app.poll()
            self.assertIn("DSDelayBob", app.players)
            held, release = asyncio.Event(), asyncio.Event()
            original_send = self.world._send_encoded
            held_once = False
            async def delayed_send(ws, encoded, timeout=None):
                nonlocal held_once
                if (ws is self.world.sessions["dsdelayalice"].websocket
                        and json.loads(encoded).get("op") == "world" and not held_once):
                    held_once = True
                    held.set()
                    await release.wait()
                await original_send(ws, encoded, timeout)
            with patch.object(self.world, "_send_encoded", side_effect=delayed_send):
                try:
                    await self.world.broadcast_once()
                    await asyncio.wait_for(held.wait(), 5)
                    await self.receive(bob, "world")
                    result = await self.action(alice, "travel", map_id=self.other["id"])
                    app.requests[result["rid"]] = "travel"
                    app.connection.incoming.put(result)
                    app.poll()
                    self.assertFalse(app.players, "Confirmed travel must clear departed remote actors immediately")
                    self.assertFalse(app.player_render)
                    self.assertFalse(app._remote_motion.samples)
                    await self.world.broadcast_once()
                    await self.receive(bob, "world")
                finally:
                    release.set()
                stale = await self.receive(alice, "world")
                fresh = await self.receive(alice, "world")
                self.assertEqual(self.entry["id"], stale["scope"][0])
                self.assertEqual(self.other["id"], fresh["scope"][0])
                app.connection.incoming.put(stale)
                app.poll()
                self.assertFalse(app.players, "An in-flight frame from the departed map must not repopulate actors")
                app.connection.incoming.put(fresh)
                app.poll()
                self.assertEqual({"DSDelayAlice"}, set(app.players))
                # Same-map stale delivery cannot overwrite a newer sequence.
                late = copy.deepcopy(fresh)
                late["sequence"] -= 1
                late["players"] = stale["players"]
                app.connection.incoming.put(late)
                app.poll()
                self.assertEqual({"DSDelayAlice"}, set(app.players))


class SnapshotScopeTests(unittest.TestCase):
    def test_same_map_activity_boundaries_and_legacy_frames_preserve_privacy(self):
        state = {"username": "DSScope", "map_id": "world_ds_030", "in_lab": False,
                 "in_farm": False, "in_story": False, "in_season": False, "battle": None}
        for flags, space in (({}, "field"), ({"in_lab": True}, "lab"),
                             ({"in_farm": True}, "farm"), ({"in_story": True}, "story"),
                             ({"in_season": True}, "season"), ({"admin_jail": {}}, "jail")):
            current = {**state, **flags}
            expected = [state["map_id"], space, "dsscope" if space in ("farm", "story", "season", "jail") else None]
            self.assertEqual(expected, world_scope(current))
            self.assertTrue(snapshot_matches(current, {"scope": expected}))
            for foreign in ("field", "lab", "farm", "story", "season", "jail"):
                if foreign != space:
                    self.assertFalse(snapshot_matches(current, {"scope": [state["map_id"], foreign, expected[2]]}))
            actor = {**current, "in_jail": space == "jail"}
            actor.pop("admin_jail", None)
            self.assertTrue(snapshot_matches(current, {"players": [actor]}))
            self.assertFalse(snapshot_matches(current, {"players": [{**actor, "username": "Foreign"}]}))

