"""Local administration acceptance against real engine, SQLite and WebSockets.

Only the local AdminConsole invokes commands. Clients send ordinary game packets
or malicious packets to verify that network traffic cannot obtain console powers.
"""
import asyncio
import copy
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from venom.common.game import GameEngine, SHOP
from venom.server.admin_commands import AdminConsole
from venom.server.database import Database, DatabaseError
from venom.server.main import WorldServer


ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "local-admin-acceptance-password"


class AdminProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.tmp.name) / "admin.sqlite3")
        self.rid = 0
        self.buffer = {}
        await self.start_server()

    async def start_server(self):
        self.db = Database({"driver": "sqlite", "path": self.database_path}, dev=True)
        self.db.initialize()
        self.engine = GameEngine(ROOT, seed=937)
        self.world = WorldServer(self.engine, self.db, {"allow_registration": True})
        self.console = AdminConsole(self.world)
        self.listener = await serve(self.world.connection, "127.0.0.1", 0, max_size=65536)
        self.url = f"ws://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}"

    async def stop_server(self):
        await self.console.close()
        self.listener.close()
        await self.listener.wait_closed()
        self.db.close()

    async def asyncTearDown(self):
        await self.stop_server()
        self.tmp.cleanup()

    def connection(self):
        return connect(self.url, max_size=8 * 1024 * 1024)

    async def receive(self, ws, op, rid=None, kind=None):
        def matches(packet):
            return (packet.get("op") == op and
                    (rid is None or packet.get("rid") == rid) and
                    (kind is None or packet.get("kind") == kind))
        pending = self.buffer.setdefault(ws, [])
        for index, packet in enumerate(pending):
            if matches(packet):
                return pending.pop(index)
        while True:
            packet = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if matches(packet):
                return packet
            pending.append(packet)

    async def request(self, ws, op, **fields):
        self.rid += 1
        rid = self.rid
        await ws.send(json.dumps({"op": op, "rid": rid, **fields}))
        return await self.receive(ws, "result", rid)

    async def action(self, ws, op, **fields):
        result = await self.request(ws, op, **fields)
        self.assertTrue(result["ok"], result)
        return result.get("state")

    async def register(self, ws, username):
        await self.receive(ws, "hello")
        return await self.action(ws, "register", username=username, password=PASSWORD,
                                 tamer=next(iter(self.engine.tamers)), starter=self.engine.starters[0])

    async def login(self, ws, username, password=PASSWORD):
        await self.receive(ws, "hello")
        return await self.request(ws, "login", username=username, password=password)

    async def command(self, line, **kwargs):
        result = await self.console.execute(line, **kwargs)
        self.assertFalse(result.startswith(("ERROR:", "DENIED:")), result)
        return result

    def create_offline(self, username):
        state = self.engine.new_player(username, next(iter(self.engine.tamers)), self.engine.starters[0])
        self.db.register(username, PASSWORD, state)
        return state

    @staticmethod
    def confirmation(output):
        return re.search(r"/confirm ([0-9a-f]+)", output).group(1)

    async def test_console_readonly_tier_and_network_packets_have_no_admin_authority(self):
        async with self.connection() as ws:
            original = await self.register(ws, "Observer")
            low = AdminConsole(self.world, role="PLAYER")
            try:
                self.assertIn("650", await low.execute("/balance Observer"))
                self.assertIn("Observer", await low.execute("/team Observer"))
                for line in ("/givemoney Observer 100", "/settitle Observer Owner", "/ban Observer permanent test"):
                    self.assertTrue((await low.execute(line)).startswith("DENIED:"))
            finally:
                await low.close()
            for op in ("admin", "console", "givemoney"):
                response = await self.request(ws, op, command="/givemoney Observer 9999", role="OWNER")
                self.assertFalse(response["ok"], response)
            response = await self.request(ws, "chat", text="/givemoney Observer 9999")
            self.assertFalse(response["ok"], response)
            self.assertIn("local world-server console", response["error"])
            saved, revision = self.db.load("observer")
            self.assertEqual(original["credits"], saved["credits"])
            self.assertEqual(0, revision)
            self.assertFalse(self.console.store.ban_status("observer"))

    async def test_offline_mutation_uses_lease_and_survives_world_restart(self):
        self.create_offline("Offline")
        self.assertTrue(self.db.acquire_session("offline", "different-world"))
        blocked = await self.console.execute("/givemoney Offline 99")
        self.assertTrue(blocked.startswith("ERROR:"), blocked)
        self.assertEqual((650, 0), (self.db.load("offline")[0]["credits"], self.db.load("offline")[1]))
        self.db.release_session("offline", "different-world")
        await self.command("/givemoney Offline 99")
        self.assertTrue(self.db.acquire_session("offline", "lease-was-released"))
        self.db.release_session("offline", "lease-was-released")
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            result = await self.login(ws, "OFFLINE")
            self.assertTrue(result["ok"], result)
            self.assertEqual(749, result["state"]["credits"])

    async def test_online_grant_serializes_with_gameplay_and_pushes_authoritative_state(self):
        async with self.connection() as ws:
            original = await self.register(ws, "Concurrent")
            # Both operations change credits and commit a revision, so a stale
            # snapshot or missing lock loses one change regardless of order.
            purchase, grant = await asyncio.gather(
                self.request(ws, "shop", item="hp_s", quantity=1),
                self.console.execute("/givemoney Concurrent 77"))
            self.assertTrue(purchase["ok"], purchase)
            self.assertFalse(grant.startswith("ERROR:"), grant)
            update = await self.receive(ws, "result", rid=0)
            self.assertTrue(update["ok"])
            self.assertIn("state", update)
            saved, revision = self.db.load("concurrent")
            self.assertEqual(original["credits"] + 77 - SHOP["hp_s"]["price"], saved["credits"])
            self.assertEqual(original["inventory"]["hp_s"] + 1, saved["inventory"]["hp_s"])
            self.assertEqual(2, revision)
            self.assertEqual(saved["credits"], self.world.sessions["concurrent"].state["credits"])
            self.assertEqual(revision, self.world.sessions["concurrent"].revision)

    async def test_failed_admin_commit_rolls_back_live_state_and_preserves_other_accounts(self):
        self.create_offline("Other")
        async with self.connection() as ws:
            await self.register(ws, "Rollback")
            session = self.world.sessions["rollback"]
            original = copy.deepcopy(session.state)
            with patch.object(self.db, "save", side_effect=DatabaseError("synthetic failure")):
                output = await self.console.execute("/givemoney Rollback 50")
            self.assertTrue(output.startswith("ERROR:"), output)
            self.assertEqual(original, session.state)
            self.assertEqual(0, session.revision)
            self.assertEqual(650, self.db.load("rollback")[0]["credits"])
            self.assertEqual(650, self.db.load("other")[0]["credits"])
            await self.action(ws, "ping")
            self.assertFalse(any(p.get("rid") == 0 for p in self.buffer[ws]))

    async def test_broadcast_and_warning_reach_private_farm_and_season(self):
        async with self.connection() as farm, self.connection() as season, self.connection() as field:
            await self.register(farm, "Farmer")
            await self.register(season, "Career")
            await self.register(field, "Explorer")
            career = await self.action(season, "season", action="enter")
            await self.action(field, "digifarm", action="return")
            self.assertTrue(career["in_season"])
            self.assertEqual(3, len({self.world.place(s) for s in self.world.sessions.values()}))
            result = await self.command('/broadcast "Server maintenance after this match"')
            self.assertIn("3", result)
            for socket in (farm, season, field):
                notice = await self.receive(socket, "notice", kind="broadcast")
                self.assertEqual("Server maintenance after this match", notice["text"])
            await self.command('/warn Career "Keep account credentials private"')
            notice = await self.receive(season, "notice", kind="warning")
            self.assertEqual("Keep account credentials private", notice["text"])
            self.assertIn("Keep account credentials private", await self.command("/warnings Career"))
            self.assertEqual(career["season"], self.world.sessions["career"].state["season"])

    async def test_ban_disconnects_and_persists_with_real_time_expiry(self):
        async with self.connection() as ws:
            await self.register(ws, "Banned")
            await self.command('/ban Banned 1h "Acceptance moderation"')
            await ws.wait_closed()
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            denied = await self.login(ws, "Banned")
            self.assertFalse(denied["ok"])
            self.assertIn("banned", denied["error"])
        # Move only the real moderation expiry; no waiting or fictional time.
        self.console.store.set_ban("banned", time.time() - 1, "Expired moderation")
        async with self.connection() as ws:
            accepted = await self.login(ws, "Banned")
            self.assertTrue(accepted["ok"], accepted)
        await self.command("/unban Banned")
        self.assertIsNone(self.console.store.ban_status("banned"))

    async def test_clear_inventory_confirmation_tracks_revision_expiry_and_single_use(self):
        async with self.connection() as ws:
            await self.register(ws, "Clearer")
            first = self.confirmation(await self.command("/clearinventory Clearer"))
            await self.command("/giveitem Clearer hp_s 1")
            denied = await self.console.execute("/confirm " + first)
            self.assertTrue(denied.startswith("ERROR:"), denied)
            self.assertIn("save changed", denied)
            self.assertEqual(6, self.db.load("clearer")[0]["inventory"]["hp_s"])
            expired = self.confirmation(await self.command("/clearinventory Clearer"))
            self.console.pending[expired]["expires"] = time.monotonic() - 1
            self.assertIn("expired", await self.console.execute("/confirm " + expired))
            valid = self.confirmation(await self.command("/clearinventory Clearer"))
            await self.command("/confirm " + valid)
            self.assertFalse(any(self.db.load("clearer")[0]["inventory"].values()))
            self.assertIn("expired", await self.console.execute("/confirm " + valid))

    async def test_delete_account_requires_offline_confirmation_and_cleans_private_history(self):
        self.create_offline("Deleted")
        self.create_offline("Survivor")
        state, revision = self.db.load("deleted")
        state["_season_archive_pending"] = [{"week": 1, "matches": [], "fixture": "own-history"}]
        self.db.save("deleted", state, revision)
        self.console.store.add_warning("deleted", "Test warning")
        async with self.connection() as ws:
            self.assertTrue((await self.login(ws, "Deleted"))["ok"])
            self.assertIn("offline", await self.console.execute("/deleteaccount Deleted"))
        await self.stop_server()
        await self.start_server()
        token = self.confirmation(await self.command("/deleteaccount Deleted"))
        self.assertTrue(self.db.acquire_session("deleted", "other-owner"))
        self.assertIn("leased", await self.console.execute("/confirm " + token))
        self.assertEqual(1, len(self.db.season_history("deleted")["items"]))
        self.db.release_session("deleted", "other-owner")
        token = self.confirmation(await self.command("/deleteaccount Deleted"))
        await self.command("/confirm " + token)
        self.assertIsNone(self.db.authenticate("deleted", PASSWORD))
        with self.assertRaises(DatabaseError):
            self.db.load("deleted")
        self.assertEqual([], self.db.season_history("deleted")["items"])
        self.assertEqual(650, self.db.load("survivor")[0]["credits"])
        self.assertEqual(0, self.db.connection.execute("SELECT count(*) FROM venom_admin_warnings WHERE username='deleted'").fetchone()[0])

    async def test_titles_persist_and_reach_self_and_other_world_snapshots(self):
        async with self.connection() as titled, self.connection() as observer:
            await self.register(titled, "Champion")
            await self.register(observer, "Witness")
            await self.action(titled, "digifarm", action="return")
            await self.action(observer, "digifarm", action="return")
            await self.command('/addtitle "Digital Vanguard"')
            await self.command('/settitle Champion "Digital Vanguard"')
            pushed = await self.receive(titled, "result", rid=0)
            self.assertEqual("Digital Vanguard", pushed["state"]["active_title"])
            self.assertEqual("Champion", pushed["state"]["username"])
            await self.world.broadcast_once()
            for socket in (titled, observer):
                snapshot = await self.receive(socket, "world")
                champion = next(p for p in snapshot["players"] if p["username"] == "Champion")
                self.assertEqual("Digital Vanguard", champion["active_title"])
            forged = await self.request(titled, "settitle", title="Owner", player="Champion")
            self.assertFalse(forged["ok"])
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            result = await self.login(ws, "Champion")
            self.assertEqual("Digital Vanguard", result["state"]["active_title"])
            self.assertIn("Digital Vanguard", result["state"]["titles"])
        self.assertIn("Digital Vanguard", await self.command("/titles"))

    async def test_password_commands_never_echo_or_audit_credentials(self):
        first_secret, second_secret = "Never-log-this-secret-938", "Hidden-reset-secret-522"
        with self.assertNoLogs("venom.admin", level="ERROR"):
            outputs = [await self.console.execute("/createaccount SecretUser " + first_secret),
                       await self.command("/createaccount SecretUser", password=first_secret),
                       await self.command("/resetpassword SecretUser", password=second_secret)]
            with patch.object(self.db, "reset_password", side_effect=ValueError(second_secret)):
                outputs.append(await self.console.execute("/resetpassword SecretUser", password=second_secret))
        self.assertTrue(outputs[0].startswith("ERROR:"))
        # Neither successful commands, usage errors nor dependency errors may
        # expose a password submitted through the hidden input path.
        audit = json.dumps(self.db.connection.execute("SELECT * FROM venom_admin_audit").fetchall())
        for secret in (first_secret, second_secret):
            self.assertNotIn(secret, "\n".join(outputs))
            self.assertNotIn(secret, audit)
        self.assertIsNone(self.db.authenticate("SecretUser", first_secret))
        self.assertEqual("secretuser", self.db.authenticate("SecretUser", second_secret))

    async def test_jail_blocks_escapes_and_resumes_exact_season_battle_after_restart(self):
        async with self.connection() as ws:
            await self.register(ws, "Detained")
            career = await self.action(ws, "season", action="enter")
            battle = await self.action(ws, "season", action="start", token=career["season"]["card"]["token"])
            before = copy.deepcopy(battle)
            await self.command('/jail Detained 1h "Paused safely"')
            jailed = (await self.receive(ws, "result", rid=0))["state"]
            self.assertIsNone(jailed["battle"])
            self.assertEqual("jail", self.world.place(self.world.sessions["detained"])[1])
            for op, fields in (("season", {"action": "leave"}), ("digifarm", {"action": "enter"}),
                               ("digilab", {"action": "enter"}), ("battle", {"action": "flee"}),
                               ("travel", {"map_id": before["map_id"]})):
                response = await self.request(ws, op, **fields)
                self.assertFalse(response["ok"], response)
                self.assertIn("holding cell", response["error"])
            await self.action(ws, "move", dx=1, dy=0, dt=0.1)
            self.assertEqual(jailed["x"], self.world.sessions["detained"].state["x"])
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            result = await self.login(ws, "Detained")
            self.assertTrue(result["state"]["admin_jail"])
            await self.command("/unjail Detained")
            released = (await self.receive(ws, "result", rid=0))["state"]
            self.assertNotIn("admin_jail", released)
            self.assertEqual(before["battle"], released["battle"])
            self.assertEqual(before["season"], released["season"])
            self.assertEqual(before["in_season"], released["in_season"])

    async def test_saveall_and_lifecycle_countdown_cancel_restart(self):
        async with self.connection() as ws:
            await self.register(ws, "Saver")
            self.world.stop_signal = asyncio.Event()
            await self.command("/saveall")
            self.assertEqual(1, self.db.load("saver")[1])
            await self.command("/shutdown 60")
            scheduled = await self.receive(ws, "notice", kind="shutdown")
            self.assertIn("60 seconds", scheduled["text"])
            self.assertIn("already scheduled", await self.console.execute("/restart 0"))
            await self.command("/shutdown cancel")
            self.assertFalse(self.world.stop_signal.is_set())
            await self.command("/restart 0")
            await asyncio.wait_for(self.world.stop_signal.wait(), 1)
            self.assertTrue(self.world.restart_requested)


if __name__ == "__main__":
    unittest.main()
