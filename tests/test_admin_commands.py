"""Console regression boundaries: commit visibility, bans and confirmation scope."""
import asyncio
import copy
import json
import re
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from venom.common.game import GameEngine
from venom.server.admin_commands import AdminConsole
from venom.server.database import Database, DatabaseError
from venom.server.main import Session, WorldServer


ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "console-boundary-test-password"


class LocalSocket:
    """Only transports output; commands still enter the real local dispatcher."""
    def __init__(self):
        self.packets = []
        self.closed = []

    async def send(self, encoded):
        self.packets.append(json.loads(encoded))

    async def close(self, code, reason):
        self.closed.append((code, reason))


class AdminCommandBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
        self.db.initialize()
        self.engine = GameEngine(ROOT, seed=881)
        self.world = WorldServer(self.engine, self.db, {"rivals": {"enabled": False, "count": 0}})
        self.console = AdminConsole(self.world)
        self.world_packets = []
        # Exercise real snapshot construction without starting a permanent
        # world sender; these tests intentionally control commit scheduling.
        self.world._queue_world = lambda session, group, encoded: self.world_packets.append(json.loads(encoded))

    async def asyncTearDown(self):
        await self.console.close()
        if self.world.community:
            self.world.community.shutdown()
        self.db.close()

    def player(self, name="Alice", online=False):
        state = self.engine.new_player(name, next(iter(self.engine.tamers)), self.engine.starters[0])
        state["in_farm"] = False
        self.db.register(name, PASSWORD, state)
        if not online:
            return state
        token = "live-session-" + name.lower()
        self.assertTrue(self.db.acquire_session(name, token))
        session = Session(LocalSocket(), name.lower(), token, copy.deepcopy(state), 0)
        self.world.sessions[session.key] = session
        return session

    async def command(self, line, **kwargs):
        result = await self.console.execute(line, **kwargs)
        self.assertFalse(result.startswith(("ERROR:", "DENIED:")), result)
        return result

    @staticmethod
    def token(output):
        found = re.search(r"/confirm ([0-9a-f]+)", output)
        assert found, output
        return found.group(1)

    async def _commit_visibility(self, fail):
        session = self.player(online=True)
        old_state = session.state
        before = copy.deepcopy(old_state)
        await self.command('/addtitle "Digital Champion"')
        entered, finish = asyncio.Event(), asyncio.Event()
        original_save = self.world.save

        async def slow_save(proposed):
            self.assertIsNot(proposed, session)
            self.assertIsNot(proposed.state, session.state)
            self.assertEqual("Digital Champion", proposed.state["active_title"])
            entered.set()
            await finish.wait()
            if fail:
                raise DatabaseError("Injected commit failure")
            await original_save(proposed)

        with patch.object(self.world, "save", side_effect=slow_save):
            action = asyncio.create_task(self.console.execute('/settitle Alice "Digital Champion"'))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                # This snapshot runs while the admin command is suspended in
                # its save. It deliberately does not acquire Session.lock.
                await self.world.broadcast_once()
                self.assertEqual("", self.world_packets[-1]["players"][0]["active_title"])
                self.assertIs(old_state, session.state)
                self.assertEqual(before, session.state)
                self.assertEqual(0, self.db.load("alice")[1])
                self.assertFalse(session.websocket.packets)
            finally:
                finish.set()
                result = await asyncio.wait_for(action, 3)
        await self.world.broadcast_once()
        if fail:
            self.assertTrue(result.startswith("ERROR:"), result)
            self.assertIs(old_state, session.state)
            self.assertEqual(before, session.state)
            self.assertEqual(0, session.revision)
            self.assertEqual("", self.world_packets[-1]["players"][0]["active_title"])
            self.assertFalse(session.websocket.packets)
        else:
            self.assertFalse(result.startswith("ERROR:"), result)
            self.assertEqual("Digital Champion", session.state["active_title"])
            self.assertEqual(1, session.revision)
            self.assertEqual("Digital Champion", self.db.load("alice")[0]["active_title"])
            self.assertEqual("Digital Champion", self.world_packets[-1]["players"][0]["active_title"])
            self.assertEqual("Digital Champion", session.websocket.packets[0]["state"]["active_title"])

    async def test_live_candidate_is_invisible_until_commit(self):
        await self._commit_visibility(fail=False)

    async def test_failed_candidate_is_never_visible_to_snapshots_or_client(self):
        await self._commit_visibility(fail=True)

    async def test_persisted_ban_closes_session_even_if_checkpoint_fails(self):
        session = self.player(online=True)
        before = copy.deepcopy(session.state)
        with patch.object(self.world, "save", new=AsyncMock(side_effect=DatabaseError("Injected checkpoint failure"))):
            result = await self.command('/ban Alice permanent "Moderation boundary test"')
        self.assertIn("checkpoint failed", result)
        self.assertTrue(session.closing)
        self.assertEqual(1008, session.websocket.closed[-1][0])
        self.assertIsNone(self.console.store.ban_status("alice")["until"])
        self.assertEqual(before, self.db.load("alice")[0])
        self.assertEqual(0, session.revision)
        # The failing forced checkpoint must not drop lease protection before
        # the normal disconnection path can retry the final save.
        self.assertFalse(self.db.acquire_session("alice", "other-world"))
        with self.assertRaisesRegex(ValueError, "banned"):
            await self.world.check_ban("alice")

    async def test_delete_invalidates_all_prior_confirmations_before_name_reuse(self):
        self.player()
        first = self.token(await self.command("/deleteaccount Alice"))
        second = self.token(await self.command("/deleteaccount Alice"))
        clear_bag = self.token(await self.command("/clearinventory Alice"))
        await self.command("/confirm " + first)
        self.assertFalse(self.console.pending)
        await self.command("/createaccount Alice", password=PASSWORD)
        fresh = self.db.load("alice")
        self.assertEqual(0, fresh[1])
        for token in (second, clear_bag, first):
            output = await self.console.execute("/confirm " + token)
            self.assertTrue(output.startswith("ERROR:"), output)
            self.assertEqual(fresh, self.db.load("alice"))

    async def test_delete_clears_real_ranked_caches_and_only_target_invitations(self):
        states = [self.player(name) for name in ("Alice", "Bobby", "Cedric")]
        await self.world.initialize_community()
        community = self.world.community
        ranked = community.ranked
        for state in states:
            community.register_player(state)
        season = ranked.tick()["id"]
        with community.store.transaction() as cursor:
            cursor.execute(self.db._sql("INSERT INTO venom_ranked_records(season_id,participant_id,points,wins) VALUES (?,?,?,?)"),
                           (season, "player:alice", 20, 1))
        self.assertIn("player:alice", [p["id"] for p in ranked.available_opponents("player:bobby")])
        self.assertIn("player:alice", [p["id"] for p in ranked.leaderboard()["entries"]])
        self.assertTrue(ranked._power_order)
        self.assertTrue(ranked._standings_cache)
        community.challenges = {
            "deleted-offer": {"player_id": "player:alice", "expires_at": time.time() + 180},
            "kept-offer": {"player_id": "player:bobby", "expires_at": time.time() + 180},
        }
        community.next_invite = {"player:alice": 123, "player:bobby": 456}
        token = self.token(await self.command("/deleteaccount Alice"))
        await self.command("/confirm " + token)

        self.assertNotIn("player:alice", ranked.profiles)
        self.assertNotIn("player:alice", community.next_invite)
        self.assertEqual(456, community.next_invite["player:bobby"])
        self.assertEqual({"kept-offer"}, set(community.challenges))
        # The first post-deletion lookup must rebuild immediately; retaining
        # an old power index would crash here rather than merely show a ghost.
        opponents = ranked.available_opponents("player:bobby")
        self.assertEqual({"player:cedric"}, {p["id"] for p in opponents})
        self.assertNotIn("player:alice", ranked._indexed_ids)
        self.assertFalse(ranked.leaderboard()["entries"])
        with self.assertRaises(DatabaseError):
            self.db.load("alice")
        self.assertEqual(0, self.db.connection.execute(
            "SELECT COUNT(*) FROM venom_competitors WHERE id='player:alice'").fetchone()[0])

    async def test_failed_deletion_keeps_ranked_identity_and_account(self):
        state = self.player()
        other = self.player("Bobby")
        await self.world.initialize_community()
        community = self.world.community
        for player in (state, other):
            community.register_player(player)
        before = community.ranked.available_opponents("player:bobby")
        community.challenges = {"active": {"player_id": "player:alice", "expires_at": time.time() + 180}}
        token = self.token(await self.command("/deleteaccount Alice"))
        with patch.object(self.db, "delete_account", side_effect=DatabaseError("Injected deletion failure")):
            output = await self.console.execute("/confirm " + token)
        self.assertTrue(output.startswith("ERROR:"), output)
        self.assertEqual(state, self.db.load("alice")[0])
        self.assertIn("player:alice", community.ranked.profiles)
        self.assertEqual(before, community.ranked.available_opponents("player:bobby"))
        self.assertIn("active", community.challenges)
        self.assertTrue(self.db.acquire_session("alice", "lease-released-after-failure"))

    async def test_confirmation_expiry_permission_and_revision_are_rechecked(self):
        self.player()
        before = self.db.load("alice")
        expired = self.token(await self.command("/deleteaccount Alice"))
        self.console.pending[expired]["expires"] = time.monotonic() - 1
        self.assertTrue((await self.console.execute("/confirm " + expired)).startswith("ERROR:"))
        self.assertEqual(before, self.db.load("alice"))

        downgraded = self.token(await self.command("/deleteaccount Alice"))
        self.console.role = "ADMIN"
        self.assertTrue((await self.console.execute("/confirm " + downgraded)).startswith("ERROR:"))
        self.assertEqual(before, self.db.load("alice"))
        self.console.role = "OWNER"

        stale = self.token(await self.command("/clearinventory Alice"))
        await self.command("/givemoney Alice 1")
        latest = self.db.load("alice")
        self.assertTrue((await self.console.execute("/confirm " + stale)).startswith("ERROR:"))
        self.assertEqual(latest, self.db.load("alice"))


if __name__ == "__main__":
    unittest.main()
