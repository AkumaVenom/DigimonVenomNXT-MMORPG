"""Guided setup operations, separate from the native window and console UI.

Only explicit configure operations change the game database or hosting files.
Connection tests read the server greeting and authenticate without selecting or
creating a database. Passwords are kept in memory and private server config.
"""
from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
import socket
import ssl
import threading
import time
import zipfile

from tools import setup
from tools.setup_diagnostics import DiagnosticReport, SetupFailure


def _failure(stage, code, message, action):
    return SetupFailure(stage=stage, code=code, message=message, action=action)


def inspect_mysql_endpoint(host, port, timeout=4.0):
    """Read a bounded protocol greeting without sending credentials or SQL."""
    deadline = time.monotonic() + timeout
    with socket.create_connection((host, port), timeout=timeout) as connection:
        def receive(count):
            data = bytearray()
            while len(data) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout()
                connection.settimeout(remaining)
                piece = connection.recv(count - len(data))
                if not piece:
                    raise _failure("endpoint", "NO_GREETING", "The selected service closed before sending a MySQL greeting.",
                                   "Check the MySQL port in XAMPP. The game port (normally 8765) is a separate service.")
                data.extend(piece)
            return bytes(data)

        try:
            header = receive(4)
            length = int.from_bytes(header[:3], "little")
            if header[3] != 0 or not 1 <= length <= 16384:
                raise _failure("endpoint", "NOT_MYSQL", "This port did not send a valid MySQL/MariaDB greeting.",
                               "Use the database service's port shown in XAMPP, usually 3306. Do not use a website or game port.")
            packet = receive(length)
        except (TimeoutError, socket.timeout) as exc:
            raise _failure("endpoint", "NO_GREETING", "The service did not send a MySQL greeting within four seconds.",
                           "Check that MySQL is running and use its configured port. Website/game ports often wait for a different protocol.") from exc
    if packet[0] == 255 and len(packet) >= 3:
        import pymysql
        raise pymysql.err.OperationalError(int.from_bytes(packet[1:3], "little"), "Server rejected the connection before authentication")
    separator = packet.find(b"\0", 1)
    fixed = separator + 1
    invalid = packet[0] != 10 or separator < 2 or len(packet) < fixed + 15
    if not invalid:
        flags = int.from_bytes(packet[fixed + 13:fixed + 15], "little")
        invalid = packet[fixed + 12] != 0 or (flags & 512 and len(packet) < fixed + 31)
    if invalid:
        raise _failure("endpoint", "NOT_MYSQL", "The selected port is not serving the supported MySQL protocol.",
                       "Choose your MySQL/MariaDB endpoint in XAMPP; leave the game TCP port for the Hosting page.")
    version = packet[1:separator].decode("ascii", "replace")
    return "".join(c for c in version if 32 <= ord(c) < 127)[:120]


def find_xampp_configs(root, candidates=None):
    """Read only known my.ini locations; never read passwords or scan ports."""
    if candidates is None:
        drive = os.environ.get("SystemDrive", "C:")
        bases = [Path(drive + "/xampp"), Path("D:/xampp"), Path("C:/tools/xampp")]
        location = os.environ.get("XAMPP_HOME")
        if location:
            bases.insert(0, Path(location))
        bases.extend([Path(root) / "xampp", Path(root).parent / "xampp"])
        candidates = [base / "mysql/bin/my.ini" for base in bases]
    results = []
    seen = set()
    for candidate in candidates:
        path = Path(candidate)
        if str(path) in seen or not path.is_file():
            continue
        seen.add(str(path))
        try:
            parser = configparser.RawConfigParser(strict=False, allow_no_value=True,
                                                 inline_comment_prefixes=("#", ";"))
            parser.read_string(path.read_text(encoding="utf-8-sig", errors="replace"))
            if not parser.has_section("mysqld"):
                continue
            raw_port = parser.get("mysqld", "port", fallback="3306")
            if raw_port is None:
                continue
            port = setup.validated_port(raw_port.strip().strip('"\''))
            results.append({"host": "127.0.0.1", "port": port, "path": str(path)})
        except (OSError, ValueError, configparser.Error):
            continue
    return results


def check_game_port(bind, port):
    family = socket.AF_INET6 if ":" in bind else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as candidate:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            candidate.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            candidate.bind((bind, port))
        except OSError as exc:
            raise _failure("hosting", "BIND_FAILED", "The game cannot use the selected local bind address and TCP port.",
                           "Use 0.0.0.0 to listen on this PC, and choose a free game port. Stop an already-running NXT server before rechecking.") from exc


def verify_tls_files(root, server_config, client_config):
    """Complete a real TLS handshake in memory with the player's trust settings."""
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(str(root / server_config["tls_cert"]), str(root / server_config["tls_key"]))
    client = ssl.create_default_context(cafile=str(root / client_config["ca_file"]))
    client.check_hostname = True
    incoming_client, outgoing_client = ssl.MemoryBIO(), ssl.MemoryBIO()
    incoming_server, outgoing_server = ssl.MemoryBIO(), ssl.MemoryBIO()
    peer = client.wrap_bio(incoming_client, outgoing_client,
                           server_hostname=client_config.get("server_name", client_config["host"]))
    authority = server.wrap_bio(incoming_server, outgoing_server, server_side=True)
    complete_client = complete_server = False
    for _ in range(20):
        if not complete_client:
            try:
                peer.do_handshake()
                complete_client = True
            except ssl.SSLWantReadError:
                pass
        if outgoing_client.pending:
            incoming_server.write(outgoing_client.read())
        if not complete_server:
            try:
                authority.do_handshake()
                complete_server = True
            except ssl.SSLWantReadError:
                pass
        if outgoing_server.pending:
            incoming_client.write(outgoing_server.read())
        if complete_client and complete_server:
            return peer.version()
    raise _failure("verify", "TLS_INCOMPLETE", "The certificate verification handshake did not complete.",
                   "Run the Hosting page again to generate a matching server certificate and player kit.")


class SetupService:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.report = DiagnosticReport(self.root)
        self.diagnostic_path = self.report.path
        self._tested = None
        self._stage = "validate"
        self._lock = threading.RLock()

    def _mark(self, stage, status="started", **metadata):
        self._stage = stage
        self.report.record(stage, "success" if status == "passed" else status, **metadata)

    def _read_config(self, name):
        try:
            config = setup.read_json(self.root / "config" / name)
            if not isinstance(config, dict):
                raise ValueError()
            return config
        except (ValueError, OSError) as exc:
            raise _failure("validate", "CONFIG_INVALID", "A saved configuration file could not be read.",
                           "Restore the config folder from your last working server backup. Keep that folder until its settings have been recovered.") from exc

    def defaults(self):
        try:
            return self._defaults()
        except Exception as exc:
            raise self.report.failure("validate", exc) from exc

    def _defaults(self):
        config = self._read_config("server.json")
        client = self._read_config("client.json")
        db = config.get("database") or {}
        if not isinstance(db, dict):
            raise _failure("validate", "CONFIG_INVALID", "Saved database settings are invalid.", "Restore a working config/server.json backup.")
        return {"host": db.get("host", "127.0.0.1"), "port": db.get("port", 3306),
                "name": db.get("name", "digimon_venom_nxt"), "user": db.get("user", "venom_nxt"),
                "account_host": db.get("account_host", "localhost"), "admin_user": "root",
                "public_host": client.get("host", "localhost"), "game_port": config.get("port", 8765),
                "bind": config.get("host", "0.0.0.0"), "has_database": bool(db)}

    def find_local_database(self):
        return find_xampp_configs(self.root)

    @staticmethod
    def _connection_settings(settings):
        try:
            host = setup.hostname(settings.get("host", "127.0.0.1"))
            port = setup.validated_port(settings.get("port", 3306))
        except (ValueError, TypeError) as exc:
            raise _failure("validate", "ENDPOINT_INVALID", "Enter a database hostname/IP and a separate port from 1 to 65535.",
                           "For same-PC XAMPP, use 127.0.0.1 and the MySQL port shown in its control panel. Do not paste a URL.") from exc
        user = settings.get("admin_user", "root")
        password = settings.get("admin_password", "")
        if not isinstance(user, str) or not user.strip() or any(ord(c) < 32 for c in user):
            raise _failure("validate", "USER_INVALID", "Enter the XAMPP administrator username.", "The usual XAMPP administrator username is root.")
        if not isinstance(password, str):
            raise _failure("validate", "PASSWORD_INVALID", "The administrator password must be text.", "Enter the existing XAMPP password, or leave it blank if it has no password.")
        try:
            password.encode("utf-8")
        except UnicodeError as exc:
            raise _failure("validate", "PASSWORD_INVALID", "The password contains an incomplete Unicode character.", "Clear the field and paste the complete password.") from exc
        return {"host": host, "port": port, "admin_user": user.strip(), "admin_password": password}

    @staticmethod
    def _connection_key(values):
        return tuple(values[k] for k in ("host", "port", "admin_user", "admin_password"))

    def test_database(self, settings):
        import pymysql
        with self._lock:
            self._tested = None
            try:
                self._mark("validate")
                values = self._connection_settings(settings)
                self._mark("endpoint", host=values["host"], port=values["port"])
                banner = inspect_mysql_endpoint(values["host"], values["port"])
                self._mark("endpoint", "passed", server_version=banner)
                self._mark("administrator", user=values["admin_user"])
                connection = pymysql.connect(host=values["host"], port=values["port"],
                    user=values["admin_user"], password=values["admin_password"].encode("utf-8"),
                    charset="utf8mb4", autocommit=True, connect_timeout=8, read_timeout=8, write_timeout=8)
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT VERSION(), CURRENT_USER()")
                        version, account = cursor.fetchone()
                finally:
                    connection.close()
                result = {"server_version": str(version), "account": str(account), "host": values["host"], "port": values["port"]}
                self._tested = self._connection_key(values)
                self._mark("administrator", "passed", **result)
                return result
            except Exception as exc:
                raise self.report.failure(self._stage, exc) from exc

    def configure_database(self, settings):
        with self._lock:
            try:
                self._mark("validate")
                values = self._connection_settings(settings)
                if self._tested != self._connection_key(values):
                    self.test_database(values)
                defaults = self.defaults()
                answers = {**values, **{key: settings.get(key, defaults[key]) for key in ("name", "user", "account_host")},
                           "password": settings.get("password", "")}
                try:
                    answers["name"] = setup.validated_identifier(answers["name"].strip(), "Database name")
                    answers["user"] = setup.validated_identifier(answers["user"].strip(), "Database username", 32)
                except (ValueError, AttributeError) as exc:
                    raise _failure("validate", "NAME_INVALID", "Use letters, digits and underscores for the game database and username, starting with a letter.",
                                   "Keep the suggested game database name and username for a fresh installation.") from exc
                if answers["user"].lower() in {"root", "mysql", "mariadb", values["admin_user"].lower()}:
                    raise _failure("validate", "USER_RESERVED", "Choose a separate username for the game's database login.", "Use the default venom_nxt; your XAMPP administrator remains separate.")
                password = answers["password"]
                if not isinstance(password, str) or any(ord(c) < 32 or ord(c) == 127 for c in password):
                    raise _failure("validate", "PASSWORD_INVALID", "Use a single-line game password without control characters.", "Leave this field blank to generate a game password automatically.")
                try:
                    password.encode("utf-8")
                except UnicodeError as exc:
                    raise _failure("validate", "PASSWORD_INVALID", "The game password contains an incomplete Unicode character.", "Clear the field and paste the complete password.") from exc
                self._mark("validate", "passed", database=answers["name"], user=answers["user"])
                return setup.mysql_setup(self.root, answers, interactive=False, stage_callback=self._mark)
            except Exception as exc:
                if isinstance(exc, SetupFailure):
                    raise self.report.failure(exc.stage, exc) from None
                raise self.report.failure(self._stage, exc) from exc

    def configure_hosting(self, settings):
        with self._lock:
            try:
                self._mark("hosting")
                try:
                    host = setup.hostname(settings.get("host", "localhost"))
                    port = setup.validated_port(settings.get("port", 8765))
                    bind = str(setup.ipaddress.ip_address(str(settings.get("bind", "0.0.0.0")).strip()))
                except (ValueError, TypeError) as exc:
                    raise _failure("hosting", "ADDRESS_INVALID", "Enter a hostname/IP, a valid game port and a local bind IP.", "Use localhost for local play, port 8765 if free, and bind 0.0.0.0. For online play use your public hostname/IP.") from exc
                check_game_port(bind, port)
                kit = setup.hosting_setup(self.root, {"host": host, "port": port, "bind": bind}, interactive=False)
                self._mark("hosting", "passed", host=host, port=port)
                return kit
            except Exception as exc:
                raise self.report.failure(self._stage, exc) from exc

    def verify_installation(self):
        from venom.server.database import Database, SCHEMA_VERSION
        with self._lock:
            try:
                self._mark("verify")
                config, client = self._read_config("server.json"), self._read_config("client.json")
                db = config.get("database")
                if not db or db.get("driver") != "mysql":
                    raise _failure("verify", "DATABASE_MISSING", "The server has no configured MySQL game login.", "Complete the Database and Game Login pages before starting the server.")
                database = Database(db)
                try:
                    with database._connect().cursor() as cursor:
                        cursor.execute("SELECT version FROM venom_schema")
                        if cursor.fetchall() != ((SCHEMA_VERSION,),):
                            raise _failure("verify", "SCHEMA_VERSION", "The saved database uses an unsupported game schema.", "Restore the matching server version or migrate your database before continuing.")
                        cursor.execute("SELECT username FROM venom_accounts LIMIT 0")
                        cursor.execute("SELECT username FROM venom_players LIMIT 0")
                finally:
                    database.close()
                if not client or not client.get("tls") or client.get("port") != config.get("port"):
                    raise _failure("verify", "HOSTING_MISSING", "Client and server connection settings are incomplete or use different ports.", "Complete the Hosting page to create matching settings and a player kit.")
                self._mark("verify", "passed", database=db["name"], user=db["user"])
                self._mark("hosting")
                tls_version = verify_tls_files(self.root, config, client)
                kit = self.root / "Public_Player_Connection_Kit.zip"
                with zipfile.ZipFile(kit) as archive:
                    if set(archive.namelist()) != {"config/client.json", "config/server-ca.pem"}:
                        raise _failure("hosting", "KIT_CONTENT", "The player kit has unexpected contents.", "Generate a fresh kit on the Hosting page.")
                    if json.loads(archive.read("config/client.json")) != client or archive.read("config/server-ca.pem") != (self.root / client["ca_file"]).read_bytes():
                        raise _failure("hosting", "KIT_MISMATCH", "The player kit does not match the current server settings.", "Generate a fresh kit on the Hosting page and copy it to each client.")
                check_game_port(config.get("host", "0.0.0.0"), int(config["port"]))
                self._mark("verify", "passed", host=client["host"], port=client["port"])
                return {"database": db["name"], "user": db["user"], "host": client["host"], "port": client["port"],
                        "tls": tls_version, "player_kit": str(kit), "ready": True,
                        "note": "Local configuration verified. Public Internet reachability, router forwarding and Windows Firewall are checked on your host."}
            except Exception as exc:
                raise self.report.failure(self._stage, exc) from exc

    def report_text(self):
        return self.report.text()
