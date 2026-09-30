"""The established live-socket region contract, exercised on Xros map assets.

These tests share the existing protocol harness: real WebSockets, SQLite,
collision masks, presence, bot paths, save restoration and native client queues.
"""
from __future__ import annotations

import asyncio
import copy
import math
from unittest.mock import patch

import test_world_ds_replication as region_contract
from test_world_ds_acceptance import command_for
from test_xros_acceptance import xros_maps


class SuperXrosReplicationTests(region_contract.WorldDSReplicationTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        areas = xros_maps(self.engine)
        self.entry = areas[0]
        self.other = areas[1]
        self.large = max(areas, key=lambda area: area["width"] * area["height"])

    async def test_walking_earns_shiny_encounter_and_persists_real_scan_after_server_restart(self):
        async with self.client() as alice, self.client() as bob:
            state = await self.register(alice, "XrosWalkAlice")
            await self.register(bob, "XrosWalkBob")
            session = self.world.sessions["xroswalkalice"]
            start_wallet = copy.deepcopy({key: state[key] for key in ("scan", "credits", "wins")})
            walked = 0.0
            direction = (1, 0)
            # Walk the complete normal 850 px interval with real movement
            # budgets. Only the valid 1% event's RNG outcome is pinned.
            with patch.object(self.engine.rng, "random", return_value=.03), \
                    patch.object(self.engine.rng, "choices", return_value=[1]):
                for _ in range(100):
                    x, y = session.state["x"], session.state["y"]
                    choices = (direction, (-direction[0], -direction[1]), (0, 1), (0, -1), (1, 0), (-1, 0))
                    direction = next((d for d in choices if all(
                        self.world._walkable(self.entry, x + d[0] * step, y + d[1] * step)
                        and 12 <= x + d[0] * step <= self.entry["width"] - 12
                        and 12 <= y + d[1] * step <= self.entry["height"] - 12
                        for step in range(1, 19))), None)
                    self.assertIsNotNone(direction, "Spawn component needs an ordinary walking corridor")
                    await asyncio.sleep(.105)
                    packet = await self.action(alice, "move", dx=direction[0], dy=direction[1], dt=.1)
                    walked += math.dist((x, y), (session.state["x"], session.state["y"]))
                    if "state" in packet:
                        state = packet["state"]
                        break
                    self.assertIn("position", packet)
                else:
                    self.fail("Full-distance real walking never triggered a Xros encounter")
            self.assertGreaterEqual(walked, 850)
            self.assertTrue(state["battle"])
            enemies = state["battle"]["enemies"]
            self.assertEqual(1, len(enemies))
            species_id = enemies[0]["species_id"]
            self.assertIn(species_id, self.engine._shiny_pools[self.entry["id"]])
            self.assertTrue(enemies[0]["shiny"])
            persisted, _ = self.db.load("xroswalkalice")
            self.assertEqual(state["battle"], persisted["battle"])
            frame, peer = await self.snapshot(alice, bob)
            self.assertEqual(frame, peer)
            actor = self.humans(peer)["XrosWalkAlice"]
            self.assertTrue(actor["battle"])
            self.assertEqual((actor["dx"], actor["dy"]), (0, 0))
            for _ in range(100):
                if not state["battle"]:
                    break
                await asyncio.sleep(.175)
                state = (await self.action(alice, "battle", **command_for(state)))["state"]
            self.assertIsNone(state["battle"])
            self.assertEqual(start_wallet["wins"] + 1, state["wins"])
            self.assertEqual(start_wallet["scan"].get(species_id, 0) + 5, state["scan"][species_id])
            self.assertGreater(state["credits"], start_wallet["credits"])
            await self.action(alice, "logout")
            await alice.wait_closed()
            await self.wait_logout("xroswalkalice")
        # Restart both authoritative engine and database connection, retaining
        # only the SQLite save. No gameplay state is copied into the new server.
        self.listener.close()
        await self.listener.wait_closed()
        if self.world.community:
            await asyncio.to_thread(self.world.community.shutdown)
        self.db.close()
        self.db = region_contract.Database({"driver": "sqlite", "path": str(
            region_contract.Path(self.tmp.name) / "world.sqlite3")}, dev=True)
        self.db.initialize()
        self.engine = region_contract.GameEngine(region_contract.ROOT, seed=1097)
        self.world = region_contract.WorldServer(self.engine, self.db, {"rivals": {"count": 0}})
        self.listener = await region_contract.serve(self.world.connection, "127.0.0.1", 0, max_size=65536)
        self.url = f"ws://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}"
        self.pending.clear()
        async with self.client() as restored_client:
            await self.receive(restored_client, "hello")
            restored = (await self.action(restored_client, "login", username="XrosWalkAlice",
                                          password=region_contract.PASSWORD))["state"]
            for key in ("map_id", "x", "y", "party", "scan", "credits", "wins"):
                self.assertEqual(state[key], restored[key], key)
