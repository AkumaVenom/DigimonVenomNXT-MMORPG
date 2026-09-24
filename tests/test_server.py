"""Persistence, concurrency, movement and real WebSocket protocol regression tests."""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path

from venom.server.database import AccountExists, Database, DatabaseError, verify_password


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
        self.db.initialize()
        self.state = {"username": "Tester", "party": [], "credits": 250, "events": []}

    def tearDown(self):
        self.db.close()

    def test_password_and_case_insensitive_unique_account(self):
        self.db.register("Tester", "correct-horse-123", self.state)
        self.assertEqual("tester", self.db.authenticate("TESTER", "correct-horse-123"))
        self.assertIsNone(self.db.authenticate("Tester", "wrong-password"))
        self.assertIsNone(self.db.authenticate("Unknown", "correct-horse-123"))
        with self.assertRaises(AccountExists):
            self.db.register("tester", "correct-horse-123", self.state)
        stored = self.db.connection.execute("SELECT password_hash FROM venom_accounts").fetchone()[0]
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertNotIn("correct-horse", stored)
        self.assertTrue(verify_password("correct-horse-123", stored))

    def test_revision_guard_and_transaction_rollback(self):
        self.db.register("Tester", "correct-horse-123", self.state)
        state, revision = self.db.load("tester")
        state["credits"] = 400
        revision = self.db.save("tester", state, revision)
        state["credits"] = 900
        with self.assertRaises(DatabaseError):
            self.db.save("tester", state, 0)
        saved, saved_revision = self.db.load("tester")
        self.assertEqual((400, 1), (saved["credits"], saved_revision))
        self.assertEqual(1, revision)

    def test_account_lease_blocks_second_world_and_wrong_owner_save(self):
        self.db.register("Tester", "correct-horse-123", self.state)
        self.assertTrue(self.db.acquire_session("tester", "world-one"))
        self.assertFalse(self.db.acquire_session("tester", "world-two"))
        with self.assertRaises(DatabaseError):
            self.db.save("tester", self.state, 0, "world-two")
        self.assertEqual(1, self.db.save("tester", self.state, 0, "world-one"))
        self.db.release_session("tester", "world-two")
        self.assertFalse(self.db.acquire_session("tester", "world-two"))
        self.db.release_session("tester", "world-one")
        self.assertTrue(self.db.acquire_session("tester", "world-two"))

    def test_sqlite_requires_explicit_development_and_schema_is_checked(self):
        with self.assertRaises(DatabaseError):
            Database({"driver": "sqlite", "path": ":memory:"})
        self.db.connection.execute("UPDATE venom_schema SET version=999")
        self.db.connection.commit()
        with self.assertRaises(DatabaseError):
            self.db.initialize()


class ProtocolEngine:
    """Deterministic gameplay seam; tests exercise the actual server/database stack."""
    def __init__(self):
        self.maps = {"test": {"id": "test", "width": 1000, "height": 1000, "walkable": None}}

    def new_player(self, username, tamer, starter):
        if tamer != "tamer" or starter != "rookie":
            raise ValueError("Invalid starter or tamer.")
        return {"username": username, "tamer": tamer, "map_id": "test", "x": 100.0, "y": 100.0,
                "credits": 250, "party": [{"species_id": "rookie"}], "events": [], "battle": None, "in_lab": False}

    def handle(self, state, op, payload):
        if op == "shop":
            state["credits"] -= 25
            if payload.get("item") == "invalid":
                raise ValueError("Invalid item.")
        elif op == "encounter":
            state["battle"] = {"enemies": [{"name": "Enemy"}]}
        return state


class ServerMovementTests(unittest.TestCase):
    def setUp(self):
        from venom.server.main import Session, WorldServer
        self.engine = ProtocolEngine()
        self.world = WorldServer(self.engine, None, {})
        self.session = Session(None, "tester", "token", self.engine.new_player("Tester", "tamer", "rookie"), 0)

    def test_client_cannot_speed_up_with_many_movement_packets(self):
        start = time.monotonic()
        for _ in range(1000):
            self.world.move(self.session, {"dx": 1, "dy": 0, "dt": 0.1})
        elapsed = time.monotonic() - start
        self.assertLessEqual(self.session.state["x"] - 100, 180 * (elapsed + 0.1) + 1.1)
        for dt in (1, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.world.move(self.session, {"dx": 1, "dy": 0, "dt": dt})

    def test_collision_does_not_tunnel_through_one_pixel_wall(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            mask = Image.new("L", (1000, 1000), 255)
            for y in range(1000):
                mask.putpixel((110, y), 0)
            mask.save(Path(tmp) / "mask.png")
            self.world.root = Path(tmp)
            self.engine.maps["test"]["walkable"] = "mask.png"
            self.world.move(self.session, {"dx": 1, "dy": 0, "dt": 0.1})
            self.assertLess(self.session.state["x"], 110)
            self.assertGreater(self.session.state["x"], 100)

    def test_battle_and_lab_prevent_world_movement(self):
        for flag, value in (("battle", {"enemies": []}), ("in_lab", True)):
            self.session.state[flag] = value
            self.world.move(self.session, {"dx": 1, "dy": 0, "dt": 0.1})
            self.assertEqual(100, self.session.state["x"])
            self.session.state[flag] = None if flag == "battle" else False


class NetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from venom.server.main import WorldServer
        from websockets.asyncio.server import serve
        self.db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
        self.db.initialize()
        self.world = WorldServer(ProtocolEngine(), self.db, {})
        self.listener = await serve(self.world.connection, "127.0.0.1", 0, max_size=65536)
        self.url = f"ws://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}"

    async def asyncTearDown(self):
        self.listener.close()
        await self.listener.wait_closed()
        self.db.close()

    async def request(self, ws, rid, op, **fields):
        await ws.send(json.dumps({"op": op, "rid": rid, **fields}))
        while True:
            response = json.loads(await asyncio.wait_for(ws.recv(), 3))
            if response.get("op") == "result" and response["rid"] == rid:
                return response

    async def test_register_save_duplicate_session_chat_and_login(self):
        from websockets.asyncio.client import connect
        async with connect(self.url) as first, connect(self.url) as second:
            self.assertEqual("hello", json.loads(await first.recv())["op"])
            await second.recv()
            r = await self.request(first, 1, "register", username="Tester", password="correct-horse-123", tamer="tamer", starter="rookie")
            self.assertTrue(r["ok"], r)
            duplicate = await self.request(second, 1, "login", username="tester", password="correct-horse-123")
            self.assertFalse(duplicate["ok"])
            self.assertIn("already online", duplicate["error"])
            bad = await self.request(first, 2, "shop", item="invalid")
            self.assertFalse(bad["ok"])
            good = await self.request(first, 3, "shop", item="hp_s")
            self.assertEqual(225, good["state"]["credits"])  # failed action was rolled back
            await self.world.broadcast_once()
            snapshot = json.loads(await first.recv())
            self.assertEqual("world", snapshot["op"])
            self.assertEqual("rookie", snapshot["players"][0]["lead"])
            await first.send(json.dumps({"op": "chat", "rid": 4, "text": "Hello Digital World"}))
            chat = json.loads(await first.recv())
            self.assertEqual(("chat", "Tester"), (chat["op"], chat["username"]))
            self.assertTrue(json.loads(await first.recv())["ok"])
        # Listener close awaits final persistence and releases the lease.
        self.listener.close()
        await self.listener.wait_closed()
        saved, revision = self.db.load("tester")
        self.assertEqual(225, saved["credits"])
        self.assertGreaterEqual(revision, 2)
        self.assertTrue(self.db.acquire_session("tester", "after-logout"))

    async def test_normal_move_is_small_and_auto_encounter_returns_full_state(self):
        from websockets.asyncio.client import connect
        async with connect(self.url) as ws:
            await ws.recv()
            registration = await self.request(ws, 1, "register", username="MovingTester",
                password="correct-horse-123", tamer="tamer", starter="rookie")
            self.assertTrue(registration["ok"])
            session = self.world.sessions["movingtester"]
            # Large inventories must never inflate the 20 Hz movement acknowledgment.
            session.state["storage"] = [{"species_id": "rookie", "history": list(range(50))}] * 2000
            session.state["scan"] = {f"species_{i}": 100 for i in range(1004)}
            movement = await self.request(ws, 2, "move", dx=1, dy=0, dt=0.1)
            self.assertTrue(movement["ok"])
            self.assertEqual({"space", "map_id", "x", "y"}, set(movement["position"]))
            self.assertEqual("field", movement["position"]["space"])
            self.assertGreater(movement["position"]["x"], 100)
            self.assertNotIn("state", movement)
            self.assertLess(len(json.dumps(movement)), 180)
            session.walked = session.next_encounter
            encounter = await self.request(ws, 3, "move", dx=0, dy=0, dt=0)
            self.assertTrue(encounter["ok"])
            self.assertIsNotNone(encounter["state"]["battle"])
            self.assertNotIn("position", encounter)
            saved, _ = self.db.load("movingtester")
            self.assertIsNotNone(saved["battle"])

    async def test_rejects_malformed_json_and_unauthenticated_actions(self):
        from websockets.asyncio.client import connect
        async with connect(self.url) as ws:
            await ws.recv()
            await ws.send('{"op":"move","dx":NaN}')
            result = json.loads(await ws.recv())
            self.assertFalse(result["ok"])
            self.assertIn("finite", result["error"])
            result = await self.request(ws, 2, "shop", item="hp_s")
            self.assertFalse(result["ok"])
            self.assertIn("Sign in", result["error"])
            result = await self.request(ws, 3, "ping")
            self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
