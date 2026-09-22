"""Protect a successor world's bot saves when an older process resumes."""
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from venom.common.game import GameEngine
from venom.server.community import Community
from venom.server.community_store import CommunityStore
from venom.server.database import Database, DatabaseError
from venom.server.ranked import GRADES, RankedService


def test_shutdown_does_not_flush_after_another_world_acquires_the_lease():
    db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
    db.initialize()
    service = Community(SimpleNamespace(root=Path(__file__).resolve().parents[1]), db,
                        {"rivals": {"count": 0}})
    service.store.initialize()
    now = time.time()
    assert service.store.acquire_world(service.token, lease_seconds=90, now=now - 200)
    service.lease_owned = service.ready = True
    # The former worker paused long enough for an administrator to start a
    # successor server. Its old in-memory progress must no longer be written.
    assert service.store.acquire_world("successor-world", lease_seconds=90, now=now)
    service.store.bot_save_batch([{"id": "bot:00001", "earned_xp": 99}])
    writes = []

    def stale_flush(force=False):
        writes.append(force)
        service.store.bot_save_batch([{"id": "bot:00001", "earned_xp": 10}])

    service.bots = SimpleNamespace(flush=stale_flush)
    try:
        service.shutdown()
        assert not writes
        assert service.store.bot_load_all() == [{"id": "bot:00001", "earned_xp": 99}]
        assert service.store.renew_world("successor-world", now=now + 1)
        assert not service.lease_owned
    finally:
        db.close()


def test_former_world_cannot_save_bots_after_successor_acquires_lease():
    db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
    db.initialize()
    former, successor = CommunityStore(db), CommunityStore(db)
    former.initialize()
    now = time.time()
    assert former.acquire_world("former", lease_seconds=90, now=now - 200)
    former.owner_token = "former"
    assert successor.acquire_world("successor", now=now)
    successor.owner_token = "successor"
    successor.bot_save_batch([{"id": "bot:00001", "earned_xp": 99}])
    try:
        with pytest.raises(DatabaseError, match="lease"):
            former.bot_save_batch([{"id": "bot:00001", "earned_xp": 10}])
        with pytest.raises(DatabaseError, match="lease"):
            former.add_events([{"id": "stale-win", "kind": "wild_win"}], {"wild_wins": 1})
        assert successor.bot_load_all() == [{"id": "bot:00001", "earned_xp": 99}]
        assert successor.activity() == {"events": [], "counters": {}}
        # Lease operations keep their boolean API even on a fenced-out store.
        assert not former.renew_world("former")
        assert not former.release_world("former")
        assert successor.renew_world("successor")
    finally:
        db.close()


def test_former_world_cannot_commit_a_ranked_result_or_spend_energy():
    db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
    db.initialize()
    former, successor = CommunityStore(db), CommunityStore(db)
    former.initialize()
    engine = GameEngine(Path(__file__).resolve().parents[1], seed=717)
    service = RankedService(engine, former, {"match_cooldown": 0, "opponent_cooldown": 0})
    participants = [{"id": ident, "name": ident, "kind": "bot",
                     "tamer": next(iter(engine.tamers)),
                     "party": [engine._monster(engine.starters[0], level=level)]}
                    for ident, level in (("bot:00001", 20), ("bot:00002", 1))]
    service.register_many(participants)
    now = time.time()
    # Also cover a combat result computed before suspension but committed after
    # failover, so the write boundary itself must reject the former owner.
    result = service._fight(participants[0], participants[1], "fight-before-failover")
    result.update(id="stale-commit", attacker_id="bot:00001", defender_id="bot:00002",
                  winner_id="bot:00001" if result["attacker_won"] else "bot:00002",
                  ranked=True, season_id=service.tick()["id"], played_at=now)
    assert former.acquire_world("former", lease_seconds=90, now=now - 200)
    former.owner_token = "former"
    assert successor.acquire_world("successor", now=now)
    successor.owner_token = "successor"
    try:
        with pytest.raises(DatabaseError, match="lease"):
            service.start_match("bot:00001", "bot:00002", "stale-match")
        with pytest.raises(DatabaseError, match="lease"):
            former.commit_match(result, now, 5, 1800, 0, 20, 5, GRADES)
        assert successor.match("stale-match") is None
        assert successor.match("stale-commit") is None
        assert successor.competitor("bot:00001")["energy"] == 5
        assert successor.competitor("bot:00001")["career_wins"] == 0
        assert successor.competitor("bot:00002")["career_losses"] == 0
        assert successor.standings(career=True) == []
    finally:
        db.close()


def test_shutdown_flushes_and_releases_a_valid_owned_lease():
    db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
    db.initialize()
    service = Community(SimpleNamespace(root=Path(__file__).resolve().parents[1]), db,
                        {"rivals": {"count": 0}})
    service.store.initialize()
    assert service.store.acquire_world(service.token)
    service.lease_owned = service.ready = True
    writes = []
    service.bots = SimpleNamespace(flush=lambda force=False: writes.append(force))
    try:
        service.shutdown()
        assert writes == [True]
        assert service.store.acquire_world("successor-world")
        assert not service.ready and not service.lease_owned
    finally:
        db.close()
