"""Ownership, relocation and real graceful world-stop regression coverage."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

import pymysql
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from venom.server.database import Database, DatabaseError
from venom.server.lifecycle import (WorldControlError, WorldProcessLock,
                                    is_world_running, read_world_control,
                                    request_world_stop)


class PortableDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="Venom portable ")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def connection(self, directory=None, port=3307):
        connection = MagicMock()
        connection.cursor.return_value.fetchone.return_value = (str(directory or self.root / "mysql/data"), port)
        return connection

    def test_wrong_datadir_cannot_receive_schema_or_save_writes(self):
        connection = self.connection(self.root / "xampp/mysql/data")
        with patch("pymysql.connect", return_value=connection):
            database = Database({"driver": "mysql"}, root=self.root)
            with self.assertRaisesRegex(DatabaseError, "outside this server"):
                database.initialize()
        self.assertIsNone(database.connection)
        connection.close.assert_called_once()
        self.assertEqual(["SELECT @@datadir, @@port"],
                         [call.args[0] for call in connection.cursor.return_value.execute.call_args_list])

    def test_new_portable_root_and_unicode_password_are_used(self):
        connection = self.connection()
        with patch("pymysql.connect", return_value=connection) as connector:
            database = Database({"driver": "mysql", "password": "é漢!"}, root=self.root)
            database._connect()
            database.close()
        self.assertEqual(3307, connector.call_args.kwargs["port"])
        self.assertEqual("127.0.0.1", connector.call_args.kwargs["host"])
        self.assertEqual("é漢!".encode("utf-8"), connector.call_args.kwargs["password"])

    def test_dropped_connection_cannot_reconnect_to_external_instance(self):
        owned = self.connection()
        foreign = self.connection(self.root / "elsewhere/data")
        with patch("pymysql.connect", side_effect=[owned, foreign]):
            database = Database({"driver": "mysql"}, root=self.root)
            database._connect()
            owned.ping.side_effect = pymysql.err.OperationalError(2006, "Server gone")
            with self.assertRaises(DatabaseError):
                database._connect()
        owned.ping.assert_called_once_with(reconnect=False)
        owned.close.assert_called_once()
        foreign.close.assert_called_once()
        self.assertIsNone(database.connection)

    def test_remote_database_and_wrong_port_are_rejected(self):
        with self.assertRaises(DatabaseError):
            Database({"host": "remote.example"}, root=self.root)
        with patch("pymysql.connect", return_value=self.connection(port=3306)):
            with self.assertRaises(DatabaseError):
                Database({}, root=self.root)._connect()

    def test_sqlite_is_explicit_development_and_relative_to_the_server(self):
        with self.assertRaises(DatabaseError):
            Database({"driver": "sqlite"}, root=self.root)
        database = Database({"driver": "sqlite", "path": "runtime/dev.sqlite3"}, dev=True, root=self.root)
        try:
            database.initialize()
            self.assertTrue((self.root / "runtime/dev.sqlite3").is_file())
        finally:
            database.close()


class WorldControlTests(unittest.TestCase):
    def test_maintenance_prevents_world_start_without_rewriting_clean_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            with WorldProcessLock(tmp) as world:
                self.assertTrue(is_world_running(tmp))
                with self.assertRaises(WorldControlError):
                    with WorldProcessLock(tmp):
                        pass
                world.mark_stopped()
            before = read_world_control(tmp)
            with WorldProcessLock(tmp, publish=False):
                with self.assertRaises(WorldControlError):
                    with WorldProcessLock(tmp):
                        pass
            self.assertEqual(before, read_world_control(tmp))
            self.assertFalse(is_world_running(tmp))
            request_world_stop(tmp, timeout=0.2)

    def test_failed_or_crashed_world_is_never_a_clean_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            with WorldProcessLock(tmp):
                pass
            self.assertEqual("failed", read_world_control(tmp)["state"])
            with self.assertRaises(WorldControlError):
                request_world_stop(tmp, timeout=0.2)
            status_path = Path(tmp) / "runtime/world-control.json"
            status_path.write_text(json.dumps({"pid": 999999, "token": "stale", "state": "running"}))
            with self.assertRaises(WorldControlError):
                request_world_stop(tmp, timeout=0.2)

    def test_stop_token_from_a_previous_run_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            with WorldProcessLock(tmp) as world:
                (Path(tmp) / "runtime/world-stop.json").write_text(json.dumps({"token": "old-run"}))
                self.assertFalse(world.stop_requested())
                world.mark_stopped()


class MinimalEngine:
    def __init__(self, root):
        self.root = root
        self.maps = {"test": {"width": 1000, "height": 1000, "walkable": None}}

    def new_player(self, username, tamer, starter):
        return {"username": username, "party": [], "credits": 250,
                "tamer": "tamer", "map_id": "test", "x": 100, "y": 100, "events": []}


class MinimalCommunity:
    ready = True
    def __init__(self):
        self.saved = False
    def register_player(self, state):
        pass
    def snapshots(self, fields, now):
        return {}
    def step(self, started, dt):
        pass
    def invitations(self, states, now):
        pass
    def shutdown(self):
        self.saved = True


class WorldShutdownIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def exercise_shutdown(self, fail_save=False, hold_worker=False):
        from venom.server import main
        with tempfile.TemporaryDirectory(prefix="Venom moved folder ") as tmp:
            root = Path(tmp)
            ready = asyncio.Queue()
            captured = {}
            community = MinimalCommunity()
            worker_started = threading.Event()
            worker_release = threading.Event()
            if hold_worker:
                def blocked_step(started, dt):
                    worker_started.set()
                    if not worker_release.wait(4):
                        raise RuntimeError("Test did not release the active worker")
                community.step = blocked_step

            async def initialize_community(world):
                world.community = community
                captured["world"] = world

            @asynccontextmanager
            async def recording_serve(*args, **kwargs):
                async with serve(*args, **kwargs) as listener:
                    ready.put_nowait(listener.sockets[0].getsockname()[1])
                    yield listener

            config = {"host": "127.0.0.1", "port": 0,
                      "database": {"driver": "sqlite", "path": "runtime/development.sqlite3"}}
            with patch.object(main, "project_root", return_value=root), \
                 patch.object(main, "GameEngine", MinimalEngine), \
                 patch.object(main.WorldServer, "initialize_community", initialize_community), \
                 patch.object(main, "serve", recording_serve):
                runner = asyncio.create_task(main.run(config, dev=True))
                try:
                    port = await asyncio.wait_for(ready.get(), 5)
                    async with connect(f"ws://127.0.0.1:{port}") as websocket:
                        await websocket.recv()
                        await websocket.send(json.dumps({"op": "register", "rid": 1,
                            "username": "PortableTester", "password": "correct-horse-123"}))
                        while True:
                            result = json.loads(await websocket.recv())
                            if result.get("rid") == 1:
                                break
                        self.assertTrue(result["ok"], result)
                        world = captured["world"]
                        # Unsaved movement/state must survive the external stop
                        # request, even with the client still connected.
                        world.sessions["portabletester"].state["credits"] = 731
                        if fail_save:
                            world.database.save = MagicMock(side_effect=DatabaseError("disk failure"))
                        stopper = asyncio.create_task(asyncio.to_thread(request_world_stop, root, 5))
                        if hold_worker:
                            self.assertTrue(worker_started.is_set())
                            for _ in range(100):
                                if read_world_control(root)["state"] == "stopping":
                                    break
                                await asyncio.sleep(0.01)
                            self.assertEqual("stopping", read_world_control(root)["state"])
                            self.assertFalse(stopper.done())
                            self.assertFalse(community.saved)
                            worker_release.set()
                        if fail_save:
                            with self.assertRaises(DatabaseError):
                                await asyncio.wait_for(runner, 5)
                            with self.assertRaises(WorldControlError):
                                await asyncio.wait_for(stopper, 5)
                        else:
                            await asyncio.wait_for(stopper, 5)
                            await asyncio.wait_for(runner, 5)
                    self.assertTrue(community.saved)
                    self.assertFalse(is_world_running(root))
                    self.assertEqual("failed" if fail_save else "stopped", read_world_control(root)["state"])
                    if not fail_save:
                        self.assertTrue(read_world_control(root)["clean"])
                        database = Database(config["database"], dev=True, root=root)
                        try:
                            saved, revision = database.load("PortableTester")
                            self.assertEqual(731, saved["credits"])
                            self.assertGreaterEqual(revision, 1)
                            self.assertTrue(database.acquire_session("portabletester", "new-pc"))
                        finally:
                            database.close()
                finally:
                    worker_release.set()
                    if not runner.done():
                        runner.cancel()
                        await asyncio.gather(runner, return_exceptions=True)

    async def test_external_stop_flushes_players_and_rivals_before_releasing_lock(self):
        await self.exercise_shutdown()

    async def test_failed_final_save_prevents_successful_stop_for_backup(self):
        await self.exercise_shutdown(fail_save=True)

    async def test_stop_waits_for_in_flight_worker_before_final_checkpoint(self):
        await self.exercise_shutdown(hold_worker=True)
