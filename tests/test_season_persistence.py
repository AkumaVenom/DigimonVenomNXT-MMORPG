"""Private careers and completed cards commit as one durable player revision."""
import asyncio
import copy
import sqlite3
from unittest.mock import patch

import pytest

from venom.server.database import Database, DatabaseError
from venom.server.main import Session, WorldServer


def player(name="Alice"):
    return {"username": name, "party": [], "events": [], "map_id": "test",
            "in_season": True, "season": {"elapsed_days": 0, "week": 1},
            "battle": None}


def archived(week, winner="Alice"):
    return {"week": week, "career_id": "private-career", "card": {
        "token": "card-" + str(week), "matches": [{"winner": winner}]}}


@pytest.fixture
def database(tmp_path):
    db = Database({"driver": "sqlite", "path": str(tmp_path / "season.sqlite3")}, dev=True)
    db.initialize()
    db.register("Alice", "private-password", player())
    db.register("Bobby", "private-password", player("Bobby"))
    yield db
    db.close()


def test_account_scoped_numeric_history_pagination_and_large_counters(database):
    weeks = [1, 2, 9, 10, 99, 100, 10**80, 10**80 + 1]
    state, revision = database.load("alice")
    state["_season_archive_pending"] = [archived(week) for week in weeks]
    assert database.save("alice", state, revision) == 1
    assert "_season_archive_pending" not in state
    other, revision = database.load("bobby")
    other["_season_archive_pending"] = [archived(100, "Bobby")]
    database.save("bobby", other, revision)

    first = database.season_history("ALICE", 0, 3)
    second = database.season_history("alice", 1, 3)
    last = database.season_history("alice", 2, 3)
    assert [row["week"] for page in (first, second, last) for row in page["items"]] == list(reversed(weeks))
    assert [page["has_more"] for page in (first, second, last)] == [True, True, False]
    assert database.season_history("bobby")["items"] == [archived(100, "Bobby")]
    assert database.season_history("missing")["items"] == []
    assert database.season_history("alice", 10**80)["items"] == []
    assert database.season_history("alice", page_size=999)["page_size"] == 20
    persisted, _ = database.load("alice")
    assert "_season_archive_pending" not in persisted
    rows = database.connection.execute("SELECT week,week_digits,created_at FROM venom_season_history WHERE username='alice'").fetchall()
    assert all(isinstance(week, str) and len(week) == digits and created > 0 for week, digits, created in rows)


@pytest.mark.parametrize("page,size", [(True, 10), (-1, 10), (1.5, 10), (0, False), (0, 0), (0, "10")])
def test_history_rejects_invalid_paging_without_touching_career(database, page, size):
    before = database.load("alice")
    with pytest.raises(ValueError):
        database.season_history("alice", page, size)
    assert database.load("alice") == before


def test_archive_insert_failure_rolls_back_player_lease_and_all_history(database):
    assert database.acquire_session("alice", "lease-owner")
    lease = database.connection.execute("SELECT lease_until FROM venom_accounts WHERE username='alice'").fetchone()[0]
    state, revision = database.load("alice")
    before = copy.deepcopy(state)
    state["season"] = {"elapsed_days": 14, "week": 3}
    state["_season_archive_pending"] = [archived(1), archived(2)]
    database.connection.execute("""CREATE TRIGGER fail_second_season_archive
        BEFORE INSERT ON venom_season_history WHEN NEW.week='2'
        BEGIN SELECT RAISE(ABORT, 'test archive failure'); END""")
    database.connection.commit()
    with pytest.raises(sqlite3.IntegrityError, match="test archive failure"):
        database.save("alice", state, revision, "lease-owner")
    assert database.load("alice") == (before, revision)
    assert len(state["_season_archive_pending"]) == 2
    assert database.season_history("alice")["items"] == []
    assert database.connection.execute("SELECT lease_until FROM venom_accounts WHERE username='alice'").fetchone()[0] == lease
    database.connection.execute("DROP TRIGGER fail_second_season_archive")
    database.connection.commit()
    assert database.save("alice", state, revision, "lease-owner") == 1
    assert "_season_archive_pending" not in state
    assert len(database.season_history("alice")["items"]) == 2


def test_stale_revision_wrong_lease_and_duplicate_week_cannot_rewrite_history(database):
    assert database.acquire_session("alice", "correct-owner")
    state, revision = database.load("alice")
    state["_season_archive_pending"] = [archived(1)]
    with pytest.raises(DatabaseError, match="lease"):
        database.save("alice", state, revision, "wrong-owner")
    assert state["_season_archive_pending"] == [archived(1)]
    revision = database.save("alice", state, revision, "correct-owner")

    state["_season_archive_pending"] = [archived(2)]
    state["season"]["week"] = 3
    with pytest.raises(DatabaseError, match="another session"):
        database.save("alice", state, revision - 1, "correct-owner")
    assert database.season_history("alice")["items"] == [archived(1)]
    assert state["_season_archive_pending"] == [archived(2)]

    state["_season_archive_pending"] = [archived(1, "rewritten-winner")]
    with pytest.raises(DatabaseError, match="already been archived"):
        database.save("alice", state, revision, "correct-owner")
    assert database.load("alice")[0]["season"]["week"] == 1
    assert database.season_history("alice")["items"] == [archived(1)]


@pytest.mark.parametrize("week", [True, -1, 0, "1", 1.5, None])
def test_archive_week_must_be_a_positive_counter(database, week):
    state, revision = database.load("alice")
    state["_season_archive_pending"] = [archived(week)]
    with pytest.raises(DatabaseError):
        database.save("alice", state, revision)
    assert database.load("alice")[1] == revision
    assert state["_season_archive_pending"]


def test_restart_and_real_time_jump_preserve_private_date_and_exact_battle(database):
    state, revision = database.load("alice")
    state["season"] = {"elapsed_days": 3652425, "week": 521776,
        "champion": "Alice", "rivalries": [{"opponent": "rook", "heat": 40}]}
    state["battle"] = {"kind": "season", "season": True, "turn": 7,
        "queue": [{"actor": "a", "action": "skill", "target": "b"}],
        "allies": [{"uid": "a", "hp": 32, "sp": 4}], "enemies": [{"uid": "b", "hp": 17}],
        "rng_state": [1, 17, 87], "log": ["Stored exact battle turn"]}
    revision = database.save("alice", state, revision)
    config = dict(database.config)
    database.close()
    reopened = Database(config, dev=True)
    try:
        with patch("venom.server.database.time.time", return_value=40_000_000_000):
            reopened.initialize()
            assert reopened.load("alice") == (state, revision)
            assert reopened.load("bobby")[0]["season"] == {"elapsed_days": 0, "week": 1}
    finally:
        reopened.close()


def test_world_clears_live_pending_only_after_successful_copied_save(database):
    state, revision = database.load("alice")
    assert database.acquire_session("alice", "world-owner")
    state["_season_archive_pending"] = [archived(1)]
    session = Session(None, "alice", "world-owner", state, revision)
    world = WorldServer(object(), database, {})
    with patch.object(database, "save", side_effect=DatabaseError("disk unavailable")):
        with pytest.raises(DatabaseError):
            asyncio.run(world.save(session))
    assert session.state["_season_archive_pending"] == [archived(1)]
    assert session.revision == revision
    asyncio.run(world.save(session))
    assert "_season_archive_pending" not in session.state
    assert session.revision == revision + 1
    assert database.season_history("alice")["items"] == [archived(1)]
