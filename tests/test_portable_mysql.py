"""Real filesystem/lock boundaries for the folder-owned MySQL controller.

The engine is mocked here; actual MySQL initialization, save, restart and
relocation are covered separately by the runtime integration validation.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tools import portable_mysql as manager
from venom.server.lifecycle import (WorldControlError, WorldProcessLock,
                                    is_world_running, request_world_stop)


SOURCE = Path(__file__).resolve().parents[1]


class PortableManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Venom controller test ")
        self.root = Path(self.temp.name) / "Server with spaces"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def file(self, name, content=b"sample"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_initialization_never_overwrites_unidentified_save_directory(self):
        save = self.file("mysql/data/player.ibd", b"irreplaceable saves")
        with patch.object(manager, "ensure_runtime"), \
             patch.object(manager, "_listening", return_value=False), \
             patch.object(manager, "_alive", return_value=False), \
             patch.object(manager.subprocess, "run") as initialize:
            with self.assertRaisesRegex(manager.PortableError, "never overwrite"):
                manager.prepare(self.root)
        self.assertEqual(b"irreplaceable saves", save.read_bytes())
        initialize.assert_not_called()
        self.assertFalse((self.root / "mysql/instance.json").exists())

    def test_stop_cannot_shut_down_database_while_world_owns_lock(self):
        with patch.object(manager, "_stop_database") as stop:
            with WorldProcessLock(self.root) as world:
                with self.assertRaises(WorldControlError):
                    manager.stop(self.root)
                world.mark_stopped()
            stop.assert_not_called()

    def test_repeated_setup_never_reinitializes_an_existing_instance(self):
        state = {"format": 1, "stage": "ready", "root_password": "long-secret"}
        state_path = self.file("mysql/instance.json", json.dumps(state).encode())
        save = self.file("mysql/data/player.ibd", b"saved progress")
        with patch.object(manager, "ensure_runtime"), \
             patch.object(manager, "_start", return_value={"owned": True}) as start, \
             patch.object(manager.subprocess, "run") as initialize:
            result = manager.prepare(self.root)
        self.assertTrue(result["owned"])
        start.assert_called_once_with(self.root)
        initialize.assert_not_called()
        self.assertEqual(state, json.loads(state_path.read_text()))
        self.assertEqual(b"saved progress", save.read_bytes())

    def test_start_verifies_running_instance_without_launching_another(self):
        connection = MagicMock()
        with patch.object(manager, "ensure_runtime"), \
             patch.object(manager, "_credentials", return_value={"stage": "ready"}), \
             patch.object(manager, "_listening", return_value=True), \
             patch.object(manager, "_connection", return_value=connection) as connect, \
             patch.object(manager, "status", return_value={"owned": True}), \
             patch.object(manager.subprocess, "Popen") as launch:
            self.assertTrue(manager.start(self.root)["owned"])
        connect.assert_called_once_with(self.root)
        connection.close.assert_called_once()
        launch.assert_not_called()

    def test_failed_world_prevents_stop_server_from_stopping_mysql(self):
        with WorldProcessLock(self.root):
            pass
        with patch.object(manager, "_stop_database") as stop:
            with self.assertRaisesRegex(WorldControlError, "clean save"):
                manager.stop_server(self.root)
            stop.assert_not_called()

    def test_standalone_mysql_stop_does_not_claim_failed_world_was_saved(self):
        with WorldProcessLock(self.root):
            pass
        with patch.object(manager, "_stop_database") as stop:
            with self.assertRaisesRegex(manager.PortableError, "clean save"):
                manager.stop(self.root)
            stop.assert_not_called()

    def test_reserved_database_or_user_is_rejected_before_game_credentials_are_written(self):
        for settings in ({"name": "mysql"}, {"name": "sys"}, {"user": "root"}):
            with self.subTest(settings=settings), patch.object(manager, "prepare"), \
                 patch.object(manager, "_connection") as connect:
                with self.assertRaisesRegex(manager.PortableError, "reserved"):
                    manager.setup_database(self.root, settings)
                connect.assert_not_called()
                self.assertFalse((self.root / "mysql/game-login.json").exists())

    def test_database_shutdown_keeps_new_world_from_starting(self):
        def stop_database(root):
            with self.assertRaises(WorldControlError):
                with WorldProcessLock(root):
                    pass
        with patch.object(manager, "_stop_database", side_effect=stop_database):
            self.assertFalse(manager.stop_server(self.root)["running"])
        self.assertFalse(is_world_running(self.root))

    def test_nonlistening_database_with_live_process_is_not_stopped(self):
        with patch.object(manager, "_listening", return_value=False), \
             patch.object(manager, "_pid", return_value=12345), \
             patch.object(manager, "_alive", return_value=True), \
             patch.object(manager, "_connection") as connect:
            with self.assertRaisesRegex(manager.PortableError, "has not exited"):
                manager._stop_database(self.root)
            connect.assert_not_called()

    def test_missing_pid_prevents_shutdown_sql_even_with_verified_login(self):
        connection = MagicMock()
        with patch.object(manager, "_listening", return_value=True), \
             patch.object(manager, "_pid", return_value=None), \
             patch.object(manager, "_connection", return_value=connection):
            with self.assertRaisesRegex(manager.PortableError, "process ID"):
                manager._stop_database(self.root)
        connection.close.assert_called_once()
        connection.cursor.assert_not_called()

    def test_foreign_database_identity_is_rejected_and_connection_closed(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (str(self.root.parent / "external-data"), 3307,
                                       manager.VERSION_PREFIX, str(self.root / "mysql/run/mysqld.pid"))
        with patch.object(manager, "_credentials", return_value={"root_password": "secret"}), \
             patch("pymysql.connect", return_value=connection):
            with self.assertRaisesRegex(manager.PortableError, "different database"):
                manager._connection(self.root)
        connection.close.assert_called_once()
        self.assertEqual(["SELECT @@datadir, @@port, @@version, @@pid_file"],
                         [call.args[0] for call in cursor.execute.call_args_list])


class CrossProcessLockTests(unittest.TestCase):
    def hold_in_child(self, root):
        code = """import sys
from venom.server.lifecycle import WorldProcessLock
with WorldProcessLock(sys.argv[1]):
    print('held', flush=True)
    sys.stdin.readline()
"""
        child = subprocess.Popen([sys.executable, "-u", "-c", code, str(root)],
                                 cwd=SOURCE, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.close_child, child)
        self.assertEqual("held", child.stdout.readline().strip())
        return child

    @staticmethod
    def close_child(child):
        if child.poll() is None:
            child.terminate()
        child.communicate(timeout=10)

    def test_other_process_is_excluded_and_crash_does_not_mean_clean_save(self):
        with tempfile.TemporaryDirectory(prefix="Venom process lock ") as tmp:
            child = self.hold_in_child(tmp)
            self.assertTrue(is_world_running(tmp))
            with self.assertRaises(WorldControlError):
                with WorldProcessLock(tmp, publish=False):
                    pass
            child.terminate()
            child.communicate(timeout=10)
            self.assertFalse(is_world_running(tmp))
            with self.assertRaisesRegex(WorldControlError, "clean save"):
                request_world_stop(tmp, timeout=0.2)
            with WorldProcessLock(tmp, publish=False):
                pass  # OS released the crashed owner's lock without deletion.

    def test_controller_lock_is_exclusive_across_processes(self):
        with tempfile.TemporaryDirectory(prefix="Venom controller lock ") as tmp:
            root = Path(tmp)
            child = self.hold_in_child(root / "mysql/controller")
            with self.assertRaises(WorldControlError):
                with manager._control_lock(root):
                    pass
            child.terminate()
            child.communicate(timeout=10)
            with manager._control_lock(root):
                pass
