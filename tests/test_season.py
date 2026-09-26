"""Private Season domain, calendar, booking, and normal battle integration tests."""
import copy
import datetime
import json
import random
import tempfile
import unittest
from pathlib import Path

from venom.common.game import GameEngine, GameError
from venom.common import season


def make_engine(path):
    def partner(ident, stage="rookie", evolutions=None):
        return {"id": ident, "name": ident.title(), "stage": stage, "type": "free", "attribute": "neutral",
                "base_stats": {"hp": 240, "sp": 40, "atk": 40, "def": 25, "int": 36, "spd": 30},
                "evolutions": evolutions or [], "sprites": {}}
    catalog = {"species": [partner("alpha", evolutions=[{"to": "beta", "level": 3}]),
                           partner("beta", "champion"), partner("gamma")],
               "tamers": [{"id": "tamer", "name": "Tamer"}],
               "maps": [{"id": "forest", "name": "Forest", "level": 1, "width": 500,
                         "height": 500, "spawn": [150, 180]}]}
    (path / "catalog.json").write_text(json.dumps(catalog))
    return GameEngine(path, seed=7)


class CalendarTests(unittest.TestCase):
    def test_epoch_and_actual_month_lengths(self):
        self.assertEqual(season.calendar_date(0)["label"], "Monday, 1 January, Year 1")
        self.assertEqual(season.calendar_date(30)["day"], 31)
        self.assertEqual(season.calendar_date(31)["month_name"], "February")
        self.assertEqual(season.calendar_date(59)["month_name"], "March")

    def test_random_dates_match_gregorian_reference(self):
        rng = random.Random(13)
        for _ in range(2000):
            ordinal = rng.randint(1, datetime.date.max.toordinal())
            expected = datetime.date.fromordinal(ordinal)
            actual = season.calendar_date(ordinal - 1)
            self.assertEqual((actual["year"], actual["month"], actual["day"]),
                             (expected.year, expected.month, expected.day))
            self.assertEqual(actual["weekday"], expected.strftime("%A"))
            self.assertEqual(season.elapsed_for_date(expected.year, expected.month, expected.day), ordinal - 1)

    def test_leap_centuries_and_unbounded_years(self):
        for year, is_leap in ((4, True), (100, False), (400, True), (10000, True),
                              (10100, False), (10**30, True), (10**30 + 100, False)):
            self.assertEqual(season.leap_year(year), is_leap)
            before = season.elapsed_for_date(year, 2, 28)
            actual = season.calendar_date(before + 1)
            self.assertEqual((actual["year"], actual["month"], actual["day"]),
                             (year, 2, 29) if is_leap else (year, 3, 1))
            self.assertEqual(season.calendar_date(season.days_before_year(year))["label"].split(", ")[-1],
                             f"Year {year}")


class SeasonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = make_engine(Path(self.temp.name))
        self.state = self.engine.new_player("Aster", "tamer", "alpha")

    def enter(self):
        self.engine.handle(self.state, "season", {"action": "enter"})
        return self.state["season"]

    def start(self):
        self.engine.handle(self.state, "season", {"action": "start", "token": self.state["season"]["card"]["token"]})

    def fight(self, action="attack", **payload):
        battle = self.state["battle"]
        self.engine.handle(self.state, "battle", {"action": action, "battle_id": battle["id"],
                                                  "expected_turn": battle["turn"], **payload})

    def test_lazy_additive_creation_and_world_location_restore(self):
        self.assertNotIn("season", self.state)
        world = {k: self.state[k] for k in ("map_id", "x", "y", "in_farm", "in_lab")}
        career = self.enter()
        self.assertEqual(career["week"], 1)
        self.assertEqual(len(career["roster"]), 16)
        self.assertTrue(self.state["in_season"])
        self.engine.handle(self.state, "season", {"action": "return"})
        self.assertFalse(self.state["in_season"])
        self.assertEqual({k: self.state[k] for k in world}, world)
        before = copy.deepcopy(career)
        self.enter()
        self.assertEqual(self.state["season"], before)

    def test_other_players_never_share_league_state(self):
        first = self.enter()
        other = self.engine.new_player("Other", "tamer", "alpha")
        self.engine.handle(other, "season", {"action": "enter"})
        before = copy.deepcopy(other)
        season.begin_match(first, first["card"]["token"])
        season.finish_human(first, True, self.engine.species)
        season.next_week(self.state, first["card"]["token"])
        self.assertEqual(other, before)
        self.assertNotEqual(first["id"], other["season"]["id"])

    def test_card_unique_fixtures_and_hidden_other_results(self):
        career = self.enter()
        matches = career["card"]["matches"]
        self.assertEqual(len(matches), 8)
        self.assertEqual(sum(m["is_player"] for m in matches), 1)
        participants = [m[k] for m in matches for k in ("home_id", "away_id")]
        self.assertEqual(len(participants), len(set(participants)))
        self.assertTrue(all(m["winner_id"] is None for m in matches))
        self.assertEqual(season.human_match(career)["weekday"], "Tuesday")
        self.start()
        self.assertEqual(career["phase"], "battle")
        self.assertEqual(career["elapsed_days"], 1)
        self.assertTrue(all(m["winner_id"] is None for m in matches))
        self.assertIsNotNone(self.state["battle"])

    def test_no_flee_no_world_bypass_and_no_premature_advance(self):
        career = self.enter()
        with self.assertRaises(GameError):
            self.engine.handle(self.state, "season", {"action": "next", "token": career["card"]["token"]})
        self.start()
        for action in ("flee",):
            with self.assertRaises(GameError):
                self.fight(action)
        for op, payload in (("digifarm", {"action": "enter", "forfeit": True}),
                            ("travel", {"map_id": "forest"}), ("encounter", {}),
                            ("digilab", {"action": "enter"}), ("season", {"action": "return"})):
            with self.assertRaises(GameError):
                self.engine.handle(self.state, op, payload)
        self.assertEqual(career["phase"], "battle")

    def test_turn_and_card_tokens_reject_stale_actions(self):
        career = self.enter()
        with self.assertRaises(GameError):
            self.engine.handle(self.state, "season", {"action": "start", "token": "old-card"})
        self.assertEqual(career["phase"], "ready")
        self.start()
        old = {"action": "guard", "battle_id": self.state["battle"]["id"],
               "expected_turn": self.state["battle"]["turn"]}
        self.engine.handle(self.state, "battle", old)
        before = copy.deepcopy(self.state["battle"])
        with self.assertRaises(GameError):
            self.engine.handle(self.state, "battle", old)
        self.assertEqual(self.state["battle"], before)
        with self.assertRaises(GameError):
            self.engine.handle(self.state, "battle", {"action": "attack"})

    def test_actual_interactive_battle_settles_all_results_once_without_scan(self):
        career = self.enter()
        self.start()
        for _ in range(300):
            if not self.state["battle"]:
                break
            living = next(i for i, e in enumerate(self.state["battle"]["enemies"]) if e["hp"] > 0)
            self.fight(target=living)
        self.assertIsNone(self.state["battle"])
        self.assertEqual(career["phase"], "results")
        self.assertEqual(career["elapsed_days"], 6)
        self.assertEqual(self.state["scan"], {})
        self.assertTrue(all(m["status"] == "complete" for m in career["card"]["matches"]))
        self.assertTrue(all(r["matches"] == 1 for r in career["roster"]))
        self.assertTrue(self.state["in_season"])
        self.assertFalse(self.state["in_lab"])
        self.assertTrue(all(m["hp"] == m["max_hp"] for m in self.state["party"]))
        with self.assertRaises(GameError):
            self.engine.handle(self.state, "battle", {"action": "attack"})
        old_token = career["card"]["token"]
        self.engine.handle(self.state, "season", {"action": "next", "token": old_token})
        self.assertEqual(career["week"], 2)
        self.assertEqual(career["elapsed_days"], 7)
        self.assertEqual(self.state["_season_archive_pending"][0]["card"]["token"], old_token)
        with self.assertRaises(GameError):
            self.engine.handle(self.state, "season", {"action": "next", "token": old_token})

    def test_loss_recovers_in_league_and_keeps_champion(self):
        career = self.enter()
        self.start()
        self.state["party"][0]["hp"] = 0
        self.engine._check_end(self.state)
        self.assertEqual(career["career"]["losses"], 1)
        self.assertTrue(self.state["in_season"])
        self.assertFalse(self.state["in_lab"])
        self.assertIsNone(self.state["battle"])
        self.assertEqual(career["phase"], "results")

    def test_title_win_defense_loss_and_continuity(self):
        career = self.enter()
        player = season.member(career, "player")
        player["rating"] = 2390
        for week, won in ((4, True), (8, True), (12, False)):
            career["week"] = week
            season.update_views(career)
            season.book_week(career)
            fixture = season.begin_match(career, career["card"]["token"])
            self.assertTrue(fixture["title_match"])
            season.finish_human(career, won, self.engine.species)
            if week == 4:
                self.assertEqual(career["champion"]["holder_id"], "player")
                self.assertEqual(player["titles"], 1)
            elif week == 8:
                self.assertEqual(career["champion"]["defenses"], 1)
                self.assertEqual(player["defenses"], 1)
            else:
                self.assertNotEqual(career["champion"]["holder_id"], "player")
                self.assertEqual(career["title_events"][0]["kind"], "title_change")
        self.assertEqual(player["titles"], 1)
        self.assertEqual(player["defenses"], 1)
        self.assertEqual(career["recent_reigns"][-2]["holder_id"], "player")
        self.assertEqual(career["recent_reigns"][-2]["end_week"], 12)

    def test_thousand_weeks_bounded_state_npc_development_and_records(self):
        career = self.enter()
        original_forms = {row["id"]: row["species_id"] for row in career["roster"]}
        previous_ids = set()
        for week in range(1, 1001):
            self.assertEqual(career["card"]["start_day"], (week - 1) * 7)
            fixture_ids = {m["id"] for m in career["card"]["matches"]}
            self.assertFalse(fixture_ids & previous_ids)
            previous_ids.update(fixture_ids)
            season.begin_match(career, career["card"]["token"])
            season.finish_human(career, week % 3 != 0, self.engine.species)
            season.next_week(self.state, career["card"]["token"])
            snapshot = self.state.pop("_season_archive_pending")[0]
            self.assertEqual(snapshot["week"], week)
        self.assertEqual(career["week"], 1001)
        self.assertTrue(all(r["matches"] == 1000 for r in career["roster"]))
        self.assertTrue(all(r["development"] == 1000 for r in career["roster"] if not r["is_player"]))
        self.assertTrue(any(row["species_id"] != original_forms[row["id"]] for row in career["roster"] if not row["is_player"]))
        self.assertLessEqual(len(career["rivalries"]), 120)
        self.assertLessEqual(len(career["recent_reigns"]), 12)
        self.assertLessEqual(len(career["recent_news"]), 12)
        self.assertLess(len(json.dumps(career)), 65000)

    def test_far_future_booking_and_annual_event_preserve_career(self):
        career = self.enter()
        player = season.member(career, "player")
        player["wins"] = 30000
        target = season.elapsed_for_date(10000, 12, 31)
        career["week"] = target // 7 + 1
        season.book_week(career)
        self.assertEqual(career["card"]["event_kind"], "annual")
        before_id = career["id"]
        season.begin_match(career, career["card"]["token"])
        season.finish_human(career, True, self.engine.species)
        season.next_week(self.state, career["card"]["token"])
        self.assertEqual(career["calendar"]["year"], 10001)
        self.assertEqual(career["id"], before_id)
        self.assertEqual(player["wins"], 30001)
        self.assertTrue(career["rivalries"])

    def test_serialized_live_battle_and_refresh_do_not_advance_time(self):
        self.enter()
        self.start()
        self.fight("guard")
        restored = json.loads(json.dumps(self.state))
        before = copy.deepcopy(restored)
        self.engine._refresh(restored)
        self.assertEqual(restored, before)
        self.assertEqual(restored["battle"]["queue"], self.state["battle"]["queue"])
        self.assertEqual(restored["season"]["elapsed_days"], 1)
