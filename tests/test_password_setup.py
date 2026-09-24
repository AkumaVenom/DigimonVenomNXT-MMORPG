"""Password entry regressions without a live database."""
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


if __name__ == "__main__":
    unittest.main()
