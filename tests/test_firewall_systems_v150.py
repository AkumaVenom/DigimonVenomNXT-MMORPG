"""FireWall stays a real catalog identity across host, rivals and competitions."""
import copy
import random
import unittest
from pathlib import Path

import test_admin_game as admin_harness
import test_bots as bot_harness
from venom.common import season
from venom.common.game import GameEngine, GameError, variety_of
from venom.server.admin_commands import COMMANDS
from venom.server.bots import BotManager
from venom.server.community_store import CommunityStore
from venom.server.database import Database
from venom.server.ranked import RankedService

ROOT = Path(__file__).resolve().parents[1]


class FireWallAdminTests(unittest.TestCase):
    act = admin_harness.AdminGameTests.act
    partner = admin_harness.AdminGameTests.partner

    def setUp(self):
        admin_harness.AdminGameTests.setUp(self)
        for kind in ("shiny", "firewall"):
            self.engine.species[f"alpha_{kind}"] = admin_harness.species(
                f"alpha_{kind}", f"Alpha Mon ({kind})", base_id="alpha", variety=kind,
                **{kind: True})

    def test_each_canonical_variety_switch_preserves_partner_and_clears_other_flags(self):
        self.partner().update(history=["gamma"], cam=72, farm_bonuses={"atk": 9},
                              custom_metadata={"keep": True})
        uid = self.partner()["uid"]
        for kind in ("firewall", "shiny", "paradox", "firewall"):
            self.assertIn(kind.upper(), self.act(f"set{kind}", "party:1", "true"))
            current = self.partner()
            self.assertEqual(f"alpha_{kind}", current["species_id"])
            self.assertEqual(kind, current["variety"])
            self.assertEqual([kind], [flag for flag in ("firewall", "shiny", "paradox") if current[flag]])
            before = copy.deepcopy(current)
            self.act(f"set{kind}", "party:1", "true")
            self.assertEqual(before, self.partner())
        self.assertIn("FireWall: yes", self.admin.species_info(["alpha_firewall"]))
        self.act("setfirewall", "party:1", "false")
        self.assertEqual("alpha", self.partner()["species_id"])
        self.assertEqual("normal", self.partner()["variety"])
        self.assertFalse(any(self.partner()[kind] for kind in ("firewall", "shiny", "paradox")))
        self.assertEqual(["gamma", "alpha", "alpha_firewall", "alpha_shiny", "alpha_paradox"], self.partner()["history"])
        self.assertEqual(uid, self.partner()["uid"])
        self.assertEqual(72, self.partner()["cam"])
        self.assertEqual({"atk": 9}, self.partner()["farm_bonuses"])
        self.assertEqual({"keep": True}, self.partner()["custom_metadata"])

    def test_command_permission_and_failed_counterpart_requests_are_atomic(self):
        self.assertEqual("GAME_MASTER", COMMANDS["setfirewall"].permission)
        self.act("givedigimon", "gamma")
        for selector, value in (("party:2", "true"), ("party:1", "yes")):
            before = copy.deepcopy(self.state)
            with self.assertRaises(GameError):
                self.act("setfirewall", selector, value)
            self.assertEqual(before, self.state)
        # Catalog ambiguity must fail instead of selecting an arbitrary asset.
        self.engine.species["duplicate"] = {**self.engine.species["alpha_firewall"], "id": "duplicate"}
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(GameError, "one supported"):
            self.act("setfirewall", "party:1", "true")
        self.assertEqual(before, self.state)

    def test_give_spawn_and_busy_rejection_use_real_firewall_identity(self):
        self.act("givedigimon", "alpha_firewall", "40")
        self.assertEqual(("alpha_firewall", True, 40), tuple(
            self.state["party"][1][key] for key in ("species_id", "firewall", "level")))
        self.act("spawn", "alpha_firewall", "5")
        self.assertTrue(self.state["battle"]["enemies"][0]["firewall"])
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(GameError, "battle"):
            self.act("setfirewall", "party:1", "true")
        self.assertEqual(before, self.state)


def test_rivals_convert_only_earned_firewall_and_restore_its_counter():
    store = bot_harness.MemoryStore()
    manager = bot_harness.make_manager(count=1, store=store)
    bot = manager.bots["bot:00001"]
    assert all(variety_of(manager.engine.species[sid]) == "normal" for sid in manager.engine.starters)
    manager._execute(bot, "digilab", {"action": "enter"})
    bot["state"]["scan"]["agumon_firewall"] = 99
    manager._materialize(bot)
    assert bot["stats"]["firewall_materialized"] == 0
    bot["state"]["scan"]["agumon_firewall"] = 100
    manager._materialize(bot)
    assert bot["stats"]["firewall_materialized"] == 1
    assert bot["stats"]["shiny_materialized"] == bot["stats"]["paradox_materialized"] == 0
    assert bot["state"]["scan"]["agumon_firewall"] == 0
    partner = next(m for m in bot["state"]["party"] + bot["state"]["storage"]
                   if m["species_id"] == "agumon_firewall")
    assert partner["firewall"] and not partner["paradox"] and not partner["shiny"]
    store.bot_save_batch([manager._serialize(bot, 0)])
    restored = BotManager(manager.engine, store, config={"count": 1})
    restored.initialize(1)
    saved = restored.bots[bot["id"]]
    assert saved["stats"]["firewall_materialized"] == 1
    assert partner in saved["state"]["party"] + saved["state"]["storage"]


def test_rival_firewall_partner_evolves_through_normal_authoritative_gameplay():
    manager = bot_harness.make_manager(count=1)
    bot = manager.bots["bot:00001"]
    state = bot["state"]
    state["party"] = [manager.engine._monster("agumon_firewall", 99, abi=200, cam=100),
                      manager.engine._monster("agumon", 99, abi=200, cam=100)]
    uid = state["party"][0]["uid"]
    manager._execute(bot, "digilab", {"action": "enter"})
    manager._evolve(bot)
    partner = state["party"][0]
    assert bot["stats"]["evolutions"] == 1
    assert partner["uid"] == uid
    assert partner["species_id"] != "agumon_firewall"
    assert partner["firewall"] and partner["variety"] == "firewall"
    assert "agumon_firewall" in partner["history"]


def test_legacy_rival_save_adds_only_the_new_counter():
    store = bot_harness.MemoryStore()
    manager = bot_harness.make_manager(count=2, store=store)
    for bot in manager.bots.values():
        row = manager._serialize(bot, 0)
        row["stats"].pop("firewall_materialized")
        row["stats"]["shiny_materialized"] = 7
        store.bot_save_batch([row])
    old_maps = {ident: bot["state"]["map_id"] for ident, bot in manager.bots.items()}
    restored = BotManager(manager.engine, store, config={"count": 2})
    restored.initialize(1)
    assert {ident: bot["state"]["map_id"] for ident, bot in restored.bots.items()} == old_maps
    for bot in restored.bots.values():
        assert bot["stats"]["firewall_materialized"] == 0
        assert bot["stats"]["shiny_materialized"] == 7


def test_ranked_snapshot_and_replays_keep_firewall_partner_after_database_restart(tmp_path):
    engine = GameEngine(ROOT, seed=57)
    database_config = {"driver": "sqlite", "path": str(tmp_path / "firewall_ranked.sqlite3")}
    config = {"match_cooldown": 0, "opponent_cooldown": 0}
    profiles = [{"id": ident, "name": ident, "kind": kind, "tamer": next(iter(engine.tamers)),
                 "party": [engine._monster(sid, level)]}
                for ident, kind, sid, level in (("player:firewall", "player", "agumon_firewall", 50),
                                               ("bot:firetest", "bot", "agumon", 1))]
    for index in range(2):
        db = Database(database_config, dev=True)
        db.initialize()
        try:
            store = CommunityStore(db)
            store.initialize()
            ranked = RankedService(engine, store, config)
            if not index:
                ranked.register_many(profiles)
            assert ranked.profiles["player:firewall"]["party"][0] == profiles[0]["party"][0]
            match = ranked.start_match("player:firewall", "bot:firetest", f"firewall-ranked-v150-{index}")
            partner = match["replay"]["party"][0]
            assert partner["species_id"] == "agumon_firewall" and partner["firewall"]
            assert match["replay"]["events"]
            assert "scan" not in ranked.profiles["player:firewall"]
        finally:
            db.close()


def test_season_uses_owned_firewall_stats_and_npc_rosters_remain_normal():
    engine = GameEngine(ROOT, seed=71)
    state = engine.new_player("FireCircuit", next(iter(engine.tamers)), "agumon")
    state["party"] = [engine._monster("agumon_firewall", 40, abi=12, cam=90)]
    original = copy.deepcopy(state["party"])
    # Exercise the defensive NPC filter even if a future caller supplies an
    # overbroad starter list; the player's existing partner is kept unchanged.
    career = season.create_career(state, engine.species, engine.tamers, ["agumon", "agumon_firewall"])
    assert season.member(career, season.PLAYER_ID)["team"][0]["species_id"] == "agumon_firewall"
    assert all(variety_of(engine.species[m["species_id"]]) == "normal"
               for row in career["roster"] if not row["is_player"] for m in row["team"])
    engine.handle(state, "season", {"action": "enter"})
    assert state["party"] == original
    engine.handle(state, "season", {"action": "start", "token": state["season"]["card"]["token"]})
    assert state["party"][0]["atk"] == original[0]["atk"]
    assert state["party"][0]["max_hp"] == original[0]["max_hp"]
    for _ in range(300):
        if not state["battle"]:
            break
        target = next(i for i, monster in enumerate(state["battle"]["enemies"]) if monster["hp"] > 0)
        engine.handle(state, "battle", {"action": "attack", "target": target,
                                       "battle_id": state["battle"]["id"],
                                       "expected_turn": state["battle"]["turn"]})
    assert state["battle"] is None
    assert state["scan"] == {}
    assert state["party"][0]["firewall"]


def test_season_npc_cannot_evolve_into_firewall_from_a_malformed_cross_variety_route():
    species = {"base": {"name": "Base", "evolutions": [{"to": "rare", "level": 1}]},
               "rare": {"name": "Rare", "firewall": True}}
    row = {"name": "NPC", "is_player": False, "development": 11,
           "team": [{"species_id": "base", "level": 40}], "species_id": "base", "level": 40}
    news = []
    season._develop(row, species, random.Random(1), news)
    assert row["team"] == [{"species_id": "base", "level": 41}]
    assert news == []
