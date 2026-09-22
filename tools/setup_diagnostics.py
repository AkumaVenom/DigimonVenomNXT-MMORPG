"""Safe, persistent diagnostics shared by the setup window and console.

Driver exception messages may contain SQL and credentials.  They are never
included here: only numeric error codes and messages authored by setup are used.
"""
from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import socket
import tempfile
import threading


SETUP_VERSION = "0.3.0"
STAGES = frozenset({
    "validate", "endpoint", "administrator", "create_database", "game_account",
    "grants", "schema", "save_config", "hosting", "verify",
})
SAFE_METADATA = frozenset({
    "host", "port", "database", "user", "server_version", "account",
    "error_code", "error_type", "message", "action", "version",
})
MAX_EVENTS = 100


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _text(value, maximum=2048):
    # Accept strings only: calling str() on arbitrary metadata could expose an
    # exception, a connection's repr, a SQL parameter list or a configuration.
    if not isinstance(value, str):
        return None
    return "".join(char for char in value if char.isprintable() or char in "\n\t")[:maximum]


def _code(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        if re.fullmatch(r"[0-9]{1,6}", value):
            return int(value)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,47}", value):
            return value
    return None


def _stage(value):
    return value if isinstance(value, str) and value in STAGES else "validate"


class SetupFailure(ValueError):
    """An operator-facing failure whose message/action are authored by setup.

    Do not pass str(driver_exception), SQL, passwords or configuration values to
    this constructor.  Wrap driver exceptions with describe_failure() instead.
    """

    def __init__(self, stage: str, code: int | str | None, message: str, action: str):
        self.stage = _stage(stage)
        self.code = _code(code)
        self.message = _text(message) or "Setup could not complete this step."
        self.action = _text(action) or "Review the setup settings and retry this step."
        super().__init__(self.message)

    def __str__(self):
        code = f", error {self.code}" if self.code is not None else ""
        return f"{self.message} [{self.stage}{code}]\n{self.action}"


def _exception_chain(exception):
    pending = [exception]
    seen = set()
    while pending:
        current = pending.pop(0)
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        # A suppressed context can still hold the original numeric driver code.
        pending.extend((current.__cause__, current.__context__))


def describe_failure(stage: str, exc: BaseException) -> SetupFailure:
    """Classify errors without copying driver messages or traceback contents."""
    chain = tuple(_exception_chain(exc))
    for current in chain:
        if isinstance(current, SetupFailure):
            return current
    stage = _stage(stage)
    code = None
    for current in chain:
        if current.args:
            candidate = _code(current.args[0])
            if isinstance(candidate, int):
                code = candidate
                break

    if code == 1043:
        message = "The database server rejected the connection handshake."
        action = ("Check the MySQL host and database port shown in XAMPP. The database port is usually "
                  "3306; game port 8765 is a separate service. Save this report if the database endpoint "
                  "is correct. Re-entering a password does not resolve a protocol handshake failure.")
    elif code in (1045, 1698):
        if stage == "administrator":
            message = "MySQL rejected the administrator sign-in."
            action = ("Check the administrator username and the password already used by this XAMPP/MySQL "
                      "installation. Leave the password blank only if that administrator has no password, "
                      "then test the connection again.")
        elif stage in ("game_account", "schema", "verify"):
            message = "MySQL rejected the game's database sign-in."
            action = ("Run the game database account step again so setup can create or verify its own login. "
                      "A fresh install does not require an existing game-account password. Check the account "
                      "host if MySQL runs on another computer.")
        else:
            message = "MySQL rejected the database sign-in."
            action = "Check the login used at the indicated step and test that connection again."
    elif code in (1044, 1142, 1143, 1227):
        message = "The database login does not have permission for this setup step."
        action = ("Use a MySQL administrator permitted to create the game database and its separate login, "
                  "then grant access to that game database. Keep the other MMOs' accounts and grants intact.")
    elif code == 1049:
        message = "The selected game database does not exist on this server."
        action = "Check the database name and selected MySQL endpoint, then run the database creation step."
    elif code == 1396:
        message = "MySQL could not complete the game database account operation."
        action = ("Retry the account step to allocate a separate game login. Setup must not reset an occupied "
                  "account's password. Save this report if account creation still fails.")
    elif code == 1819:
        message = "MySQL's password policy rejected the new game database password."
        action = "Choose a game database password that satisfies your MySQL policy, or let setup generate one."
    elif code in (2002, 2003):
        message = "Setup could not reach the MySQL database service."
        action = ("Start MySQL in XAMPP and check its host and database port. Use 127.0.0.1 when it runs on "
                  "this computer. The database port is usually 3306; game port 8765 is separate.")
    elif code == 2005 or any(isinstance(current, socket.gaierror) for current in chain):
        message = "The database hostname could not be resolved."
        action = "Check the MySQL hostname or use 127.0.0.1 for a database on this computer. Enter no URL or path."
    elif code in (2006, 2013):
        message = "The connection to MySQL was lost or timed out."
        action = ("Check that MySQL is still running and that the endpoint is its database service. Review "
                  "the XAMPP MySQL log if it stopped, then retry this step.")
    elif code == 2026:
        message = "The database TLS connection could not be established."
        action = ("Check the database server's TLS configuration and trusted certificate. Game hosting "
                  "certificates are separate from database TLS. Do not disable certificate verification to retry.")
    elif code in (1251, 1524, 2059, 2061):
        message = "The database authentication method could not be used."
        action = ("Check that the selected database account uses an authentication method supported by the "
                  "installed server and client. Save this report with the database version; do not reset shared accounts.")
    elif code == 1129:
        message = "MySQL has temporarily blocked connections from this host."
        action = ("Stop retrying and check the MySQL server log for interrupted connections. Have the database "
                  "administrator resolve the connection problem and unblock the host.")
    elif code == 1130:
        message = "MySQL does not permit this computer to connect with the selected account."
        action = "Check the database account host and the address from which the game server connects."
    elif code in (1040, 1203):
        message = "MySQL has reached its connection limit."
        action = "Check active database clients and the configured connection limit, then retry when capacity is available."
    elif code == 1064:
        message = "The database server rejected a setup statement."
        action = "Save this diagnostic report with the database server version so the setup compatibility issue can be checked."
    elif any(isinstance(current, PermissionError) for current in chain):
        message = "Setup could not access a required file or folder."
        action = "Extract the complete source or server kit into a writable folder, close programs locking its files, and retry."
    elif any(isinstance(current, (TimeoutError, ConnectionError)) for current in chain):
        message = "The connection failed or timed out during this step."
        action = "Check that the selected database service is running at the host and port shown, then retry."
    elif stage == "validate":
        message = "One or more setup settings could not be validated."
        action = "Review the highlighted settings and retry. Save the diagnostic report if the problem persists."
    elif stage == "save_config":
        message = "Setup could not save the server configuration."
        action = "Check that the server's config folder is writable and its files are not locked, then retry setup."
    elif stage == "hosting":
        message = "Hosting certificates or the player connection kit could not be prepared."
        action = "Review the hosting address and existing certificate files, then save this report if the step still fails."
    elif stage == "schema":
        message = "The game database schema could not be prepared or verified."
        action = "Check the selected game database and save this report. Keep the existing player database intact."
    else:
        message = "Setup could not complete this step."
        action = "Review the connection settings and save this diagnostic report before retrying."
    return SetupFailure(stage, code, message, action)


class DiagnosticReport:
    """Bounded, thread-safe run history; filesystem problems never abort setup."""

    def __init__(self, root: Path):
        self.path = Path(root) / "logs" / "setup-latest.json"
        self.write_error = ""
        self._lock = threading.RLock()
        try:
            driver_version = metadata.version("PyMySQL")
        except metadata.PackageNotFoundError:
            driver_version = "not installed"
        now = _timestamp()
        self._data = {
            "report_version": 1, "setup_version": SETUP_VERSION,
            "created_at": now, "updated_at": now,
            "environment": {
                "python": platform.python_version(),
                "platform": " ".join((platform.system(), platform.release(), platform.machine())),
                "pymysql": driver_version,
            },
            "events": [],
        }

    def record(self, stage: str, status: str, **safe_metadata):
        with self._lock:
            now = _timestamp()
            # Unknown arbitrary status values are not copied into reports.
            selected_status = status if status in {"started", "running", "passed", "success", "failure", "warning", "cancelled", "skipped", "info"} else "info"
            event = {"timestamp": now, "stage": _stage(stage), "status": selected_status}
            for key in SAFE_METADATA.intersection(safe_metadata):
                value = safe_metadata[key]
                if key in {"port", "error_code"}:
                    sanitized = _code(value)
                    if sanitized is not None:
                        event[key] = sanitized
                else:
                    sanitized = _text(value, maximum=2048 if key in {"message", "action"} else 256)
                    if sanitized is not None:
                        event[key] = sanitized
            self._data["events"].append(event)
            del self._data["events"][:-MAX_EVENTS]
            self._data["updated_at"] = now
            self._write()

    def failure(self, stage: str, exc: BaseException) -> SetupFailure:
        failure = describe_failure(stage, exc)
        self.record(failure.stage, "failure", error_code=failure.code,
                    error_type=type(exc).__name__, message=failure.message, action=failure.action)
        return failure

    def text(self) -> str:
        with self._lock:
            return json.dumps(self._data, indent=2, ensure_ascii=True) + "\n"

    def _write(self):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # A unique temporary file avoids clobbering reports from another
            # open setup process; mkstemp creates it with restrictive access.
            fd, name = tempfile.mkstemp(prefix=".setup-report-", suffix=".tmp", dir=self.path.parent)
            temporary = Path(name)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(self.text())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.write_error = ""
        except Exception as exc:
            # Do not expose a path, OS exception message, or original SQL here.
            self.write_error = f"The diagnostic file could not be saved ({type(exc).__name__}). Copy the report from the setup window."
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
