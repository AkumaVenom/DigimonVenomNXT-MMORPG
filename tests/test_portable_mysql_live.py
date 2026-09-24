"""Opt-in, destructive-only-to-a-temporary-fixture MySQL 8.4 integration.

Set VENOM_TEST_MYSQL_RUNTIME to an extracted matching Linux runtime and supply
its required LD_LIBRARY_PATH. Port 3307 must be free. The test starts actual
production WSS world subprocesses and manually ZIPs a fully stopped fixture.
It never connects to or imports an existing player's server.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

from websockets.asyncio.client import connect

from tools import portable_mysql as pm
from tools.setup import create_certificates
from venom.common.game import GameEngine
from venom.server.database import Database
from venom.server.lifecycle import read_world_control, request_world_stop


RUNTIME = os.environ.get("VENOM_TEST_MYSQL_RUNTIME")
SOURCE = Path(__file__).resolve().parents[1]


def _copy_file(source, destination):
    """Hardlink immutable inputs when possible; always dereference symlinks."""
    original = Path(source).resolve()
    try:
        os.link(original, destination)
    except OSError:
        shutil.copy2(original, destination)
    return str(destination)


def _fixture(root):
    shutil.copytree(Path(RUNTIME), root / "mysql/runtime", copy_function=_copy_file)
    shutil.copytree(SOURCE / "venom", root / "venom", copy_function=_copy_file,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(SOURCE / "tools", root / "tools", copy_function=_copy_file,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(SOURCE / "data", root / "data", copy_function=_copy_file)
    # A dedicated world needs collision masks, not client rendering textures.
    catalog = json.loads((root / "data/catalog.json").read_text(encoding="utf-8"))
    for entry in catalog["maps"]:
        if entry.get("walkable"):
            target = root / entry["walkable"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                _copy_file(SOURCE / entry["walkable"], target)
    assert not any(path.is_symlink() for path in (root / "mysql").rglob("*"))


def _zip_and_restore(source, destination, archive):
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as package:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(source).as_posix())
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
        package.extractall(destination)
    # ZIP extraction on Linux does not restore executable mode bits. Windows
    # EXEs do not require this test-environment-only step.
    for path in (destination / "mysql/runtime/bin").iterdir():
        if path.is_file():
            path.chmod(path.stat().st_mode | 0o111)


@unittest.skipUnless(RUNTIME and os.name != "nt", "Set VENOM_TEST_MYSQL_RUNTIME for opt-in Linux/MySQL validation")
class PortableMySQLLiveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if pm._listening():
            self.fail("Port 3307 is in use. Stop the other test instance before opting in.")
        self.temporary = tempfile.TemporaryDirectory(prefix="venom-live-")
        self.base = Path(self.temporary.name)
        self.original = self.base / "Fresh Server"
        self.restored = self.base / "Moved Server 日本語 é"
        self.active_root = self.original
        self.world = None
        self.log = None
        self.rid = 0
        await asyncio.to_thread(_fixture, self.original)

    async def asyncTearDown(self):
        try:
            if self.world is not None and self.world.poll() is None:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(request_world_stop, self.active_root, 30)
                    await asyncio.to_thread(self.world.wait, 30)
            if self.log:
                self.log.close()
            # Never kill a database. Ownership is checked by the actual manager.
            if pm._listening():
                await asyncio.to_thread(pm.stop, self.active_root)
        finally:
            if not pm._listening():
                self.temporary.cleanup()

    async def start_world(self, root):
        self.active_root = root
        config = json.loads((root / "config/server.json").read_text(encoding="utf-8"))
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        config.update({"host": "127.0.0.1", "port": port,
                       "tls_cert": "config/server-cert.pem", "tls_key": "config/server-key.pem",
                       "rivals": {"count": 8, "save_interval": 2}})
        (root / "config/server.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        if self.log:
            self.log.close()
        (root / "runtime/logs").mkdir(parents=True, exist_ok=True)
        self.log = (root / "runtime/logs/live-test-world.log").open("ab")
        environment = dict(os.environ, VENOM_ROOT=str(root), PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE="1")
        self.world = subprocess.Popen([sys.executable, "-m", "venom.server.main"], cwd=root,
                                      env=environment, stdin=subprocess.DEVNULL,
                                      stdout=self.log, stderr=self.log)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.world.poll() is not None:
                self.log.flush()
                self.fail((root / "runtime/logs/live-test-world.log").read_text(encoding="utf-8"))
            control = read_world_control(root)
            if control and control.get("pid") == self.world.pid and control.get("state") == "running":
                tls = ssl.create_default_context(cafile=str(root / "config/server-ca.pem"))
                return f"wss://127.0.0.1:{port}", tls
            await asyncio.sleep(0.05)
        self.fail("World did not become ready; inspect " + str(root / "runtime/logs/live-test-world.log"))

    async def request(self, websocket, op, **fields):
        self.rid += 1
        await websocket.send(json.dumps({"op": op, "rid": self.rid, **fields}))
        while True:
            message = json.loads(await asyncio.wait_for(websocket.recv(), 10))
            if message.get("op") == "result" and message.get("rid") == self.rid:
                self.assertTrue(message["ok"], message)
                return message

    async def stop_world(self, root):
        await asyncio.to_thread(request_world_stop, root, 45)
        self.assertEqual(0, await asyncio.to_thread(self.world.wait, 10))
        self.assertTrue(read_world_control(root)["clean"])
        self.world = None

    def saved_snapshot(self, root, config):
        database = Database(config, root=root)
        try:
            saved, revision = database.load("PortableTester")
            connection = database._connect()
            with connection.cursor() as cursor:
                cursor.execute("SELECT session_token,lease_until FROM venom_accounts WHERE username='portabletester'")
                self.assertEqual((None, 0.0), cursor.fetchone())
                cursor.execute("SELECT COUNT(*) FROM venom_community_meta WHERE name='world_lease'")
                self.assertEqual(0, cursor.fetchone()[0])
                cursor.execute("SELECT id,state_json FROM venom_bot_state ORDER BY id")
                rivals = cursor.fetchall()
                self.assertEqual(8, len(rivals))
                cursor.execute("SELECT COUNT(*) FROM venom_ranked_seasons")
                self.assertGreater(cursor.fetchone()[0], 0)
                cursor.execute("SELECT @@datadir")
                self.assertEqual((root / "mysql/data").resolve(), Path(cursor.fetchone()[0]).resolve())
            return saved, revision, rivals
        finally:
            database.close()

    async def test_production_mysql_wss_manual_zip_and_moved_folder_recovery(self):
        root = self.original
        config = await asyncio.to_thread(pm.setup_database, root, {"password": "Portable-db-é漢-2026!"})
        create_certificates(root, "localhost")
        engine = GameEngine(root, seed=7)
        url, tls = await self.start_world(root)
        password = "Portable-player-é漢-2026!"
        async with connect(url, ssl=tls, server_hostname="localhost", max_size=8 * 1024 * 1024) as websocket:
            hello = json.loads(await websocket.recv())
            self.assertIn("rivals", hello["features"])
            result = await self.request(websocket, "register", username="PortableTester", password=password,
                                        tamer=next(iter(engine.tamers)), starter=engine.starters[0])
            state = result["state"]
            original_credits = state["credits"]
            original_items = state["inventory"]["hp_s"]
            await self.request(websocket, "digilab", action="enter")
            state = (await self.request(websocket, "shop", item="hp_s", quantity=1))["state"]
            self.assertEqual(original_credits - 60, state["credits"])
            self.assertEqual(original_items + 1, state["inventory"]["hp_s"])
            state = (await self.request(websocket, "digilab", action="return"))["state"]
            movement = await self.request(websocket, "move", dx=0, dy=-1, dt=0.1)
            state.update(movement["position"])
            expected = {key: value for key, value in state.items() if key != "events"}
            # The player remains connected when the manager requests its final save.
            await self.stop_world(root)
        before = await asyncio.to_thread(self.saved_snapshot, root, config)
        self.assertEqual(expected, {key: value for key, value in before[0].items() if key != "events"})
        await asyncio.to_thread(pm.stop, root)
        self.assertFalse(pm._listening())
        archive = self.base / "Whole Stopped Server.zip"
        await asyncio.to_thread(_zip_and_restore, root, self.restored, archive)
        # Remove the original directory from discovery: the extracted copy must
        # stand on its own, including TLS, credentials, rival saves and InnoDB.
        original_unavailable = self.base / "Original unavailable"
        root.rename(original_unavailable)
        self.active_root = self.restored
        await asyncio.to_thread(pm.start, self.restored)
        after = await asyncio.to_thread(self.saved_snapshot, self.restored, config)
        self.assertEqual(before, after)
        url, tls = await self.start_world(self.restored)
        async with connect(url, ssl=tls, server_hostname="localhost", max_size=8 * 1024 * 1024) as websocket:
            await websocket.recv()
            restored = (await self.request(websocket, "login", username="PORTABLETESTER", password=password))["state"]
            self.assertEqual(expected, {key: value for key, value in restored.items() if key != "events"})
            await self.stop_world(self.restored)
        await asyncio.to_thread(pm.stop, self.restored)
        self.assertFalse(pm._listening())
