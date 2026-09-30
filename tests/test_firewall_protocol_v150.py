"""Real WebSocket and SQLite coverage for FireWall rewards and persistence."""
import copy
import unittest

import test_story_protocol as harness
from test_shiny_gameplay_v120 import EventRng
from venom.common import story
from venom.server.admin_commands import AdminConsole


class FireWallProtocolTests(unittest.IsolatedAsyncioTestCase):
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
    battle_fields = staticmethod(harness.StoryProtocolTests.battle_fields)

    async def finish_battle(self, ws, state, **payload):
        for _ in range(80):
            if not state["battle"]:
                break
            target = next(i for i, enemy in enumerate(state["battle"]["enemies"]) if enemy["hp"] > 0)
            state = await self.action(ws, "battle", **self.battle_fields(state, "attack", target=target), **payload)
        self.assertIsNone(state["battle"])
        return state

    async def test_firewall_pending_bonus_survives_restart_and_all_masteries_remain_independent(self):
        name, key = "FireResume", "fireresume"
        async with self.connection() as ws:
            await self.register(ws, name)
            await self.action(ws, "digifarm", action="return")
            self.assertFalse((await self.console.execute(f"/setlevel {name} party:1 99")).startswith("ERROR:"))
            # A trusted save fixture supplies earned entitlements. Campaign
            # tests separately verify the actual first-victory reward source.
            session = self.world.sessions[key]
            session.state["permanent_rewards"] = {"firewall_scan_mastery": True,
                                                   "shiny_scan_mastery": True,
                                                   "paradox_scan_mastery": True}
            self.engine.rng = EventRng(.04, count=3)
            state = await self.action(ws, "encounter")
            index = next(i for i, enemy in enumerate(state["battle"]["enemies"]) if enemy["firewall"])
            sid = state["battle"]["enemies"][index]["species_id"]
            state = await self.action(ws, "battle", **self.battle_fields(state, "attack", target=index))
            self.assertIsNotNone(state["battle"])
            self.assertEqual(5, state["scan"][sid])
            self.assertEqual({sid: 1}, state["battle"]["firewall_mastery_pending"])
            self.assertFalse(state["battle"].get("shiny_mastery_pending"))
            self.assertFalse(state["battle"].get("paradox_mastery_pending"))
            expected = copy.deepcopy({k: state[k] for k in ("scan", "battle", "party", "permanent_rewards")})
            await self.rejected(ws, key, "materialize", species_id=sid)
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout(key)
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            hello = await self.receive(ws, "hello")
            self.assertIn("firewall_varieties", hello["features"])
            state = await self.action(ws, "login", username=name, password=harness.PASSWORD)
            self.assertEqual(expected, {k: state[k] for k in expected})
            state = await self.finish_battle(ws, state, firewall_mastery_pending={sid: 1000}, bonus=1000)
            self.assertEqual(6, state["scan"][sid])
            await self.rejected(ws, key, "battle", action="attack", target=0, firewall_scan_gain=1000)
            stored, _ = self.db.load(key)
            self.assertEqual(6, stored["scan"][sid])
            self.assertEqual(expected["permanent_rewards"], stored["permanent_rewards"])
            # Both earlier rare families retain their own 5 + 1 contract.
            for roll, variety in ((.03, "shiny"), (.001, "paradox")):
                self.world.sessions[key].last_encounter = 0
                self.engine.rng = EventRng(roll)
                state = await self.action(ws, "encounter")
                enemy = state["battle"]["enemies"][0]
                self.assertTrue(enemy[variety])
                other_sid = enemy["species_id"]
                state = await self.finish_battle(ws, state)
                self.assertEqual(6, state["scan"][other_sid])
                self.assertEqual(6, state["scan"][sid])
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout(key)
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            state = await self.action(ws, "login", username=name, password=harness.PASSWORD)
            self.assertEqual(6, state["scan"][sid])
            self.assertEqual(expected["permanent_rewards"], state["permanent_rewards"])

    async def test_client_cannot_forge_firewall_identity_reward_or_host_console_access(self):
        async with self.connection() as ws:
            await self.register(ws, "FireUnforged")
            await self.action(ws, "digifarm", action="return")
            low = AdminConsole(self.world, role="PLAYER")
            try:
                self.assertTrue((await low.execute("/setfirewall FireUnforged party:1 true")).startswith("DENIED:"))
            finally:
                await low.close()
            await self.rejected(ws, "fireunforged", "setfirewall", species_id="agumon_firewall", role="OWNER")
            self.assertFalse((await self.console.execute("/setlevel FireUnforged party:1 99")).startswith("ERROR:"))
            self.engine.rng = EventRng(.04)
            state = await self.action(ws, "encounter", species_id="forged", firewall=False,
                                      permanent_rewards={"firewall_scan_mastery": True}, firewall_encounter_chance=1)
            sid = state["battle"]["enemies"][0]["species_id"]
            self.assertTrue(state["battle"]["enemies"][0]["firewall"])
            state = await self.finish_battle(ws, state, permanent_rewards={"firewall_scan_mastery": True},
                                             firewall_scan_gain=100, winner="player")
            self.assertEqual(5, state["scan"][sid])
            self.assertFalse(state.get("permanent_rewards", {}).get("firewall_scan_mastery"))
            self.assertFalse(state["party"][0]["firewall"])
            saved, _ = self.db.load("fireunforged")
            self.assertEqual(5, saved["scan"][sid])
            self.assertFalse(saved.get("permanent_rewards", {}).get("firewall_scan_mastery"))

    async def test_parked_legacy_dawn_completion_repairs_reward_on_login_without_regranting_scan(self):
        name, key = "OldDawnHero", "olddawnhero"
        async with self.connection() as ws:
            await self.register(ws, name)
            session = self.world.sessions[key]
            # Model a genuine pre-v1.5 save: Dawn was completed, its title was
            # subsequently lost, and the player switched to Ghostline.
            dawn = story._new_profile(story.content(self.engine, story.DAWN_CAMPAIGN), story.DAWN_CAMPAIGN)
            dawn.pop("campaign_id")
            dawn["champion"].update(first_victory=True, status="reclaim")
            active = story._new_profile(story.content(self.engine, story.XROS_CAMPAIGN), story.XROS_CAMPAIGN)
            session.state.update(story=active, story_campaigns={story.DAWN_CAMPAIGN: dawn},
                                 permanent_rewards={"shiny_scan_mastery": True, "paradox_scan_mastery": True})
            session.state["scan"]["agumon_firewall"] = 0
            expected_party = copy.deepcopy(session.state["party"])
            await self.world.save(session)
            saved, _ = self.db.load(key)
            self.assertNotIn("firewall_scan_mastery", saved["permanent_rewards"])
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout(key)
        await self.stop_server()
        await self.start_server()
        for _ in range(2):
            async with self.connection() as ws:
                await self.receive(ws, "hello")
                state = await self.action(ws, "login", username=name, password=harness.PASSWORD,
                                          permanent_rewards={"firewall_scan_mastery": False})
                self.assertEqual({"firewall_scan_mastery": True, "shiny_scan_mastery": True,
                                  "paradox_scan_mastery": True}, state["permanent_rewards"])
                self.assertEqual(0, state["scan"]["agumon_firewall"])
                self.assertEqual(expected_party, state["party"])
                self.assertEqual("reclaim", state["story_campaigns"][story.DAWN_CAMPAIGN]["champion"]["status"])
                self.assertEqual(story.XROS_CAMPAIGN, state["story"]["campaign_id"])
                await self.action(ws, "logout")
                await ws.wait_closed()
            await self.wait_for_logout(key)

    async def test_capture_public_lead_and_partner_survive_server_restart(self):
        name, key = "FireCollector", "firecollector"
        async with self.connection() as ws:
            initial = await self.register(ws, name)
            await self.action(ws, "digifarm", action="return")
            self.assertFalse((await self.console.execute(f"/setlevel {name} party:1 99")).startswith("ERROR:"))
            maps = [initial["map_id"]] + [next(m["id"] for m in self.engine.maps.values()
                     if m.get("region_id") == region and m.get("level") == 1)
                     for region in ("world_ds", "xros_wars")]
            for map_id in maps:
                await self.action(ws, "travel", map_id=map_id)
                self.world.sessions[key].last_encounter = 0
                self.engine.rng = EventRng(.04)
                state = await self.action(ws, "encounter")
                sid = state["battle"]["enemies"][0]["species_id"]
                self.assertIn(sid, self.engine._firewall_pools[map_id])
                self.assertTrue(state["battle"]["enemies"][0]["firewall"])
                # A mature account's pre-existing 95 scan plus this real defeat
                # supplies conversion; unrelated variety scan accounts stay put.
                session = self.world.sessions[key]
                session.state["scan"][sid] = 95
                state = await self.finish_battle(ws, state)
                self.assertEqual(100, state["scan"][sid])
                state = await self.action(ws, "digilab", action="enter")
                state = await self.action(ws, "materialize", species_id=sid)
                self.assertEqual(0, state["scan"][sid])
                self.assertTrue(next(m for m in state["party"] + state["storage"] if m["species_id"] == sid)["firewall"])
                state = await self.action(ws, "digilab", action="return")
            self.assertFalse((await self.console.execute(f"/setfirewall {name} party:1 true")).startswith("ERROR:"))
            state = copy.deepcopy(self.world.sessions[key].state)
            expected_party = copy.deepcopy(state["party"] + state["storage"])
            await self.world.broadcast_once()
            world = await self.receive(ws, "world")
            self.assertEqual(state["party"][0]["species_id"], world["players"][0]["lead"])
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout(key)
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            state = await self.action(ws, "login", username=name, password=harness.PASSWORD)
            self.assertEqual(expected_party, state["party"] + state["storage"])
            self.assertTrue(state["party"][0]["firewall"])
            self.assertEqual(0, state["scan"][sid])
