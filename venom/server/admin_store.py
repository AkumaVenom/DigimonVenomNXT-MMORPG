"""Local-console moderation metadata, separate from game and Season clocks.

Only the host's console dispatcher calls these writes. This module never accepts
network requests, plaintext command lines, passwords, or connection addresses.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import math
import re
import secrets
import time
import unicodedata

from venom.server.database import DatabaseError, USERNAME


def account_key(username):
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        raise ValueError("Use an exact registered tamer name (3–24 letters, numbers or underscores).")
    return username.lower()


def clean_text(value, maximum, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    # Reject line breaks, terminal escape sequences, invisible controls and
    # directional overrides before whitespace normalization.
    if any(unicodedata.category(char).startswith("C") or char in "\r\n\t" for char in value):
        raise ValueError(f"{label} cannot contain control characters.")
    value = " ".join(unicodedata.normalize("NFC", value).split())
    if not 1 <= len(value) <= maximum:
        raise ValueError(f"{label} must contain 1–{maximum} characters.")
    return value


class AdminStore:
    def __init__(self, database):
        self.database = database
        self._sql = database._sql

    @contextmanager
    def transaction(self):
        with self.database.lock:
            db = self.database._connect()
            cursor = db.cursor()
            try:
                if self.database.driver == "sqlite":
                    cursor.execute("BEGIN IMMEDIATE")
                yield cursor
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                cursor.close()

    def initialize(self, cursor=None):
        """Add tables without rewriting accounts, saves, or existing version 1."""
        if cursor is None:
            with self.transaction() as owned:
                return self.initialize(owned)
        suffix = " ENGINE=InnoDB" if self.database.driver == "mysql" else ""
        for statement in (
            """CREATE TABLE IF NOT EXISTS venom_admin_warnings (
                id CHAR(32) PRIMARY KEY, username VARCHAR(24) NOT NULL,
                reason VARCHAR(240) NOT NULL, created_at DOUBLE NOT NULL,
                FOREIGN KEY(username) REFERENCES venom_accounts(username) ON DELETE CASCADE)""",
            """CREATE TABLE IF NOT EXISTS venom_admin_bans (
                username VARCHAR(24) PRIMARY KEY, until_at DOUBLE NULL,
                reason VARCHAR(240) NOT NULL, created_at DOUBLE NOT NULL,
                FOREIGN KEY(username) REFERENCES venom_accounts(username) ON DELETE CASCADE)""",
            """CREATE TABLE IF NOT EXISTS venom_admin_titles (
                id CHAR(16) PRIMARY KEY, name VARCHAR(32) NOT NULL,
                name_key CHAR(64) NOT NULL UNIQUE, created_at DOUBLE NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS venom_admin_audit (
                id CHAR(32) PRIMARY KEY, action VARCHAR(48) NOT NULL,
                target VARCHAR(24) NULL, permission VARCHAR(16) NOT NULL,
                status VARCHAR(12) NOT NULL, created_at DOUBLE NOT NULL)""",
        ):
            cursor.execute(statement + suffix)
        for name, table, columns in (
            ("venom_warning_owner_time", "venom_admin_warnings", "username, created_at"),
            ("venom_admin_audit_time", "venom_admin_audit", "created_at"),
        ):
            if self.database.driver == "mysql":
                cursor.execute(self._sql("SELECT COUNT(*) FROM information_schema.statistics "
                                        "WHERE table_schema=DATABASE() AND table_name=? AND index_name=?"),
                               (table, name))
                if not cursor.fetchone()[0]:
                    cursor.execute(f"CREATE INDEX {name} ON {table} ({columns})")
            else:
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")

    def _require_account(self, cursor, key):
        # On MySQL the account lock serializes moderation with account deletion.
        suffix = " FOR UPDATE" if self.database.driver == "mysql" else ""
        cursor.execute(self._sql("SELECT username FROM venom_accounts WHERE username=?" + suffix), (key,))
        if not cursor.fetchone():
            raise DatabaseError("That tamer account does not exist.")

    @staticmethod
    def _ban(row):
        return dict(zip(("username", "until", "reason", "created_at"), row)) if row else None

    def ban_status(self, username, now=None):
        """Return the active ban; reading never removes an expired record."""
        key = account_key(username)
        now = time.time() if now is None else float(now)
        if not math.isfinite(now):
            raise ValueError("The ban check needs a finite real timestamp.")
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT username,until_at,reason,created_at "
                                     "FROM venom_admin_bans WHERE username=?"), (key,))
            record = self._ban(cursor.fetchone())
            if record and (record["until"] is None or record["until"] > now):
                return record
        return None

    def set_ban(self, username, until, reason):
        key = account_key(username)
        reason = clean_text(reason, 240, "Reason")
        if until is not None:
            if isinstance(until, bool) or not isinstance(until, (int, float)) or not math.isfinite(until) or until <= 0:
                raise ValueError("Ban expiry must be a positive real timestamp, or permanent.")
            until = float(until)
        stamp = time.time()
        with self.transaction() as cursor:
            self._require_account(cursor, key)
            cursor.execute(self._sql("SELECT username FROM venom_admin_bans WHERE username=?"), (key,))
            if cursor.fetchone():
                cursor.execute(self._sql("UPDATE venom_admin_bans SET until_at=?,reason=?,created_at=? WHERE username=?"),
                               (until, reason, stamp, key))
            else:
                cursor.execute(self._sql("INSERT INTO venom_admin_bans(username,until_at,reason,created_at) VALUES (?,?,?,?)"),
                               (key, until, reason, stamp))
        return {"username": key, "until": until, "reason": reason, "created_at": stamp}

    def unban(self, username):
        key = account_key(username)
        with self.transaction() as cursor:
            self._require_account(cursor, key)
            cursor.execute(self._sql("DELETE FROM venom_admin_bans WHERE username=?"), (key,))
            return cursor.rowcount > 0

    def add_warning(self, username, reason):
        key = account_key(username)
        reason = clean_text(reason, 240, "Reason")
        record = {"id": secrets.token_hex(16), "username": key, "reason": reason, "created_at": time.time()}
        with self.transaction() as cursor:
            self._require_account(cursor, key)
            cursor.execute(self._sql("INSERT INTO venom_admin_warnings(id,username,reason,created_at) VALUES (?,?,?,?)"),
                           tuple(record[name] for name in ("id", "username", "reason", "created_at")))
        return record

    def warnings(self, username, limit=20, page=0):
        key = account_key(username)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("Warning limit must be a positive whole number.")
        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ValueError("Warning page must be a non-negative whole number.")
        limit = min(limit, 100)
        offset = page * limit
        if offset > 2**63 - 1:
            return []
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT id,username,reason,created_at FROM venom_admin_warnings "
                                     "WHERE username=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?"),
                           (key, limit, offset))
            return [dict(zip(("id", "username", "reason", "created_at"), row)) for row in cursor.fetchall()]

    @staticmethod
    def _title_key(name):
        return hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()

    def add_title(self, name):
        name = clean_text(name, 32, "Title")
        key = self._title_key(name)
        with self.transaction() as cursor:
            suffix = " FOR UPDATE" if self.database.driver == "mysql" else ""
            cursor.execute(self._sql("SELECT id,name FROM venom_admin_titles WHERE name_key=?" + suffix), (key,))
            old = cursor.fetchone()
            if old:
                return dict(zip(("id", "name"), old))
            ident = secrets.token_hex(8)
            cursor.execute(self._sql("INSERT INTO venom_admin_titles(id,name,name_key,created_at) VALUES (?,?,?,?)"),
                           (ident, name, key, time.time()))
            return {"id": ident, "name": name}

    def titles(self):
        with self.transaction() as cursor:
            cursor.execute("SELECT id,name FROM venom_admin_titles ORDER BY name,id")
            return [dict(zip(("id", "name"), row)) for row in cursor.fetchall()]

    def find_title(self, name_or_id):
        name = clean_text(name_or_id, 32, "Title")
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT id,name FROM venom_admin_titles WHERE id=? OR name_key=?"),
                           (name.lower(), self._title_key(name)))
            row = cursor.fetchone()
            return dict(zip(("id", "name"), row)) if row else None

    def audit(self, action, target=None, permission="OWNER", status="success"):
        """Record metadata only: never accept an arbitrary command/detail string."""
        if not isinstance(action, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", action):
            raise ValueError("Audit action must be a command identifier without arguments.")
        if permission not in ("PLAYER", "MODERATOR", "GAME MASTER", "GAME_MASTER", "ADMIN", "DEVELOPER", "OWNER"):
            raise ValueError("Invalid audit permission level.")
        if status not in ("success", "error", "denied", "ok", "failed"):
            raise ValueError("Invalid audit result.")
        key = account_key(target) if target is not None else None
        record = {"id": secrets.token_hex(16), "action": action, "target": key,
                  "permission": permission, "status": status, "created_at": time.time()}
        with self.transaction() as cursor:
            cursor.execute(self._sql("INSERT INTO venom_admin_audit(id,action,target,permission,status,created_at) "
                                     "VALUES (?,?,?,?,?,?)"), tuple(record.values()))
        return record
