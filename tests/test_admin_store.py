"""Local operator metadata and destructive account writes preserve save guards."""
import json
import sqlite3
import time
from unittest.mock import patch

import pytest

from venom.server.admin_store import AdminStore
from venom.server.community_store import CommunityStore
from venom.server.database import Database, DatabaseError, verify_password


def state(name="Alice"):
    return {"username": name, "party": [], "credits": 400, "events": [],
            "season": {"week": 10**24, "elapsed_days": 7 * 10**24}}


@pytest.fixture
def database(tmp_path):
    db = Database({"driver": "sqlite", "path": str(tmp_path / "admin.sqlite3")}, dev=True)
    db.initialize()
    db.register("Alice", "old-password-123", state())
    db.register("Bobby", "other-password-123", state("Bobby"))
    yield db
    db.close()


def test_additive_upgrade_and_restart_preserve_existing_saves(database):
    before = database.load("alice")
    for table in ("venom_admin_warnings", "venom_admin_bans", "venom_admin_titles", "venom_admin_audit"):
        database.connection.execute("DROP TABLE " + table)
    database.connection.commit()
    database.initialize()
    database.initialize()
    assert database.load("alice") == before
    assert database.connection.execute("SELECT version FROM venom_schema").fetchall() == [(1,)]
    admin = AdminStore(database)
    warning = admin.add_warning("ALICE", "A saved warning")
    admin.set_ban("Bobby", None, "Permanent test")
    title = admin.add_title("Digital Champion")
    database.close()
    database.initialize()
    assert admin.warnings("alice") == [warning]
    assert admin.ban_status("bobby")["until"] is None
    assert admin.find_title(title["id"]) == title
    assert database.load("alice") == before


def test_temporary_permanent_bans_and_read_only_expiry(database):
    admin = AdminStore(database)
    before = database.load("alice")
    ban = admin.set_ban("ALICE", 2000, "Testing")
    assert admin.ban_status("alice", now=1999) == ban
    assert admin.ban_status("alice", now=2000) is None
    assert database.connection.execute("SELECT COUNT(*) FROM venom_admin_bans").fetchone()[0] == 1
    admin.set_ban("Alice", None, "Permanent")
    assert admin.ban_status("alice", now=10**15)["until"] is None
    assert admin.unban("Alice") is True
    assert admin.unban("Alice") is False
    assert admin.ban_status("alice") is None
    assert database.load("alice") == before
    for method, arguments in ((admin.set_ban, ("Ghost", None, "Reason")),
                              (admin.unban, ("Ghost",)), (admin.add_warning, ("Ghost", "Reason"))):
        with pytest.raises(DatabaseError, match="does not exist"):
            method(*arguments)
    for invalid in (True, 0, -1, float("inf"), float("nan"), "forever"):
        with pytest.raises(ValueError):
            admin.set_ban("alice", invalid, "Reason")


def test_warnings_are_private_bounded_and_pageable(database):
    admin = AdminStore(database)
    warnings = []
    for number in range(5):
        with patch("venom.server.admin_store.time.time", return_value=100 + number):
            warnings.append(admin.add_warning("ALICE", f"Reason {number}"))
    admin.add_warning("Bobby", "Other account")
    assert admin.warnings("alice", 2) == list(reversed(warnings))[:2]
    assert admin.warnings("alice", 2, page=1) == list(reversed(warnings))[2:4]
    assert len(admin.warnings("bobby")) == 1
    assert admin.warnings("alice", page=10**50) == []
    for invalid in ("", "a" * 241, "Injected\nconsole", "\x1b[31mEscape", "\u202eBidi"):
        with pytest.raises(ValueError):
            admin.add_warning("alice", invalid)
    for invalid in (True, -1, 0, "2"):
        with pytest.raises(ValueError):
            admin.warnings("alice", invalid)


def test_titles_have_stable_ids_casefold_uniqueness_and_safe_text(database):
    admin = AdminStore(database)
    first = admin.add_title("  Digital   Champion  ")
    assert first["name"] == "Digital Champion"
    assert admin.add_title("DIGITAL CHAMPION") == first
    assert admin.find_title("digital champion") == first
    assert admin.find_title(first["id"].upper()) == first
    assert admin.find_title("missing") is None
    unicode_title = admin.add_title("Straße Hero")
    assert admin.add_title("STRASSE HERO") == unicode_title
    assert len(admin.titles()) == 2
    for invalid in ("", "x" * 33, "Title\nInject", "Title\x00", "Title\u200b"):
        with pytest.raises(ValueError):
            admin.add_title(invalid)


def test_password_reset_requires_owned_unexpired_lease_and_only_stores_hash(database):
    assert database.acquire_session("alice", "owner")
    old = database.connection.execute("SELECT password_hash FROM venom_accounts WHERE username='alice'").fetchone()[0]
    for token in (None, "", "not-owner"):
        with pytest.raises(DatabaseError, match="lease"):
            database.reset_password("alice", "new-password-987", token)
    assert database.connection.execute("SELECT password_hash FROM venom_accounts WHERE username='alice'").fetchone()[0] == old
    assert database.reset_password("ALICE", "new-password-987", "owner")
    encoded = database.connection.execute("SELECT password_hash FROM venom_accounts WHERE username='alice'").fetchone()[0]
    assert encoded != old and "new-password" not in encoded
    assert verify_password("new-password-987", encoded)
    assert database.authenticate("alice", "new-password-987") == "alice"
    assert database.authenticate("alice", "old-password-123") is None
    lease = database.connection.execute("SELECT lease_until FROM venom_accounts WHERE username='alice'").fetchone()[0]
    with patch("venom.server.database.time.time", return_value=lease + 1):
        with pytest.raises(DatabaseError, match="lease"):
            database.reset_password("alice", "third-password-456", "owner")
    assert database.authenticate("alice", "new-password-987") == "alice"


def prepare_deletion(database):
    admin = AdminStore(database)
    admin.add_warning("alice", "Recorded")
    admin.set_ban("alice", None, "Recorded")
    admin.audit("ban", "alice", "MODERATOR", "success")
    saved, revision = database.load("alice")
    saved["_season_archive_pending"] = [{"week": 1, "card": {"winner": "Alice"}}]
    revision = database.save("alice", saved, revision)
    community = CommunityStore(database)
    community.initialize()
    community.register_many([{"id": "player:alice", "name": "Alice", "kind": "player"}], now=123)
    c = database.connection
    c.execute("INSERT INTO venom_ranked_records(season_id,participant_id) VALUES (1,'player:alice')")
    c.execute("INSERT INTO venom_ranked_rewards VALUES (1,'player:alice',100,1,123)")
    c.execute("INSERT INTO venom_rival_matches VALUES ('player:alice','old-match')")
    c.execute("INSERT INTO venom_rival_history VALUES ('player:alice','bot:one',1,0,123,'old-match')")
    c.execute("INSERT INTO venom_rival_history VALUES ('player:bobby','player:alice',1,0,123,'old-match')")
    c.execute("INSERT INTO venom_ranked_matches VALUES ('old-match',1,'player:bobby','player:alice','player:alice',1,123,?)",
              (json.dumps({"defender_name": "Alice"}),))
    c.commit()
    assert database.acquire_session("alice", "delete-owner")
    return revision


def test_delete_cleans_private_and_live_community_records_atomically(database):
    other = database.load("bobby")
    revision = prepare_deletion(database)
    assert database.delete_account("ALICE", "delete-owner", revision)
    for table in ("venom_accounts", "venom_players", "venom_season_history", "venom_admin_warnings", "venom_admin_bans"):
        assert database.connection.execute(f"SELECT COUNT(*) FROM {table} WHERE username='alice'").fetchone()[0] == 0
    for table in ("venom_ranked_records", "venom_ranked_rewards", "venom_rival_matches", "venom_rival_history", "venom_competitors"):
        assert database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert database.connection.execute("SELECT COUNT(*) FROM venom_ranked_matches").fetchone()[0] == 1
    assert database.connection.execute("SELECT COUNT(*) FROM venom_admin_audit").fetchone()[0] == 1
    assert database.load("bobby") == other
    database.register("Alice", "brand-new-password", state())
    assert AdminStore(database).ban_status("alice") is None
    assert database.load("alice")[1] == 0


def test_delete_checks_revision_and_lease_before_destructive_work(database):
    revision = prepare_deletion(database)
    before = database.load("alice")
    for token, check_revision in (("wrong", revision), (None, revision), ("delete-owner", revision - 1)):
        with pytest.raises(DatabaseError):
            database.delete_account("alice", token, check_revision)
        assert database.load("alice") == before
        assert AdminStore(database).warnings("alice")
        assert database.season_history("alice")["items"]
    lease = database.connection.execute("SELECT lease_until FROM venom_accounts WHERE username='alice'").fetchone()[0]
    with patch("venom.server.database.time.time", return_value=lease + 1):
        with pytest.raises(DatabaseError, match="lease"):
            database.delete_account("alice", "delete-owner", revision)
    assert database.load("alice") == before


def test_delete_failure_rolls_back_all_owned_rows(database):
    revision = prepare_deletion(database)
    database.connection.execute("""CREATE TRIGGER reject_account_delete BEFORE DELETE ON venom_accounts
        BEGIN SELECT RAISE(ABORT, 'simulated delete failure'); END""")
    database.connection.commit()
    with pytest.raises(sqlite3.IntegrityError, match="simulated delete failure"):
        database.delete_account("alice", "delete-owner", revision)
    assert database.load("alice")[1] == revision
    assert len(database.season_history("alice")["items"]) == 1
    assert AdminStore(database).warnings("alice")
    assert AdminStore(database).ban_status("alice")
    assert database.connection.execute("SELECT COUNT(*) FROM venom_competitors").fetchone()[0] == 1


def test_audit_accepts_only_structured_metadata_without_secrets(database):
    admin = AdminStore(database)
    row = admin.audit("resetpassword", "ALICE", "ADMIN", "success")
    assert row["target"] == "alice"
    assert set(row) == {"id", "action", "target", "permission", "status", "created_at"}
    for action in ("resetpassword alice secret-password", "/resetpassword", "\x1breset", "reset\npassword"):
        with pytest.raises(ValueError):
            admin.audit(action)
    with pytest.raises(ValueError):
        admin.audit("ipinfo", "192.0.2.10")
    with pytest.raises(TypeError):
        admin.audit("resetpassword", "alice", password="secret-password")
    with pytest.raises(ValueError):
        admin.audit("resetpassword", "alice", status="secret-password")
    stored = database.connection.execute("SELECT * FROM venom_admin_audit").fetchall()
    assert len(stored) == 1
    assert "secret-password" not in repr(stored)
    assert "192.0.2.10" not in repr(stored)
