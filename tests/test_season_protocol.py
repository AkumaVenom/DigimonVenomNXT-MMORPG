"""Private career acceptance tests over the real server, engine and SQLite saves.

Every player result below comes from ordinary battle-control requests. These tests
never submit a winner, call settlement directly, or substitute replay combat.
"""
import asyncio
import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from venom.common.game import GameEngine
from venom.server.database import Database
from venom.server.main import WorldServer


ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "season-protocol-password-123"


class SeasonProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.tmp.name) / "season.sqlite3")
        self.rid = 0
        await self.start_server()

    async def start_server(self):
        self.db = Database({"driver": "sqlite", "path": self.database_path}, dev=True)
        self.db.initialize()
        self.engine = GameEngine(ROOT, seed=317)
        self.world = WorldServer(self.engine, self.db, {
            "allow_registration": True,
            "rivals": {"enabled": False, "count": 0},
        })
        self.listener = await serve(self.world.connection, "127.0.0.1", 0, max_size=65536)
        self.url = f"ws://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}"

    async def stop_server(self):
        self.listener.close()
        await self.listener.wait_closed()
        if self.world.community:
            await asyncio.to_thread(self.world.community.shutdown)
        self.db.close()

    async def asyncTearDown(self):
        await self.stop_server()
        self.tmp.cleanup()

    def connection(self):
        return connect(self.url, max_size=8 * 1024 * 1024)

    async def receive(self, ws, op, rid=None):
        while True:
            result = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if result.get("op") == op and (rid is None or result.get("rid") == rid):
                return result

    async def request(self, ws, op, **fields):
        # Stay within the unchanged production action limiter, including rejection
        # scenarios; a rate-limit error must never masquerade as validation.
        if op in {"season", "battle", "digifarm", "digilab", "encounter", "travel", "party"}:
            await asyncio.sleep(0.175)
        self.rid += 1
        await ws.send(json.dumps({"op": op, "rid": self.rid, **fields}))
        return await self.receive(ws, "result", self.rid)

    async def action(self, ws, op, **fields):
        response = await self.request(ws, op, **fields)
        self.assertTrue(response["ok"], response)
        return response.get("state")

    async def register(self, ws, username):
        self.assertEqual("hello", (await self.receive(ws, "hello"))["op"])
        return await self.action(ws, "register", username=username, password=PASSWORD,
                                 tamer=next(iter(self.engine.tamers)), starter=self.engine.starters[0])

    async def enter(self, ws, username):
        await self.register(ws, username)
        state = await self.action(ws, "season", action="enter")
        self.assertTrue(state["in_season"])
        self.assertEqual("ready", state["season"]["phase"])
        matches = state["season"]["card"]["matches"]
        self.assertEqual(1, sum(bool(match["is_player"]) for match in matches))
        self.assertTrue(all(match.get("winner_id") is None for match in matches))
        return state

    async def start_match(self, ws, state):
        state = await self.action(ws, "season", action="start", token=state["season"]["card"]["token"])
        self.assertEqual("battle", state["season"]["phase"])
        self.assertEqual("season", state["battle"]["kind"])
        self.assertTrue(state["battle"]["season"])
        self.assertIsInstance(state["battle"]["actor"], int)
        return state

    @staticmethod
    def battle_fields(state, action="attack", **fields):
        return {"action": action, "battle_id": state["battle"]["id"],
                "expected_turn": state["battle"]["turn"], **fields}

    async def finish_match(self, ws, state):
        controls = 0
        player_damage = False
        while state.get("battle") and controls < 150:
            battle = state["battle"]
            actor = state["party"][battle["actor"]]
            target = next(i for i, enemy in enumerate(battle["enemies"]) if enemy["hp"] > 0)
            # Exercise the exact native controls. Either an honestly played win
            # or loss is a valid league result; no HP or outcome is fabricated.
            if actor["hp"] < actor["max_hp"] // 2 and state["inventory"].get("hp_s", 0):
                command = self.battle_fields(state, "item", item="hp_s", party_index=battle["actor"])
            elif actor["sp"] >= actor["skills"][0]["sp"]:
                command = self.battle_fields(state, "skill", skill_index=0, target=target)
            else:
                command = self.battle_fields(state, "attack", target=target)
            self.last_match_command = copy.deepcopy(command)
            state = await self.action(ws, "battle", **command)
            player_damage |= any(event.get("kind") == "damage" and event.get("attacker_side") == "player"
                                 for event in state["events"])
            controls += 1
        self.assertGreater(controls, 0, "The server must wait for human fight controls")
        self.assertTrue(player_damage, "A real player attack must reach the authoritative combat engine")
        self.assertIsNone(state.get("battle"), "The ordinary interactive fixture must reach a result")
        self.assertEqual("results", state["season"]["phase"])
        self.assertTrue(all(match.get("winner_id") for match in state["season"]["card"]["matches"]))
        return state

    async def assert_rejected_without_change(self, ws, account_key, op, **fields):
        before, revision = self.db.load(account_key)
        response = await self.request(ws, op, **fields)
        self.assertFalse(response["ok"], response)
        self.assertNotIn("between actions", response.get("error", ""), response)
        after, new_revision = self.db.load(account_key)
        self.assertEqual(revision, new_revision)
        self.assertEqual(before, after)
        return response

    async def wait_for_logout(self, username):
        for _ in range(100):
            if username.lower() not in self.world.sessions:
                return
            await asyncio.sleep(0.01)
        self.fail("The server did not release the disconnected player's session")

    def ranked_snapshot(self):
        tables = ("venom_ranked_seasons", "venom_ranked_records", "venom_ranked_matches",
                  "venom_ranked_rewards", "venom_rival_matches", "venom_rival_history")
        snapshot = {table: sorted(self.db.connection.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
                    for table in tables}
        snapshot["competitor_records"] = self.db.connection.execute(
            "SELECT id,career_wins,career_losses,career_rating,digirubies,energy,last_attack "
            "FROM venom_competitors ORDER BY id").fetchall()
        return snapshot

    async def test_human_fixture_week_history_and_ranked_isolation(self):
        await self.world.initialize_community()
        async with self.connection() as alice, self.connection() as bob:
            state = await self.enter(alice, "SeasonAlice")
            bob_state = await self.enter(bob, "SeasonBob")
            bob_career = copy.deepcopy(bob_state["season"])
            bob_saved, bob_revision = self.db.load("seasonbob")
            ranked_before = self.ranked_snapshot()
            first_card = copy.deepcopy(state["season"]["card"])
            first_week = int(state["season"]["week"])
            self.assertEqual(0, state["season"]["elapsed_days"])
            self.assertEqual(("Monday", 1, "January", 1), tuple(state["season"]["calendar"][key]
                for key in ("weekday", "day", "month_name", "year")))

            await self.assert_rejected_without_change(alice, "seasonalice", "season", action="start",
                                                      token=bob_state["season"]["card"]["token"])
            await self.assert_rejected_without_change(alice, "seasonalice", "community", action="overview")

            # A completed match cannot be invented by client-supplied results.
            await self.assert_rejected_without_change(alice, "seasonalice", "season", action="next",
                token=first_card["token"], winner_id="player", result="win", username="SeasonBob")
            state = await self.start_match(alice, state)
            self.assertEqual(1, state["season"]["elapsed_days"])
            state = await self.finish_match(alice, state)
            self.assertEqual(6, state["season"]["elapsed_days"])
            completed = copy.deepcopy(state["season"])
            completed_card = copy.deepcopy(completed["card"])
            await self.assert_rejected_without_change(alice, "seasonalice", "battle", **self.last_match_command)

            await self.assert_rejected_without_change(alice, "seasonalice", "season", action="start",
                                                      token=first_card["token"])
            state = await self.action(alice, "season", action="next", token=first_card["token"])
            self.assertEqual("ready", state["season"]["phase"])
            self.assertNotEqual(first_card["token"], state["season"]["card"]["token"])
            self.assertEqual(first_week + 1, int(state["season"]["week"]))
            self.assertEqual(7, state["season"]["elapsed_days"])
            self.assertNotIn("_season_archive_pending", state)
            await self.assert_rejected_without_change(alice, "seasonalice", "season", action="next",
                                                      token=first_card["token"])

            history = await self.request(alice, "season", action="history", page=0, page_size=1)
            self.assertTrue(history["ok"], history)
            archive = history["season_history"]
            self.assertEqual(1, len(archive["items"]))
            self.assertEqual(first_week, int(archive["items"][0]["week"]))
            self.assertFalse(archive["has_more"])
            self.assertIn(first_card["token"], json.dumps(archive["items"][0]))
            self.assertTrue(all(match["winner_id"] for match in completed_card["matches"]))
            empty_page = await self.request(alice, "season", action="history", page=1, page_size=1)
            self.assertTrue(empty_page["ok"], empty_page)
            self.assertEqual([], empty_page["season_history"]["items"])

            # History ownership always comes from the authenticated connection.
            foreign = await self.request(bob, "season", action="history", username="SeasonAlice",
                                         owner="seasonalice", page=0, page_size=1)
            self.assertTrue(foreign["ok"], foreign)
            self.assertEqual([], foreign["season_history"]["items"])
            self.assertEqual((bob_saved, bob_revision), self.db.load("seasonbob"))
            self.assertEqual(bob_career, self.world.sessions["seasonbob"].state["season"])
            self.assertEqual(ranked_before, self.ranked_snapshot())

    async def test_no_autoplay_flee_forged_match_or_stale_turn(self):
        async with self.connection() as ws:
            state = await self.enter(ws, "SeasonControls")
            token = state["season"]["card"]["token"]
            await self.assert_rejected_without_change(ws, "seasoncontrols", "season", action="start", token="forged")
            state = await self.start_match(ws, state)
            before = copy.deepcopy(state)

            # Waiting, world broadcasts, pings and archive reads never play our turn.
            await asyncio.sleep(0.2)
            await self.world.broadcast_once()
            self.assertTrue((await self.request(ws, "ping"))["ok"])
            self.assertTrue((await self.request(ws, "season", action="history"))["ok"])
            saved, _ = self.db.load("seasoncontrols")
            self.assertEqual(before["battle"], saved["battle"])
            self.assertEqual(before["party"], saved["party"])
            self.assertEqual(before["season"], saved["season"])

            for op, fields in (
                ("battle", self.battle_fields(state, "flee")),
                ("battle", {"action": "attack", "target": 0}),
                ("battle", {**self.battle_fields(state, target=0), "battle_id": "foreign-battle"}),
                ("battle", {**self.battle_fields(state, target=0), "expected_turn": -1}),
                ("season", {"action": "return"}),
                ("season", {"action": "next", "token": token}),
                ("season", {"action": "finish", "token": token, "winner_id": "player"}),
                ("digifarm", {"action": "enter", "forfeit": True}),
                ("digilab", {"action": "enter"}),
                ("encounter", {}),
            ):
                await self.assert_rejected_without_change(ws, "seasoncontrols", op, **fields)

            command = self.battle_fields(state, "guard")
            state = await self.action(ws, "battle", **command)
            self.assertIsNotNone(state["battle"])
            self.assertGreater(state["battle"]["turn"], before["battle"]["turn"])
            await self.assert_rejected_without_change(ws, "seasoncontrols", "battle", **command)
            self.assertEqual(token, state["season"]["card"]["token"])

    async def test_restart_restores_exact_live_battle_and_career_then_continues(self):
        async with self.connection() as ws:
            state = await self.enter(ws, "SeasonResume")
            state = await self.start_match(ws, state)
            state = await self.action(ws, "battle", **self.battle_fields(state, "guard"))
            expected = {key: copy.deepcopy(state[key]) for key in ("season", "party", "battle", "in_season")}
            self.assertIsNotNone(expected["battle"])
            self.assertTrue(expected["battle"]["queue"])
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout("seasonresume")

        # Reopen the on-disk database in a completely new server and engine.
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            # A three-year wall-clock jump changes audit time, never league time.
            with patch("venom.server.main.time.time", return_value=time.time() + 3 * 365 * 86400):
                restored = await self.action(ws, "login", username="SEASONRESUME", password=PASSWORD)
            self.assertEqual(expected, {key: restored[key] for key in expected})
            restored = await self.finish_match(ws, restored)
            settled = copy.deepcopy(restored["season"])
            await self.action(ws, "season", action="return")
            continued = await self.action(ws, "season", action="enter")
            self.assertEqual(settled, continued["season"])
            saved, _ = self.db.load("seasonresume")
            self.assertEqual(settled, saved["season"])

    async def test_private_place_blocks_world_movement_and_restores_world(self):
        async with self.connection() as alice, self.connection() as bob:
            await self.register(alice, "PrivateAlice")
            await self.register(bob, "PrivateBob")
            field = await self.action(alice, "digifarm", action="return")
            await self.action(bob, "digifarm", action="return")
            position = {key: field[key] for key in ("map_id", "x", "y", "in_farm", "in_lab")}
            state = await self.action(alice, "season", action="enter")
            career = copy.deepcopy(state["season"])
            alice_session = self.world.sessions["privatealice"]
            bob_session = self.world.sessions["privatebob"]
            self.assertFalse(self.world.same_place(alice_session, bob_session))
            await self.world.broadcast_once()
            world = await self.receive(bob, "world")
            self.assertNotIn("PrivateAlice", {player["username"] for player in world["players"]})
            movement = await self.request(alice, "move", dx=1, dy=0, dt=0.1)
            self.assertTrue(movement["ok"], movement)
            self.assertEqual(position, {key: alice_session.state[key] for key in position})
            self.assertEqual(career, alice_session.state["season"])
            restored = await self.action(alice, "season", action="return")
            self.assertFalse(restored["in_season"])
            self.assertEqual(position, {key: restored[key] for key in position})
            self.assertTrue(self.world.same_place(alice_session, bob_session))
            returned = await self.action(alice, "season", action="enter")
            self.assertEqual(career, returned["season"])


if __name__ == "__main__":
    unittest.main()
