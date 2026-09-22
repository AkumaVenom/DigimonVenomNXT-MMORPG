"""Password entry and shared-XAMPP setup regressions without a live database."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pymysql

from tools.password_prompt import GUIUnavailable, PasswordCancelled, read_password, windows_password
from tools.setup import choice, mysql_setup


class WindowsPasswordTests(unittest.TestCase):
    def enter(self, characters, clipboard=None):
        keys = iter(characters)
        output = io.StringIO()
        result = windows_password(
            "Existing administrator password",
            read_char=lambda: next(keys),
            output=output,
            paste=clipboard,
        )
        return result, output.getvalue()

    def test_special_characters_spaces_and_unicode_are_unchanged_and_masked(self):
        password = "  Fictional!%&^$()[]{};'\"\\?é漢 secret  "
        entered, output = self.enter(password + "\r")
        self.assertEqual(password, entered)
        self.assertNotIn(password, output)
        self.assertNotIn("Fictional", output)
        self.assertIn("*" * len(password), output)

    def test_editing_and_navigation_do_not_add_hidden_password_characters(self):
        # Windows getwch returns an extended-key prefix followed by a key code.
        entered, _ = self.enter("typo\x15Correctx\b!\x00H\xe0K\r")
        self.assertEqual("Correct!", entered)

    def test_backspace_on_empty_and_blank_submission_are_safe(self):
        entered, _ = self.enter("\b\b\r")
        self.assertEqual("", entered)

    def test_backspace_removes_a_complete_supplementary_unicode_character(self):
        # msvcrt.getwch yields two UTF-16 code units for this emoji on Windows.
        entered, _ = self.enter("kept\ud83d\ude00\b!\r")
        self.assertEqual("kept!", entered)

    def test_paste_keeps_punctuation_and_surrounding_spaces(self):
        pasted = "  Clipboard!%&^'\"\\?é  "
        entered, output = self.enter("a\x16z\r", clipboard=lambda: pasted)
        self.assertEqual("a" + pasted + "z", entered)
        self.assertNotIn(pasted, output)

    def test_multiline_or_nul_clipboard_content_is_rejected_without_partial_entry(self):
        for pasted in ("prefix\nsecond", "prefix\rsecond", "prefix\x00second"):
            with self.subTest(clipboard=repr(pasted)):
                entered, output = self.enter("kept\x16!\r", clipboard=lambda: pasted)
                self.assertEqual("kept!", entered)
                self.assertNotIn("prefix", output)

    def test_escape_and_control_c_cancel_instead_of_submitting_an_empty_password(self):
        for cancel in ("\x1b", "\x03"):
            with self.subTest(cancel=repr(cancel)):
                with self.assertRaises(PasswordCancelled):
                    self.enter("partial" + cancel)


class PasswordDispatchTests(unittest.TestCase):
    def test_windows_default_opens_editable_dialog_and_preserves_its_result(self):
        password = "  Dialog fixture!%&  "
        with patch("tools.password_prompt.sys.platform", "win32"), \
             patch("tools.password_prompt.password_dialog", return_value=password) as dialog, \
             patch("tools.password_prompt.windows_password") as console:
            self.assertEqual(password, read_password("Existing administrator password"))
        dialog.assert_called_once_with("Existing administrator password")
        console.assert_not_called()

    def test_cancelling_dialog_never_falls_back_to_another_password_prompt(self):
        with patch("tools.password_prompt.sys.platform", "win32"), \
             patch("tools.password_prompt.password_dialog", side_effect=PasswordCancelled), \
             patch("tools.password_prompt.windows_password") as console:
            with self.assertRaises(PasswordCancelled):
                read_password("Game password")
        console.assert_not_called()

    def test_missing_gui_falls_back_to_masked_windows_console(self):
        terminal = MagicMock()
        terminal.isatty.return_value = True
        output = io.StringIO()
        with patch("tools.password_prompt.sys.platform", "win32"), \
             patch("tools.password_prompt.sys.stdin", terminal), \
             patch("tools.password_prompt.password_dialog", side_effect=GUIUnavailable), \
             patch("tools.password_prompt.windows_password", return_value="FallbackFixture!") as console, \
             redirect_stderr(output):
            self.assertEqual("FallbackFixture!", read_password("Game password"))
        console.assert_called_once_with("Game password")
        self.assertIn("console", output.getvalue().lower())
        self.assertNotIn("FallbackFixture!", output.getvalue())

    def test_console_override_does_not_try_to_open_a_dialog(self):
        terminal = MagicMock()
        terminal.isatty.return_value = True
        with patch("tools.password_prompt.sys.platform", "win32"), \
             patch("tools.password_prompt.sys.stdin", terminal), \
             patch("tools.password_prompt.password_dialog") as dialog, \
             patch("tools.password_prompt.windows_password", return_value="ConsoleFixture!"):
            self.assertEqual("ConsoleFixture!", read_password("Game password", mode="console"))
        dialog.assert_not_called()

    def test_unavailable_desktop_and_noninteractive_stdin_do_not_silently_submit_blank(self):
        terminal = MagicMock()
        terminal.isatty.return_value = False
        with patch("tools.password_prompt.sys.platform", "win32"), \
             patch("tools.password_prompt.sys.stdin", terminal), \
             patch("tools.password_prompt.password_dialog", side_effect=GUIUnavailable), \
             patch("tools.password_prompt.windows_password") as console, \
             redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "interactive"):
                read_password("Game password")
        console.assert_not_called()

    def test_unexpected_dialog_error_is_not_treated_as_gui_unavailability(self):
        with patch("tools.password_prompt.sys.platform", "win32"), \
             patch("tools.password_prompt.password_dialog", side_effect=ValueError("fixture error")), \
             patch("tools.password_prompt.windows_password") as console:
            with self.assertRaisesRegex(ValueError, "fixture error"):
                read_password("Game password")
        console.assert_not_called()


class SecretChoiceTests(unittest.TestCase):
    def test_secret_input_is_not_stripped_and_default_is_not_displayed(self):
        password = "  Edited!$%& secret  "
        with patch("tools.setup.read_password", return_value=password) as reader:
            value = choice({}, "password", "Game password", "PRIVATE_DEFAULT", secret=True)
        self.assertEqual(password, value)
        self.assertNotIn("PRIVATE_DEFAULT", str(reader.call_args))

    def test_blank_preserves_the_existing_game_password(self):
        with patch("tools.setup.read_password", return_value=""):
            self.assertEqual(
                "RetainedGamePassword!",
                choice({}, "password", "Game password", "RetainedGamePassword!", secret=True),
            )

    def test_cancel_does_not_select_the_default(self):
        with patch("tools.setup.read_password", side_effect=PasswordCancelled):
            with self.assertRaises(PasswordCancelled):
                choice({}, "password", "Game password", "RetainedGamePassword!", secret=True)


class SharedMySQLPasswordTests(unittest.TestCase):
    @staticmethod
    def settings():
        return {
            "host": "127.0.0.1",
            "port": 3306,
            "name": "venom_password_test",
            "admin_user": "root",
            "user": "venom_password_test",
            "account_host": "localhost",
        }

    def test_interactive_passwords_reach_mysql_exactly_without_shell_or_sql_interpolation(self):
        admin_password = "  FakeAdmin!%&^$()[]{};'\"\\?é  "
        game_password = "  FakeGame!%&^$()[]{};'\"\\?é  "
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("tools.setup.read_password", side_effect=[admin_password, game_password]), \
                 patch("pymysql.connect", return_value=connection) as connect, \
                 patch("tools.setup._probe_game_login", side_effect=[False, True]), \
                 patch("venom.server.database.initialize_database") as initialize, \
                 redirect_stdout(output), redirect_stderr(output):
                mysql_setup(root, self.settings(), interactive=True)
            self.assertEqual(admin_password.encode("utf-8"), connect.call_args.kwargs["password"])
            saved = (root / "config/server.json").read_text(encoding="utf-8")
            config = json.loads(saved)
            self.assertEqual(game_password, config["database"]["password"])
            self.assertNotIn(admin_password, saved)
            self.assertNotIn("FakeAdmin", saved)
            initialize.assert_called_once_with(config["database"])
        statements = cursor.execute.call_args_list
        create_user = next(call for call in statements if call.args[0].startswith("CREATE USER"))
        self.assertEqual(game_password, create_user.args[1][-1])
        self.assertNotIn(game_password, create_user.args[0])
        self.assertFalse(any("ALTER USER" in call.args[0] or "SET PASSWORD" in call.args[0] for call in statements))
        self.assertNotIn(admin_password, output.getvalue())
        self.assertNotIn(game_password, output.getvalue())
        connection.close.assert_called_once()

    def test_explicit_blank_administrator_password_is_supported(self):
        connection = MagicMock()
        with tempfile.TemporaryDirectory() as temporary:
            with patch("tools.setup.read_password", side_effect=["", "DedicatedFixturePassword!"]), \
                 patch("pymysql.connect", return_value=connection) as connect, \
                 patch("tools.setup._probe_game_login", side_effect=[False, True]), \
                 patch("venom.server.database.initialize_database"), redirect_stdout(io.StringIO()):
                mysql_setup(Path(temporary), self.settings(), interactive=True)
        self.assertEqual(b"", connect.call_args.kwargs["password"])

    def test_cancellation_before_login_does_not_create_or_replace_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            path = root / "config/server.json"
            original = '{"port": 9831, "database": {"password": "PreviousGamePassword!"}}'
            path.write_text(original, encoding="utf-8")
            with patch("tools.setup.read_password", side_effect=PasswordCancelled), \
                 patch("pymysql.connect") as connect, redirect_stdout(io.StringIO()):
                with self.assertRaises(PasswordCancelled):
                    mysql_setup(root, self.settings(), interactive=True)
            connect.assert_not_called()
            self.assertEqual(original, path.read_text(encoding="utf-8"))

    def test_existing_account_password_mismatch_uses_an_isolated_account(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value

        def execute(sql, parameters=None):
            if sql.startswith("CREATE USER") and parameters[0] == self.settings()["user"]:
                raise pymysql.err.OperationalError(1396, "Account already exists")

        cursor.execute.side_effect = execute
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            path = root / "config/server.json"
            path.write_text('{"port": 9831, "database": {"password": "PreviousGamePassword!"}}', encoding="utf-8")
            answers = dict(self.settings(), admin_password="AdminFixturePassword!", password="ChosenDedicatedPassword!")
            with patch("pymysql.connect", return_value=connection), \
                 patch("tools.setup._probe_game_login", side_effect=[False, True]), \
                 patch("venom.server.database.initialize_database") as initialize, \
                 redirect_stdout(output), redirect_stderr(output):
                result = mysql_setup(root, answers, interactive=False)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(9831, saved["port"])
            self.assertEqual(self.settings()["name"], result["name"])
            self.assertNotEqual(self.settings()["user"], result["user"])
            self.assertEqual("ChosenDedicatedPassword!", result["password"])
            self.assertEqual(result, saved["database"])
            initialize.assert_called_once_with(result)
        self.assertNotIn("ChosenDedicatedPassword!", output.getvalue())
        statements = cursor.execute.call_args_list
        self.assertFalse(any("ALTER USER" in call.args[0] or "SET PASSWORD" in call.args[0] for call in statements))
        grants = [call for call in statements if call.args[0].startswith("GRANT")]
        self.assertEqual(1, len(grants))
        self.assertEqual(result["user"], grants[0].args[1][0])
        connection.close.assert_called_once()

    def test_rejected_administrator_login_has_actionable_redacted_error_and_no_mutations(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            answers = dict(self.settings(), admin_password="AdminFixturePassword!", password="DedicatedFixturePassword!")
            with patch("pymysql.connect", side_effect=pymysql.err.OperationalError(1045, "driver fixture AdminFixturePassword!")), \
                 patch("venom.server.database.initialize_database") as initialize, \
                 redirect_stdout(output), redirect_stderr(output):
                with self.assertRaises(ValueError) as raised:
                    mysql_setup(root, answers, interactive=False)
            initialize.assert_not_called()
            self.assertFalse((root / "config/server.json").exists())
        explanation = str(raised.exception) + output.getvalue()
        self.assertIn("administrator", explanation.lower())
        self.assertIn("existing", explanation.lower())
        self.assertNotIn("AdminFixturePassword!", explanation)

    def test_provisioning_errors_do_not_echo_driver_sql_or_passwords(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = pymysql.err.OperationalError(1064, "unsafe driver text DedicatedFixturePassword!")
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            answers = dict(self.settings(), admin_password="AdminFixturePassword!", password="DedicatedFixturePassword!")
            with patch("pymysql.connect", return_value=connection), \
                 redirect_stdout(output), redirect_stderr(output):
                with self.assertRaises(ValueError) as raised:
                    mysql_setup(root, answers, interactive=False)
            self.assertFalse((root / "config/server.json").exists())
        explanation = str(raised.exception) + output.getvalue()
        self.assertIn("1064", explanation)
        self.assertNotIn("DedicatedFixturePassword!", explanation)
        self.assertNotIn("unsafe driver text", explanation)
        connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
