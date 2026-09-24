"""Wizard control-flow checks plus real Tk tests when a desktop is available.

Run the GUI checks on Windows or under DISPLAY (for example Xvfb on Linux).
No live database is needed here; database integration has a separate suite.
"""
from pathlib import Path
import os
import threading
import time
import unittest

from tools.setup_diagnostics import SetupFailure
from tools.setup_wizard import SetupWizard, _port, _single_line, tk


class WizardInputTests(unittest.TestCase):
    def test_database_and_game_ports_must_be_valid_tcp_ports(self):
        for value in ("0", "65536", "8765/http", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _port(value, "Database port")
        self.assertEqual(3307, _port("3307", "Database port"))
        self.assertEqual(8765, _port("8765", "Game port"))

    def test_password_input_keeps_unicode_and_spaces_but_rejects_controls(self):
        self.assertTrue(_single_line("  Game!%&é漢字?  "))
        for value in ("line\nnext", "secret\x00", "tab\t"):
            self.assertFalse(_single_line(value))


class FakeService:
    def __init__(self, root):
        self.root = root
        self.diagnostic_path = root / "logs" / "setup-latest.json"
        self.calls = []
        self.error = None
        self.block = None
        self.candidates = []

    def defaults(self):
        return {"host": "127.0.0.1", "port": 3307, "name": "venom_nxt", "user": "venom_nxt",
                "admin_user": "root", "account_host": "127.0.0.1", "public_host": "localhost",
                "game_port": 8765, "bind": "127.0.0.1", "has_database": False,
                "password": "must never appear in the UI", "admin_password": "must never appear"}

    def _call(self, action, settings=None):
        self.calls.append((action, settings, threading.get_ident()))
        if self.block is not None:
            self.block.wait(4)
        if self.error:
            raise self.error

    def test_database(self, settings):
        self._call("test", settings)
        return {"server_version": "8.4.11 MySQL", "account": "root@127.0.0.1"}

    def configure_database(self, settings):
        self._call("configure", settings)
        return dict(settings, user="venom_nxt_unique")

    def configure_hosting(self, settings):
        self._call("hosting", settings)
        return self.root / "client_kit"

    def verify_installation(self):
        self._call("verify")
        return {"database": True}

    def find_local_database(self):
        self._call("find")
        return self.candidates

    def report_text(self):
        return "Setup 0.3.0\nEndpoint: 127.0.0.1:3307\nPasswords omitted."


@unittest.skipUnless(tk is not None and (os.name == "nt" or os.environ.get("DISPLAY")), "Requires a graphical desktop / Xvfb")
class WizardDesktopTests(unittest.TestCase):
    def setUp(self):
        self.window = tk.Tk()
        self.service = FakeService(Path("fixture_server"))
        self.wizard = SetupWizard(self.window, self.service)
        self.window.update()

    def tearDown(self):
        if self.service.block:
            self.service.block.set()
        if not self.wizard.closed:
            self.wait_idle()
            self.wizard._close()

    def wait_idle(self, timeout=5):
        deadline = time.monotonic() + timeout
        while self.wizard.busy:
            self.window.update()
            if time.monotonic() > deadline:
                self.fail("The wizard worker did not finish.")
            time.sleep(0.005)
        self.window.update()

    def to_game_step(self):
        self.wizard._test_database()
        self.wait_idle()
        self.assertEqual(1, self.wizard.page_index)

    def test_fresh_install_needs_no_administrator_credentials(self):
        self.assertEqual("", self.wizard.values["password"].get())
        self.assertNotIn("admin_password", self.wizard.values)
        self.assertEqual("3307", self.wizard.values["port"].get())
        self.assertEqual("8765", self.wizard.values["game_port"].get())

    def test_full_flow_uses_one_background_worker_and_saved_actual_username(self):
        self.to_game_step()
        self.wizard.values["password"].set("  Game!%&漢  ")
        self.wizard._configure_database()
        self.wait_idle()
        self.assertEqual(2, self.wizard.page_index)
        self.assertEqual("venom_nxt_unique", self.wizard.values["user"].get())
        self.wizard._configure_hosting()
        self.wait_idle()
        self.assertEqual(3, self.wizard.page_index)
        self.assertEqual(0, self.wizard.exit_code)
        self.assertEqual(["test", "configure", "hosting", "verify"], [call[0] for call in self.service.calls])
        worker_threads = {call[2] for call in self.service.calls}
        self.assertEqual(1, len(worker_threads))
        self.assertNotIn(threading.get_ident(), worker_threads)
        self.assertNotIn("admin_password", self.service.calls[0][1])
        self.assertEqual("  Game!%&漢  ", self.service.calls[1][1]["password"])
        self.assertIn("client_kit", self.wizard.ready_summary.get())

    def test_error_code_stays_visible_and_retry_keeps_game_settings(self):
        self.service.error = SetupFailure("endpoint", "PORTABLE_MYSQL", "Port in use.", "Close the other database, then retry.")
        self.wizard.values["password"].set("chosen game password")
        self.wizard._test_database()
        self.wait_idle()
        self.assertEqual(0, self.wizard.page_index)
        self.assertIn("PORTABLE_MYSQL", self.wizard.error_title.get())
        self.assertIn("other database", self.wizard.error_text.get("1.0", "end"))
        self.assertEqual("chosen game password", self.wizard.values["password"].get())
        self.service.error = None
        self.wizard._retry()
        self.wait_idle()
        self.assertEqual(1, self.wizard.page_index)
        self.assertEqual(2, len(self.service.calls))

    def test_busy_operation_prevents_close_and_duplicate_submissions(self):
        self.service.block = threading.Event()
        self.wizard._test_database()
        self.window.update()
        self.wizard._test_database()
        self.wizard._close()
        self.assertFalse(self.wizard.closed)
        self.assertIn("Please wait", self.wizard.status.get())
        self.assertTrue(self.wizard.primary.instate(["disabled"]))
        self.service.block.set()
        self.wait_idle()
        self.assertEqual(1, len(self.service.calls))

    def test_closing_after_database_does_not_configure_hosting(self):
        self.to_game_step()
        self.wizard._configure_database()
        self.wait_idle()
        self.assertEqual(2, self.wizard.page_index)
        self.wizard._close()
        self.assertEqual(["test", "configure"], [call[0] for call in self.service.calls])
        self.assertTrue(self.wizard.closed)

    def test_actual_clipboard_paste_preserves_secrets_and_rejects_multiline(self):
        entry = next(control for control in self.wizard._controls
                     if isinstance(control, __import__("tkinter.ttk", fromlist=["Entry"]).Entry)
                     and str(control.cget("textvariable")) == str(self.wizard.values["password"]))
        self.window.clipboard_clear()
        self.window.clipboard_append("  !%&é漢字?  ")
        self.wizard._paste(entry)
        self.assertEqual("  !%&é漢字?  ", self.wizard.values["password"].get())
        self.window.clipboard_clear()
        self.window.clipboard_append("bad\npassword")
        self.wizard._paste(entry)
        self.assertEqual("  !%&é漢字?  ", self.wizard.values["password"].get())
        self.wizard._copy_report()
        self.assertNotIn("!%&", self.window.clipboard_get())
        self.assertIn("Passwords omitted", self.window.clipboard_get())

    def test_portable_database_page_has_no_external_endpoint_controls(self):
        names = {str(control.cget("textvariable")) for control in self.wizard._controls
                 if isinstance(control, __import__("tkinter.ttk", fromlist=["Entry"]).Entry)}
        self.assertNotIn(str(self.wizard.values["host"]), names)
        self.assertNotIn(str(self.wizard.values["port"]), names)
        self.assertEqual("Prepare MySQL", self.wizard.primary.cget("text"))

    def test_small_window_scrolls_and_primary_controls_remain_visible(self):
        self.window.geometry("640x480")
        self.window.update()
        self.assertGreater(self.wizard.canvas.bbox("all")[3], self.wizard.canvas.winfo_height())
        for button in (self.wizard.primary, self.wizard.back, self.wizard.copy_button):
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), self.window.winfo_rootx() + self.window.winfo_width())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), self.window.winfo_rooty() + self.window.winfo_height())
        self.wizard._show_page(2)
        self.window.update()
        self.assertLessEqual(self.wizard.primary.winfo_rootx() + self.wizard.primary.winfo_width(), self.window.winfo_rootx() + self.window.winfo_width())

    def test_invalid_game_port_does_not_start_hosting_work(self):
        self.wizard._show_page(2)
        self.wizard.values["game_port"].set("8765/incorrect")
        self.wizard._configure_hosting()
        self.assertFalse(self.wizard.busy)
        self.assertEqual([], self.service.calls)
        self.assertIn("1 to 65535", self.wizard.error_text.get("1.0", "end"))
