"""Host-console game operations exercise real gameplay on isolated candidates."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from venom.common.game import GameEngine, GameError, SHOP, xp_required
from venom.server.admin_game import AdminGame, GAME_COMMANDS, MAX_CREDITS


def species(sid, name=None, stage="rookie", **extra):
    return {"id": sid, "name": name or sid.title(), "stage": stage, "type": "vaccine",
            "attribute": "fire", "base_stats": {"hp": 240, "sp": 40, "atk": 40,
                                                 "def": 25, "int": 36, "spd": 30},
            "sprites": {}, "evolutions": [], "paradox": False, **extra}


class AdminGameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        catalog = {
            "species": [species("alpha", "Alpha Mon", evolutions=[
                {"to": "beta", "level": 80, "abi": 200, "cam": 100},
                {"to": "delta", "level": 80, "abi": 200, "cam": 100}]),
                species("beta", "Beta Mon", "champion"),
                species("delta", "Delta Mon", "champion"),
                species("gamma"),
                species("alpha_paradox", "Alpha Mon Paradox", paradox=True, base_id="alpha"),
                species("beta_paradox", "Beta Mon Paradox", "champion", paradox=True, base_id="beta")],
            "tamers": [{"id": "tamer", "name": "Tamer", "frames": {}}],
            "maps": [{"id": "forest", "name": "Digital Forest", "level": 1,
                      "width": 500, "height": 500, "spawn": [150, 180]},
                     {"id": "mountain", "name": "Data Mountain", "level": 20,
                      "width": 500, "height": 500, "spawn": [250, 250]}],
        }
        (self.root / "catalog.json").write_text(json.dumps(catalog))
        self.engine = GameEngine(self.root, seed=17)
        self.admin = AdminGame(self.engine)
        self.state = self.engine.new_player("test", "tamer", "alpha")
        self.engine.handle(self.state, "digifarm", {"action": "return"})

    def act(self, command, *args):
        # Match the console's atomic-candidate contract.
        candidate = copy.deepcopy(self.state)
        result = self.admin.execute(command, candidate, list(args))
        self.state = candidate
        return result

    def partner(self):
        return self.state["party"][0]

    def test_read_only_lists_are_nonmutating_and_work_during_battle(self):
        self.act("spawn", "gamma")
        before = copy.deepcopy(self.state)
        for command, args in [("digimon", []), ("team", []), ("bag", []), ("money", []),
                              ("balance", []), ("digimoninfo", ["party:1"])]:
            self.assertTrue(self.admin.execute(command, self.state, args))
        self.assertEqual(self.state, before)
        self.assertIn("party:1", self.act("digimon"))

    def test_registry_rejects_arbitrary_commands(self):
        self.assertIn("setparadox", GAME_COMMANDS)
        for command in ("__dict__", "handle", "pokemon", "exec"):
            with self.assertRaises(GameError):
                self.act(command)

    def test_species_and_owned_selectors_support_exact_names_ids_and_slots(self):
        self.act("givedigimon", "Beta", "Mon", "15")
        self.assertEqual(self.state["party"][1]["level"], 15)
        self.act("setcam", "Beta Mon", "76")
        self.assertEqual(self.state["party"][1]["cam"], 76)
        uid = self.state["party"][1]["uid"]
        self.act("setabi", uid, "140")
        self.assertEqual(self.state["party"][1]["abi"], 140)
        self.assertIn("Beta Mon", self.admin.species_info(["beta"]))
        self.assertIn("alpha_paradox", self.admin.species_info(["Alpha Mon Paradox"]))

    def test_ambiguous_owned_names_fail_without_changing_either_partner(self):
        self.act("givedigimon", "alpha")
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(GameError, "Ambiguous"):
            self.act("setlevel", "Alpha Mon", "40")
        self.assertEqual(self.state, before)
        self.act("setlevel", "party:2", "40")
        self.assertEqual([p["level"] for p in self.state["party"]], [1, 40])
        for selector in ("party:0", "party:3", "storage:1", "not_owned"):
            with self.assertRaises(GameError):
                self.act("setcam", selector, "1")

    def test_duplicate_catalog_name_requires_id(self):
        self.engine.species["gamma"]["name"] = "Beta Mon"
        with self.assertRaisesRegex(GameError, "Ambiguous"):
            self.act("givedigimon", "Beta Mon")
        self.act("givedigimon", "beta")
        self.assertEqual(self.state["party"][1]["species_id"], "beta")

    def test_give_and_clone_obey_capacity_and_never_reuse_uids(self):
        for _ in range(5):
            self.act("givedigimon", "gamma", "2")
        self.act("givedigimon", "beta", "3")
        self.assertEqual(len(self.state["party"]), 6)
        self.assertEqual(len(self.state["storage"]), 1)
        source = self.state["storage"][0]
        source["farm_bonuses"] = {"atk": 8}
        source["history"] = ["alpha"]
        self.act("clonedigimon", "storage:1")
        clone = self.state["storage"][1]
        self.assertNotEqual(source["uid"], clone["uid"])
        self.assertEqual(source["history"], clone["history"])
        clone["farm_bonuses"]["atk"] = 9
        self.assertEqual(self.state["storage"][0]["farm_bonuses"]["atk"], 8)
        self.state["storage"] = [self.engine._monster("gamma") for _ in range(100)]
        for command, args in [("givedigimon", ("alpha",)), ("clonedigimon", ("party:1",))]:
            with self.assertRaisesRegex(GameError, "full"):
                self.act(command, *args)

    def test_cannot_remove_final_party_member_even_with_storage(self):
        self.state["storage"] = [self.engine._monster("beta")]
        with self.assertRaisesRegex(GameError, "at least one"):
            self.act("removedigimon", "party:1")
        self.act("removedigimon", "storage:1")
        self.assertEqual(self.state["storage"], [])
        self.act("givedigimon", "gamma")
        self.act("removedigimon", "party:1")
        self.assertEqual(self.partner()["species_id"], "gamma")

    def test_numeric_caps_are_explicit_not_silent_clamping(self):
        for command, values in {
            "setlevel": ["0", "100", "1.5", "true", "-1"],
            "setabi": ["201", "-1"],
            "setcam": ["101", "-1"],
            "setfriendshiplevel": ["101"],
            "setexp": [str(xp_required(1)), "-1", "1e4"],
        }.items():
            for value in values:
                with self.subTest(command=command, value=value), self.assertRaises(GameError):
                    self.act(command, "party:1", value)
        self.act("setabi", "party:1", "200")
        self.act("setfriendshiplevel", "party:1", "100")
        self.assertEqual(self.partner()["abi"], 200)
        self.assertEqual(self.partner()["cam"], 100)

    def test_level_and_xp_are_within_level_progress(self):
        self.act("setexp", "party:1", str(xp_required(1) - 1))
        self.assertEqual(self.partner()["level"], 1)
        self.act("setlevel", "party:1", "30")
        self.assertEqual(self.partner()["xp"], 0)
        self.act("setexp", "party:1", str(xp_required(30) - 1))
        self.act("setlevel", "party:1", "99")
        self.assertEqual(self.partner()["xp"], 0)
        with self.assertRaises(GameError):
            self.act("setexp", "party:1", "1")
        self.act("setexp", "party:1", "0")

    def test_recomputation_preserves_identity_history_bonuses_and_defeat(self):
        self.partner().update(history=["legacy"], farm_bonuses={"hp": 10, "atk": 20},
                              custom_metadata={"record": "preserve"})
        uid = self.partner()["uid"]
        self.act("setlevel", "party:1", "55")
        self.act("setabi", "party:1", "123")
        partner = self.partner()
        expected = self.engine.stats_for(self.engine.species["alpha"], 55, 123, {"hp": 10, "atk": 20})
        self.assertEqual(partner["max_hp"], expected["hp"])
        self.assertEqual(partner["atk"], expected["atk"])
        self.assertEqual(partner["skills"], self.engine._skills(partner))
        self.assertEqual(partner["uid"], uid)
        self.assertEqual(partner["history"], ["legacy"])
        self.assertEqual(partner["custom_metadata"], {"record": "preserve"})
        partner["hp"] = 0
        self.act("setlevel", "party:1", "60")
        self.assertEqual(self.partner()["hp"], 0)
        self.act("heal")
        self.assertEqual(self.partner()["hp"], self.partner()["max_hp"])

    def test_force_evolution_only_supported_routes_preserves_metadata(self):
        self.partner().update(history=["legacy"], cam=73, farm_bonuses={"atk": 7},
                              custom_metadata={"preserved": True})
        uid = self.partner()["uid"]
        with self.assertRaisesRegex(GameError, "explicit target"):
            self.act("evolve", "party:1")
        with self.assertRaises(GameError):
            self.act("evolve", "party:1", "gamma")
        self.act("evolve", "Alpha", "Mon", "Beta", "Mon")
        partner = self.partner()
        self.assertEqual(partner["species_id"], "beta")
        self.assertEqual(partner["level"], 1)
        self.assertEqual(partner["cam"], 73)
        self.assertEqual(partner["uid"], uid)
        self.assertEqual(partner["history"], ["legacy", "alpha"])
        self.assertEqual(partner["farm_bonuses"], {"atk": 7})
        self.assertTrue(partner["custom_metadata"]["preserved"])
        self.act("devolve", "party:1", "alpha")
        self.assertEqual(self.partner()["species_id"], "alpha")
        self.assertEqual(self.partner()["uid"], uid)
        self.assertIn("beta", self.partner()["history"])

    def test_paradox_maps_catalog_forms_and_keeps_identity(self):
        uid = self.partner()["uid"]
        self.act("setparadox", "party:1", "true")
        self.assertEqual(self.partner()["species_id"], "alpha_paradox")
        self.assertTrue(self.partner()["paradox"])
        self.act("setparadox", "party:1", "true")
        self.assertEqual(self.partner()["uid"], uid)
        self.act("evolve", "party:1", "beta_paradox")
        self.act("setparadox", "party:1", "false")
        self.assertEqual(self.partner()["species_id"], "beta")
        self.assertFalse(self.partner()["paradox"])
        self.assertEqual(self.partner()["uid"], uid)
        self.act("givedigimon", "gamma")
        for selector, value in [("party:2", "true"), ("party:1", "yes")]:
            with self.assertRaises(GameError):
                self.act("setparadox", selector, value)

    def test_inventory_uses_real_items_with_exact_bounds(self):
        self.act("giveitem", "Small HP Capsule", "5")
        self.assertEqual(self.state["inventory"]["hp_s"], 10)
        self.act("setitem", "hp_s", "999")
        with self.assertRaises(GameError):
            self.act("giveitem", "hp_s", "1")
        self.act("removeitem", "hp_s", "999")
        self.assertEqual(self.state["inventory"]["hp_s"], 0)
        for command, item, amount in [("removeitem", "hp_s", "1"), ("giveitem", "fake", "1"),
                                      ("setitem", "hp_s", "1000"), ("setitem", "hp_s", "-1")]:
            with self.assertRaises(GameError):
                self.act(command, item, amount)
        self.act("setitem", "digimeat_cam", "999")
        party = copy.deepcopy(self.state["party"])
        self.state["inventory"]["legacy_item"] = 7
        self.act("clearinventory")
        self.assertTrue(all(quantity == 0 for quantity in self.state["inventory"].values()))
        self.assertTrue(set(SHOP) <= set(self.state["inventory"]))
        self.assertEqual(self.state["party"], party)

    def test_money_bounds_prevent_underflow_and_precision_overflow(self):
        self.act("setmoney", "0")
        with self.assertRaises(GameError):
            self.act("removemoney", "1")
        self.act("givemoney", "65")
        self.act("removemoney", "5")
        self.assertEqual(self.state["credits"], 60)
        self.act("setmoney", str(MAX_CREDITS))
        self.assertEqual(self.state["credits"], MAX_CREDITS)
        for command, value in [("givemoney", "1"), ("setmoney", str(MAX_CREDITS + 1)),
                               ("setmoney", "-1"), ("givemoney", "9" * 5000)]:
            with self.assertRaises(GameError):
                self.act(command, value)

    def test_all_mutations_reject_active_battle_season_and_jailed_state(self):
        for context in ({"battle": {"id": "paused"}}, {"in_season": True},
                        {"admin_jail": {"suspended": {"battle": {"id": "paused"}}}}):
            for command in GAME_COMMANDS - {"digimon", "team", "bag", "money", "balance", "digimoninfo"}:
                with self.subTest(context=context, command=command):
                    candidate = {**copy.deepcopy(self.state), **context}
                    before = copy.deepcopy(candidate)
                    with self.assertRaises(GameError):
                        self.admin.execute(command, candidate, [])
                    self.assertEqual(candidate, before)

    def test_teleport_changes_only_location_and_checks_collision(self):
        from PIL import Image
        Image.new("L", (50, 50), 0).save(self.root / "blocked.png")
        self.engine.maps["mountain"]["walkable"] = "blocked.png"
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(GameError, "blocked"):
            self.act("teleportplayer", "Data", "Mountain")
        self.assertEqual(before, self.state)
        self.engine.maps["mountain"].pop("walkable")
        self.admin.navigation.masks.clear()
        self.state.update(in_farm=True, return_location={"map_id": "forest", "x": 100, "y": 100})
        self.act("teleportplayer", "Data Mountain")
        self.assertEqual((self.state["map_id"], self.state["x"], self.state["y"]), ("mountain", 250, 250))
        self.assertFalse(self.state["in_farm"])
        self.assertNotIn("return_location", self.state)

    def test_spawn_waits_for_real_player_and_supports_normal_controls(self):
        self.act("setlevel", "party:1", "99")
        self.act("spawn", "gamma", "1")
        battle = self.state["battle"]
        self.assertEqual(battle["enemies"][0]["species_id"], "gamma")
        self.assertEqual(battle["enemies"][0]["hp"], battle["enemies"][0]["max_hp"])
        self.assertEqual(battle["actor"], 0)
        self.assertEqual(self.state["wins"], 0)
        # It is a normal persisted wild battle. Player attack awards normal
        # victory and scan only when the player explicitly sends that action.
        restored = json.loads(json.dumps(self.state))
        self.engine.handle(restored, "battle", {"action": "attack", "target": 0})
        self.assertIsNone(restored["battle"])
        self.assertEqual(restored["wins"], 1)
        self.assertEqual(restored["scan"]["gamma"], 20)
        self.assertEqual(self.state["wins"], 0)

    def test_spawn_rejects_hubs_unhealthy_team_and_unknown_species(self):
        for key in ("in_farm", "in_lab"):
            self.state[key] = True
            with self.assertRaises(GameError):
                self.act("spawn", "gamma")
            self.state[key] = False
        self.partner()["hp"] = 0
        with self.assertRaises(GameError):
            self.act("spawn", "gamma")
        self.act("heal")
        with self.assertRaises(GameError):
            self.act("spawn", "missing")


if __name__ == "__main__":
    unittest.main()
