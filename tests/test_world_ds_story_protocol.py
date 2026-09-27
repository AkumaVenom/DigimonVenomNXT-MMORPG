"""World DS integration over real WebSockets and persistent SQLite saves.

Reuse the established server harness without inheriting its Dawn test cases.
Progress is always requested through production packets; clients never supply
NPC teams, quest results, badges, battle winners or permanent rewards.
"""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from venom.common import story
import test_story_protocol as _protocol

PASSWORD = _protocol.PASSWORD

CAMPAIGN = "world_ds_paradox"


class WorldDSStoryProtocolTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = _protocol.StoryProtocolTests.asyncSetUp
    asyncTearDown = _protocol.StoryProtocolTests.asyncTearDown
    start_server = _protocol.StoryProtocolTests.start_server
    stop_server = _protocol.StoryProtocolTests.stop_server
    connection = _protocol.StoryProtocolTests.connection
    receive = _protocol.StoryProtocolTests.receive
    request = _protocol.StoryProtocolTests.request
    action = _protocol.StoryProtocolTests.action
    register = _protocol.StoryProtocolTests.register
    wait_for_logout = _protocol.StoryProtocolTests.wait_for_logout
    battle_fields = staticmethod(_protocol.StoryProtocolTests.battle_fields)

    async def rejected(self, ws, key, op, **fields):
        before = copy.deepcopy(self.world.sessions[key].state)
        response = await _protocol.StoryProtocolTests.rejected(self, ws, key, op, **fields)
        self.assertEqual(before, self.world.sessions[key].state)
        return response

    async def enter_ds(self, ws, username):
        original = await self.register(ws, username)
        state = await self.action(ws, "story", action="enter", campaign_id=CAMPAIGN)
        self.assertTrue(state["in_story"])
        self.assertEqual(CAMPAIGN, state["story"]["campaign_id"])
        self.assertEqual([], state["story"]["badges"])
        return original, state

    async def test_native_services_and_independent_campaign_locations_survive_switching(self):
        async with self.connection() as ws:
            original = await self.register(ws, "DSNativeHero")
            dawn = await self.action(ws, "story", action="enter", campaign_id="dawn_relay")
            dawn_profile = copy.deepcopy(dawn["story"])
            await self.action(ws, "story", action="return")

            state = await self.action(ws, "story", action="enter", campaign_id=CAMPAIGN)
            self.assertNotEqual(dawn_profile["id"], state["story"]["id"])
            self.assertEqual(original["party"], state["party"])
            self.assertEqual(original["inventory"], state["inventory"])
            state = await self.action(ws, "story", action="travel", chapter=1)
            data = story.content(self.engine, CAMPAIGN)
            quest_id = next(ident for ident in data["regions"][1]["npc_ids"]
                            if data["npcs"][ident]["role"] == "quest")
            # The arrival guide is an ordinary nearby NPC. Accept a real quest
            # so campaign switching exercises saved progress, not empty saves.
            state = await self.action(ws, "story", action="talk", npc_id=quest_id)
            while any(choice["id"] == "next" for choice in state["story"]["view"]["dialogue"]["choices"]):
                token = state["story"]["view"]["dialogue"]["token"]
                state = await self.action(ws, "story", action="dialogue", token=token, choice="next")
            token = state["story"]["view"]["dialogue"]["token"]
            state = await self.action(ws, "story", action="dialogue", token=token, choice="accept_quest")
            self.assertIn(quest_id, state["story"]["quest_accepted"])
            await self.rejected(ws, "dsnativehero", "story", action="dialogue",
                                token=token, choice="accept_quest")
            location = {key: state[key] for key in ("map_id", "x", "y")}
            state = await self.action(ws, "digilab", action="enter")
            self.assertTrue(state["in_story"] and state["in_lab"])
            credits, capsules = state["credits"], state["inventory"]["hp_s"]
            state = await self.action(ws, "shop", item="hp_s", quantity=1)
            self.assertLess(state["credits"], credits)
            self.assertEqual(capsules + 1, state["inventory"]["hp_s"])
            state = await self.action(ws, "digilab", action="return")
            self.assertEqual(location, {key: state[key] for key in location})
            state = await self.action(ws, "digifarm", action="enter")
            self.assertTrue(state["in_story"] and state["in_farm"])
            state = await self.action(ws, "digifarm", action="return")
            self.assertEqual(location, {key: state[key] for key in location})
            ds_profile = copy.deepcopy(state["story"])
            owned = copy.deepcopy({key: state[key] for key in
                                  ("party", "storage", "inventory", "credits", "scan")})
            world = await self.action(ws, "story", action="return")
            self.assertFalse(world["in_story"])
            self.assertEqual(original["map_id"], world["map_id"])
            self.assertEqual(owned, {key: world[key] for key in owned})

            resumed = await self.action(ws, "story", action="enter", campaign_id="dawn_relay")
            for key in ("id", "location", "badges", "completed", "quest_accepted", "stats"):
                self.assertEqual(dawn_profile[key], resumed["story"][key])
            self.assertEqual(ds_profile["id"], resumed["story_campaigns"][CAMPAIGN]["id"])
            self.assertEqual(owned, {key: resumed[key] for key in owned})
            await self.action(ws, "story", action="return")
            resumed = await self.action(ws, "story", action="enter", campaign_id=CAMPAIGN)
            for key in ("id", "location", "badges", "completed", "quest_accepted", "stats"):
                self.assertEqual(ds_profile[key], resumed["story"][key])
            self.assertEqual(owned, {key: resumed[key] for key in owned})
            persisted, _ = self.db.load("dsnativehero")
            self.assertEqual(resumed["story"], persisted["story"])
            self.assertEqual(dawn_profile["id"], persisted["story_campaigns"]["dawn_relay"]["id"])

    async def test_story_npcs_never_enter_shared_bot_or_ranked_population(self):
        await self.world.initialize_community()
        community = self.world.community
        async with self.connection() as alice, self.connection() as bob:
            await self.register(alice, "DSPrivateAlice")
            await self.register(bob, "DSPrivateBob")
            with patch.object(community, "register_player", wraps=community.register_player) as publish:
                for ws in (alice, bob):
                    await self.action(ws, "story", action="enter", campaign_id=CAMPAIGN)
                a, b = self.world.sessions["dsprivatealice"], self.world.sessions["dsprivatebob"]
                self.assertFalse(self.world.same_place(a, b))
                self.assertFalse(self.world.shared_profile(a.state))
                self.assertEqual((a.state["map_id"], "story", a.key), self.world.place(a))
                with patch.object(community, "snapshots", return_value={}) as snapshots:
                    await self.world.broadcast_once()
                    self.assertEqual(set(), snapshots.call_args.args[0])
                for ws, username in ((alice, "DSPrivateAlice"), (bob, "DSPrivateBob")):
                    packet = await self.receive(ws, "world")
                    self.assertEqual([username], [row["username"] for row in packet["players"]])
                    self.assertTrue(packet["players"][0]["in_story"])
                for op, fields in (("community", {"action": "overview"}),
                                   ("community", {"action": "challenge", "bot_id": "forged"}),
                                   ("season", {"action": "history"}),
                                   ("season", {"action": "enter"})):
                    await self.rejected(alice, "dsprivatealice", op, **fields)
                await self.action(alice, "logout")
                await alice.wait_closed()
                await self.wait_for_logout("dsprivatealice")
                publish.assert_not_called()
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            with patch.object(community, "register_player", wraps=community.register_player) as publish:
                restored = await self.action(ws, "login", username="DSPrivateAlice", password=PASSWORD)
                self.assertEqual(CAMPAIGN, restored["story"]["campaign_id"])
                self.assertTrue(restored["in_story"])
                publish.assert_not_called()

    async def test_forged_quest_boss_finale_and_reward_payloads_do_not_mutate_save(self):
        async with self.connection() as ws:
            _, state = await self.enter_ds(ws, "DSForgeGuard")
            data = story.content(self.engine, CAMPAIGN)
            first = data["regions"][1]
            roles = {data["npcs"][ident]["role"]: ident for ident in first["npc_ids"]}
            finale = next(npc for npc in data["npcs"].values() if npc["role"] == "final")
            self.assertFalse(state["story"]["view"]["training_available"])
            for op, fields in (
                ("story", {"action": "train"}),
                ("encounter", {}),
                ("story", {"action": "travel", "chapter": 2}),
                ("story", {"action": "travel", "chapter": 17}),
                ("story", {"action": "enter", "campaign_id": "dawn_relay"}),
                ("story", {"action": "complete_quest", "npc_id": roles["quest"], "reward": 999999}),
                ("story", {"action": "dialogue", "choice": "complete_quest", "token": "forged"}),
                ("story", {"action": "challenge", "npc_id": roles["warden"], "token": "forged"}),
                ("story", {"action": "challenge", "npc_id": finale["id"], "token": "forged",
                           "badges": [r["badge"]["id"] for r in data["regions"][1:]]}),
                ("story", {"action": "complete", "winner": "player",
                           "permanent_rewards": {"paradox_scan_mastery": True}}),
                ("story", {"action": "travel", "chapter": 1, "campaign_id": "dawn_relay"}),
                ("story", {"action": "enter", "campaign_id": {"world_ds_paradox": True}}),
            ):
                await self.rejected(ws, "dsforgeguard", op, **fields)
            persisted, _ = self.db.load("dsforgeguard")
            self.assertEqual([], persisted["story"]["completed"])
            self.assertEqual([], persisted["story"]["quest_accepted"])
            self.assertEqual([], persisted["story"]["badges"])
            self.assertFalse(persisted.get("permanent_rewards", {}).get("paradox_scan_mastery"))
            self.assertIsNone(persisted["battle"])

    async def test_real_restart_restores_ds_battle_and_rejects_replayed_turn(self):
        async with self.connection() as ws:
            await self.enter_ds(ws, "DSBattleResume")
            await self.action(ws, "story", action="travel", chapter=1)
            state = await self.action(ws, "story", action="train")
            self.assertEqual("story", state["battle"]["kind"])
            self.assertEqual(CAMPAIGN, state["battle"]["story_campaign_id"])
            self.assertEqual(state["story"]["id"], state["battle"]["story_profile_id"])
            expected = copy.deepcopy({key: state[key] for key in
                ("party", "inventory", "credits", "scan", "battle", "story", "story_return_state",
                 "in_story", "map_id", "x", "y", "in_lab", "in_farm")})
            await self.rejected(ws, "dsbattleresume", "battle", action="win", winner="player",
                                battle_id=state["battle"]["id"], expected_turn=state["battle"]["turn"])
            await self.rejected(ws, "dsbattleresume", "story", action="return")
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout("dsbattleresume")
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            restored = await self.action(ws, "login", username="DSBATTLERESUME", password=PASSWORD)
            self.assertEqual(expected, {key: restored[key] for key in expected})
            command = self.battle_fields(restored, "guard")
            changed = await self.action(ws, "battle", **command)
            self.assertTrue(any(event.get("kind") in ("guard", "damage", "message")
                                for event in changed["events"]))
            await self.rejected(ws, "dsbattleresume", "battle", **command)
            persisted, _ = self.db.load("dsbattleresume")
            self.assertEqual(changed["battle"], persisted["battle"])
            self.assertEqual(changed["story"], persisted["story"])


if __name__ == "__main__":
    unittest.main()
