"""Local stdin is the only command transport; hidden input never echoes."""
import asyncio
import getpass
import io
import queue
import unittest
import warnings
from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from venom.server.local_console import LocalConsole


class Terminal:
    def __init__(self):
        self.lines = queue.Queue()
    def isatty(self):
        return True
    def readline(self):
        return self.lines.get(timeout=3)


class Service:
    def __init__(self, allowed=True):
        self.calls = []
        self.allowed = allowed
        self.called = asyncio.Event()
    def can_execute(self, command):
        return self.allowed
    def required_permission(self, command):
        return "ADMIN"
    async def execute(self, line, password=None):
        self.calls.append((line, password))
        self.called.set()
        return "Done."


class LocalConsoleTests(unittest.IsolatedAsyncioTestCase):
    async def finish(self, console, terminal):
        terminal.lines.put("")
        for _ in range(100):
            if not console._thread.is_alive():
                break
            await asyncio.sleep(.005)
        self.assertFalse(console._thread.is_alive())
        console.close()

    async def test_hidden_password_separate_from_command_and_output(self):
        terminal, output, service = Terminal(), io.StringIO(), Service()
        console = LocalConsole(asyncio.get_running_loop(), terminal, output,
                               lambda *args, **kwargs: "hidden-password-123")
        console.attach(service)
        terminal.lines.put('/createaccount "TestTamer"\n')
        await asyncio.wait_for(service.called.wait(), 2)
        await self.finish(console, terminal)
        self.assertEqual([('/createaccount "TestTamer"', "hidden-password-123")], service.calls)
        self.assertNotIn("hidden-password-123", output.getvalue())
        self.assertIn("world remains running", output.getvalue())

    async def test_no_password_prompt_before_permission_or_with_password_argument(self):
        terminal, output, service = Terminal(), io.StringIO(), Service(False)
        def unwanted_prompt(*args, **kwargs):
            raise AssertionError("Password prompt must not run")
        console = LocalConsole(asyncio.get_running_loop(), terminal, output, unwanted_prompt)
        console.attach(service)
        terminal.lines.put('/resetpassword TestTamer\n')
        terminal.lines.put('/createaccount TestTamer visible-secret\n')
        await self.finish(console, terminal)
        self.assertFalse(service.calls)
        self.assertIn("Permission denied", output.getvalue())
        self.assertNotIn("visible-secret", output.getvalue())

    async def test_one_reader_survives_service_replacement(self):
        terminal, output = Terminal(), io.StringIO()
        console = LocalConsole(asyncio.get_running_loop(), terminal, output)
        first, second = Service(), Service()
        console.attach(first)
        thread = console._thread
        console.detach(first)
        console.attach(second)
        self.assertIs(thread, console._thread)
        self.assertTrue(thread.daemon)
        terminal.lines.put('/saveall\n')
        await asyncio.wait_for(second.called.wait(), 2)
        await self.finish(console, terminal)
        self.assertFalse(first.calls)
        self.assertEqual([('/saveall', None)], second.calls)

    async def test_redirected_input_cannot_start_reader(self):
        console = LocalConsole(asyncio.get_running_loop(), io.StringIO('/shutdown 0\n'), io.StringIO())
        self.assertFalse(console.attach(Service()))
        self.assertIsNone(console._thread)
        with self.assertRaisesRegex(ValueError, "interactive"):
            console._hidden_password()

    async def test_getpass_fallback_aborts_before_echo_input(self):
        def no_terminal(*args, **kwargs):
            warnings.warn("Can not control echo", getpass.GetPassWarning)
            raise AssertionError("Echo fallback must never be reached")
        console = LocalConsole(asyncio.get_running_loop(), Terminal(), io.StringIO(), no_terminal)
        with self.assertRaisesRegex(ValueError, "Hidden password input is unavailable"):
            console._hidden_password()

    async def test_mismatched_passwords_leave_account_untouched(self):
        passwords = iter(["first-password", "second-password"])
        terminal, output, service = Terminal(), io.StringIO(), Service()
        console = LocalConsole(asyncio.get_running_loop(), terminal, output,
                               lambda *args, **kwargs: next(passwords))
        console.attach(service)
        terminal.lines.put('/resetpassword TestTamer\n')
        await self.finish(console, terminal)
        self.assertFalse(service.calls)
        self.assertIn("did not match", output.getvalue())
        self.assertNotIn("first-password", output.getvalue())

    async def test_actual_restart_drains_players_and_reopens_same_saved_world(self):
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve
        from venom.server import main
        from venom.server.admin_commands import AdminConsole

        class Engine:
            def __init__(self, root):
                self.root = root
                self.maps = {"test": {"id": "test", "width": 1000, "height": 1000}}
            def new_player(self, username, tamer, starter):
                return {"username": username, "party": [], "credits": 250, "tamer": "tamer",
                        "map_id": "test", "x": 100, "y": 100, "events": []}

        class Community:
            ready = True
            def register_player(self, state): pass
            def snapshots(self, fields, now): return {}
            def step(self, started, dt): pass
            def invitations(self, states, now): pass
            def shutdown(self): self.ready = False

        class Console:
            instances = []
            def __init__(self, loop):
                self.attached = []
                self.closed = False
                self.instances.append(self)
            def attach(self, service):
                self.attached.append(service)
                return True
            def detach(self, service): pass
            def close(self): self.closed = True

        worlds, ready = [], asyncio.Queue()
        async def initialize(world):
            world.community = Community()
            worlds.append(world)

        @asynccontextmanager
        async def recording_serve(*args, **kwargs):
            async with serve(*args, **kwargs) as listener:
                ready.put_nowait(listener.sockets[0].getsockname()[1])
                yield listener

        with tempfile.TemporaryDirectory() as tmp:
            config = {"host": "127.0.0.1", "port": 0,
                      "database": {"driver": "sqlite", "path": "runtime/development.sqlite3"}}
            with patch.object(main, "project_root", return_value=Path(tmp)), \
                 patch.object(main, "GameEngine", Engine), \
                 patch.object(main.WorldServer, "initialize_community", initialize), \
                 patch.object(main, "serve", recording_serve), \
                 patch("venom.server.local_console.LocalConsole", Console):
                runner = asyncio.create_task(main.run(config, dev=True))
                try:
                    port = await asyncio.wait_for(ready.get(), 5)
                    async with connect(f"ws://127.0.0.1:{port}") as ws:
                        await ws.recv()
                        await ws.send(json.dumps({"op": "register", "rid": 1,
                            "username": "Tester", "password": "correct-horse-123"}))
                        while True:
                            result = json.loads(await ws.recv())
                            if result.get("rid") == 1: break
                        self.assertTrue(result["ok"], result)
                        worlds[0].sessions["tester"].state["credits"] = 987
                        self.assertIn("scheduled", await Console.instances[0].attached[0].execute("/restart 0"))
                        second_port = await asyncio.wait_for(ready.get(), 5)
                    self.assertEqual(1, len(Console.instances))
                    self.assertEqual(2, len(Console.instances[0].attached))
                    self.assertTrue(Console.instances[0].attached[0].closed)
                    async with connect(f"ws://127.0.0.1:{second_port}") as ws:
                        await ws.recv()
                        await ws.send(json.dumps({"op": "login", "rid": 2,
                            "username": "Tester", "password": "correct-horse-123"}))
                        while True:
                            result = json.loads(await ws.recv())
                            if result.get("rid") == 2: break
                        self.assertTrue(result["ok"], result)
                        self.assertEqual(987, result["state"]["credits"])
                        worlds[-1].stop_signal.set()
                        await asyncio.wait_for(runner, 5)
                    self.assertTrue(Console.instances[0].closed)
                    self.assertTrue(all(not world.community.ready for world in worlds))
                finally:
                    if not runner.done():
                        worlds[-1].stop_signal.set()
                        await asyncio.wait_for(runner, 5)
