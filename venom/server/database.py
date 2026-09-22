"""Transactional player persistence. SQLite is an explicitly local development mode."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA_VERSION = 1
USERNAME = re.compile(r"^[A-Za-z0-9_]{3,24}$")
SCRYPT_N, SCRYPT_R, SCRYPT_P = 16384, 8, 1


class DatabaseError(RuntimeError):
    pass


class AccountExists(ValueError):
    pass


def validate_credentials(username, password):
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        raise ValueError("Use 3–24 letters, numbers or underscores for your tamer name.")
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise ValueError("Password must contain 8–128 characters.")
    return username.lower()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N,
                            r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "$".join(("scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
                     base64.b64encode(salt).decode(), base64.b64encode(digest).decode()))


def verify_password(password: str, encoded: str) -> bool:
    try:
        kind, n, r, p, salt, expected = encoded.split("$")
        if kind != "scrypt" or (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        actual = hash_password(password, base64.b64decode(salt)).split("$")[-1]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class Database:
    """Each operation runs under a lock and its own committed transaction.

    Blocking calls are run by the server in worker threads. Revision checks and
    renewable session leases prevent two world processes from overwriting a player.
    """
    def __init__(self, config: dict, dev: bool = False):
        self.config = dict(config)
        self.driver = self.config.get("driver", "mysql")
        if self.driver not in ("mysql", "sqlite"):
            raise DatabaseError("Database driver must be mysql or sqlite.")
        if self.driver == "sqlite" and not dev:
            raise DatabaseError("SQLite is allowed only with --dev on localhost.")
        self.lock = threading.RLock()
        self.connection = None
        self.dummy_hash = hash_password(secrets.token_urlsafe(24))

    def _connect(self):
        if self.connection is None:
            if self.driver == "sqlite":
                path = self.config.get("path", "runtime/development.sqlite3")
                if path != ":memory:":
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                self.connection = sqlite3.connect(path, check_same_thread=False, timeout=15)
                self.connection.execute("PRAGMA foreign_keys=ON")
                self.connection.execute("PRAGMA journal_mode=WAL")
            else:
                import pymysql
                self.connection = pymysql.connect(
                    host=self.config.get("host", "127.0.0.1"),
                    port=int(self.config.get("port", 3306)),
                    user=self.config.get("user", "venom"),
                    # PyMySQL encodes str passwords as latin1. Our setup and JSON
                    # use UTF-8, including passwords containing non-ASCII text.
                    password=self.config.get("password", "").encode("utf-8"),
                    database=self.config.get("name", "digimon_venom_nxt"),
                    charset="utf8mb4", autocommit=False,
                    connect_timeout=10, read_timeout=15, write_timeout=15,
                )
        elif self.driver == "mysql":
            self.connection.ping(reconnect=True)
        return self.connection

    def _sql(self, sql):
        return sql if self.driver == "sqlite" else sql.replace("?", "%s")

    def initialize(self):
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                suffix = " ENGINE=InnoDB" if self.driver == "mysql" else ""
                c.execute("CREATE TABLE IF NOT EXISTS venom_schema (version INTEGER NOT NULL)" + suffix)
                c.execute("SELECT version FROM venom_schema")
                versions = c.fetchall()
                if versions and (len(versions) != 1 or versions[0][0] != SCHEMA_VERSION):
                    raise DatabaseError("Unsupported database schema; restore a compatible server or migrate first.")
                if not versions:
                    c.execute(self._sql("INSERT INTO venom_schema(version) VALUES (?)"), (SCHEMA_VERSION,))
                # Canonical ASCII account names avoid collation-dependent duplicates.
                c.execute("""CREATE TABLE IF NOT EXISTS venom_accounts (
                    username VARCHAR(24) PRIMARY KEY,
                    display_name VARCHAR(24) NOT NULL,
                    password_hash VARCHAR(256) NOT NULL,
                    created_at DOUBLE NOT NULL,
                    session_token VARCHAR(64) NULL,
                    lease_until DOUBLE NOT NULL DEFAULT 0
                )""" + suffix)
                c.execute("""CREATE TABLE IF NOT EXISTS venom_players (
                    username VARCHAR(24) PRIMARY KEY,
                    state_json LONGTEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0,
                    updated_at DOUBLE NOT NULL,
                    FOREIGN KEY(username) REFERENCES venom_accounts(username) ON DELETE CASCADE
                )""" + suffix)
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                c.close()

    def register(self, username, password, state):
        key = validate_credentials(username, password)
        encoded = hash_password(password)
        raw = self._serialize(state)
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                c.execute(self._sql("SELECT username FROM venom_accounts WHERE username=?"), (key,))
                if c.fetchone():
                    raise AccountExists("That tamer name is already registered.")
                c.execute(self._sql("INSERT INTO venom_accounts(username,display_name,password_hash,created_at) VALUES (?,?,?,?)"),
                          (key, username, encoded, time.time()))
                c.execute(self._sql("INSERT INTO venom_players(username,state_json,schema_version,revision,updated_at) VALUES (?,?,?,?,?)"),
                          (key, raw, SCHEMA_VERSION, 0, time.time()))
                db.commit()
            except AccountExists:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                # Handle concurrent registration on another process too.
                if isinstance(exc, sqlite3.IntegrityError) or type(exc).__name__ == "IntegrityError":
                    raise AccountExists("That tamer name is already registered.") from exc
                raise
            finally:
                c.close()
        return key

    def authenticate(self, username, password):
        key = validate_credentials(username, password)
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                c.execute(self._sql("SELECT password_hash FROM venom_accounts WHERE username=?"), (key,))
                row = c.fetchone()
                db.commit()
            finally:
                c.close()
        # Missing accounts pay the same scrypt cost as wrong passwords.
        valid = verify_password(password, row[0] if row else self.dummy_hash)
        return key if row and valid else None

    def acquire_session(self, username, token, lease_seconds=90):
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                now = time.time()
                c.execute(self._sql("""UPDATE venom_accounts SET session_token=?,lease_until=?
                    WHERE username=? AND (session_token IS NULL OR lease_until < ? OR session_token=?)"""),
                          (token, now + lease_seconds, username.lower(), now, token))
                ok = c.rowcount == 1
                db.commit()
                return ok
            except Exception:
                db.rollback()
                raise
            finally:
                c.close()

    def load(self, username):
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                c.execute(self._sql("SELECT state_json,schema_version,revision FROM venom_players WHERE username=?"), (username.lower(),))
                row = c.fetchone()
                db.commit()
            finally:
                c.close()
        if not row or row[1] != SCHEMA_VERSION:
            raise DatabaseError("Player save is missing or has an unsupported version.")
        state = json.loads(row[0])
        if not isinstance(state, dict) or not isinstance(state.get("party"), list):
            raise DatabaseError("Player save is invalid; contact the server administrator.")
        return state, int(row[2])

    @staticmethod
    def _serialize(state):
        return json.dumps(state, ensure_ascii=True, separators=(",", ":"), allow_nan=False)

    def save(self, username, state, revision, session_token=None):
        raw = self._serialize(state)
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                if session_token:
                    # Atomic lease ownership check and renewal, before updating the save.
                    c.execute(self._sql("""UPDATE venom_accounts SET lease_until=?
                        WHERE username=? AND session_token=? AND lease_until>=?"""),
                              (time.time() + 90, username.lower(), session_token, time.time()))
                    if c.rowcount != 1:
                        raise DatabaseError("Account session lease expired or belongs to another world server.")
                c.execute(self._sql("""UPDATE venom_players SET state_json=?,revision=revision+1,updated_at=?
                    WHERE username=? AND revision=?"""),
                          (raw, time.time(), username.lower(), revision))
                if c.rowcount != 1:
                    raise DatabaseError("Player save changed in another session; refusing to overwrite it.")
                db.commit()
                return revision + 1
            except Exception:
                db.rollback()
                raise
            finally:
                c.close()

    def release_session(self, username, token):
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                c.execute(self._sql("UPDATE venom_accounts SET session_token=NULL,lease_until=0 WHERE username=? AND session_token=?"),
                          (username.lower(), token))
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                c.close()

    def close(self):
        with self.lock:
            if self.connection is not None:
                self.connection.close()
                self.connection = None


def initialize_database(database_config: dict):
    """Setup entry point: create only this application's tables, never change users."""
    db = Database(database_config)
    try:
        db.initialize()
    finally:
        db.close()
