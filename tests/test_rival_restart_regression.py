"""Restart a progressed durable world without replaying or resetting its history.

Slow-start checks advance wall time instead of making the suite wait minutes.
The population, SQL lease, gameplay progression and saved battles remain real.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from venom.common.game import GameEngine
from venom.server.bots import BotManager
from venom.server.community import Community
from venom.server import community as community_module
from venom.server.community_store import CommunityStore
from venom.server.database import Database, DatabaseError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def aged_world(tmp_path, monkeypatch):
    wall = [2_000_000_000.0]
    monkeypatch.setattr(time, "time", lambda: wall[0])
    db = Database({"driver": "sqlite", "path": str(tmp_path / "progressed-world.sqlite3")}, dev=True)
    db.initialize()
    engine = GameEngine(ROOT, seed=1744)
    config = {"rivals": {"count": 4, "seed": 517, "action_interval": .1,
                         "explore_seconds": 2, "min_dwell": 60, "max_dwell": 90,
                         "tick_budget_ms": 100, "save_interval": 10000},
              "ranked": {"match_cooldown": 0, "opponent_cooldown": 0,
                         "season_seconds": 604800, "season_anchor": wall[0]}}
    running = Community(engine, db, config)
    services = [running]
    running.initialize()
    start = time.monotonic()
    for tick in range(1, 721):
        running.bots.tick(start + tick * .5, .5, budget=1000)
    assert sum(bot["stats"]["wild_wins"] for bot in running.bots.bots.values()) > 50
    assert sum(len(bot["state"]["party"]) for bot in running.bots.bots.values()) > 4
    assert db.connection.execute("SELECT COUNT(*) FROM venom_ranked_matches").fetchone()[0] > 0
    # Leave a real, unfinished wild battle in the durable checkpoint.
    fighter = running.bots.bots["bot:00001"]
    if not fighter["state"].get("battle"):
        if fighter["state"].get("in_lab"):
            running.bots._execute(fighter, "digilab", {"action": "return"})
        running.bots._execute(fighter, "encounter", {})
    assert fighter["state"].get("battle")
    running.bots.flush(force=True)
    human = engine.new_player("RestartHuman", next(iter(engine.tamers)), "agumon")
    human["credits"] = 54321
    human["scan"]["agumon"] = 140
    db.register("RestartHuman", "restart-preservation-password", human)
    running.register_player(human)
    db.connection.execute("UPDATE venom_competitors SET digirubies=137 WHERE id='player:restarthuman'")
    db.connection.commit()
    running.shutdown()
    saved = {row["id"]: row for row in CommunityStore(db).bot_load_all()}
    human_saved = db.load("restarthuman")
    history = db.connection.execute("SELECT id,result_json FROM venom_ranked_matches ORDER BY id").fetchall()
    wall[0] += 86400  # No offline simulation is allowed during the next startup.

    def restart():
        service = Community(engine, db, config)
        services.append(service)
        return service

    try:
        yield SimpleNamespace(db=db, wall=wall, saved=saved, history=history,
                              human=human_saved, restart=restart, services=services)
    finally:
        for service in reversed(services):
            if service.lease_owned:
                service.shutdown()
        db.close()


def assert_preserved(world, service):
    assert service.ready and service.bots.initialized
    assert set(service.bots.bots) == set(world.saved)
    for ident, saved in world.saved.items():
        actual = service.bots.bots[ident]
        # Map coordinates and the exact battle timeline must survive alongside
        # partners, storage, scans, inventory, credits and progression.
        assert actual["state"] == saved["state"]
        assert actual["stats"] == saved["stats"]
        assert actual["runtime"]["cycle"] == saved["runtime"]["cycle"]
        assert actual["runtime"]["path"] is None
    assert service.bots.processed == 0, "A restart must not replay a day's offline work"
    assert world.db.load("restarthuman") == world.human
    assert service.store.competitor("player:restarthuman")["digirubies"] == 137
    assert world.db.connection.execute("SELECT id,result_json FROM venom_ranked_matches ORDER BY id").fetchall() == world.history


def test_day_aged_durable_bots_restore_exact_progress_and_unfinished_battle(aged_world):
    service = aged_world.restart()
    service.initialize()
    assert_preserved(aged_world, service)


def test_long_progressed_population_restore_keeps_its_world_lease_alive(aged_world, monkeypatch):
    monkeypatch.setattr(community_module, "LEASE_HEARTBEAT_SECONDS", .005, raising=False)
    service = aged_world.restart()
    heartbeat = threading.Event()
    renewals = []
    original_renew = service.store.renew_world

    def observe_renewal(*args, **kwargs):
        result = original_renew(*args, **kwargs)
        if result:
            renewals.append(aged_world.wall[0])
            heartbeat.set()
        return result

    monkeypatch.setattr(service.store, "renew_world", observe_renewal)
    original_restore = BotManager._restore
    slowed = []

    def restore_with_slow_disk(manager, row, ordinal, now, **options):
        original_restore(manager, row, ordinal, now, **options)
        if not slowed:
            slowed.append(row["id"])
            for _ in range(6):
                heartbeat.clear()
                aged_world.wall[0] += 20
                heartbeat.wait(.2)

    monkeypatch.setattr(BotManager, "_restore", restore_with_slow_disk)
    before = aged_world.wall[0]
    service.initialize()
    assert aged_world.wall[0] - before == 120
    assert len(renewals) >= 5, "A separate heartbeat must run while population restoration is busy"
    assert_preserved(aged_world, service)
    assert service.store.renew_world(service.token), "The completed startup must still own a live lease"


def test_long_locked_database_load_renews_before_releasing_its_lease_row(aged_world):
    service = aged_world.restart()
    service.initialize()
    before = copy.deepcopy(aged_world.saved)
    # A real transaction pins the lease row while slow disk/JSON work runs.
    # Renewal must occur before COMMIT releases that row to a successor.
    with service.store.transaction() as cursor:
        cursor.execute("SELECT COUNT(*) FROM venom_bot_state")
        assert cursor.fetchone()[0] == 4
        aged_world.wall[0] += 120
    assert service.store.renew_world(service.token), "A held lease must not expire at the end of a long startup transaction"
    assert {row["id"]: row for row in service.store.bot_load_all()} == before
    assert_preserved(aged_world, service)


def test_restart_cannot_replace_a_live_successor_world_or_touch_its_progress(aged_world):
    successor = CommunityStore(aged_world.db)
    assert successor.acquire_world("newer-running-world", lease_seconds=90)
    successor.owner_token = "newer-running-world"
    snapshot = copy.deepcopy(aged_world.saved)
    service = aged_world.restart()
    with pytest.raises(DatabaseError):
        service.initialize()
    assert not service.ready and not service.lease_owned
    assert {row["id"]: row for row in successor.bot_load_all()} == snapshot
    assert successor.renew_world("newer-running-world")
    assert aged_world.db.load("restarthuman") == aged_world.human
    successor.release_world("newer-running-world")
