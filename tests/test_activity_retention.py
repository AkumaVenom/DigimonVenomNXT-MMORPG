"""Global activity stays recent and bounded without touching game progress.

The activity dashboard deliberately uses conservative minute buckets: an entire
bucket expires at its start plus twelve hours, so no counter can include an
older action. Feed events retain their precise timestamps.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import time
from types import SimpleNamespace

import pytest

from venom.server.community_store import CommunityStore
from venom.server.database import Database

WINDOW = 12 * 60 * 60
BASE = 1_800_000_000.0  # UTC minute boundary.


@pytest.fixture
def world(monkeypatch, tmp_path):
    clock = [BASE]
    monkeypatch.setattr(time, 'time', lambda: clock[0])
    db = Database({'driver': 'sqlite', 'path': str(tmp_path / 'world.sqlite3')}, dev=True)
    db.initialize()
    store = CommunityStore(db)
    store.initialize()
    try:
        yield SimpleNamespace(clock=clock, db=db, store=store)
    finally:
        db.close()


def add_batch(world, ident='one', value=3, at=None, events=True):
    at = world.clock[0] if at is None else at
    payload = [{'id': 'event-' + ident, 'bot_id': 'bot:00001', 'kind': 'wild_win',
                'text': 'Won a wild battle.', 'at': at}] if events else []
    buckets = [{'at': int(at // 60) * 60, 'counters': {'wild_wins': value}}]
    world.store.add_activity_batch(payload, buckets, ident, at, now=world.clock[0])
    return payload, buckets


def table_count(world, table):
    return world.db.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


def test_minute_bucket_and_exact_feed_expire_without_any_new_activity(world):
    world.clock[0] = BASE + .25
    add_batch(world)
    world.clock[0] = BASE + WINDOW - .001
    before = world.store.activity_snapshot()
    assert before['counters']['wild_wins'] == 3
    assert len(before['events']) == 1
    assert before['window_seconds'] == WINDOW
    assert before['precision_seconds'] == 60

    # Counters never retain an older-than-window action. The newer exact feed
    # event remains visible for its final fraction of a second.
    world.clock[0] = BASE + WINDOW
    boundary = world.store.activity_snapshot()
    assert boundary['counters'].get('wild_wins', 0) == 0
    assert len(boundary['events']) == 1
    world.clock[0] += .25
    assert world.store.activity_snapshot()['events'] == []
    world.store.maintain_activity(drain=True)
    assert table_count(world, 'venom_activity_windows') == 0
    assert table_count(world, 'venom_activity') == 0
    assert table_count(world, 'venom_activity_batches') == 0


def test_retry_across_minute_boundary_counts_once_and_keeps_original_time(world):
    world.clock[0] = BASE + 59.75
    events, buckets = add_batch(world, 'stable-id', 7)
    original_at = world.clock[0]
    world.clock[0] += 1
    world.store.add_activity_batch(events, buckets, 'stable-id', original_at)
    snapshot = world.store.activity_snapshot()
    assert snapshot['counters']['wild_wins'] == 7
    assert len(snapshot['events']) == 1
    assert [bucket['at'] for bucket in snapshot['buckets']] == [BASE]
    assert table_count(world, 'venom_activity_batches') == 1
    # An independent counters-only flush is real activity even if its values
    # happen to match the preceding flush.
    add_batch(world, 'independent-id', 7, events=False)
    assert world.store.activity_snapshot()['counters']['wild_wins'] == 14


def test_expired_receipt_retry_cannot_resurrect_old_activity(world):
    events, buckets = add_batch(world, 'expired-id')
    world.clock[0] += WINDOW + 61
    world.store.maintain_activity(drain=True)
    assert table_count(world, 'venom_activity_batches') == 0
    world.store.add_activity_batch(events, buckets, 'expired-id', BASE)
    snapshot = world.store.activity_snapshot()
    assert snapshot['counters'].get('wild_wins', 0) == 0
    assert snapshot['events'] == []
    assert snapshot['buckets'] == []
    assert table_count(world, 'venom_activity_batches') == 0


def test_activity_commit_failure_rolls_back_receipt_events_and_counters(world):
    world.db.connection.execute(
        "CREATE TRIGGER fail_activity BEFORE INSERT ON venom_activity_windows "
        "BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END")
    world.db.connection.commit()
    with pytest.raises(sqlite3.DatabaseError, match='simulated disk failure'):
        add_batch(world, 'retry-after-failure', 9)
    for table in ('venom_activity_windows', 'venom_activity_batches', 'venom_activity'):
        assert table_count(world, table) == 0
    world.db.connection.execute('DROP TRIGGER fail_activity')
    world.db.connection.commit()
    add_batch(world, 'retry-after-failure', 9)
    assert world.store.activity_snapshot()['counters']['wild_wins'] == 9


def test_empty_flushes_do_not_create_receipts_and_fractional_distance_survives(world):
    for number in range(100):
        assert not world.store.add_activity_batch(
            [], [{'at': BASE, 'counters': {'wild_wins': 0}}], f'empty-{number}', BASE)
    assert table_count(world, 'venom_activity_batches') == 0
    assert table_count(world, 'venom_activity_windows') == 0
    world.store.add_activity_batch([], [{'at': BASE, 'counters': {'walking_distance': 1.25}}],
                                   'distance', BASE)
    assert world.store.activity_snapshot()['counters']['walking_distance'] == 1.25
    for value in (float('inf'), float('-inf'), float('nan')):
        with pytest.raises(ValueError, match='finite'):
            world.store.add_activity_batch([], [{'at': BASE, 'counters': {'walking_distance': value}}],
                                           'invalid-distance', BASE)
    assert world.store.activity_snapshot()['counters']['walking_distance'] == 1.25
    assert table_count(world, 'venom_activity_batches') == 1


def test_four_weeks_of_activity_keep_only_twelve_hours_of_storage(world):
    # Minute-frequency traffic first exercises the full 720-bucket bound.
    for minute in range(36 * 60):
        world.clock[0] = BASE + minute * 60
        add_batch(world, f'minute-{minute}', 1)
        if minute % 60 == 0:
            world.store.maintain_activity()
    world.store.maintain_activity(drain=True)
    assert table_count(world, 'venom_activity_windows') == 720
    assert table_count(world, 'venom_activity_batches') <= 720
    assert table_count(world, 'venom_activity') <= 100

    for hour in range(36, 28 * 24):
        world.clock[0] = BASE + hour * 3600
        add_batch(world, f'hour-{hour}', 1)
        world.store.maintain_activity()
    snapshot = world.store.activity_snapshot()
    assert snapshot['counters']['wild_wins'] == 12
    assert len(snapshot['buckets']) == 12
    assert len(snapshot['events']) == 12
    assert table_count(world, 'venom_activity_windows') == 12
    assert table_count(world, 'venom_activity_batches') == 12
    assert table_count(world, 'venom_activity_counters') == 0


def test_legacy_migration_drops_undated_global_totals_without_changing_progress(world):
    # Simulate the legacy database immediately before its first upgrade.
    bot = {'id': 'bot:00001', 'state': {'credits': 500, 'scan': {'agumon': 150},
           'party': [{'uid': 'partner', 'level': 44}], 'storage': []},
           'stats': {'wild_wins': 1000000}, 'runtime': {'cycle': 4000}}
    world.store.bot_save_batch([bot])
    human = {'username': 'ActivityHuman', 'credits': 54321, 'scan': {'agumon': 160}, 'party': [],
             'world_ds': {'crests': ['one', 'two']}}
    world.db.register('ActivityHuman', 'keep-progress-password', human)
    world.store.register_many([{'id': 'player:activityhuman', 'kind': 'player',
                                'name': 'ActivityHuman', 'tamer': 'test', 'party': []}], BASE)
    connection = world.db.connection
    connection.execute("UPDATE venom_competitors SET digirubies=137,career_wins=19 WHERE id='player:activityhuman'")
    connection.execute("INSERT INTO venom_ranked_matches VALUES ('past-match',1,'player:activityhuman','bot:00001','player:activityhuman',1,?,?)",
                       (BASE - 86400, json.dumps({'id': 'past-match', 'winner_id': 'player:activityhuman'})))
    connection.execute("DELETE FROM venom_community_meta WHERE name='activity_window_v1'")
    connection.execute("INSERT INTO venom_activity_counters(name,value) VALUES ('wild_wins',999999999)")
    connection.executemany('INSERT INTO venom_activity_batches(id,happened_at) VALUES (?,?)',
                           [(f'legacy-{i}', BASE - 7 * 86400) for i in range(2505)])
    connection.commit()
    original_human = world.db.load('activityhuman')
    original_match = connection.execute('SELECT * FROM venom_ranked_matches').fetchall()
    world.store.initialize()
    snapshot = world.store.activity_snapshot()
    assert snapshot['counters'].get('wild_wins', 0) == 0
    assert snapshot['tracking_since'] == BASE
    assert table_count(world, 'venom_activity_counters') == 0
    assert table_count(world, 'venom_activity_batches') == 0
    assert world.store.bot_load_all() == [bot]
    assert world.db.load('activityhuman') == original_human
    competitor = world.store.competitor('player:activityhuman')
    assert competitor['digirubies'] == 137 and competitor['career_wins'] == 19
    assert connection.execute('SELECT * FROM venom_ranked_matches').fetchall() == original_match
    add_batch(world, 'after-migration', 2)
    world.store.initialize()  # Migration may not wipe the new rolling window.
    assert world.store.activity_snapshot()['counters']['wild_wins'] == 2


def test_manager_idle_expiry_and_days_later_restart_preserve_all_rival_progress(world):
    from test_bots import make_manager, simulate

    manager = make_manager(count=2, store=world.store)
    simulate(manager, 90)
    manager.flush(force=True)
    saved = {row['id']: row for row in world.store.bot_load_all()}
    recent = manager.activity()
    assert recent['counters']['wild_wins'] > 0
    assert recent['events']
    same_day = make_manager(count=2, store=world.store)
    assert same_day.activity()['counters'] == recent['counters']

    world.clock[0] += 3 * 86400
    expired = manager.activity()  # No ticks, new events or flushes are needed.
    assert not any(expired['counters'].values())
    assert expired['events'] == []
    later = make_manager(count=2, store=world.store)
    assert not any(later.activity()['counters'].values())
    assert later.activity()['events'] == []
    assert later.processed == 0
    for ident, bot in later.bots.items():
        assert bot['state'] == saved[ident]['state']
        assert bot['stats'] == saved[ident]['stats']
        assert bot['runtime']['cycle'] == saved[ident]['runtime']['cycle']


def test_manager_lost_commit_acknowledgement_retries_frozen_payload_before_new_activity(world, monkeypatch):
    from test_bots import make_manager

    manager = make_manager(count=1, store=world.store)
    bot = manager.bots['bot:00001']
    original = world.store.add_activity_batch
    calls = []

    def commit_then_disconnect(*args, **kwargs):
        calls.append(copy.deepcopy(kwargs))
        result = original(*args, **kwargs)
        if len(calls) == 1:
            raise ConnectionError('Commit succeeded but its acknowledgement was lost')
        return result

    monkeypatch.setattr(world.store, 'add_activity_batch', commit_then_disconnect)
    world.clock[0] = BASE + 59.75
    manager._increment(bot, 'wild_wins', 7)
    manager._record(bot, 'wild_win', 'First batch')
    with pytest.raises(ConnectionError, match='acknowledgement'):
        manager.flush(force=True)
    assert world.store.activity_snapshot()['counters']['wild_wins'] == 7
    world.clock[0] += 1  # Retry crosses a minute boundary with new work waiting.
    manager._increment(bot, 'wild_wins', 5)
    manager._record(bot, 'wild_win', 'Second batch')
    manager.flush(force=True)
    assert len(calls) == 3
    assert calls[0]['batch_id'] == calls[1]['batch_id'] != calls[2]['batch_id']
    for key in ('batch_at', 'events', 'buckets'):
        assert calls[0][key] == calls[1][key]
    assert world.store.activity_snapshot()['counters']['wild_wins'] == 12
    assert manager.activity()['counters']['wild_wins'] == 12
    assert len(world.store.activity_snapshot()['events']) == 2
    assert table_count(world, 'venom_activity_batches') == 2
    assert bot['stats']['wild_wins'] == 12


def test_unflushed_manager_activity_remains_bounded_across_four_weeks(world):
    from test_bots import make_manager

    manager = make_manager(count=1, store=world.store, save_interval=10**12)
    bot = manager.bots['bot:00001']
    for hour in range(28 * 24):
        world.clock[0] = BASE + hour * 3600
        manager._increment(bot, 'exploration_steps')
        manager._record(bot, 'explore', f'Hour {hour}')
    current = manager.activity()
    assert current['counters']['exploration_steps'] == 12
    assert len(current['events']) == 12
    assert len(manager.activity_window.buckets) == 12
    assert len(manager.pending_buckets) == 12
    assert len(manager.pending_events) == 12
    assert bot['stats']['exploration_steps'] == 28 * 24
    manager.flush(force=True)
    assert world.store.activity_snapshot()['counters']['exploration_steps'] == 12
