"""Shiny IDs stay authoritative across local administration, WSS and rivals."""
import copy
import unittest
from unittest.mock import patch

import test_admin_game as _admin
import test_bots as _bots
import test_story_protocol as _protocol
from venom.common.game import GameEngine, GameError
from venom.server.admin_commands import AdminConsole, COMMANDS
from venom.server.bots import BotManager
from venom.server.community_store import CommunityStore
from venom.server.database import Database
from venom.server.ranked import RankedService


class ShinyAdminTests(unittest.TestCase):
    act = _admin.AdminGameTests.act
    partner = _admin.AdminGameTests.partner

    def setUp(self):
        _admin.AdminGameTests.setUp(self)
        self.engine.species["alpha_shiny"] = _admin.species(
            "alpha_shiny", "Alpha Mon Shiny", shiny=True, base_id="alpha", variety="shiny")

    def test_canonical_variety_switch_preserves_partner_and_records_actual_changes(self):
        self.partner().update(history=["gamma"], cam=72, farm_bonuses={"atk": 9},
                              custom_metadata={"retain": True})
        uid = self.partner()["uid"]
        self.assertIn("SHINY", self.act("setshiny", "party:1", "true"))
        self.assertEqual(("alpha_shiny", True, False, "shiny"), tuple(
            self.partner()[key] for key in ("species_id", "shiny", "paradox", "variety")))
        history = copy.deepcopy(self.partner()["history"])
        self.act("setshiny", "party:1", "true")
        self.assertEqual(history, self.partner()["history"])
        # Switching directly from Shiny to Paradox clears incompatible flags.
        self.act("setparadox", "party:1", "true")
        self.assertEqual(("alpha_paradox", False, True, "paradox"), tuple(
            self.partner()[key] for key in ("species_id", "shiny", "paradox", "variety")))
        self.act("setshiny", "party:1", "true")
        self.act("setshiny", "party:1", "false")
        self.assertEqual(("alpha", False, False, "normal"), tuple(
            self.partner()[key] for key in ("species_id", "shiny", "paradox", "variety")))
        self.assertEqual(["gamma", "alpha", "alpha_shiny", "alpha_paradox"], self.partner()["history"])
        self.assertEqual(uid, self.partner()["uid"])
        self.assertEqual(72, self.partner()["cam"])
        self.assertEqual({"atk": 9}, self.partner()["farm_bonuses"])
        self.assertTrue(self.partner()["custom_metadata"]["retain"])

    def test_missing_counterpart_and_busy_player_reject_without_mutation(self):
        self.assertEqual("GAME_MASTER", COMMANDS["setshiny"].permission)
        self.act("givedigimon", "gamma")
        for selector, value in (("party:2", "true"), ("party:1", "yes")):
            before = copy.deepcopy(self.state)
            with self.assertRaises(GameError):
                self.act("setshiny", selector, value)
            self.assertEqual(before, self.state)
        self.act("spawn", "gamma")
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(GameError, "battle"):
            self.act("setshiny", "party:1", "true")
        self.assertEqual(before, self.state)


class ShinyProtocolTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = _protocol.StoryProtocolTests.asyncSetUp
    asyncTearDown = _protocol.StoryProtocolTests.asyncTearDown
    start_server = _protocol.StoryProtocolTests.start_server
    stop_server = _protocol.StoryProtocolTests.stop_server
    connection = _protocol.StoryProtocolTests.connection
    receive = _protocol.StoryProtocolTests.receive
    request = _protocol.StoryProtocolTests.request
    action = _protocol.StoryProtocolTests.action
    register = _protocol.StoryProtocolTests.register
    wait_for_logout = _protocol.StoryProtocolTests.wait_for_logout
    battle_fields = staticmethod(_protocol.StoryProtocolTests.battle_fields)

    async def test_world_map_shiny_scan_conversion_and_partner_survive_server_restart(self):
        """Actual encounter, attacks, 5% scan, conversion, save and login protocol."""
        async with self.connection() as ws:
            initial = await self.register(ws, "ShinyWorld")
            low = AdminConsole(self.world, role="PLAYER")
            try:
                denied = await low.execute("/setshiny ShinyWorld party:1 true")
                self.assertTrue(denied.startswith("DENIED:"), denied)
            finally:
                await low.close()
            rejected = await self.request(ws, "setshiny", species_id="agumon_shiny", role="OWNER")
            self.assertFalse(rejected["ok"])
            self.assertFalse(self.world.sessions["shinyworld"].state["party"][0].get("shiny"))
            raised = await self.console.execute("/setlevel ShinyWorld party:1 99")
            self.assertFalse(raised.startswith("ERROR:"), raised)

            maps = [initial["map_id"], next(m["id"] for m in self.engine.maps.values()
                    if m.get("region_id") == "world_ds" and m.get("level") == 1)]
            for map_id in maps:
                state = await self.action(ws, "travel", map_id=map_id)
                # Deterministic server-side RNG selects the real Shiny interval;
                # client encounter fields remain untrusted and are ignored.
                session = self.world.sessions["shinyworld"]
                session.last_encounter = 0
                with patch.object(self.engine.rng, "choices", return_value=[1]), \
                     patch.object(self.engine.rng, "random", return_value=.03):
                    state = await self.action(ws, "encounter", shiny=False, species_id="forged")
                enemy = state["battle"]["enemies"][0]
                self.assertTrue(enemy["shiny"])
                self.assertFalse(enemy["paradox"])
                shiny_id = enemy["species_id"]
                self.assertIn(shiny_id, self.engine._shiny_pools[map_id])
                # A mature account already earned 95%; one genuine defeat must
                # add precisely the remaining five without changing base scans.
                async with session.lock:
                    session.state["scan"][shiny_id] = 95
                    base_id = self.engine.species[shiny_id]["base_id"]
                    base_scan = session.state["scan"].get(base_id, 0)
                    await self.world.save(session)
                for _ in range(30):
                    if not state["battle"]:
                        break
                    state = await self.action(ws, "battle", **self.battle_fields(state, "attack", target=0))
                self.assertIsNone(state["battle"])
                self.assertEqual(100, state["scan"][shiny_id])
                self.assertEqual(base_scan, state["scan"].get(base_id, 0))
                self.assertEqual(5, next(event["amount"] for event in state["events"]
                                         if event["kind"] == "scan"))
                state = await self.action(ws, "digilab", action="enter")
                state = await self.action(ws, "materialize", species_id=shiny_id)
                self.assertEqual(0, state["scan"][shiny_id])
                partner = next(m for m in state["party"] + state["storage"]
                               if m["species_id"] == shiny_id)
                self.assertTrue(partner["shiny"])
                self.assertEqual("shiny", partner["variety"])
                state = await self.action(ws, "digilab", action="return")
            owned = copy.deepcopy(state["party"] + state["storage"])
            scans = copy.deepcopy(state["scan"])
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout("shinyworld")
        await self.stop_server()
        await self.start_server()
        async with self.connection() as ws:
            hello = await self.receive(ws, "hello")
            self.assertIn("shiny_varieties", hello["features"])
            state = await self.action(ws, "login", username="ShinyWorld", password=_protocol.PASSWORD)
            self.assertEqual(scans, state["scan"])
            self.assertEqual(owned, state["party"] + state["storage"])
            result = await self.console.execute("/setshiny ShinyWorld party:1 true")
            self.assertFalse(result.startswith("ERROR:"), result)
            session = self.world.sessions["shinyworld"]
            self.assertTrue(session.state["party"][0]["shiny"])
            await self.world.broadcast_once()
            packet = await self.receive(ws, "world")
            self.assertEqual(session.state["party"][0]["species_id"], packet["players"][0]["lead"])
            persisted, _ = self.db.load("shinyworld")
            self.assertEqual(session.state["party"][0], persisted["party"][0])


def test_rivals_materialize_earned_shiny_and_restore_the_counter_and_partner():
    store = _bots.MemoryStore()
    manager = _bots.make_manager(count=1, store=store)
    bot = manager.bots["bot:00001"]
    assert all(not manager.engine.species[sid].get("shiny") for sid in manager.engine.starters)
    manager._execute(bot, "digilab", {"action": "enter"})
    bot["state"]["scan"]["agumon_shiny"] = 99
    manager._materialize(bot)
    assert bot["stats"]["shiny_materialized"] == 0
    bot["state"]["scan"]["agumon_shiny"] = 100
    manager._materialize(bot)
    assert bot["stats"]["shiny_materialized"] == 1
    assert bot["stats"]["paradox_materialized"] == 0
    assert bot["state"]["scan"]["agumon_shiny"] == 0
    partner = next(m for m in bot["state"]["party"] + bot["state"]["storage"]
                   if m["species_id"] == "agumon_shiny")
    assert partner["shiny"] and not partner["paradox"]
    store.bot_save_batch([manager._serialize(bot, 0)])
    restored = BotManager(manager.engine, store, config={"count": 1})
    restored.initialize(1)
    saved = restored.bots[bot["id"]]
    assert saved["stats"]["shiny_materialized"] == 1
    assert partner in saved["state"]["party"] + saved["state"]["storage"]


def test_ranked_defender_snapshot_retains_shiny_for_replays_after_restart(tmp_path):
    engine = GameEngine(_protocol.ROOT, seed=57)
    database_config = {"driver": "sqlite", "path": str(tmp_path / "shiny_ranked.sqlite3")}
    config = {"match_cooldown": 0, "opponent_cooldown": 0}
    profiles = [{"id": ident, "name": ident, "kind": kind,
                 "tamer": next(iter(engine.tamers)),
                 "party": [engine._monster(sid, level)]}
                for ident, kind, sid, level in (("player:shiny", "player", "agumon_shiny", 50),
                                               ("bot:shinytest", "bot", "agumon", 1))]
    db = Database(database_config, dev=True)
    db.initialize()
    try:
        store = CommunityStore(db)
        store.initialize()
        ranked = RankedService(engine, store, config)
        ranked.register_many(profiles)
        result = ranked.start_match("player:shiny", "bot:shinytest", "shiny-ranked-v120")
        assert result["replay"]["party"][0]["species_id"] == "agumon_shiny"
        assert result["replay"]["party"][0]["shiny"]
        assert result["replay"]["events"]
    finally:
        db.close()
    db = Database(database_config, dev=True)
    db.initialize()
    try:
        store = CommunityStore(db)
        store.initialize()
        restored = RankedService(engine, store, config)
        partner = restored.profiles["player:shiny"]["party"][0]
        assert partner == profiles[0]["party"][0]
        match = store.match("shiny-ranked-v120")
        assert match["winner_id"] == result["winner_id"]
        # The existing ledger intentionally stores compact outcomes, not old
        # animation frames. Fresh fights replay the restored species correctly.
        replay = restored.start_match("player:shiny", "bot:shinytest", "shiny-ranked-after-restart")
        assert replay["replay"]["party"][0]["species_id"] == "agumon_shiny"
        assert replay["replay"]["party"][0]["shiny"]
    finally:
        db.close()
