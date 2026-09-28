"""Startup progress is not a deadline, and only startup socket I/O is unbounded."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import copy
import logging
import sqlite3
import threading
from types import SimpleNamespace

import pymysql
import pytest

from venom.server import community as community_module
from venom.server import main as server_main
from venom.server.database import Database, DatabaseError


class RecordedConnection:
    """A MySQL socket stand-in that still runs the real identity verification."""

    def __init__(self, data_directory, port):
        self.identity = (str(data_directory), port)
        self.closed = 0
        self.cursor_closed = 0
        self.statements = []
        self.pings = []

    def cursor(self):
        connection = self

        class Cursor:
            def execute(self, sql):
                connection.statements.append(sql)

            def fetchone(self):
                return connection.identity

            def close(self):
                connection.cursor_closed += 1

        return Cursor()

    def ping(self, reconnect):
        self.pings.append(reconnect)

    def close(self):
        self.closed += 1


@pytest.fixture
def mysql_database(tmp_path, monkeypatch):
    db = Database({'driver': 'mysql', 'host': '127.0.0.1', 'port': 3307,
                   'user': 'venom', 'password': 'test-password', 'name': 'venom_test'},
                  root=tmp_path)
    calls, connections = [], []

    def connect(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        connection = RecordedConnection(db.data_directory, db.port)
        connections.append(connection)
        return connection

    monkeypatch.setattr(pymysql, 'connect', connect)
    yield db, calls, connections
    db.close()


def test_loading_changes_only_socket_io_and_rechecks_identity_on_every_connection(mysql_database):
    db, calls, connections = mysql_database
    live = db._connect()
    assert calls[-1]['read_timeout'] == calls[-1]['write_timeout'] == 15

    with db.loading_io():
        assert live.closed == 1
        assert db.connection is None
        loading = db._connect()
        assert calls[-1]['read_timeout'] is None
        assert calls[-1]['write_timeout'] is None
        assert loading is not live
        with db.loading_io():
            assert db._connect() is loading
            assert loading.closed == 0
        assert loading.closed == 0
        assert db._connect() is loading

    assert loading.closed == 1
    assert db.connection is None
    resumed = db._connect()
    assert resumed not in (live, loading)
    assert calls[-1]['read_timeout'] == calls[-1]['write_timeout'] == 15
    assert len(calls) == 3
    assert all(call['connect_timeout'] == 10 for call in calls)
    assert all(call['host'] == '127.0.0.1' and call['port'] == 3307 for call in calls)
    assert all(call['autocommit'] is False for call in calls)
    for connection in connections:
        assert connection.statements == ['SELECT @@datadir, @@port']
        assert connection.cursor_closed == 1
        assert all(reconnect is False for reconnect in connection.pings)


def test_loading_failure_closes_startup_connection_and_restores_live_timeouts(mysql_database):
    db, calls, _ = mysql_database
    with pytest.raises(RuntimeError, match='restore failed'):
        with db.loading_io():
            connection = db._connect()
            raise RuntimeError('restore failed')
    assert connection.closed == 1
    assert db.connection is None
    assert db._loading_io == 0
    db._connect()
    assert calls[-1]['read_timeout'] == calls[-1]['write_timeout'] == 15
    assert calls[-1]['connect_timeout'] == 10


def test_loading_still_rejects_foreign_mysql_identity(mysql_database, monkeypatch, tmp_path):
    db, _, _ = mysql_database
    foreign = RecordedConnection(tmp_path / 'another-server' / 'mysql' / 'data', db.port)
    monkeypatch.setattr(pymysql, 'connect', lambda **kwargs: foreign)
    with pytest.raises(DatabaseError, match='outside this server'):
        with db.loading_io():
            db._connect()
    assert foreign.statements == ['SELECT @@datadir, @@port']
    assert foreign.cursor_closed == 1
    assert foreign.closed == 1
    assert db.connection is None
    assert db._loading_io == 0


def test_heartbeat_can_acquire_database_lock_while_loading_context_is_active(mysql_database):
    db, calls, _ = mysql_database
    caller = threading.get_ident()

    def heartbeat():
        assert threading.get_ident() != caller
        acquired = db.lock.acquire(timeout=1)
        if not acquired:
            return False
        try:
            assert db._loading_io > 0
            db._connect()
            return True
        finally:
            db.lock.release()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with db.loading_io():
            assert pool.submit(heartbeat).result(timeout=2), 'Loading retained the DB lock across its yield'
            assert calls[-1]['read_timeout'] is None
    assert db._loading_io == 0


def test_sqlite_loading_keeps_its_connection_state_and_normal_timeout(tmp_path, monkeypatch):
    calls = []
    original_connect = sqlite3.connect

    def connect(*args, **kwargs):
        calls.append((args, dict(kwargs)))
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', connect)
    db = Database({'driver': 'sqlite', 'path': ':memory:'}, dev=True, root=tmp_path)
    try:
        connection = db._connect()
        connection.execute('CREATE TABLE retained(value TEXT NOT NULL)')
        connection.execute('INSERT INTO retained(value) VALUES (?)', ('saved progress',))
        connection.commit()
        with pytest.raises(RuntimeError, match='sqlite restore failed'):
            with db.loading_io():
                with db.loading_io():
                    assert db._connect() is connection
                assert connection.execute('SELECT value FROM retained').fetchone() == ('saved progress',)
                raise RuntimeError('sqlite restore failed')
        assert db._connect() is connection
        assert connection.execute('SELECT value FROM retained').fetchone() == ('saved progress',)
        assert db._loading_io == 0
        assert len(calls) == 1
        assert calls[0][1]['timeout'] == 15
        assert calls[0][1]['check_same_thread'] is False
    finally:
        db.close()


def test_many_progress_intervals_do_not_cancel_or_time_limit_startup(tmp_path, monkeypatch, caplog):
    db = Database({'driver': 'sqlite', 'path': ':memory:'}, dev=True, root=tmp_path)
    entered, release = threading.Event(), threading.Event()
    clock = {'now': 1000.0}
    observations = []

    class ControlledCommunity:
        ready = False
        calls = 0

        def initialize(self):
            self.calls += 1
            assert db._loading_io == 1
            entered.set()
            # Test watchdog only. Production startup has no overall deadline.
            assert release.wait(5), 'Test did not release its controlled worker'
            self.ready = True

    service = ControlledCommunity()
    monkeypatch.setattr(community_module, 'Community', lambda *args: service)
    # Replace this module's clock, not the process clock used by asyncio.
    monkeypatch.setattr(server_main, 'time', SimpleNamespace(monotonic=lambda: clock['now']))
    original_wait = asyncio.wait
    world = server_main.WorldServer(SimpleNamespace(root=tmp_path), db)

    async def rapid_progress(tasks, timeout):
        assert timeout == 15
        assert len(tasks) == 1
        worker = next(iter(tasks))
        if not observations:
            assert await asyncio.to_thread(entered.wait, 1)
        assert not worker.done()
        assert not worker.cancelled()
        assert world.community is None
        assert db._loading_io == 1
        observations.append(worker)
        clock['now'] += 15
        if len(observations) <= 137:
            await asyncio.sleep(0)
            return set(), set(tasks)
        release.set()
        done, pending = await original_wait(tasks, timeout=2)
        assert done == set(tasks) and not pending
        return done, pending

    monkeypatch.setattr(asyncio, 'wait', rapid_progress)
    try:
        with caplog.at_level(logging.INFO, logger=server_main.LOG.name):
            asyncio.run(world.initialize_community())
        assert len(observations) == 138
        assert len({id(worker) for worker in observations}) == 1
        assert not observations[0].cancelled()
        assert service.calls == 1 and service.ready
        assert world.community is service
        assert db._loading_io == 0
        progress = [record.getMessage() for record in caplog.records
                    if 'Still loading saved ranked seasons and rivals' in record.getMessage()]
        assert len(progress) == 137
        assert all('no overall timeout' in message for message in progress)
        assert '2055 seconds elapsed' in progress[-1]
    finally:
        release.set()
        db.close()


def test_failed_restore_leaves_no_published_service_and_exits_loading_mode(tmp_path, monkeypatch):
    db = Database({'driver': 'sqlite', 'path': ':memory:'}, dev=True, root=tmp_path)

    class FailedCommunity:
        ready = False

        def initialize(self):
            assert db._loading_io == 1
            raise DatabaseError('saved world failed validation')

    monkeypatch.setattr(community_module, 'Community', lambda *args: FailedCommunity())
    world = server_main.WorldServer(SimpleNamespace(root=tmp_path), db)
    try:
        with pytest.raises(DatabaseError, match='saved world failed validation'):
            asyncio.run(world.initialize_community())
        assert world.community is None
        assert db._loading_io == 0
    finally:
        db.close()
