"""Retire the final 2,000 legacy rivals without changing earned player history.

The full-fleet check uses all 5,000 durable IDs and real game-state templates.
There is no synthetic player socket and no need for a gigabyte-sized fixture.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from venom.common.game import GameEngine, GameError
from venom.server.bots import BotManager, STAT_KEYS
from venom.server.community import Community
from venom.server import community_store as store_module
from venom.server.community_store import CommunityStore
from venom.server.database import Database, DatabaseError


ROOT = Path(__file__).resolve().parents[1]
KEPT = tuple(f"bot:{ordinal:05d}" for ordinal in range(1, 3001))
RETIRED = tuple(f"bot:{ordinal:05d}" for ordinal in range(3001, 5001))
HUMAN = "player:retirementhuman"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.fixture(scope="module")
def engine():
    return GameEngine(ROOT, seed=5123)


@pytest.fixture
def store(tmp_path):
    database = Database({"driver": "sqlite", "path": str(tmp_path / "retirement.sqlite3")}, dev=True)
    database.initialize()
    storage = CommunityStore(database)
    storage.initialize()
    try:
        yield storage
    finally:
        database.close()


def table_rows(store, table):
    with store.transaction(require_lease=False) as cursor:
        cursor.execute(f"SELECT * FROM {table}")
        return sorted(cursor.fetchall())


def bot_ids(store):
    with store.transaction(require_lease=False) as cursor:
        cursor.execute("SELECT id FROM venom_bot_state ORDER BY id")
        return [row[0] for row in cursor.fetchall()]


def profile(engine, ident, state, kind="bot"):
    return {"id": ident, "kind": kind, "name": state["username"], "tamer": state["tamer"],
            "party": copy.deepcopy(state["party"]), "power": 1000}


def own_world(store, token="retirement-owner"):
    assert store.acquire_world(token, lease_seconds=90)
    store.owner_token = token


def seed_small_population(store):
    rows = [{"id": ident, "state": {"credits": 8701, "partner_uid": "keep-" + ident}}
            for ident in ("bot:00001", "bot:03000", "bot:03001", "bot:03101", "bot:05000")]
    store.bot_save_batch(rows)
    store.register_many([{"id": row["id"], "kind": "bot", "name": row["id"]} for row in rows], time.time())
    return rows


def test_real_5000_saved_fleet_retires_exactly_2000_and_old_config_cannot_regenerate_them(store, engine):
    template = engine.new_player("Template", next(iter(engine.tamers)), "agumon")
    template["credits"] = 54321
    template["scan"]["agumon"] = 140
    template["inventory"]["hp_s"] = 17
    template["storage"] = [engine._monster("gabumon", level=23, cam=42)]
    template["wins"], template["losses"] = 834, 19
    expected = {}
    rows, profiles = [], []
    for ordinal, ident in enumerate(KEPT + RETIRED, 1):
        state = copy.deepcopy(template)
        state["username"] = "SavedRival" + str(ordinal)
        state["credits"] += ordinal
        state["party"][0]["uid"] = "active-" + ident
        state["storage"][0]["uid"] = "stored-" + ident
        row = {"id": ident, "state": state, "runtime": {"phase": "explore", "cycle": ordinal,
               "dwell_remaining": 300}, "stats": {key: 0 for key in STAT_KEYS}}
        rows.append(row)
        profiles.append(profile(engine, ident, state))
        if ordinal <= 3000:
            expected[ident] = digest(state)
        if len(rows) == 100:
            store.bot_save_batch(rows)
            store.register_many(profiles, time.time())
            rows.clear()
            profiles.clear()
    assert len(bot_ids(store)) == 5000
    human = engine.new_player("RetirementHuman", next(iter(engine.tamers)), "agumon")
    human["credits"] = 976543
    human["scan"]["agumon"] = 89
    store.database.register("RetirementHuman", "population-test-password", human)
    store.register_many([profile(engine, HUMAN, human, "player")], time.time())
    with store.transaction() as cursor:
        cursor.execute("UPDATE venom_competitors SET digirubies=137 WHERE id=?", (HUMAN,))
        cursor.execute("INSERT INTO venom_ranked_seasons VALUES (17,10,20,'closed')")
        cursor.executemany("INSERT INTO venom_ranked_records VALUES (17,?,?,1,0,0,0,?)",
                           [(HUMAN, 100, 2), ("bot:05000", 200, 1)])
        cursor.executemany("INSERT INTO venom_ranked_rewards VALUES (17,?,?,?,20)",
                           [(HUMAN, 90, 2), ("bot:05000", 110, 1)])
        cursor.execute("INSERT INTO venom_ranked_matches VALUES ('human-retired',17,?,?,?,1,15,?)",
                       (HUMAN, "bot:05000", HUMAN,
                        json.dumps({"id": "human-retired", "attacker_id": HUMAN,
                                    "defender_id": "bot:05000", "winner_id": HUMAN, "ranked": True})))
        cursor.execute("INSERT INTO venom_rival_history VALUES (?,?,2,1,15,'human-retired')", (HUMAN, "bot:05000"))
        cursor.execute("INSERT INTO venom_rival_matches VALUES (?,'human-retired')", (HUMAN,))
        for ident in ("bot:00001", "bot:03000", "bot:03001", "bot:05000"):
            cursor.execute("INSERT INTO venom_activity VALUES (?,?,?, ?,?)",
                           ("activity-" + ident, ident, "travel", time.time(), json.dumps({"bot_id": ident})))
    protected = {table: table_rows(store, table) for table in (
        "venom_ranked_records", "venom_ranked_rewards", "venom_ranked_matches",
        "venom_rival_history", "venom_rival_matches")}
    saved_human = store.database.load("retirementhuman")
    before_kept_rows = {row[0]: row[1] for row in table_rows(store, "venom_bot_state") if row[0] in expected}
    for restart in range(2):
        service = Community(engine, store.database, {"rivals": {"count": 5000, "seed": 445}})
        try:
            service.initialize()
            assert service.ready and service.rivals_config["count"] == 3000
            assert set(service.bots.bots) == set(KEPT)
            assert bot_ids(store) == list(KEPT)
            assert {ident: digest(bot["state"]) for ident, bot in service.bots.bots.items()} == expected
            assert all(bot["runtime"]["cycle"] == int(ident.split(":")[1])
                       for ident, bot in service.bots.bots.items())
            assert service.bots.processed == 0
            assert set(service.ranked.profiles) == set(KEPT) | {HUMAN}
            assert {row[0] for row in table_rows(store, "venom_competitors")} == set(KEPT) | {HUMAN}
            assert not set(RETIRED) & {row[1] for row in table_rows(store, "venom_activity")}
            assert not set(RETIRED) & {row["id"] for row in service.ranked.available_opponents(HUMAN, 100)}
            with pytest.raises(GameError, match="registered competitor"):
                service.ranked.start_match(HUMAN, "bot:05000", match_id="retired-rejected")
            for table, original in protected.items():
                assert table_rows(store, table) == original, table
            assert store.database.load("retirementhuman") == saved_human
            assert store.competitor(HUMAN)["digirubies"] == 137
            historic = service.ranked.leaderboard("history", season_id=17)["entries"]
            assert [(row["id"], row["rank"]) for row in historic] == [(HUMAN, 2)]
            assert not service.store.rival_history(HUMAN)
            if restart == 0:
                # The retirement itself must never rewrite a kept checkpoint.
                assert {row[0]: row[1] for row in table_rows(store, "venom_bot_state")} == before_kept_rows
        finally:
            service.shutdown()


def test_retirement_retry_after_a_committed_batch_preserves_kept_rows(store, monkeypatch):
    seed_small_population(store)
    own_world(store)
    keep_before = {row[0]: row for row in table_rows(store, "venom_bot_state") if row[0] in KEPT}
    original = store.transaction
    commits = []

    @contextmanager
    def interrupted(*args, **kwargs):
        with original(*args, **kwargs) as cursor:
            yield cursor
        commits.append(True)
        if len(commits) == 2:  # Durable plan first, then the first deletion page.
            raise RuntimeError("Simulated process interruption after a committed retirement page")

    monkeypatch.setattr(store, "transaction", interrupted)
    with pytest.raises(RuntimeError, match="interruption"):
        store.retire_legacy_bots()
    monkeypatch.setattr(store, "transaction", original)
    assert "bot:03001" not in bot_ids(store) and "bot:03101" in bot_ids(store)
    store.retire_legacy_bots()
    assert set(bot_ids(store)) == {"bot:00001", "bot:03000"}
    assert {row[0]: row for row in table_rows(store, "venom_bot_state")} == keep_before
    once = {name: table_rows(store, name) for name in ("venom_bot_state", "venom_competitors")}
    store.retire_legacy_bots()
    assert all(table_rows(store, name) == rows for name, rows in once.items())


def test_retirement_requires_exclusive_population_ownership_before_deleting_anything(store):
    seed_small_population(store)
    before = table_rows(store, "venom_bot_state")
    with pytest.raises(DatabaseError, match="ownership|lease|owner"):
        store.retire_legacy_bots()
    assert table_rows(store, "venom_bot_state") == before


def test_interrupted_retirement_finishes_the_same_roster_change_across_a_season_boundary(store, monkeypatch):
    clock = [2_000_000_000.0]
    monkeypatch.setattr(store_module, "time", SimpleNamespace(time=lambda: clock[0]))
    identities = ("bot:00001", "bot:03000", HUMAN) + RETIRED
    kept = set(identities) - set(RETIRED)
    store.bot_save_batch([{"id": ident, "state": {"credits": 87654, "partner_uid": "saved-" + ident}}
                          for ident in identities])
    store.register_many([{"id": ident, "kind": "player" if ident == HUMAN else "bot", "name": ident}
                         for ident in identities], clock[0])
    with store.transaction() as cursor:
        cursor.execute("UPDATE venom_competitors SET digirubies=137 WHERE id=?", (HUMAN,))
        cursor.executemany("INSERT INTO venom_ranked_seasons VALUES (?,?,?,?)", [
            (1, clock[0] - 300, clock[0] - 200, "closed"),
            (2, clock[0] - 200, clock[0] - 100, "active"),
            (3, clock[0] - 100, clock[0] + 100, "active")])
        for season_id in (1, 2, 3):
            cursor.executemany("INSERT INTO venom_ranked_records VALUES (?,?,10,1,0,0,0,NULL)",
                               [(season_id, ident) for ident in identities])
    historical_before = [row for row in table_rows(store, "venom_ranked_records") if row[0] < 3]
    kept_states = [row for row in table_rows(store, "venom_bot_state") if row[0] in kept]
    own_world(store, "interrupted-owner")
    original = store.transaction
    commits = []

    @contextmanager
    def interrupted(*args, **kwargs):
        with original(*args, **kwargs) as cursor:
            yield cursor
        commits.append(True)
        if len(commits) == 2:
            raise RuntimeError("Interrupted after a committed 100-rival page")

    monkeypatch.setattr(store, "transaction", interrupted)
    with pytest.raises(RuntimeError, match="committed 100-rival"):
        store.retire_legacy_bots()
    monkeypatch.setattr(store, "transaction", original)
    rows = table_rows(store, "venom_ranked_records")
    assert len([row for row in rows if row[0] == 3 and row[1] in RETIRED]) == 1900
    pending = dict(table_rows(store, "venom_community_meta"))[CommunityStore.RETIREMENT_PLAN]
    assert json.loads(pending) == {"pending_season_ids": [3]}

    # This is a different legitimate world owner after the crashed process's
    # lease and original current season both expire. A new current season may
    # already exist from an interrupted administrative or older-server start.
    clock[0] += 200
    successor = CommunityStore(store.database)
    own_world(successor, "resumed-owner")
    with successor.transaction() as cursor:
        cursor.execute("INSERT INTO venom_ranked_seasons VALUES (4,?,?,'active')", (clock[0] - 100, clock[0] + 100))
        cursor.executemany("INSERT INTO venom_ranked_records VALUES (4,?,20,2,0,0,0,NULL)",
                           [(ident,) for ident in identities])
    current_kept = [row for row in table_rows(successor, "venom_ranked_records")
                    if row[0] >= 3 and row[1] in kept]
    removed = successor.retire_legacy_bots()
    assert removed["bot_states"] == 1900
    assert removed["season_records"] == 3900  # Original 1,900 plus all 2,000 in the new season.
    after = table_rows(successor, "venom_ranked_records")
    assert [row for row in after if row[0] < 3] == historical_before
    assert [row for row in after if row[0] >= 3] == current_kept
    assert table_rows(successor, "venom_bot_state") == kept_states
    assert {row[0] for row in table_rows(successor, "venom_competitors")} == kept
    assert successor.competitor(HUMAN)["digirubies"] == 137
    pending = dict(table_rows(successor, "venom_community_meta"))[CommunityStore.RETIREMENT_PLAN]
    assert json.loads(pending) == {"pending_season_ids": []}
    assert not any(successor.retire_legacy_bots().values())
    assert table_rows(successor, "venom_ranked_records") == after


@pytest.mark.parametrize("invalid_plan", ['invalid json', '{}', '{"pending_season_ids":[true]}'])
def test_invalid_retirement_plan_fails_before_any_population_data_is_removed(store, invalid_plan):
    seed_small_population(store)
    own_world(store)
    with store.transaction() as cursor:
        cursor.execute("INSERT INTO venom_community_meta VALUES (?,?)", (CommunityStore.RETIREMENT_PLAN, invalid_plan))
    before = table_rows(store, "venom_bot_state")
    with pytest.raises(DatabaseError, match="retirement plan is invalid"):
        store.retire_legacy_bots()
    assert table_rows(store, "venom_bot_state") == before


def test_expired_owner_cannot_retire_rows_after_a_successor_acquires_the_world(store, monkeypatch):
    seed_small_population(store)
    clock = [1000.0]
    monkeypatch.setattr(store_module, "time", SimpleNamespace(time=lambda: clock[0]))
    assert store.acquire_world("former", lease_seconds=90)
    store.owner_token = "former"
    before = table_rows(store, "venom_bot_state")
    clock[0] += 91
    successor = CommunityStore(store.database)
    assert successor.acquire_world("successor", lease_seconds=90)
    successor.owner_token = "successor"
    with pytest.raises(DatabaseError, match="lease"):
        store.retire_legacy_bots()
    assert table_rows(store, "venom_bot_state") == before
    assert successor.renew_world("successor", lease_seconds=90)
    successor.retire_legacy_bots()
    assert set(bot_ids(store)) == {"bot:00001", "bot:03000"}


def test_retirement_preserves_expired_season_placement_and_unpaid_human_rewards(store):
    own_world(store)
    store.register_many([{"id": ident, "kind": "player" if ident == HUMAN else "bot", "name": ident}
                         for ident in (HUMAN, "bot:00001", "bot:05000")], now=50)
    with store.transaction() as cursor:
        cursor.execute("UPDATE venom_competitors SET digirubies=137 WHERE id=?", (HUMAN,))
        cursor.execute("INSERT INTO venom_ranked_seasons VALUES (0,0,100,'active')")
        for ident, points in ((HUMAN, 100), ("bot:00001", 200), ("bot:05000", 300)):
            cursor.execute("INSERT INTO venom_ranked_records VALUES (0,?,?,1,0,0,0,NULL)", (ident, points))
            cursor.execute("INSERT INTO venom_ranked_matches VALUES (?,0,?, ?,?,1,50,'{}')",
                           ("old-" + ident, ident, "bot:00002", ident))
    store.retire_legacy_bots()
    store.season(1, 100, 200, 150, lambda rank, points, grade: 1000 - rank)
    assert store.record(HUMAN, 0)["final_rank"] == 3
    assert store.competitor(HUMAN)["digirubies"] == 137 + 997
    with store.transaction() as cursor:
        cursor.execute("SELECT amount,final_rank FROM venom_ranked_rewards WHERE participant_id=?", (HUMAN,))
        assert cursor.fetchall() == [(997, 3)]
    store.retire_legacy_bots()
    store.season(1, 100, 200, 150, lambda rank, points, grade: 1000 - rank)
    assert store.competitor(HUMAN)["digirubies"] == 137 + 997


def test_only_retired_ids_leave_current_season_while_expired_and_closed_records_remain(store, monkeypatch):
    clock = 2_000_000_000.0
    monkeypatch.setattr(store_module, "time", SimpleNamespace(time=lambda: clock))
    seed_small_population(store)
    # Human IDs and noncanonical/custom IDs must never enter the removal set.
    for ident in (HUMAN, "player:bot:03001", "bot:030001", "bot:05001"):
        store.bot_save_batch([{"id": ident, "state": {"credits": 8800}}])
        store.register_many([{"id": ident, "kind": "player", "name": ident}], clock)
    all_ids = bot_ids(store)
    with store.transaction() as cursor:
        cursor.executemany("INSERT INTO venom_ranked_seasons VALUES (?,?,?,?)", [
            (1, clock - 200, clock - 100, "closed"),
            (2, clock - 100, clock, "active"),
            (3, clock, clock + 100, "active")])
        for season_id in (1, 2, 3):
            cursor.executemany("INSERT INTO venom_ranked_records VALUES (?,?,10,1,0,0,0,NULL)",
                               [(season_id, ident) for ident in all_ids])
        cursor.executemany("INSERT INTO venom_activity VALUES (?,?,?, ?,?)",
                           [("activity-" + ident, ident, "walk", clock, "{}") for ident in all_ids])
    before = table_rows(store, "venom_ranked_records")
    own_world(store)
    removed = store.retire_legacy_bots()
    assert removed == {"bot_states": 3, "competitors": 3, "activity_events": 3, "season_records": 3}
    remaining = set(all_ids) - set(RETIRED)
    assert set(bot_ids(store)) == remaining
    assert {row[0] for row in table_rows(store, "venom_competitors")} == remaining
    assert {row[1] for row in table_rows(store, "venom_activity")} == remaining
    after = table_rows(store, "venom_ranked_records")
    assert [row for row in after if row[0] != 3] == [row for row in before if row[0] != 3]
    assert {row[1] for row in after if row[0] == 3} == remaining


def test_disabled_population_still_cleans_retired_profiles_before_loading_ranked(store, engine):
    template = engine.new_player("RetiredDefender", next(iter(engine.tamers)), "agumon")
    store.bot_save_batch([{"id": "bot:05000", "state": template}])
    store.register_many([profile(engine, "bot:05000", template)], time.time())
    service = Community(engine, store.database, {"rivals": {"enabled": False, "count": 5000}})
    try:
        service.initialize()
        assert service.ready and service.bots.count == 0
        assert not service.bots.bots and not service.ranked.profiles
        assert not bot_ids(store) and not table_rows(store, "venom_competitors")
    finally:
        service.shutdown()


@pytest.mark.parametrize("configured, expected", [(None, 3000), (5000, 3000), (3000, 3000), (7, 7)])
def test_population_default_and_legacy_config_cap_are_consistent(store, engine, configured, expected):
    config = {} if configured is None else {"count": configured}
    assert BotManager(engine, store, config=config).count == expected
    assert Community(engine, store.database, {"rivals": config}).rivals_config["count"] == expected
