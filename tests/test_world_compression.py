"""Lossless negotiated compression through the existing native client protocol."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from websockets.frames import Frame, OP_TEXT

from tools.benchmark_world_bandwidth import build_fixture, server_extension
from venom.client.network import Connection
from venom.server.database import Database
from venom.server.main import MAX_MESSAGE, WorldServer, transport_extensions

ROOT = Path(__file__).resolve().parents[1]


class WorldCompressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine, self.manager, _ = build_fixture(160)
        self.map_id = next(iter(self.engine.maps))
        self.db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
        self.db.initialize()
        self.world = WorldServer(self.engine, self.db)
        self.listener = await serve(self.world.connection, "127.0.0.1", 0,
                                    max_size=MAX_MESSAGE, compression=None,
                                    extensions=transport_extensions())
        self.port = self.listener.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{self.port}"
        self.native = None

    async def asyncTearDown(self):
        if self.native:
            self.native.close()
        self.listener.close()
        await self.listener.wait_closed()
        if self.native:
            await asyncio.to_thread(self.native.thread.join, 5)
        self.db.close()

    async def native_receive(self, op, rid=None):
        async def receive():
            while True:
                try:
                    packet = self.native.incoming.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(.005)
                    continue
                if packet.get("op") == "error":
                    self.fail(packet)
                if packet.get("op") == op and (rid is None or packet.get("rid") == rid):
                    return packet
        return await asyncio.wait_for(receive(), 5)

    async def socket_receive(self, ws, op, rid=None):
        while True:
            packet = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if packet.get("op") == op and (rid is None or packet.get("rid") == rid):
                return packet

    def registration(self, username):
        return {"username": username, "password": "compression-fixture-123",
                "tamer": next(iter(self.engine.tamers)), "starter": self.engine.starters[0]}

    async def test_native_client_and_uncompressed_peer_get_exact_same_complete_world(self):
        self.native = Connection({"host": "127.0.0.1", "port": self.port}, ROOT, dev=True)
        await self.native_receive("hello")
        rid = self.native.send("register", **self.registration("CompressedAlice"))
        self.assertTrue((await self.native_receive("result", rid))["ok"])
        async with connect(self.url, compression=None) as plain:
            await self.socket_receive(plain, "hello")
            await plain.send(json.dumps({"op": "register", "rid": 1, **self.registration("PlainBob")}))
            self.assertTrue((await self.socket_receive(plain, "result", 1))["ok"])
            alice, bob = self.world.sessions["compressedalice"], self.world.sessions["plainbob"]
            extension, = alice.websocket.protocol.extensions
            self.assertEqual(extension.name, "permessage-deflate")
            self.assertTrue(extension.local_no_context_takeover)
            self.assertTrue(extension.remote_no_context_takeover)
            self.assertEqual(extension.local_max_window_bits, 12)
            self.assertEqual(extension.remote_max_window_bits, 12)
            self.assertEqual(bob.websocket.protocol.extensions, [])
            for session in (alice, bob):
                session.state.update(in_farm=False, in_lab=False, map_id=self.map_id)
            rows = self.manager.snapshot(self.map_id, now=1000.4)
            self.world.community = SimpleNamespace(ready=True,
                snapshots=lambda fields, now: {self.map_id: rows}, register_player=lambda state: None)
            for tick in range(3):
                rows[:] = self.manager.snapshot(self.map_id, now=1000.4 + tick * .1)
                # Exercise immediate battle/status changes without changing any
                # coordinates, directions, field names or actor membership.
                rows[0].update(battle=bool(tick % 2), status="Battling" if tick % 2 else "Exploring")
                await self.world.broadcast_once()
                native_packet = await self.native_receive("world")
                plain_packet = await self.socket_receive(plain, "world")
                self.assertEqual(native_packet, plain_packet)
                self.assertEqual(native_packet["players"][2:], rows)
                self.assertEqual(len(native_packet["players"]), 162)
                self.assertEqual(native_packet["sequence"], tick + 1)
                self.assertEqual(native_packet["scope"], [self.map_id, "field", None])
            # Both peers enter private homes. Shared-map rows must not leak
            # through the compressed socket or the plain fallback connection.
            for session in (alice, bob):
                session.state["in_farm"] = True
            await self.world.broadcast_once()
            a, b = await self.native_receive("world"), await self.socket_receive(plain, "world")
            self.assertEqual([row["username"] for row in a["players"]], ["CompressedAlice"])
            self.assertEqual([row["username"] for row in b["players"]], ["PlainBob"])
            self.assertEqual(a["scope"], [self.map_id, "farm", "compressedalice"])
            self.assertEqual(b["scope"], [self.map_id, "farm", "plainbob"])

    async def test_compressed_input_cannot_bypass_existing_decompressed_message_limit(self):
        async with connect(self.url) as ws:
            await self.socket_receive(ws, "hello")
            self.assertTrue(ws.protocol.extensions)
            # On the wire this repeated string is tiny; its decoded size is
            # still checked against the production 64KiB request limit.
            await ws.send(json.dumps({"op": "ping", "padding": "x" * (MAX_MESSAGE + 1)}))
            with self.assertRaises(ConnectionClosed) as closed:
                await ws.recv()
            self.assertEqual(closed.exception.rcvd.code, 1009)
            self.assertEqual(self.world.sessions, {})


class IndependentCompressionMessagesTests(unittest.TestCase):
    def test_no_message_or_peer_reuses_previous_compression_dictionary(self):
        peer_a, peer_b = server_extension(), server_extension()
        payload = json.dumps({"op": "world", "players": [{"username": "SharedTamer", "x": 1.23456789}] * 50}).encode()
        secret = b'{"op":"result","private":"only-this-connection-should-see-this"}'
        peer_a.encode(Frame(OP_TEXT, secret))
        a = peer_a.encode(Frame(OP_TEXT, payload))
        b = peer_b.encode(Frame(OP_TEXT, payload))
        self.assertEqual(a.data, b.data)
        self.assertTrue(a.rsv1)
        self.assertEqual(peer_a.encode(Frame(OP_TEXT, payload)).data, a.data)
        # A fresh decoder can decode each frame independently: no preceding
        # private result, another scene or another peer's dictionary is needed.
        for frame in (a, b):
            decoded = server_extension().decode(frame, max_size=8 * 1024 * 1024)
            self.assertEqual(decoded.data, payload)
            self.assertFalse(decoded.rsv1)

    def test_crowded_moving_map_frames_are_lossless_and_materially_smaller(self):
        _, manager, _ = build_fixture(160)
        map_id = next(iter(manager.by_map))
        sender, receiver = server_extension(), server_extension()
        baseline_size = compressed_size = 0
        for tick in range(5):
            rows = manager.snapshot(map_id, now=1000.1 + tick * .1)
            self.assertTrue(any(row["moving"] for row in rows))
            payload = json.dumps({"op": "world", "players": rows, "sequence": tick}, separators=(",", ":")).encode()
            source = Frame(OP_TEXT, payload)
            encoded = sender.encode(source)
            baseline_size += len(source.serialize(mask=False))
            compressed_size += len(source.serialize(mask=False, extensions=[server_extension()]))
            self.assertEqual(receiver.decode(encoded, max_size=8 * 1024 * 1024).data, payload)
        self.assertLess(compressed_size, baseline_size * .4)
