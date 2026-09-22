"""Rival behavior tests use the real wild GameEngine and controlled small maps."""
import copy
import math
from pathlib import Path

import pytest
from PIL import Image

from venom.common.game import GameEngine, GameError
from venom.server.bots import BotManager
from venom.server.navigation import Navigation


ROOT = Path(__file__).resolve().parents[1]


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.events = []
        self.counters = {}

    def bot_load_all(self):
        return copy.deepcopy(list(self.rows.values()))

    def bot_save_batch(self, rows):
        for row in rows:
            self.rows[row["id"]] = copy.deepcopy(row)

    def add_events(self, events, counters=None):
        self.events = (self.events + copy.deepcopy(events))[-100:]
        for key, value in (counters or {}).items():
            self.counters[key] = self.counters.get(key, 0) + value

    def activity(self, limit=100):
        return {"events": list(reversed(self.events[-limit:])), "counters": dict(self.counters)}


class RankedStub:
    """Only scheduler sequencing is stubbed; real ranked tests cover the ledger."""
    def __init__(self, cooldown=False):
        self.profiles = {}
        self.matches = []
        self.cooldown = cooldown

    def register_many(self, profiles):
        self.profiles.update({profile["id"]: copy.deepcopy(profile) for profile in profiles})

    def register_participant(self, ident, profile):
        self.profiles[ident] = copy.deepcopy(profile)

    def start_match(self, ident):
        if self.cooldown:
            raise GameError("Battle stamina is recharging.")
        opponent = next(key for key in self.profiles if key != ident)
        result = {"id": f"test-match-{len(self.matches)}", "attacker_id": ident,
                  "defender_id": opponent, "winner_id": ident, "ranked": True}
        self.matches.append(result)
        return result


def make_manager(count=4, store=None, ranked=None, **config):
    engine = GameEngine(ROOT, seed=151)
    engine.maps = dict(list(engine.maps.items())[:2])
    engine.starters = ["agumon"]
    for area in engine.maps.values():
        area["level"] = 1
        engine._pools[area["id"]] = (["agumon"], [])
    manager = BotManager(engine, store or MemoryStore(), ranked or RankedStub(),
                         {"count": count, "action_interval": .1, "explore_seconds": 2,
                          "min_dwell": 60, "max_dwell": 90, "save_interval": 10000,
                          "tick_budget_ms": 100, **config})
    manager.initialize(0)
    return manager


def simulate(manager, seconds):
    for tick in range(1, int(seconds * 10) + 1):
        manager.tick(tick / 10, .1, budget=1000)


def test_every_rival_trains_scans_materializes_and_enters_ranked():
    manager = make_manager()
    simulate(manager, 180)
    for bot in manager.bots.values():
        stats, state = bot["stats"], bot["state"]
        assert stats["wild_wins"] == state["wins"] > 0
        assert stats["wild_losses"] == state["losses"]
        assert stats["level_ups"] > 0
        assert stats["scans"] >= 5
        assert stats["materialized"] > 0
        assert stats["ranked_started"] > 0
        assert stats["exploration_steps"] > 0
        assert stats["heals"] > 0
        assert 2 <= len(state["party"]) <= 6
        assert len({m["uid"] for m in state["party"]}) == len(state["party"])
    assert manager.counters["ranked_wins"] == manager.counters["ranked_losses"] == len(manager.ranked.matches)
    assert manager.counters["wild_wins"] == sum(bot["state"]["wins"] for bot in manager.bots.values())


def test_ranked_stamina_wait_never_starves_wild_training():
    manager = make_manager(ranked=RankedStub(cooldown=True))
    simulate(manager, 100)
    assert all(bot["state"]["wins"] >= 3 for bot in manager.bots.values())
    assert all(bot["runtime"]["cycle"] >= 3 for bot in manager.bots.values())
    assert manager.counters["errors"] == 0
    assert manager.counters["ranked_started"] == 0


def test_materialization_requires_real_full_scan_and_consumes_it():
    manager = make_manager(count=1)
    bot = manager.bots["bot:00001"]
    manager._execute(bot, "digilab", {"action": "enter"})
    bot["state"]["scan"]["agumon"] = 99
    manager._materialize(bot)
    assert bot["stats"]["materialized"] == 0
    with pytest.raises(GameError, match="100%"):
        manager._execute(bot, "materialize", {"species_id": "agumon"})
    bot["state"]["scan"]["agumon"] = 100
    manager._materialize(bot)
    assert bot["stats"]["materialized"] == 1
    assert len(bot["state"]["party"]) == 2
    assert bot["state"]["scan"]["agumon"] == 0
    assert manager.events[-1]["metadata"]["scan_before"] == 100


def test_real_wild_loss_recovers_and_moves_to_an_easier_sector():
    manager = make_manager(count=1)
    bot = manager.bots["bot:00001"]
    area = manager.engine.maps[bot["state"]["map_id"]]
    area["level"] = 80
    manager._execute(bot, "encounter", {})
    # Faster high-level wild opponents may already defeat the Rookie during
    # the encounter's real opening enemy turns.
    if bot["state"].get("battle"):
        for monster in bot["state"]["party"]:
            monster["hp"] = 1
        manager._execute(bot, "battle", {"action": "attack", "target": 0})
    assert bot["state"]["losses"] == bot["stats"]["wild_losses"] == 1
    assert bot["state"]["in_lab"]
    assert bot["runtime"]["relocate"]
    assert any(event["kind"] == "wild_loss" for event in manager.events)
    manager._execute(bot, "digilab", {"action": "return"})
    manager._relocate(bot, 30, easier=True)
    assert manager.engine.maps[bot["state"]["map_id"]]["level"] < 80
    assert bot["runtime"]["leave_at"] >= 90
    assert bot["stats"]["travels"] == 1


def test_restart_restores_real_party_scan_progress_and_counters():
    store = MemoryStore()
    manager = make_manager(store=store)
    simulate(manager, 100)
    manager.flush(force=True)
    saved = copy.deepcopy(store.rows)
    restored = make_manager(store=store)
    for ident, bot in restored.bots.items():
        assert bot["state"]["party"] == saved[ident]["state"]["party"]
        assert bot["state"]["scan"] == saved[ident]["state"]["scan"]
        assert bot["state"]["credits"] == saved[ident]["state"]["credits"]
        assert bot["stats"] == saved[ident]["stats"]
        assert bot["runtime"]["cycle"] == saved[ident]["runtime"]["cycle"]
    assert dict(restored.counters) == dict(manager.counters)


def test_ranked_result_accounts_for_both_sides_once():
    manager = make_manager(count=2)
    result = {"id": "committed-match", "attacker_id": "bot:00001", "defender_id": "bot:00002",
              "winner_id": "bot:00002", "ranked": True}
    manager.record_ranked_result(result)
    manager.record_ranked_result(result)
    manager.record_ranked_result({**result, "duplicate": True})
    assert manager.bots["bot:00001"]["stats"]["ranked_losses"] == 1
    assert manager.bots["bot:00002"]["stats"]["ranked_wins"] == 1


def test_snapshots_share_authoritative_continuous_positions_and_cannot_spoof_logins():
    manager = make_manager(count=1)
    manager.tick(0, .1)
    bot = manager.bots["bot:00001"]
    path = bot["runtime"]["path"]
    assert path
    end = path.get("segments", [path])[0]["end"]
    before = manager.snapshot(bot["state"]["map_id"], end * .3)[0]
    after = manager.snapshot(bot["state"]["map_id"], end * .6)[0]
    assert before == manager.snapshot(bot["state"]["map_id"], end * .3)[0]
    moved = math.hypot(after["x"] - before["x"], after["y"] - before["y"])
    assert moved == pytest.approx(Navigation.SPEED * end * .3, abs=.003)
    assert " " in before["username"]
    assert before["id"] == "bot:00001" and before["is_bot"]
    assert manager.navigation.walkable(before["map_id"], before["x"], before["y"])


def test_navigation_checks_each_collision_pixel_without_teleporting(tmp_path):
    mask = Image.new("L", (128, 128), 255)
    for y in range(128):
        mask.putpixel((64, y), 0)
    mask.save(tmp_path / "walk.png")
    maps = {"test": {"width": 128, "height": 128, "walkable": "walk.png", "spawn": [32, 64]}}
    nav = Navigation(tmp_path, maps)
    target = nav.trace("test", (32, 64), (96, 64))
    assert 63 <= target[0] < 64 and target[1] == 64
    assert nav.walkable("test", *target)
    path = {"from": (32, 64), "to": target, "start": 10, "end": 11}
    assert nav.sample(path, 10.5)[0] == pytest.approx((32 + target[0]) / 2)
    assert nav.sample(path, 20) == (*target, 0, 0)


def test_directory_and_history_are_bounded_and_profile_reads_cannot_mutate_state():
    manager = make_manager(count=4)
    for number in range(130):
        manager._record(manager.bots["bot:00001"], "test", f"Event {number}")
    assert len(manager.activity()["events"]) == 100
    assert manager.activity()["events"][0]["text"] == "Event 129"
    directory = manager.directory(offset=1, limit=2)
    assert directory["total"] == 4 and len(directory["entries"]) == 2
    profile = manager.profile("bot:00001")
    profile["party"][0]["hp"] = 0
    profile["stats"]["wild_wins"] = 999
    assert manager.bots["bot:00001"]["state"]["party"][0]["hp"] > 0
    assert manager.bots["bot:00001"]["stats"]["wild_wins"] == 0


def test_polyline_walking_distance_counts_corners_instead_of_displacement():
    manager = make_manager(count=1)
    bot = manager.bots["bot:00001"]
    bot["runtime"]["path"] = {
        "from": (20, 20), "to": (20, 20), "start": 0, "end": 2,
        "segments": [{"from": (20, 20), "to": (200, 20), "start": 0, "end": 1},
                     {"from": (200, 20), "to": (20, 20), "start": 1, "end": 2}],
        "ends": [1, 2],
    }
    manager._stop(bot, 2)
    assert bot["state"]["x"] == 20
    assert bot["stats"]["walking_distance"] == 360


def test_restart_reconciles_ranked_ledger_after_a_later_bot_checkpoint():
    store = MemoryStore()
    manager = make_manager(count=2, store=store)
    # Simulate the ranked SQL transaction having committed after the latest bot
    # checkpoint; this source is authoritative for both attacker and defender.
    store.ranked_totals = lambda: {
        "bot:00001": {"ranked_wins": 7, "ranked_losses": 2, "ranked_started": 5,
                      "rival_wins": 3, "rival_losses": 1},
        "bot:00002": {"ranked_wins": 2, "ranked_losses": 7, "ranked_started": 4,
                      "rival_wins": 1, "rival_losses": 3},
    }
    restored = make_manager(count=2, store=store)
    assert restored.bots["bot:00001"]["stats"]["ranked_wins"] == 7
    assert restored.bots["bot:00002"]["stats"]["ranked_losses"] == 7
    assert restored.counters["ranked_started"] == 9
    assert restored.counters["ranked_wins"] == restored.counters["ranked_losses"] == 9
    assert restored.counters["wild_wins"] == 0
