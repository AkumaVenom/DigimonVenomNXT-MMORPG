"""One local terminal reader for the lifetime of the world-server process.

No socket, chat hook, RPC or network transport is exposed. A daemon thread owns
stdin so an idle console cannot keep asyncio's executor alive during shutdown.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import getpass
import shlex
import sys
import threading
import warnings


class LocalConsole:
    def __init__(self, loop, stream=None, output=None, password_reader=None):
        self.loop = loop
        self.stream = stream if stream is not None else sys.stdin
        self.output = output if output is not None else sys.stderr
        self.password_reader = password_reader or getpass.getpass
        self._guard = threading.Lock()
        self._service = None
        self._thread = None
        self._closed = False

    @staticmethod
    def terminal_available(stream):
        try:
            return stream is not None and bool(stream.isatty())
        except (AttributeError, OSError, ValueError):
            return False

    def attach(self, service):
        with self._guard:
            if self._closed:
                return False
            self._service = service
        if self._thread is None and self.terminal_available(self.stream):
            self._thread = threading.Thread(target=self._read_loop, name="venom-local-console", daemon=True)
            self._thread.start()
            return True
        return self._thread is not None

    def detach(self, service=None):
        with self._guard:
            if service is None or service is self._service:
                self._service = None

    def close(self):
        # Never join an idle readline. This thread owns no database resources
        # and daemon termination cannot interrupt a save.
        with self._guard:
            self._closed = True
            self._service = None

    def _write(self, text):
        try:
            self.output.write(text)
            self.output.flush()
        except (OSError, ValueError, AttributeError):
            pass

    def _hidden_password(self):
        if not self.terminal_available(self.stream):
            raise ValueError("Password commands require an interactive local terminal.")
        # getpass normally falls back to echoed stdin when terminal controls
        # fail. Treat that warning as an error before it reads any password.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            try:
                first = self.password_reader("New password: ", stream=self.output)
                second = self.password_reader("Confirm password: ", stream=self.output)
            except getpass.GetPassWarning as exc:
                raise ValueError("Hidden password input is unavailable; no password was read.") from exc
        if first != second:
            raise ValueError("Passwords did not match; no change was made.")
        return first

    def _read_loop(self):
        self._write("Local admin console ready. Type /help for commands.\n")
        while True:
            with self._guard:
                if self._closed:
                    return
            self._write("venom> ")
            try:
                line = self.stream.readline()
            except (OSError, ValueError):
                self._write("Local console input is unavailable. The world remains running.\n")
                return
            if not line:
                self._write("Local console input closed. The world remains running.\n")
                return
            line = line.strip()
            if not line:
                continue
            with self._guard:
                service = self._service
                closed = self._closed
            if closed:
                return
            if service is None:
                self._write("The world is restarting or stopping; command was not run.\n")
                continue
            password = None
            try:
                words = shlex.split(line)
                command = words[0].lstrip("/").lower() if words else ""
                if command in {"createaccount", "resetpassword"}:
                    if len(words) != 2:
                        raise ValueError("Use /" + command + " [username]. Passwords are accepted only at the hidden prompt.")
                    if not service.can_execute(command):
                        raise ValueError("Permission denied. This command requires " + service.required_permission(command) + ".")
                    password = self._hidden_password()
                    with self._guard:
                        if self._service is not service or self._closed:
                            raise ValueError("The world changed while prompting; no password was changed.")
                future = asyncio.run_coroutine_threadsafe(service.execute(line, password=password), self.loop)
                try:
                    result = future.result()
                except concurrent.futures.CancelledError:
                    result = "The world is stopping; command was not completed."
                self._write(str(result) + "\n")
            except (ValueError, EOFError) as exc:
                self._write(str(exc) + "\n")
            except Exception:
                # Neither the command line nor the password is printed on
                # failure. Trusted dispatcher audit records redact secrets.
                self._write("The command could not be completed; check the server log.\n")
            finally:
                password = None
