"""Live WSS integration with the imported ROM maps and the real gameplay engine.

No database daemon is required: temporary SQLite is used only by this test harness.
The listener uses the production TLS helper and the setup-generated certificate chain.
"""
import asyncio
import contextlib
import json
import ssl
import tempfile
import unittest
from pathlib import Path

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from tools.setup import create_certificates
from venom.common.game import GameEngine
from venom.common.paths import root_path
from venom.server.database import Database
from venom.server.main import WorldServer, tls_context


@unittest.skipUnless((root_path() / "data/catalog.json").exists(), "Imported source assets required")
class ImportedGameWSSTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.tmp.name)
        self.ca_path, _ = create_certificates(self.temp_root, "localhost")
        tls = tls_context({"tls_cert": "config/server-cert.pem", "tls_key": "config/server-key.pem"}, self.temp_root)
        self.client_tls = ssl.create_default_context(cafile=str(self.ca_path))
        self.db = Database({"driver": "sqlite", "path": str(self.temp_root / "integration.sqlite3")}, dev=True)
        self.db.initialize()
        self.engine = GameEngine(root_path(), seed=1)
        self.world = WorldServer(self.engine, self.db, {"allow_registration": True})
        self.listener = await serve(self.world.connection, "127.0.0.1", 0, ssl=tls, origins=[None], max_size=65536)
        self.url = f"wss://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}"
        self.world_task = asyncio.create_task(self.world.world_loop())
        self.rid = 0

    async def asyncTearDown(self):
        self.world.stopping = True
        self.listener.close()
        await self.listener.wait_closed()
        self.world_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.world_task
        self.db.close()
        self.tmp.cleanup()

    def connection(self, **kwargs):
        return connect(self.url, ssl=self.client_tls, server_hostname="localhost", max_size=8 * 1024 * 1024, **kwargs)

    async def receive(self, ws, op, rid=None):
        while True:
            payload = json.loads(await asyncio.wait_for(ws.recv(), timeout=4))
            if payload.get("op") == op and (rid is None or payload.get("rid") == rid):
                return payload

    async def request(self, ws, op, **fields):
        # Exercise production anti-spam limits at a normal UI interaction rate.
        if op in {"battle", "digilab", "digifarm", "shop", "encounter", "travel", "materialize", "party"}:
            await asyncio.sleep(0.18)
        self.rid += 1
        await ws.send(json.dumps({"op": op, "rid": self.rid, **fields}))
        return await self.receive(ws, "result", self.rid)

    async def action(self, ws, op, **fields):
        result = await self.request(ws, op, **fields)
        self.assertTrue(result["ok"], result)
        return result.get("state")

    async def test_full_live_tls_world_battle_lab_shop_save_and_relogin(self):
        tamers = list(self.engine.tamers)
        starter = "agumon" if "agumon" in self.engine.starters else self.engine.starters[0]
        async with self.connection() as alice, self.connection() as bob:
            self.assertEqual("Digimon Venom NXT", (await self.receive(alice, "hello"))["game"])
            await self.receive(bob, "hello")
            state = await self.action(alice, "register", username="AliceOne", password="integration-pass-123", tamer=tamers[0], starter=starter)
            await self.action(bob, "register", username="BobTwo", password="integration-pass-456", tamer=tamers[1], starter=starter)
            # v0.6.0 registration starts at the private home. This test exercises
            # the shared field, so both tamers explicitly leave their farms.
            self.assertTrue(state["in_farm"])
            state = await self.action(alice, "digifarm", action="return")
            await self.action(bob, "digifarm", action="return")
            snapshot = await self.receive(alice, "world")
            while len(snapshot["players"]) < 2:
                snapshot = await self.receive(alice, "world")
            self.assertEqual({"AliceOne", "BobTwo"}, {p["username"] for p in snapshot["players"]})
            self.assertTrue(all(p["lead"] == starter for p in snapshot["players"]))
            self.assertNotIn("password", json.dumps(snapshot))

            # Walk against authentic ROM collision, verifying the feet never cross it.
            area = self.engine.maps[state["map_id"]]
            self.assertTrue(area["walkable"])
            x0, y0 = state["x"], state["y"]
            blocked_at = next(n for n in range(1, 400) if not self.world._walkable(area, x0, y0 - n))
            for _ in range(25):
                await asyncio.sleep(0.02)
                movement = await self.request(alice, "move", dx=0, dy=-1, dt=0.1)
                self.assertTrue(movement["ok"], movement)
                self.assertNotIn("state", movement)
                state.update(movement["position"])
                self.assertTrue(self.world._walkable(area, state["x"], state["y"]))
                self.assertGreater(state["y"], y0 - blocked_at)
            self.assertLess(state["y"], y0)
            rejected_move = await self.request(alice, "move", dx=1, dy=0, dt=999)
            self.assertFalse(rejected_move["ok"])

            state = await self.action(alice, "encounter")
            self.assertIsNotNone(state["battle"])
            self.assertLessEqual(len(state["battle"]["enemies"]), 3)
            saw_damage = False
            for _ in range(80):
                if not state["battle"]:
                    break
                actor_index = state["battle"]["actor"]
                actor = state["party"][actor_index]
                target = next(i for i, enemy in enumerate(state["battle"]["enemies"]) if enemy["hp"] > 0)
                if actor["hp"] < 80 and state["inventory"]["hp_s"]:
                    payload = {"action": "item", "item": "hp_s", "party_index": actor_index}
                else:
                    payload = {"action": "skill" if actor["sp"] >= 7 else "attack", "target": target}
                state = await self.action(alice, "battle", **payload)
                saw_damage |= any(e["kind"] == "damage" for e in state["events"])
            self.assertIsNone(state["battle"])
            self.assertEqual(1, state["wins"])
            self.assertTrue(saw_damage)
            self.assertTrue(any(value > 0 for value in state["scan"].values()))
            return_position = (state["map_id"], state["x"], state["y"])

            state = await self.action(alice, "digilab", action="enter")
            self.assertTrue(state["in_lab"])
            self.assertTrue(all(m["hp"] == m["max_hp"] and m["sp"] == m["max_sp"] for m in state["party"]))
            # A lab visitor is absent from Bob's overworld snapshot.
            bob_world = await self.receive(bob, "world")
            for _ in range(100):
                if {p["username"] for p in bob_world["players"]} == {"BobTwo"}:
                    break
                bob_world = await self.receive(bob, "world")
            self.assertEqual({"BobTwo"}, {p["username"] for p in bob_world["players"]})
            await self.action(alice, "digilab", action="heal")
            credits_before, count_before = state["credits"], state["inventory"]["hp_s"]
            for invalid_quantity in (-10, 100000000, True):
                rejected = await self.request(alice, "shop", item="hp_s", quantity=invalid_quantity)
                self.assertFalse(rejected["ok"])
                saved, _ = self.db.load("aliceone")
                self.assertEqual((credits_before, count_before), (saved["credits"], saved["inventory"]["hp_s"]))
            state = await self.action(alice, "shop", item="hp_s", quantity=2)
            self.assertEqual((credits_before - 120, count_before + 2), (state["credits"], state["inventory"]["hp_s"]))
            state = await self.action(alice, "digilab", action="return")
            self.assertFalse(state["in_lab"])
            self.assertEqual(return_position, (state["map_id"], state["x"], state["y"]))
            state = await self.action(alice, "encounter")
            self.assertIsNotNone(state["battle"])
            state = await self.action(alice, "battle", action="flee")
            self.assertIsNone(state["battle"])
            self.assertTrue(any(event["kind"] == "flee" for event in state["events"]))
            expected = {key: state[key] for key in ("party", "scan", "inventory", "credits", "map_id", "x", "y", "wins")}
            await self.request(alice, "logout")
            await alice.wait_closed()
        # Allow connection cleanup to release the database lease before reconnecting.
        for _ in range(100):
            if "aliceone" not in self.world.sessions:
                break
            await asyncio.sleep(0.01)
        async with self.connection() as alice:
            await self.receive(alice, "hello")
            restored = await self.action(alice, "login", username="ALICEONE", password="integration-pass-123")
            self.assertEqual(expected, {key: restored[key] for key in expected})

    async def test_ca_and_hostname_verification_are_required(self):
        # Trust comes from the bundled CA; the operating-system trust store is untouched.
        with self.assertRaises(ssl.SSLCertVerificationError):
            async with connect(self.url, ssl=ssl.create_default_context(), server_hostname="localhost"):
                pass
        with self.assertRaises(ssl.SSLCertVerificationError):
            async with connect(self.url, ssl=self.client_tls, server_hostname="wrong.example"):
                pass
        async with self.connection() as ws:
            self.assertEqual("hello", (await self.receive(ws, "hello"))["op"])


if __name__ == "__main__":
    unittest.main()
