"""Real WebSocket and SQLite boundaries for the third private campaign."""
from __future__ import annotations

import copy
import unittest

from venom.common import story
import test_story_protocol as harness

CAMPAIGN = "xros_ghostline"
PASSWORD = harness.PASSWORD


class GhostlineProtocolTests(unittest.IsolatedAsyncioTestCase):
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
    battle_fields = staticmethod(harness.StoryProtocolTests.battle_fields)

    async def rejected(self, ws, key, op, **fields):
        before = copy.deepcopy(self.world.sessions[key].state)
        result = await harness.StoryProtocolTests.rejected(self, ws, key, op, **fields)
        self.assertEqual(before, self.world.sessions[key].state)
        return result

    async def enter_ghostline(self, ws, username):
        original = await self.register(ws, username)
        state = await self.action(ws, "story", action="enter", campaign_id=CAMPAIGN)
        self.assertTrue(state["in_story"])
        self.assertEqual(CAMPAIGN, state["story"]["campaign_id"])
        self.assertEqual(original["party"], state["party"])
        self.assertEqual(original["inventory"], state["inventory"])
        self.assertEqual(original["credits"], state["credits"])
        return original, state

    async def accept_first_quest(self, ws):
        state = await self.action(ws, "story", action="travel", chapter=1)
        data = story.content(self.engine, CAMPAIGN)
        quest = next(data["npcs"][ident] for ident in data["regions"][1]["npc_ids"]
                     if data["npcs"][ident]["role"] == "quest")
        state = await self.action(ws, "story", action="talk", npc_id=quest["id"])
        while "next" in {row["id"] for row in state["story"]["view"]["dialogue"]["choices"]}:
            token = state["story"]["view"]["dialogue"]["token"]
            state = await self.action(ws, "story", action="dialogue", token=token, choice="next")
        token = state["story"]["view"]["dialogue"]["token"]
        state = await self.action(ws, "story", action="dialogue", token=token, choice="accept_quest")
        self.assertIn(quest["id"], state["story"]["quest_accepted"])
        return state, quest, token

    async def test_two_real_clients_have_private_npcs_progress_chat_and_no_world_bots(self):
        # Run actual persisted rivals while both humans enter identical artwork.
        # The server's CommunityManager reads config at initialization.
        self.world.config["rivals"] = {"enabled": True, "count": 2, "seed": 1410}
        await self.world.initialize_community()
        self.assertTrue(self.world.community.ready)
        self.assertEqual(2, len(self.world.community.bots.bots))
        async with self.connection() as alice, self.connection() as bob:
            await self.enter_ghostline(alice, "GhostAlice")
            await self.enter_ghostline(bob, "GhostBob")
            a, b = self.world.sessions["ghostalice"], self.world.sessions["ghostbob"]
            self.assertNotEqual(a.state["story"]["id"], b.state["story"]["id"])
            self.assertEqual(a.state["map_id"], b.state["map_id"])
            self.assertFalse(self.world.same_place(a, b))
            self.assertFalse(self.world.shared_profile(a.state))
            before_bob = copy.deepcopy(b.state)
            await self.world.broadcast_once()
            for ws, username in ((alice, "GhostAlice"), (bob, "GhostBob")):
                packet = await self.receive(ws, "world")
                self.assertEqual([username], [row["username"] for row in packet["players"]])
                self.assertFalse(any(row.get("is_bot") for row in packet["players"]))
            await self.action(alice, "chat", text="Private Ghostline investigation")
            self.assertEqual("GhostAlice", (await self.receive(alice, "chat"))["username"])
            await self.request(bob, "ping")
            self.assertFalse(any(row.get("op") == "chat" for row in self.buffer.get(bob, [])))
            await self.accept_first_quest(alice)
            self.assertEqual(before_bob, b.state)
            self.assertEqual([], b.state["story"]["quest_accepted"])
            for op, fields in (("community", {"action": "overview"}),
                               ("community", {"action": "challenge", "bot_id": "forged"}),
                               ("season", {"action": "enter"}),
                               ("travel", {"map_id": a.state["map_id"]})):
                await self.rejected(alice, "ghostalice", op, **fields)

    async def test_forged_quest_proofs_final_boss_and_reward_packets_cannot_change_save(self):
        async with self.connection() as ws:
            _, state = await self.enter_ghostline(ws, "GhostForgery")
            data = story.content(self.engine, CAMPAIGN)
            finale = data["npcs"][data["champion_id"]]
            distant_gate = data["maps"][state["map_id"]]["exits"][0]
            self.assertIsNone(state["story"]["view"]["final_npc_id"])
            self.assertIsNone(state["story"]["champion"]["holder_id"])
            for op, fields in (
                ("story", {"action": "train"}),
                ("encounter", {}),
                ("story", {"action": "travel", "chapter": 2}),
                ("story", {"action": "travel", "chapter": 30}),
                ("story", {"action": "exit", "exit_id": "forged"}),
                ("story", {"action": "exit", "exit_id": distant_gate["id"]}),
                ("story", {"action": "complete", "winner": "player", "revealed": True,
                           "permanent_rewards": {"shiny_scan_mastery": True}}),
                ("story", {"action": "dialogue", "choice": "complete_quest", "token": "forged"}),
                ("story", {"action": "challenge", "npc_id": finale["id"], "token": "forged",
                           "badges": [row["badge"]["id"] for row in data["regions"][1:]]}),
                ("story", {"action": "enter", "campaign_id": "world_ds_paradox"}),
                ("story", {"action": "travel", "chapter": 1, "campaign_id": "dawn_relay"}),
            ):
                await self.rejected(ws, "ghostforgery", op, **fields)
            state, quest, token = await self.accept_first_quest(ws)
            await self.rejected(ws, "ghostforgery", "story", action="dialogue", token=token, choice="accept_quest")
            persisted, _ = self.db.load("ghostforgery")
            self.assertEqual([], persisted["story"]["completed"])
            self.assertEqual([], persisted["story"]["badges"])
            self.assertEqual([], persisted["story"]["hacked"])
            self.assertEqual([quest["id"]], persisted["story"]["quest_accepted"])
            self.assertFalse(persisted["story"]["revealed"])
            self.assertFalse(persisted.get("permanent_rewards", {}).get("shiny_scan_mastery"))

    async def test_actual_restart_keeps_midquest_battle_and_rejects_replayed_turns(self):
        async with self.connection() as ws:
            await self.enter_ghostline(ws, "GhostRestart")
            await self.accept_first_quest(ws)
            state = await self.action(ws, "story", action="train")
            self.assertEqual("story", state["battle"]["kind"])
            self.assertEqual(CAMPAIGN, state["battle"]["story_campaign_id"])
            state = await self.action(ws, "battle", **self.battle_fields(state, "guard"))
            expected = copy.deepcopy({key: state[key] for key in
                ("party", "inventory", "credits", "scan", "battle", "story", "story_return_state",
                 "in_story", "map_id", "x", "y", "in_lab", "in_farm")})
            await self.rejected(ws, "ghostrestart", "battle", action="win", winner="player",
                                battle_id=state["battle"]["id"], expected_turn=state["battle"]["turn"])
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout("ghostrestart")
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            state = await self.action(ws, "login", username="GHOSTRESTART", password=PASSWORD)
            self.assertEqual(expected, {key: state[key] for key in expected})
            command = self.battle_fields(state, "guard")
            changed = await self.action(ws, "battle", **command)
            await self.rejected(ws, "ghostrestart", "battle", **command)
            persisted, _ = self.db.load("ghostrestart")
            self.assertEqual(changed["battle"], persisted["battle"])
            self.assertEqual(changed["story"], persisted["story"])


if __name__ == "__main__":
    unittest.main()
