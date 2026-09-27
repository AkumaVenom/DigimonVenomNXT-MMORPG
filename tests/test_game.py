"""Meaningful server-rules tests using a small independent asset catalog."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from venom.common.game import GameEngine, GameError, attribute_multiplier, type_multiplier, effectiveness


def species(sid, stage="rookie", typ="free", attribute="neutral", speed=30, paradox=False, **extra):
    return {"id": sid, "name": sid.title(), "stage": stage, "type": typ, "attribute": attribute,
            "base_stats": {"hp": 240, "sp": 40, "atk": 40, "def": 25, "int": 36, "spd": speed},
            "sprites": {}, "evolutions": [], "paradox": paradox,
            "base_id": sid.replace("_paradox", ""), **extra}


class GameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name)
        (path / "data").mkdir()
        catalog = {"species": [species("alpha", evolutions=[{"to": "beta", "level": 2, "abi": 0, "cam": 0, "stats": {"atk": 45}}]),
                               species("beta", "champion"), species("gamma"),
                               species("alpha_paradox", paradox=True)],
                   "tamers": [{"id": "tamer", "name": "Tamer", "frames": {}}],
                   "maps": [{"id": "forest", "name": "Forest", "level": 1, "width": 500, "height": 500, "spawn": [150, 180]},
                            {"id": "mountain", "name": "Mountain", "level": 20, "width": 500, "height": 500, "spawn": [250, 250]}]}
        (path / "data/catalog.json").write_text(json.dumps(catalog))
        self.engine = GameEngine(path, seed=17)
        self.state = self.engine.new_player("test", "tamer", "alpha")
        # These legacy rule scenarios explicitly begin in the field. New players
        # now spawn at home; home behavior is exercised in test_digifarm.py.
        self.engine.handle(self.state, "digifarm", {"action": "return"})

    def act(self, op, **payload):
        return self.engine.handle(self.state, op, payload)

    def battle(self, enemy_hp=50, enemy_speed=20):
        self.act("encounter")
        enemy = self.engine._monster("gamma")
        enemy["hp"] = enemy["max_hp"] = enemy_hp
        enemy["spd"] = enemy_speed
        b = self.state["battle"]
        b.update(enemies=[enemy], active=[0], actor=0, queue=[{"side": "enemy", "index": 0, "at": 50}], scanned=[], clock=0)
        return enemy

    def test_type_and_attribute_multipliers(self):
        for a, b in [("vaccine", "virus"), ("virus", "data"), ("data", "vaccine")]:
            self.assertEqual(type_multiplier(a, b), 2)
            self.assertEqual(type_multiplier(b, a), .5)
        self.assertEqual(type_multiplier("free", "virus"), 1)
        self.assertEqual(attribute_multiplier("fire", "plant"), 1.5)
        self.assertEqual(attribute_multiplier("plant", "fire"), 1)
        self.assertEqual(attribute_multiplier("light", "dark"), 1.5)
        self.assertEqual(attribute_multiplier("dark", "light"), 1.5)
        self.assertEqual(effectiveness({"type": "vaccine", "attribute": "fire"}, {"type": "virus", "attribute": "plant"}), 3)

    def test_starter_validation(self):
        for starter in ("beta", "alpha_paradox", "missing"):
            with self.assertRaises(GameError):
                self.engine.new_player("test", "tamer", starter)
        with self.assertRaises(GameError):
            self.engine.new_player("test", "missing", "alpha")
        self.assertEqual(len(self.state["party"]), 1)

    def test_zero_sp_regular_attack_is_free(self):
        enemy = self.battle(enemy_hp=1000)
        self.state["party"][0]["sp"] = 0
        self.act("battle", action="attack", target=0)
        self.assertLess(enemy["hp"], 1000)
        self.assertEqual(self.state["party"][0]["sp"], 0)
        self.act("battle", action="attack", target=0)
        with self.assertRaises(GameError):
            self.act("battle", action="skill", target=0)

    def test_kill_scan_once_and_victory_rewards(self):
        self.battle(enemy_hp=1)
        old = self.state["credits"]
        self.act("battle", action="attack", target=0)
        self.assertIsNone(self.state["battle"])
        self.assertEqual(self.state["scan"]["gamma"], 20)
        self.assertEqual(self.state["wins"], 1)
        self.assertGreater(self.state["credits"], old)
        self.assertGreater(self.state["party"][0]["cam"], 10)
        with self.assertRaises(GameError):
            self.act("battle", action="attack", target=0)
        self.assertEqual(self.state["scan"]["gamma"], 20)

    def test_paradox_scan_is_lower_and_cap_200(self):
        self.battle()
        rare = self.engine._monster("alpha_paradox")
        rare["hp"] = 0
        self.state["battle"]["enemies"] = [rare]
        self.state["scan"]["alpha_paradox"] = 198
        self.engine._scan_defeat(self.state, 0)
        self.assertEqual(self.state["scan"]["alpha_paradox"], 200)
        self.engine._scan_defeat(self.state, 0)
        self.assertEqual(self.state["scan"]["alpha_paradox"], 200)

    def test_materialize_requires_lab_consumes_scan_and_respects_six_slots(self):
        self.state["scan"]["gamma"] = 200
        with self.assertRaises(GameError):
            self.act("materialize", species_id="gamma")
        self.act("digilab", action="enter")
        self.act("materialize", species_id="gamma")
        self.assertEqual(self.state["party"][-1]["abi"], 5)
        self.assertEqual(self.state["scan"]["gamma"], 0)
        with self.assertRaises(GameError):
            self.act("materialize", species_id="gamma")
        for _ in range(5):
            self.state["scan"]["gamma"] = 100
            self.act("materialize", species_id="gamma")
        self.assertEqual(len(self.state["party"]), 6)
        self.assertEqual(len(self.state["storage"]), 1)

    def test_lab_roundtrip_heals_and_preserves_exact_world_location(self):
        self.state.update(x=132.75, y=299.2)
        monster = self.state["party"][0]
        monster.update(hp=1, sp=0)
        self.act("digilab", action="enter")
        self.assertEqual(monster["hp"], monster["max_hp"])
        self.assertEqual(monster["sp"], monster["max_sp"])
        self.act("digilab", action="return")
        self.assertEqual((self.state["map_id"], self.state["x"], self.state["y"]), ("forest", 132.75, 299.2))
        self.assertFalse(self.state["in_lab"])

    def test_shop_rejects_negative_bool_and_overspending(self):
        self.act("digilab", action="enter")
        for q in (-1, 0, True, 100, "2"):
            money = self.state["credits"]
            with self.assertRaises(GameError):
                self.act("shop", item="hp_s", quantity=q)
            self.assertEqual(money, self.state["credits"])
        with self.assertRaises(GameError):
            self.act("shop", item="sp_l", quantity=2)
        self.act("shop", item="hp_s", quantity=2)
        self.assertEqual(self.state["credits"], 530)
        self.assertEqual(self.state["inventory"]["hp_s"], 7)

    def test_item_rejects_full_hp_without_consuming(self):
        before = self.state["inventory"]["hp_s"]
        with self.assertRaises(GameError):
            self.act("item", item="hp_s", party_index=0)
        self.assertEqual(self.state["inventory"]["hp_s"], before)
        self.state["party"][0]["hp"] = 1
        self.act("item", item="hp_s", party_index=0)
        self.assertEqual(self.state["inventory"]["hp_s"], before - 1)
        self.assertEqual(self.state["party"][0]["hp"], self.state["party"][0]["max_hp"])

    def test_evolution_checks_stats_and_devolution_preserves_identity(self):
        self.act("digilab", action="enter")
        monster = self.state["party"][0]
        uid = monster["uid"]
        with self.assertRaises(GameError):
            self.act("evolve", party_index=0, to="beta")
        monster["level"] = 2
        with self.assertRaises(GameError):
            self.act("evolve", party_index=0, to="beta")
        monster["atk"] = 45
        self.act("evolve", party_index=0, to="beta")
        evolved = self.state["party"][0]
        self.assertEqual(evolved["uid"], uid)
        self.assertEqual(evolved["level"], 1)
        self.assertEqual(evolved["cam"], 10)
        evolved["level"] = 5
        old_abi = evolved["abi"]
        self.act("evolve", party_index=0, to="alpha")
        self.assertGreater(self.state["party"][0]["abi"], old_abi)
        self.assertEqual(self.state["party"][0]["uid"], uid)

    def test_faster_partner_gets_extra_turns(self):
        self.battle(enemy_hp=10000, enemy_speed=10)
        self.state["party"][0]["spd"] = 200
        for _ in range(3):
            self.act("battle", action="attack", target=0)
            self.assertEqual(self.state["battle"]["actor"], 0)
            enemy_events = [e for e in self.state["events"] if e.get("attacker_side") == "enemy"]
            self.assertEqual(enemy_events, [])

    def test_battle_only_uses_first_three_party_slots(self):
        self.state["party"] += [self.engine._monster("gamma") for _ in range(5)]
        self.act("encounter")
        self.assertEqual(self.state["battle"]["active"], [0, 1, 2])
        self.assertTrue(all(q["index"] < 3 for q in self.state["battle"]["queue"] if q["side"] == "player"))

    def test_lab_travel_party_changes_blocked_during_battle(self):
        self.battle()
        for op, payload in [("digilab", {"action": "enter"}), ("travel", {"map_id": "mountain"}),
                            ("party", {"action": "lead", "index": 0}), ("item", {"item": "hp_s"})]:
            with self.assertRaises(GameError):
                self.engine.handle(self.state, op, payload)

    def test_loss_recovers_with_no_currency_or_scan_penalty(self):
        self.battle()
        money = self.state["credits"]
        self.state["scan"]["gamma"] = 20
        self.state["party"][0]["hp"] = 0
        self.engine._check_end(self.state)
        self.assertIsNone(self.state["battle"])
        self.assertTrue(self.state["in_lab"])
        self.assertEqual(self.state["party"][0]["hp"], self.state["party"][0]["max_hp"])
        self.assertEqual(self.state["credits"], money)
        self.assertEqual(self.state["scan"]["gamma"], 20)

    def test_all_species_have_encounter_locations(self):
        available = {sid for normal, rare in self.engine._pools.values() for sid in normal + rare}
        self.assertEqual(available, set(self.engine.species))


if __name__ == "__main__":
    unittest.main()
