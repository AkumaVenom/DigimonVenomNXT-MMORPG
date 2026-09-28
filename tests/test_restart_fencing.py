"""Restart lease concurrency, failure cleanup and successor ownership safety.

These tests exercise real SQLite transactions and the production heartbeat
thread. Only slow population-loading phases and wall-clock passage are replaced;
there is no real multi-minute sleep or imposed population-loading deadline.
"""
from __future__ import annotations

import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from venom.server import community as community_module
from venom.server import community_store as store_module
from venom.server.community import Community
from venom.server.community_store import CommunityStore
from venom.server.database import Database, DatabaseError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(tmp_path):
    db = Database({"driver": "sqlite", "path": str(tmp_path / "restart.sqlite3")}, dev=True)
    db.initialize()
    yield db
    db.close()


def lease_snapshot(store):
    with store.transaction(require_lease=False) as cursor:
        cursor.execute("SELECT value_json FROM venom_community_meta WHERE name='world_lease'")
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None


def saved_bots(store):
    with store.transaction(require_lease=False) as cursor:
        cursor.execute("SELECT state_json FROM venom_bot_state ORDER BY id")
        return [json.loads(row[0]) for row in cursor.fetchall()]


def population_stubs(monkeypatch, initialize=lambda: None, flush=lambda: None):
    """Replace costly phases, preserving Community's actual lifecycle and SQL."""
    class Ranked:
        def __init__(self, *args, **kwargs):
            pass

        def tick(self):
            pass

    class Bots:
        def __init__(self, *args, **kwargs):
            pass

        def initialize(self):
            initialize()

        def flush(self, force=False):
            assert force
            flush()

    monkeypatch.setattr(community_module, "GameEngine", lambda root: SimpleNamespace(root=root))
    monkeypatch.setattr("venom.server.ranked.RankedService", Ranked)
    monkeypatch.setattr("venom.server.bots.BotManager", Bots)
    monkeypatch.setattr(community_module, "LEASE_HEARTBEAT_SECONDS", .01)


def test_queued_heartbeat_uses_time_after_locked_transaction_finishes(database, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(store_module, "time", SimpleNamespace(time=lambda: clock[0]))
    store = CommunityStore(database)
    store.initialize()
    assert store.acquire_world("restoring-world", lease_seconds=90)
    store.owner_token = "restoring-world"
    original = {"id": "bot:00001", "earned_xp": 812345, "storage": [{"uid": "owned-partner"}]}
    store.bot_save_batch([original])
    waiting = threading.Event()
    result, errors = [], []

    class ObservedLock:
        def __enter__(self):
            if threading.current_thread().name == "queued-test-heartbeat":
                waiting.set()
            database.lock.acquire()
            return self

        def __exit__(self, *exc):
            database.lock.release()

    store.lock = ObservedLock()

    def renew():
        try:
            result.append(store.renew_world("restoring-world", lease_seconds=90))
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=renew, name="queued-test-heartbeat", daemon=True)
    with store.transaction() as cursor:
        worker.start()
        assert waiting.wait(2), "The heartbeat did not queue behind the owned transaction"
        # The transaction is still holding ownership. Simulate a restore query
        # lasting beyond 90 seconds while its queued heartbeat cannot get in.
        clock[0] += 121
        cursor.execute("UPDATE venom_bot_state SET updated_at=? WHERE id=?", (clock[0], original["id"]))
    worker.join(2)
    assert not worker.is_alive()
    assert not errors and result == [True]
    lease = lease_snapshot(store)
    assert lease["token"] == "restoring-world"
    assert lease["until"] >= clock[0] + 90, "A queued heartbeat must not overwrite renewal with a stale timestamp"
    assert store.bot_load_all() == [original]


@pytest.mark.parametrize("elapsed", [90, 91])
def test_expiry_without_a_held_transaction_does_not_allow_lease_resurrection(database, monkeypatch, elapsed):
    clock = [1000.0]
    monkeypatch.setattr(store_module, "time", SimpleNamespace(time=lambda: clock[0]))
    former = CommunityStore(database)
    former.initialize()
    assert former.acquire_world("former", lease_seconds=90)
    former.owner_token = "former"
    original = {"id": "bot:00001", "earned_xp": 812345, "scan": {"paradox_partner": 79}}
    former.bot_save_batch([original])
    clock[0] += elapsed
    expired = lease_snapshot(former)
    assert not former.renew_world("former", lease_seconds=90)
    with pytest.raises(DatabaseError, match="lease"):
        former.bot_save_batch([{"id": original["id"], "earned_xp": 0}])
    assert lease_snapshot(former) == expired
    assert saved_bots(former) == [original]
    successor = CommunityStore(database)
    assert successor.acquire_world("successor", lease_seconds=90)
    successor.owner_token = "successor"
    assert not former.renew_world("former")
    assert not former.release_world("former")
    assert successor.bot_load_all() == [original]


@pytest.mark.parametrize("release_fails", [False, True])
def test_failed_startup_stops_heartbeat_preserves_original_error_and_saved_progress(
        database, monkeypatch, release_fails):
    service = Community(SimpleNamespace(root=ROOT), database, {"rivals": {"count": 0}})
    service.store.initialize()
    original = {"id": "bot:00001", "earned_xp": 812345, "party": [{"uid": "persistent-partner", "level": 77}]}
    service.store.bot_save_batch([original])
    startup_error = RuntimeError("Specific saved population decode failure")
    workers = []

    def fail_restore():
        assert not service.ready and service.lease_owned
        workers.append(service._lease_thread)
        assert workers[-1].is_alive()
        raise startup_error

    population_stubs(monkeypatch, initialize=fail_restore)
    if release_fails:
        def fail_release(token):
            raise RuntimeError("Secondary database failure during lease release")
        monkeypatch.setattr(service.store, "release_world", fail_release)
    with pytest.raises(RuntimeError) as failure:
        service.initialize()
    assert failure.value is startup_error, "Cleanup must preserve the useful original loading error"
    assert not service.ready and not service.lease_owned
    assert service._lease_thread is None and service._lease_stop.is_set()
    assert not workers[0].is_alive()
    assert saved_bots(service.store) == [original]
    if not release_fails:
        assert lease_snapshot(service.store) is None
        assert CommunityStore(database).acquire_world("successor")
    else:
        # Failed cleanup must leave the existing lease to expire; it cannot
        # create a replacement population or hide the original restore error.
        assert lease_snapshot(service.store)["token"] == service.token


def test_heartbeat_stays_active_through_final_checkpoint_then_stops(database, monkeypatch):
    service = Community(SimpleNamespace(root=ROOT), database, {"rivals": {"count": 0}})
    heartbeat_during_flush = threading.Event()
    checkpoint_started = threading.Event()
    original_renew = service.store.renew_world
    flushes = []

    def observed_renew(*args, **kwargs):
        result = original_renew(*args, **kwargs)
        if checkpoint_started.is_set() and threading.current_thread().name == "venom-rival-lease":
            heartbeat_during_flush.set()
        return result

    def flush():
        flushes.append(True)
        checkpoint_started.set()
        assert service._lease_thread.is_alive()
        assert heartbeat_during_flush.wait(2), "Shutdown stopped renewal before its checkpoint finished"
        service.store.bot_save_batch([{"id": "bot:00001", "earned_xp": 812346}])

    monkeypatch.setattr(service.store, "renew_world", observed_renew)
    population_stubs(monkeypatch, flush=flush)
    service.initialize()
    worker = service._lease_thread
    try:
        service.shutdown()
        assert flushes == [True]
        assert not worker.is_alive() and service._lease_thread is None
        assert not service.ready and not service.lease_owned
        assert lease_snapshot(service.store) is None
        assert saved_bots(service.store) == [{"id": "bot:00001", "earned_xp": 812346}]
        service.shutdown()
        assert flushes == [True], "Repeated cleanup must not repeat the checkpoint"
    finally:
        service._stop_lease_heartbeat()


def test_heartbeat_owner_loss_latches_failure_and_never_flushes_over_successor(database, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(store_module, "time", SimpleNamespace(time=lambda: clock[0]))
    service = Community(SimpleNamespace(root=ROOT), database, {"rivals": {"count": 0}})
    flushes = []
    population_stubs(monkeypatch, flush=lambda: flushes.append(True))
    service.initialize()
    worker = service._lease_thread
    successor = CommunityStore(database)
    try:
        with database.lock:
            # The paused former process outlives its lease. A successor starts
            # legitimately before the former heartbeat can resume.
            clock[0] += 91
            assert successor.acquire_world("successor", lease_seconds=90)
            successor.owner_token = "successor"
            successor.bot_save_batch([{"id": "bot:00001", "earned_xp": 999999}])
        worker.join(2)
        assert not worker.is_alive(), "A rejected heartbeat must stop instead of reacquiring ownership"
        assert service._lease_error is not None and not service.ready
        with pytest.raises(DatabaseError, match="lease could not be maintained"):
            service.step(999, .1)
        with pytest.raises(DatabaseError, match="final rival checkpoint"):
            service.shutdown()
        assert not flushes and not service.lease_owned
        assert service._lease_thread is None
        assert successor.bot_load_all() == [{"id": "bot:00001", "earned_xp": 999999}]
        assert lease_snapshot(successor)["token"] == "successor"
        assert successor.renew_world("successor")
    finally:
        service._stop_lease_heartbeat()
