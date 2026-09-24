"""Guided setup operations, separate from the native window and console UI.

Database preparation starts only this folder's portable MySQL process.
The game schema and hosting settings are created by the corresponding setup steps.
Passwords are kept in the private server folder and excluded from diagnostics.
"""
from __future__ import annotations

import json
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
                                   "Run START_MYSQL.bat in this server folder. The game port (normally 8765) is separate.")
                data.extend(piece)
            return bytes(data)

        try:
            header = receive(4)
            length = int.from_bytes(header[:3], "little")
            if header[3] != 0 or not 1 <= length <= 16384:
                raise _failure("endpoint", "NOT_MYSQL", "This port did not send a valid MySQL/MariaDB greeting.",
                               "The portable database uses 127.0.0.1:3307. Do not use a website or game port.")
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
                       "Run MYSQL_STATUS.bat to check this folder's database; leave the game TCP port for Hosting.")
    version = packet[1:separator].decode("ascii", "replace")
    return "".join(c for c in version if 32 <= ord(c) < 127)[:120]



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
        self.report.record(stage, "success" if status in ("passed", "ok") else status, **metadata)

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
        return {"host": "127.0.0.1", "port": 3307,
                "name": db.get("name", "digimon_venom_nxt"), "user": db.get("user", "venom_nxt"),
                "account_host": "127.0.0.1", "admin_user": "root",
                "public_host": client.get("host", "localhost"), "game_port": config.get("port", 8765),
                "bind": config.get("host", "0.0.0.0"), "has_database": bool(db)}

    def test_database(self, settings=None):
        """Prepare and identify our owned process without using supplied credentials."""
        from tools.portable_mysql import prepare
        with self._lock:
            self._tested = None
            try:
                self._mark("endpoint")
                result = prepare(self.root)
                self._tested = True
                self._mark("endpoint", "passed", **{
                    key: result[key] for key in ("host", "port", "server_version", "account") if key in result})
                return result
            except Exception as exc:
                raise self.report.failure(self._stage, exc) from exc

    def configure_database(self, settings=None):
        with self._lock:
            try:
                self._mark("validate")
                settings = settings or {}
                answers = {key: settings[key] for key in ("name", "user", "password") if key in settings}
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
                from tools.portable_mysql import prepare
                prepare(self.root)
                database = Database(db, root=self.root)
                try:
                    with database._connect().cursor() as cursor:
                        cursor.execute("SELECT version FROM venom_schema")
                        if cursor.fetchall() != ((SCHEMA_VERSION,),):
                            raise _failure("verify", "SCHEMA_VERSION", "The saved database uses an unsupported game schema.", "Restore the matching complete server backup before continuing.")
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
