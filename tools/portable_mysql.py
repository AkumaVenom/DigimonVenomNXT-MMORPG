"""Folder-owned MySQL: initialize, start, verify and stop cleanly.

No services, registry configuration, external database discovery, or fallback.
All mutable database state lives below ROOT/mysql. Windows release runtime is
bundled; a matching Linux runtime can be used for integration validation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time

PORT = 3307
VERSION_PREFIX = "8.4.11"
ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
if getattr(sys, "frozen", False) and ROOT.name.lower() == "admin":
    ROOT = ROOT.parent
elif getattr(sys, "frozen", False) and ROOT.name.lower() == "manager" and ROOT.parent.name.lower() == "mysql":
    ROOT = ROOT.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class PortableError(RuntimeError):
    pass


def _read(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".new")
    fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data if isinstance(data, bytes) else (json.dumps(data, indent=2) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


@contextmanager
def _control_lock(root):
    from venom.server.lifecycle import WorldProcessLock
    # Use a separate lock namespace from world startup/maintenance.
    with WorldProcessLock(root / "mysql" / "controller", publish=False):
        yield


def _paths(root):
    root = Path(root).resolve()
    base = root / "mysql"
    return root, base, base / "runtime", base / "data"


def _binary(root, name):
    return Path(root) / "mysql/runtime/bin" / (name + (".exe" if os.name == "nt" else ""))


def ensure_runtime(root, offline=False):
    root, base, runtime, data = _paths(root)
    for name in ("mysqld", "mysqldump", "mysql", "mysqladmin"):
        if not _binary(root, name).is_file():
            raise PortableError(f"Bundled MySQL runtime is missing: mysql/runtime/bin/{name}. Restore the complete server package.")
    try:
        result = subprocess.run([str(_binary(root, "mysqld")), "--no-defaults", "--version"], capture_output=True, timeout=30, text=True)
    except OSError as exc:
        raise PortableError("MySQL could not start. On Windows x64, run mysql/prerequisites/INSTALL_VC_RUNTIME.bat to install the Microsoft Visual C++ x64 runtime, then retry.") from exc
    if result.returncode or not re.search(r"\b" + re.escape(VERSION_PREFIX) + r"\b", result.stdout):
        raise PortableError("The bundled MySQL 8.4.11 runtime could not be verified. Check Microsoft Visual C++ x64 support and restore the matching runtime; do not replace the engine over existing data.")
    return runtime


def _portable_tree(root):
    root, base, runtime, data = _paths(root)
    # A junction/symlink out of the folder would defeat the backup guarantee.
    for part in (base, runtime, data, base / "logs", base / "run", base / "tmp", base / "imports"):
        if not part.resolve().is_relative_to(root):
            raise PortableError(f"Database path must stay inside the server folder: {part}")
    for folder in ("logs", "run", "tmp", "imports"):
        (base / folder).mkdir(parents=True, exist_ok=True)


def _option(value):
    value = str(value).replace("\\", "/")
    if any(x in value for x in ('"', '\n', '\r')):
        raise PortableError('The server path must not contain quotes or line breaks.')
    return '"' + value + '"'


def _configuration(root):
    root, base, runtime, data = _paths(root)
    _portable_tree(root)
    options = {
        "basedir": runtime, "datadir": data, "port": PORT,
        "bind-address": "127.0.0.1", "mysqlx": "OFF",
        "pid-file": base / "run/mysqld.pid", "log-error": base / "logs/mysql-error.log",
        "tmpdir": base / "tmp", "secure-file-priv": base / "imports",
        "local-infile": "OFF", "skip-name-resolve": "ON", "skip-log-bin": None,
        "character-set-server": "utf8mb4", "collation-server": "utf8mb4_unicode_ci",
        "lower-case-table-names": "1", "default-storage-engine": "InnoDB",
        "innodb-flush-log-at-trx-commit": "1", "innodb-doublewrite": "ON",
        "innodb-fast-shutdown": "0", "innodb-buffer-pool-size": "128M",
        "max-connections": "151", "max-allowed-packet": "64M",
        "log-error-verbosity": "2",
    }
    if os.name != "nt":
        options.update({"socket": ""})  # TCP only, same transport as Windows
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            options["user"] = "root"  # isolated Linux integration environment only
    text = "# Generated for this folder on every start. Do not copy external my.ini settings.\n[mysqld]\n"
    for key, value in options.items():
        text += key + ("=" + _option(value) if isinstance(value, Path) else "=" + str(value) if value is not None else "") + "\n"
    path = base / "my.ini"
    _write(path, text.encode("utf-8"))
    return path


def _listening():
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def _alive(pid):
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 5:
                raise PortableError("Cannot verify database process exit (access denied).")
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat")
        if stat.is_file() and stat.read_text().split(")", 1)[1].strip().startswith("Z"):
            return False
        return True
    except ProcessLookupError:
        return False


def _pid(root):
    try:
        return int((Path(root) / "mysql/run/mysqld.pid").read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _credentials(root):
    state = _read(Path(root) / "mysql/instance.json")
    if not state.get("root_password") or state.get("format") != 1:
        raise PortableError("This folder has no initialized portable MySQL. Run 02_SETUP_MYSQL.bat first.")
    return state


def _connection(root):
    import pymysql
    state = _credentials(root)
    connection = pymysql.connect(host="127.0.0.1", port=PORT, user="root",
        password=state["root_password"].encode("utf-8"), charset="utf8mb4", autocommit=True,
        connect_timeout=3, read_timeout=15, write_timeout=15)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT @@datadir, @@port, @@version, @@pid_file")
            datadir, port, version, pidfile = cur.fetchone()
        _, base, runtime, data = _paths(root)
        if Path(datadir).resolve() != data.resolve() or port != PORT or not str(version).startswith(VERSION_PREFIX):
            raise PortableError("Port 3307 belongs to a different database. No changes were made; stop that instance or run this folder on its own.")
        if Path(pidfile).resolve() != (base / "run/mysqld.pid").resolve():
            raise PortableError("Database PID file does not belong to this server folder.")
        return connection
    except BaseException:
        connection.close()
        raise


def status(root):
    root = Path(root).resolve()
    from venom.server.lifecycle import is_world_running
    state = _read(root / "mysql/instance.json")
    info = {"host": "127.0.0.1", "port": PORT, "data_directory": str(root / "mysql/data"),
            "initialized": bool(state.get("root_password")), "running": False,
            "owned": False, "world_running": is_world_running(root)}
    if _listening():
        info["running"] = True
        try:
            conn = _connection(root)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT @@version")
                    info["server_version"] = cur.fetchone()[0]
                info["owned"] = True
            finally:
                conn.close()
        except Exception:
            info["error"] = "Port 3307 is in use, but ownership/login could not be verified."
    elif _alive(_pid(root)):
        info["error"] = "Database is starting or stopping; wait before copying the folder."
    return info


def _start(root):
    root, base, runtime, data = _paths(root)
    ensure_runtime(root)
    state = _credentials(root)
    if _listening():
        connection = _connection(root)  # never accept TCP alone as readiness
        connection.close()
        return status(root)
    if _alive(_pid(root)):
        raise PortableError("This database process is still starting or stopping. Wait, then retry.")
    config = _configuration(root)
    args = [str(_binary(root, "mysqld")), "--defaults-file=" + str(config)]
    bootstrap = base / "run/bootstrap.sql"
    if state.get("stage") == "initialized":
        # Password consists exclusively of token_urlsafe characters. The init file
        # executes before network listeners open; no passwordless TCP window.
        if not re.fullmatch(r"[A-Za-z0-9_-]{40,}", state["root_password"]):
            raise PortableError("Invalid bootstrap credentials; restore mysql/instance.json.")
        password = state["root_password"]
        sql = ("ALTER USER 'root'@'localhost' IDENTIFIED BY '" + password + "';\n"
               "CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY '" + password + "';\n"
               "GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;\n")
        _write(bootstrap, sql.encode("ascii"))
        args.append("--init-file=" + str(bootstrap))
    elif state.get("stage") != "ready":
        raise PortableError("Initialization did not finish. Keep mysql/data and logs intact; see PORTABLE_SERVER_README.md recovery instructions.")
    launch = {}
    if os.name == "nt":
        launch["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        launch["start_new_session"] = True
    with (base / "logs/process.log").open("ab") as log:
        process = subprocess.Popen(args, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **launch)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise PortableError("MySQL exited during startup. Read mysql/logs/mysql-error.log and mysql/logs/process.log. No data was deleted.")
        try:
            conn = _connection(root)
            conn.close()
            state["stage"] = "ready"
            _write(base / "instance.json", state)
            bootstrap.unlink(missing_ok=True)
            return status(root)
        except Exception as exc:
            # Credentials are never written to the startup diagnostic.
            detail = str(exc) if isinstance(exc, PortableError) else type(exc).__name__ + (" " + str(exc.args[0]) if exc.args and isinstance(exc.args[0], int) else "")
            _write(base / "logs/readiness.txt", (detail + "\n").encode("utf-8"))
            time.sleep(0.25)
    raise PortableError("MySQL did not become ready within 120 seconds. It may still be starting; inspect mysql/logs before retrying. No process was forcibly killed.")


def start(root):
    root = Path(root).resolve()
    with _control_lock(root):
        return _start(root)


def prepare(root):
    root = Path(root).resolve()
    with _control_lock(root):
        ensure_runtime(root)
        base = root / "mysql"
        state = _read(base / "instance.json")
        if not state:
            if _listening() or _alive(_pid(root)):
                raise PortableError("Port 3307 or the database process is already in use. Close it before fresh setup.")
            data = base / "data"
            if data.exists() and any(data.iterdir()):
                raise PortableError("mysql/data is not empty but instance.json is missing. Restore the complete folder; setup will never overwrite existing data.")
            state = {"format": 1, "engine": VERSION_PREFIX, "stage": "initializing", "root_password": secrets.token_urlsafe(48)}
            config = _configuration(root)
            _write(base / "instance.json", state)
            args = [str(_binary(root, "mysqld")), "--defaults-file=" + str(config), "--initialize-insecure"]
            with (base / "logs/initialize.log").open("ab") as log:
                result = subprocess.run(args, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            if result.returncode:
                raise PortableError("MySQL initialization failed. Read mysql/logs/initialize.log and mysql/logs/mysql-error.log. Existing files have been preserved.")
            state["stage"] = "initialized"
            _write(base / "instance.json", state)
        info = _start(root)
        info["account"] = "folder-managed administrator"
        return info


def _identifier(value, label, max_length=64):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0," + str(max_length - 1) + r"}", value):
        raise PortableError(f"Invalid {label}: use letters, digits and underscores, starting with a letter (maximum {max_length}).")
    return value


def setup_database(root, answers=None, stage_callback=None):
    root = Path(root).resolve()
    answers = answers or {}
    def stage(name, state="started"):
        if stage_callback:
            stage_callback(name, state)
    stage("validate")
    prepare(root)
    from venom.server.lifecycle import WorldProcessLock
    from venom.server.database import Database
    with _control_lock(root), WorldProcessLock(root, publish=False):
        config_path = root / "config/server.json"
        config = _read(config_path)
        existing = config.get("database", {})
        saved = _read(root / "mysql/game-login.json")
        if existing and (existing.get("host") != "127.0.0.1" or int(existing.get("port", 0)) != PORT or not existing.get("portable")):
            raise PortableError("config/server.json points to another database. This setup requires this folder's portable MySQL configuration.")
        db = saved or existing or {"driver": "mysql", "host": "127.0.0.1", "port": PORT,
            "name": _identifier(answers.get("name", "digimon_venom_nxt"), "database name"),
            "user": _identifier(answers.get("user", "venom_nxt"), "database user", 32),
            "password": answers.get("password") or secrets.token_urlsafe(40),
            "account_host": "127.0.0.1", "portable": True}
        _identifier(db["name"], "database name")
        if db["name"].lower() in {"mysql", "sys", "information_schema", "performance_schema"}:
            raise PortableError("Choose a game database name such as digimon_venom_nxt; system database names are reserved.")
        _identifier(db["user"], "database user", 32)
        if db["user"].lower() in {"root", "mysql", "sys", "information_schema", "performance_schema"}:
            raise PortableError("Choose a game database user such as venom; system administrator names are reserved.")
        if saved or existing:
            for key in ("name", "user", "password"):
                if answers.get(key) and answers[key] != db[key]:
                    raise PortableError("The portable database is already configured. Setup preserves its name, login and saves; use the saved settings.")
        if not isinstance(db["password"], str) or not db["password"] or any(c in db["password"] for c in "\x00\r\n"):
            raise PortableError("Database password must be nonempty text without line breaks or NUL.")
        # Persist the chosen login before DDL so interrupted setup can retry it.
        _write(root / "mysql/game-login.json", db)
        stage("validate", "ok")
        stage("connect")
        conn = _connection(root)
        try:
            stage("connect", "ok")
            stage("provision")
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db['name']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                cur.execute("CREATE USER IF NOT EXISTS %s@'127.0.0.1' IDENTIFIED BY %s", (db["user"], db["password"]))
                # MySQL 8.4 partial_revokes defaults OFF; escaping '_' scopes grants exactly.
                cur.execute("SELECT @@partial_revokes")
                grant_name = db["name"] if cur.fetchone()[0] else db["name"].replace("_", "\\_")
                cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON `{grant_name}`.* TO %s@'127.0.0.1'", (db["user"],))
            stage("provision", "ok")
        finally:
            conn.close()
        stage("verify")
        game = Database(db, root=root)
        try:
            game.initialize()
            from venom.server.community_store import CommunityStore
            CommunityStore(game).initialize()
        finally:
            game.close()
        config["database"] = db
        config.setdefault("host", "0.0.0.0")
        config.setdefault("port", 8765)
        config.setdefault("allow_registration", True)
        _write(config_path, config)
        stage("verify", "ok")
        return db


def _stop_database(root):
    if not _listening():
        if _alive(_pid(root)):
            raise PortableError("Database process has not exited. Wait for clean shutdown before making a backup.")
        return
    conn = _connection(root)
    pid = _pid(root)
    if not pid:
        conn.close()
        raise PortableError("Cannot verify the database process ID; shutdown was not attempted.")
    try:
        with conn.cursor() as cur:
            cur.execute("SET GLOBAL innodb_fast_shutdown=0")
            cur.execute("SHUTDOWN")
    finally:
        conn.close()
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if not _alive(pid) and not _listening():
            return
        time.sleep(0.25)
    raise PortableError("MySQL is still shutting down. Do not zip or move the folder yet. Check mysql/logs/mysql-error.log; the database was not forcibly killed.")


def stop(root):
    root = Path(root).resolve()
    from venom.server.lifecycle import WorldProcessLock, read_world_control
    with _control_lock(root), WorldProcessLock(root, publish=False):
        control = read_world_control(root)
        if control and not (control.get("state") == "stopped" and control.get("clean") is True):
            raise PortableError("The world did not confirm a clean save. Restart the world and stop it with STOP_SERVER.bat before moving this folder.")
        _stop_database(root)
    return {"running": False, "message": "MySQL stopped cleanly."}


def stop_server(root):
    root = Path(root).resolve()
    from venom.server.lifecycle import WorldProcessLock, request_world_stop
    with _control_lock(root):
        request_world_stop(root, timeout=120)
        with WorldProcessLock(root, publish=False):
            _stop_database(root)
    return {"running": False, "message": "World and MySQL stopped. You may zip the entire server folder."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("command", choices=("setup", "start", "stop", "stop-server", "status", "doctor"))
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            db = setup_database(args.root)
            result = {"message": "Portable MySQL is ready.", "host": db["host"], "port": db["port"], "database": db["name"]}
        elif args.command in ("status", "doctor"):
            if args.command == "doctor":
                ensure_runtime(args.root)
            result = status(args.root)
        else:
            result = {"start": start, "stop": stop, "stop-server": stop_server}[args.command](args.root)
        print(json.dumps(result, indent=2))
        return 1 if result.get("error") else 0
    except KeyboardInterrupt:
        print("Interrupted. No forced database shutdown was performed. Check MYSQL_STATUS.bat before copying files.", file=sys.stderr)
        return 130
    except Exception as exc:
        # Do not echo DB driver exceptions: they can contain SQL or credentials.
        message = str(exc) if isinstance(exc, (PortableError, RuntimeError)) else f"{type(exc).__name__}: operation failed. Check mysql/logs and config; no existing data was removed."
        print("ERROR: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
