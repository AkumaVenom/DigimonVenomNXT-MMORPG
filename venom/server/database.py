"""Transactional player persistence. SQLite is an explicitly local development mode."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from venom.common.paths import mysql_data_path, root_path

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
    def __init__(self, config: dict, dev: bool = False, root=None):
        self.config = dict(config)
        self.root = Path(root or root_path()).resolve()
        self.driver = self.config.get("driver", "mysql")
        if self.driver not in ("mysql", "sqlite"):
            raise DatabaseError("Database driver must be mysql or sqlite.")
        if self.driver == "sqlite" and not dev:
            raise DatabaseError("SQLite is allowed only with --dev on localhost.")
        if self.driver == "mysql":
            if self.config.get("host", "127.0.0.1") != "127.0.0.1":
                raise DatabaseError("The world requires its own portable MySQL on 127.0.0.1.")
            self.port = int(self.config.get("port", 3307))
            if not 1 <= self.port <= 65535:
                raise DatabaseError("The portable MySQL port must be between 1 and 65535.")
            self.data_directory = mysql_data_path(self.root)
        self.lock = threading.RLock()
        self.connection = None
        self.dummy_hash = hash_password(secrets.token_urlsafe(24))

    def _connect(self):
        if self.connection is not None and self.driver == "mysql":
            import pymysql
            try:
                # Never let the driver reconnect to a replacement server before
                # checking that server's data directory again.
                self.connection.ping(reconnect=False)
            except pymysql.MySQLError:
                with contextlib.suppress(Exception):
                    self.connection.close()
                self.connection = None
        if self.connection is None:
            if self.driver == "sqlite":
                path = self.config.get("path", "runtime/development.sqlite3")
                if path != ":memory:":
                    path = str((self.root / path).resolve())
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                self.connection = sqlite3.connect(path, check_same_thread=False, timeout=15)
                self.connection.execute("PRAGMA foreign_keys=ON")
                self.connection.execute("PRAGMA journal_mode=WAL")
            else:
                import pymysql
                connection = pymysql.connect(
                    host="127.0.0.1",
                    port=self.port,
                    user=self.config.get("user", "venom"),
                    # PyMySQL encodes str passwords as latin1. Our setup and JSON
                    # use UTF-8, including passwords containing non-ASCII text.
                    password=self.config.get("password", "").encode("utf-8"),
                    database=self.config.get("name", "digimon_venom_nxt"),
                    charset="utf8mb4", autocommit=False,
                    connect_timeout=10, read_timeout=15, write_timeout=15,
                )
                try:
                    self._verify_portable_connection(connection)
                except Exception:
                    connection.close()
                    raise
                self.connection = connection
        return self.connection

    def _verify_portable_connection(self, connection):
        """Refuse external/XAMPP databases, including after a dropped connection."""
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT @@datadir, @@port")
            row = cursor.fetchone()
            if not row or len(row) != 2:
                raise DatabaseError("Could not verify the portable MySQL data directory.")
            actual = Path(str(row[0]).replace("\\", "/")).resolve()
            if actual != self.data_directory or int(row[1]) != self.port:
                raise DatabaseError(
                    "Refusing a database outside this server's mysql/data directory. "
                    "Start this folder's MySQL launcher before starting the world.")
        finally:
            cursor.close()

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
                # Additive to schema v1: old player saves remain readable. Keep
                # the full fictional week as decimal text, never a SQL date or
                # fixed-width integer. The digest makes the owner/week identity
                # indexable on MySQL without imposing a final fictional year.
                c.execute("""CREATE TABLE IF NOT EXISTS venom_season_history (
                    username VARCHAR(24) NOT NULL,
                    week_hash CHAR(64) NOT NULL,
                    week LONGTEXT NOT NULL,
                    week_digits BIGINT NOT NULL,
                    result_json LONGTEXT NOT NULL,
                    created_at DOUBLE NOT NULL,
                    PRIMARY KEY(username, week_hash),
                    FOREIGN KEY(username) REFERENCES venom_accounts(username)
                )""" + suffix)
                # Local-console metadata is an additive extension of schema 1.
                # Use this cursor so failed initialization never publishes only
                # part of the new account metadata on transactional backends.
                from venom.server.admin_store import AdminStore
                AdminStore(self).initialize(c)
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
        # This queue belongs to the transaction, not to the active player JSON.
        state = {key: value for key, value in state.items() if key != "_season_archive_pending"}
        return json.dumps(state, ensure_ascii=True, separators=(",", ":"), allow_nan=False)

    def save(self, username, state, revision, session_token=None):
        raw = self._serialize(state)
        pending = state.get("_season_archive_pending", [])
        if not isinstance(pending, list):
            raise DatabaseError("The season archive queue is invalid.")
        archives = []
        for result in pending:
            week = result.get("week") if isinstance(result, dict) else None
            if isinstance(week, bool) or not isinstance(week, int) or week < 1:
                raise DatabaseError("A season archive must contain a positive fictional booking week.")
            decimal = str(week)
            digest = hashlib.sha256(decimal.encode("ascii")).hexdigest()
            archives.append((digest, decimal, len(decimal), self._serialize(result)))
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
                for digest, decimal, digits, result_raw in archives:
                    c.execute(self._sql("""SELECT week FROM venom_season_history
                        WHERE username=? AND week_hash=?"""), (username.lower(), digest))
                    existing = c.fetchone()
                    if existing:
                        if existing[0] != decimal:
                            raise DatabaseError("Season archive identity collision; refusing to overwrite history.")
                        raise DatabaseError("This fictional booking week has already been archived.")
                    c.execute(self._sql("""INSERT INTO venom_season_history
                        (username,week_hash,week,week_digits,result_json,created_at)
                        VALUES (?,?,?,?,?,?)"""),
                        (username.lower(), digest, decimal, digits, result_raw, time.time()))
                db.commit()
                # Never discard unsaved history on a failed lease, stale CAS,
                # archive insertion failure, or failed database commit.
                state.pop("_season_archive_pending", None)
                return revision + 1
            except Exception:
                db.rollback()
                raise
            finally:
                c.close()

    def season_history(self, username, page=0, page_size=10):
        """Read one account's immutable completed weeks, newest first.

        Fictional time is independent of created_at, which is audit metadata.
        The world supplies its authenticated account key, never a client owner.
        """
        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ValueError("Choose a non-negative history page.")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
            raise ValueError("Choose a positive history page size.")
        page_size = min(page_size, 20)
        offset = page * page_size
        # SQL offsets have a machine integer limit; a page beyond every
        # physically possible archive is simply empty, never a career reset.
        if offset > 2**63 - 1:
            return {"items": [], "page": page, "page_size": page_size, "has_more": False}
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                c.execute(self._sql("""SELECT result_json FROM venom_season_history
                    WHERE username=? ORDER BY week_digits DESC, week DESC
                    LIMIT ? OFFSET ?"""), (username.lower(), page_size + 1, offset))
                rows = c.fetchall()
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                c.close()
        return {"items": [json.loads(row[0]) for row in rows[:page_size]],
                "page": page, "page_size": page_size, "has_more": len(rows) > page_size}

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

    def _require_admin_lease(self, cursor, username, session_token):
        """Lock the account row and verify ownership in the mutation transaction."""
        if not isinstance(session_token, str) or not session_token:
            raise DatabaseError("An owned account session lease is required.")
        now = time.time()
        cursor.execute(self._sql("""UPDATE venom_accounts SET lease_until=?
            WHERE username=? AND session_token=? AND lease_until>=?"""),
            (now + 90, username, session_token, now))
        if cursor.rowcount != 1:
            raise DatabaseError("Account session lease expired or belongs to another world server.")

    def reset_password(self, username, new_password, session_token):
        """Reset under an acquired lease; caller obtains secrets via hidden stdin.

        Plaintext is only fed to scrypt, never serialized into state or an audit
        record. The caller retains responsibility for releasing its lease.
        """
        key = validate_credentials(username, new_password)
        encoded = hash_password(new_password)
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                self._require_admin_lease(c, key, session_token)
                c.execute(self._sql("UPDATE venom_accounts SET password_hash=? WHERE username=?"), (encoded, key))
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                c.close()
        return True

    def delete_account(self, username, session_token, expected_revision):
        """Delete a confirmed offline account and owned records atomically.

        Account lease ownership and the confirmed revision must still match.
        Immutable public match results may retain historical display names;
        active ranked entries, defenders, reward records and private history do
        not survive deletion or leak into a later account with the same name.
        """
        from venom.server.admin_store import account_key
        key = account_key(username)
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise ValueError("Account deletion requires the confirmed save revision.")
        with self.lock:
            db = self._connect()
            c = db.cursor()
            try:
                self._require_admin_lease(c, key, session_token)
                c.execute(self._sql("SELECT revision FROM venom_players WHERE username=?"), (key,))
                row = c.fetchone()
                if not row or row[0] != expected_revision:
                    raise DatabaseError("Player save changed since confirmation; request a new deletion confirmation.")
                # Community may be disabled and its tables not installed. All
                # identifiers below are constants, never console input.
                if self.driver == "mysql":
                    c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE()")
                else:
                    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {str(row[0]) for row in c.fetchall()}
                participant = "player:" + key
                for table, column in (
                    ("venom_ranked_records", "participant_id"),
                    ("venom_ranked_rewards", "participant_id"),
                    ("venom_rival_matches", "player_id"),
                    ("venom_rival_history", "player_id"),
                    ("venom_competitors", "id"),
                ):
                    if table in tables:
                        c.execute(self._sql(f"DELETE FROM {table} WHERE {column}=?"), (participant,))
                if "venom_rival_history" in tables:
                    c.execute(self._sql("DELETE FROM venom_rival_history WHERE rival_id=?"), (participant,))
                for table in ("venom_season_history", "venom_admin_warnings", "venom_admin_bans", "venom_players"):
                    c.execute(self._sql(f"DELETE FROM {table} WHERE username=?"), (key,))
                c.execute(self._sql("DELETE FROM venom_accounts WHERE username=?"), (key,))
                if c.rowcount != 1:
                    raise DatabaseError("The account disappeared before deletion could commit.")
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                c.close()
        return True

    def close(self):
        with self.lock:
            if self.connection is not None:
                self.connection.close()
                self.connection = None


def initialize_database(database_config: dict, root=None):
    """Setup entry point: create only this application's tables, never change users."""
    db = Database(database_config, root=root)
    try:
        db.initialize()
    finally:
        db.close()
