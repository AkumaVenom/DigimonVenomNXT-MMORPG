"""Ranked results are real combat, durable, balanced and exactly once."""
import copy
from pathlib import Path
import tempfile
import unittest

from venom.common.game import GameEngine, GameError
from venom.server.database import Database
from venom.server.community_store import CommunityStore
from venom.server.ranked import RankedService, GRADES

ROOT = Path(__file__).resolve().parents[1]


class RankedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = GameEngine(ROOT, seed=47)

    def setUp(self):
        self.db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
        self.db.initialize()
        self.store = CommunityStore(self.db)
        self.store.initialize()
        self.now = 1_800_000_000.0
        self.service = RankedService(self.engine, self.store,
                                     {"match_cooldown": 0, "opponent_cooldown": 0, "season_seconds": 600,
                                      "energy_capacity": 5, "energy_refill_seconds": 1800},
                                     clock=lambda: self.now)
        self.sid = self.engine.starters[0]
        self.a = self.profile("player:alice", "player", 45)
        self.b = self.profile("bot:00001", "bot", 1)
        self.c = self.profile("bot:00002", "bot", 10)
        self.service.register_many([self.a, self.b, self.c])

    def tearDown(self):
        self.db.close()

    def profile(self, pid, kind="bot", level=10, count=3):
        return {"id": pid, "name": pid.split(":")[-1], "tamer": next(iter(self.engine.tamers)), "kind": kind,
                "party": [self.engine._monster(self.sid, level=level) for _ in range(count)]}

    def test_combat_uses_actual_damage_and_copies_party_then_commits_both_sides(self):
        original = copy.deepcopy(self.a)
        result = self.service.start_match(self.a["id"], self.b["id"], "match-one")
        self.assertTrue(result["attacker_won"])
        self.assertEqual("knockout", result["reason"])
        damage = [e for e in result["replay"]["events"] if e["kind"] == "damage"]
        self.assertTrue(damage)
        self.assertTrue(all(e["amount"] > 0 for e in damage))
        self.assertEqual(original, self.a)
        self.assertEqual(self.a["party"], self.service.profiles[self.a["id"]]["party"])
        alice = self.service.overview(self.a["id"])["own"]
        bob = self.service.overview(self.b["id"])["own"]
        self.assertEqual((1, 0, 20, 4), (alice["wins"], alice["losses"], alice["points"], alice["energy"]["current"]))
        self.assertEqual((0, 1, 0, 5), (bob["wins"], bob["losses"], bob["points"], bob["energy"]["current"]))
        self.assertEqual(1000 * 2, alice["career_rating"] + bob["career_rating"])
        rival = self.store.rival_history(self.a["id"])[0]
        self.assertEqual((self.b["id"], 1, 0), (rival["id"], rival["wins"], rival["losses"]))

    def test_duplicate_and_foreign_match_ids_cannot_award_twice(self):
        first = self.service.start_match(self.a["id"], self.b["id"], "same-match")
        duplicate = self.service.start_match(self.a["id"], self.b["id"], "same-match")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["winner_id"], duplicate["winner_id"])
        self.assertEqual(1, self.service.overview(self.a["id"])["own"]["wins"])
        with self.assertRaises(GameError):
            self.service.start_match(self.c["id"], self.a["id"], "same-match")
        with self.assertRaises(GameError):
            self.service.start_match(self.a["id"], self.c["id"], "same-match")
        self.store.rival_record(self.a["id"], self.b["id"], first)
        self.assertEqual(1, self.store.rival_history(self.a["id"])[0]["wins"])

    def test_energy_recovery_cooldown_and_friendly_result(self):
        for i in range(5):
            self.service.start_match(self.a["id"], self.b["id"], f"energy-{i}")
        with self.assertRaisesRegex(GameError, "energy"):
            self.service.start_match(self.a["id"], self.b["id"], "exhausted")
        result = self.service.start_match(self.a["id"], self.b["id"], "friendly", ranked=False)
        self.assertFalse(result["ranked"])
        self.assertEqual(5, self.service.overview(self.a["id"])["own"]["career_wins"])
        self.now += 1800
        self.assertEqual(1, self.service.overview(self.a["id"])["own"]["energy"]["current"])
        self.service.start_match(self.a["id"], self.b["id"], "recovered")
        self.assertEqual(0, self.service.overview(self.a["id"])["own"]["energy"]["current"])

    def test_season_closes_awards_once_keeps_history_and_career(self):
        self.service.start_match(self.a["id"], self.b["id"], "season-match")
        old = self.service.tick()["id"]
        self.now = self.service.tick()["ends_at"] + 1
        self.service.tick()
        own = self.service.overview(self.a["id"])["own"]
        self.assertEqual((0, 0, 1), (own["wins"], own["losses"], own["career_wins"]))
        self.assertEqual(self.service.reward_for(1, 20, 0), own["digirubies"])
        historical = self.service.leaderboard("history", old)
        self.assertEqual(2, historical["total"])
        self.assertEqual("closed", historical["season"]["status"])
        self.assertEqual(self.a["id"], historical["entries"][0]["id"])
        before = own["digirubies"]
        self.service.tick()
        restarted = RankedService(self.engine, self.store, self.service.config, clock=lambda: self.now)
        self.assertEqual(before, restarted.overview(self.a["id"])["own"]["digirubies"])
        self.assertEqual(0, restarted.overview(self.c["id"])["own"]["digirubies"])
        self.assertEqual(0, restarted.overview(self.b["id"])["own"]["digirubies"])
        self.assertEqual(1, self.db.connection.execute("SELECT COUNT(*) FROM venom_ranked_rewards").fetchone()[0])

    def test_promotion_requires_an_additional_attacking_win(self):
        for i in range(5):
            result = self.service.start_match(self.a["id"], self.b["id"], f"promotion-{i}")
        own = self.service.overview(self.a["id"])["own"]
        self.assertEqual("Bronze", own["grade"])
        self.assertTrue(own["promotion_pending"])
        # Regenerate energy without closing this test's season.
        self.db.connection.execute("UPDATE venom_competitors SET energy=1 WHERE id=?", (self.a["id"],))
        self.db.connection.commit()
        result = self.service.start_match(self.a["id"], self.b["id"], "promotion-victory")
        self.assertTrue(result["promotion"]["promoted"])
        self.assertEqual("Silver", self.service.overview(self.a["id"])["own"]["grade"])

    def test_defender_is_not_given_the_wild_damage_handicap(self):
        # For each side's first physical/skill hit, recompute the minimum
        # original combat damage and verify it is not multiplied by .72.
        equal = self.profile("bot:equal", level=20, count=1)
        self.service.register_participant(equal["id"], equal)
        result = self.service._fight(equal, equal, "symmetric-damage")
        seen = {}
        for e in result["replay"]["events"]:
            if e["kind"] == "damage":
                seen.setdefault(e["attacker_side"], e)
        self.assertEqual({"player", "enemy"}, set(seen))
        self.assertLess(abs(seen["player"]["amount"] - seen["enemy"]["amount"]), 15)

    def test_reserves_join_and_zero_sp_finishes_with_free_attacks(self):
        low = self.profile("bot:low", level=1, count=6)
        high = self.profile("bot:high", level=99, count=3)
        result = self.service._fight(high, low, "reserves")
        self.assertEqual(3, len([e for e in result["replay"]["events"] if e["kind"] == "reserve"]))
        self.assertTrue(result["attacker_won"])
        a = self.profile("bot:drained-a", level=10, count=1)
        b = self.profile("bot:drained-b", level=10, count=1)
        for p in (a, b):
            p["party"][0]["max_sp"] = 1
            p["party"][0]["max_hp"] = 3000
        result = self.service._fight(a, b, "no-affordable-skill")
        self.assertTrue(all(e.get("move") in ("Attack", "Struggle") for e in result["replay"]["events"] if e["kind"] == "damage"))
        self.assertGreater(result["turns"], 1)

    def test_ranked_rematch_cooldown_is_enforced_without_spending_energy(self):
        self.service.config["opponent_cooldown"] = 60
        self.service.start_match(self.a["id"], self.b["id"], "cooldown-first")
        with self.assertRaisesRegex(GameError, "cooldown"):
            self.service.start_match(self.a["id"], self.b["id"], "cooldown-second")
        self.assertEqual(4, self.service.overview(self.a["id"])["own"]["energy"]["current"])
        self.assertIsNone(self.store.match("cooldown-second"))
        self.now += 60
        self.service.start_match(self.a["id"], self.b["id"], "cooldown-third")

    def test_season_rules_are_frozen_and_clock_changes_require_migration(self):
        self.service.start_match(self.a["id"], self.b["id"], "frozen-first")
        old = self.service.tick()["id"]
        changed = {**self.service.config, "win_points": 99}
        restarted = RankedService(self.engine, self.store, changed, clock=lambda: self.now)
        self.assertEqual(20, restarted.config["win_points"])
        self.assertEqual(99, restarted.requested_config["win_points"])
        restarted.reward_for = lambda *args: 99999
        self.now = restarted.tick()["ends_at"] + 1
        restarted.tick()
        self.assertEqual(99, restarted.config["win_points"])
        self.assertEqual(310, restarted.overview(self.a["id"])["own"]["digirubies"])
        archived = restarted.leaderboard("history", old)
        self.assertEqual(20, archived["season"]["rules"]["config"]["win_points"])
        with self.assertRaisesRegex(GameError, "clock"):
            RankedService(self.engine, self.store, {**changed, "season_seconds": 1200}, clock=lambda: self.now)

    def test_delayed_rival_callback_and_reconciliation_use_ledger_once(self):
        first = self.service.start_match(self.a["id"], self.b["id"], "history-first")
        self.service.start_match(self.a["id"], self.b["id"], "history-second", ranked=False)
        self.store.rival_record(self.a["id"], self.b["id"], first)
        self.assertEqual(2, self.store.rival_history(self.a["id"])[0]["wins"])
        totals = self.store.ranked_totals()[self.b["id"]]
        self.assertEqual({"ranked_wins": 0, "ranked_losses": 1, "ranked_started": 0,
                          "rival_wins": 0, "rival_losses": 1}, totals)

    def test_database_failure_rolls_back_both_rankings_stamina_and_ledger(self):
        self.db.connection.execute("CREATE TRIGGER fail_ledger BEFORE INSERT ON venom_ranked_matches BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        self.db.connection.commit()
        with self.assertRaises(Exception):
            self.service.start_match(self.a["id"], self.b["id"], "broken")
        self.assertEqual((0, 0), (self.store.competitor(self.a["id"])["career_wins"], self.store.competitor(self.b["id"])["career_losses"]))
        self.assertEqual(5, self.store.competitor(self.a["id"])["energy"])
        self.assertIsNone(self.store.match("broken"))
        self.assertEqual([], self.store.rival_history(self.a["id"]))


class CommunityStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = Database({"driver": "sqlite", "path": ":memory:"}, dev=True)
        self.db.initialize()
        self.store = CommunityStore(self.db)
        self.store.initialize()

    def tearDown(self):
        self.db.close()

    def test_world_lease_rejects_second_writer_and_renews_only_owner(self):
        self.assertTrue(self.store.acquire_world("one", now=100))
        self.assertFalse(self.store.acquire_world("two", now=110))
        self.assertFalse(self.store.renew_world("two", now=110))
        self.assertTrue(self.store.renew_world("one", now=110))
        self.assertFalse(self.store.release_world("two"))
        self.assertTrue(self.store.release_world("one"))
        self.assertTrue(self.store.acquire_world("two", now=120))
        self.assertTrue(self.store.acquire_world("three", now=250))
        self.assertFalse(self.store.renew_world("two", now=251))

    def test_bot_save_and_latest_activity_are_durable_bounded(self):
        self.store.bot_save_batch([{"id": "bot:00001", "xp": 10}, {"id": "bot:00002", "xp": 20}])
        self.store.bot_save_batch([{"id": "bot:00001", "xp": 50}])
        self.assertEqual([50, 20], [row["xp"] for row in self.store.bot_load_all()])
        self.store.add_events([{"id": f"evt-{i:04d}", "bot_id": "bot:00001", "kind": "wild_win", "at": i} for i in range(150)],
                              {"wild_wins": 150})
        activity = self.store.activity()
        self.assertEqual(100, len(activity["events"]))
        self.assertEqual(149, activity["events"][0]["at"])
        self.assertEqual(50, activity["events"][-1]["at"])
        self.assertEqual(150, activity["counters"]["wild_wins"])
        self.store.add_events([{"id": f"evt-{i:04d}", "bot_id": "bot:00001", "kind": "wild_win", "at": i} for i in range(150)],
                              {"wild_wins": 150})
        self.assertEqual(150, self.store.activity()["counters"]["wild_wins"])
        self.store.initialize()
        self.assertEqual(100, len(self.store.activity()["events"]))
        self.assertEqual(1, self.db.connection.execute("SELECT version FROM venom_schema").fetchone()[0])
