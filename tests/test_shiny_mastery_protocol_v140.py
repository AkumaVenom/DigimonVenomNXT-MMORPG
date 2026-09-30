"""Shiny victory bonuses persist through real WebSocket and SQLite restarts."""
import copy
import unittest

import test_story_protocol as harness
from test_shiny_gameplay_v120 import EventRng


class ShinyMasteryProtocolTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = harness.StoryProtocolTests.asyncSetUp
    asyncTearDown = harness.StoryProtocolTests.asyncTearDown
    start_server = harness.StoryProtocolTests.start_server
    stop_server = harness.StoryProtocolTests.stop_server
    connection = harness.StoryProtocolTests.connection
    receive = harness.StoryProtocolTests.receive
    request = harness.StoryProtocolTests.request
    action = harness.StoryProtocolTests.action
    register = harness.StoryProtocolTests.register
    wait_for_logout = harness.StoryProtocolTests.wait_for_logout
    rejected = harness.StoryProtocolTests.rejected

    async def test_shiny_pending_bonus_survives_database_restart_and_cannot_repeat(self):
        name, key = "ShinyResume", "shinyresume"
        async with self.connection() as ws:
            await self.register(ws, name)
            await self.action(ws, "digifarm", action="return")
            result = await self.console.execute(f"/setlevel {name} party:1 99")
            self.assertFalse(result.startswith("ERROR:"), result)
            # Seed the earned account reward on the trusted server side; the
            # campaign acceptance suite proves its one-time finale grant.
            session = self.world.sessions[key]
            session.state["permanent_rewards"] = {"shiny_scan_mastery": True, "paradox_scan_mastery": True}
            self.engine.rng = EventRng(.03, count=3)
            state = await self.action(ws, "encounter")
            shiny_index = next(i for i, enemy in enumerate(state["battle"]["enemies"]) if enemy["shiny"])
            shiny_id = state["battle"]["enemies"][shiny_index]["species_id"]
            state = await self.action(ws, "battle", action="attack", target=shiny_index)
            self.assertIsNotNone(state["battle"])
            self.assertEqual(5, state["scan"][shiny_id])
            self.assertEqual({shiny_id: 1}, state["battle"]["shiny_mastery_pending"])
            expected = copy.deepcopy({k: state[k] for k in ("scan", "battle", "party", "permanent_rewards")})
            await self.rejected(ws, key, "materialize", species_id=shiny_id)
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout(key)
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            hello = await self.receive(ws, "hello")
            self.assertIn("ghostline_story", hello["features"])
            state = await self.action(ws, "login", username=name, password=harness.PASSWORD)
            self.assertEqual(expected, {k: state[k] for k in expected})
            for _ in range(25):
                if not state["battle"]:
                    break
                target = next(i for i, enemy in enumerate(state["battle"]["enemies"]) if enemy["hp"] > 0)
                state = await self.action(ws, "battle", action="attack", target=target,
                                          shiny_scan_mastery=True, bonus=1000)
            self.assertIsNone(state["battle"])
            self.assertEqual(6, state["scan"][shiny_id])
            await self.rejected(ws, key, "battle", action="attack", target=0)
            stored, _ = self.db.load(key)
            self.assertEqual(6, stored["scan"][shiny_id])
            self.assertEqual(expected["permanent_rewards"], stored["permanent_rewards"])
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout(key)
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            state = await self.action(ws, "login", username=name, password=harness.PASSWORD)
            self.assertEqual(6, state["scan"][shiny_id])
            self.assertEqual(expected["permanent_rewards"], state["permanent_rewards"])

    async def test_client_cannot_unlock_or_inflate_shiny_mastery(self):
        async with self.connection() as ws:
            await self.register(ws, "NoForgedShiny")
            await self.action(ws, "digifarm", action="return")
            result = await self.console.execute("/setlevel NoForgedShiny party:1 99")
            self.assertFalse(result.startswith("ERROR:"), result)
            self.engine.rng = EventRng(.03)
            state = await self.action(ws, "encounter", permanent_rewards={"shiny_scan_mastery": True},
                                      shiny_scan_gain=100, shiny_encounter_chance=1)
            shiny = state["battle"]["enemies"][0]["species_id"]
            self.assertTrue(state["battle"]["enemies"][0]["shiny"])
            state = await self.action(ws, "battle", action="attack", target=0,
                                      permanent_rewards={"shiny_scan_mastery": True}, winner="player")
            self.assertIsNone(state["battle"])
            self.assertEqual(5, state["scan"][shiny])
            self.assertFalse(state.get("permanent_rewards", {}).get("shiny_scan_mastery"))
            stored, _ = self.db.load("noforgedshiny")
            self.assertEqual(5, stored["scan"][shiny])
            self.assertFalse(stored.get("permanent_rewards", {}).get("shiny_scan_mastery"))
