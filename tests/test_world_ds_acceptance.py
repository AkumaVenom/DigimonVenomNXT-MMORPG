"""Played World DS acceptance against shipped assets, packets and saved states.

Combat is driven exclusively through the ordinary battle commands. Scan data,
credits and recruits below are earned by those battles, never injected results.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import random
import tempfile
import unittest
from pathlib import Path

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from venom.common.game import GameEngine, effectiveness
from venom.server.database import Database
from venom.server.bots import BotManager
from venom.server.community_store import CommunityStore
from venom.server.main import GAME_OPS, WorldServer
from venom.server.navigation import Navigation


ROOT = Path(__file__).resolve().parents[1]
LEGACY_POOL_SHA256 = "d0a16339bfb3be241617060d420d71bac5e432a83f75e8bf83f469f127247f29"


def ds_maps(engine):
    areas = [area for area in engine.maps.values() if area.get("region_id") == "world_ds"]
    assert areas, "The imported World DS region must be available in the production catalog"
    return sorted(areas, key=lambda area: (area["level"], area["id"]))


def command_for(state):
    """Choose an ordinary available attack from the same public combat stats."""
    battle = state["battle"]
    actor = state["party"][battle["actor"]]
    if actor["hp"] < actor["max_hp"] * .35 and state["inventory"].get("hp_s", 0):
        return {"action": "item", "item": "hp_s", "party_index": battle["actor"]}
    choices = []
    for target, enemy in enumerate(battle["enemies"]):
        if enemy["hp"] <= 0:
            continue
        moves = [("attack", None)] + [("skill", index) for index, skill in enumerate(actor["skills"])
                                        if actor["sp"] >= skill["sp"]]
        for action, index in moves:
            skill = actor["skills"][index] if index is not None else None
            magic = bool(skill and skill["kind"] == "magic")
            damage = max(1, (8 + actor["int" if magic else "atk"] * .72
                             - enemy["int" if magic else "def"] * .28)
                         * (skill["power"] if skill else 1)
                         * effectiveness(actor, enemy, skill["attribute"] if skill else "neutral"))
            command = {"action": action, "target": target}
            if index is not None:
                command["skill_index"] = index
            choices.append((damage / enemy["hp"], damage, command))
    return max(choices, key=lambda row: (row[0], row[1]))[2]


def fight(engine, state):
    controls = 0
    damaged = False
    while state.get("battle"):
        engine.handle(state, "battle", command_for(state))
        damaged |= any(event.get("kind") == "damage" and event.get("attacker_side") == "player"
                       for event in state["events"])
        controls += 1
        assert controls < 1000, "Ordinary World DS wild combat must resolve"
    assert controls > 0 and damaged, "The player must issue real fight controls"
    return controls


def test_original_dawn_encounter_assignments_and_tamer_roster_remain_exact():
    engine = GameEngine(ROOT, seed=431)
    legacy = {key: pool for key, pool in engine._pools.items() if key.startswith("map_")}
    assert len(legacy) == 254
    signature = hashlib.sha256(json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert signature == LEGACY_POOL_SHA256, "Adding World DS must not reshuffle old wild species"
    assert len(engine.tamers) == 64, "The supplied new character archive is intentionally not imported"
    assert min(area["level"] for area in ds_maps(engine)) == 1
    assert max(area["level"] for area in ds_maps(engine)) == 99


def test_every_world_ds_map_supports_distributed_safe_spawns_and_real_patrols():
    engine = GameEngine(ROOT, seed=117)
    navigation = Navigation(ROOT, engine.maps)
    rng = random.Random(3017)
    for area in ds_maps(engine):
        mid = area["id"]
        points = [navigation.spawn(mid, index) for index in range(20)]
        assert len(set(points)) > 1, f"{mid}: tamers cannot all be stranded at one point"
        assert all(navigation.walkable(mid, *point) for point in points), mid
        route = navigation.patrol(mid, *points[3], rng, 100.0, seconds=12)
        assert route and route["loop"], f"{mid}: no continuous, safe rival patrol"
        for segment in route["segments"]:
            assert math.dist(navigation.trace(mid, segment["from"], segment["to"]), segment["to"]) < .001, mid
        duration = route["end"] - route["start"]
        previous = navigation.sample(route, 100.0)
        for index in range(1, 161):
            now = 100.0 + duration * 2 * index / 160
            sample = navigation.sample(route, now)
            assert navigation.walkable(mid, *sample[:2]), (mid, sample)
            assert math.dist(previous[:2], sample[:2]) <= Navigation.SPEED * duration / 80 + .001, mid
            previous = sample


def test_every_world_ds_map_starts_normal_level_bounded_wild_battles():
    engine = GameEngine(ROOT, seed=391)
    state = engine.new_player("DSFieldSurvey", next(iter(engine.tamers)), "agumon")
    # An established owned partner allows surveying endgame maps without
    # fabricating a battle result or altering the generated opponents.
    state["party"] = [engine._monster("omnimon", level=99, cam=80) for _ in range(3)]
    for area in ds_maps(engine):
        engine.handle(state, "travel", {"map_id": area["id"]})
        engine.handle(state, "encounter", {})
        battle = state["battle"]
        assert battle and battle.get("kind") not in ("story", "season"), area["id"]
        assert 1 <= len(battle["enemies"]) <= 3
        permitted = set().union(*map(set, engine._pools[area["id"]]))
        for enemy in battle["enemies"]:
            assert enemy["species_id"] in permitted
            assert area["level_min"] <= enemy["level"] <= area["level_max"]
        engine.handle(state, "battle", {"action": "flee"})
        engine.handle(state, "digilab", {"action": "enter"})
        engine.handle(state, "digilab", {"action": "return"})


def test_fresh_owned_rookie_earns_scan_and_materializes_without_a_separate_party():
    engine = GameEngine(ROOT, seed=7709)
    state = engine.new_player("DSRookie", next(iter(engine.tamers)), "agumon")
    original_uid = state["party"][0]["uid"]
    area = ds_maps(engine)[0]
    engine.handle(state, "travel", {"map_id": area["id"]})
    controls = 0
    for _ in range(150):
        engine.handle(state, "encounter", {})
        controls += fight(engine, state)
        engine.handle(state, "digilab", {"action": "enter"})
        capturable = next((sid for sid, total in state["scan"].items() if total >= 100), None)
        if capturable:
            before_scan = state["scan"][capturable]
            engine.handle(state, "materialize", {"species_id": capturable})
            assert state["scan"][capturable] == 0
            assert before_scan >= 100
            assert state["party"][1]["species_id"] == capturable
            assert state["party"][1]["level"] == 1
            break
        engine.handle(state, "digilab", {"action": "return"})
    else:
        pytest.fail("A fresh player could not earn a World DS recruit within 150 normal encounters")
    assert controls and state["wins"] >= 5
    assert state["party"][0]["uid"] == original_uid
    assert state["party"][0]["level"] > 1
    assert state["credits"] > 650
    engine.handle(state, "digilab", {"action": "return"})
    assert state["map_id"] == area["id"]
    assert not state.get("story") and not state.get("season")


def test_world_ds_location_roundtrips_through_hubs_and_both_private_modes():
    engine = GameEngine(ROOT, seed=628)
    state = engine.new_player("DSReturn", next(iter(engine.tamers)), "agumon")
    area = ds_maps(engine)[len(ds_maps(engine)) // 2]
    engine.handle(state, "travel", {"map_id": area["id"]})
    navigation = Navigation(ROOT, engine.maps)
    state["x"], state["y"] = navigation.spawn(area["id"], 7)
    location = {key: state[key] for key in ("map_id", "x", "y")}
    possessions = copy.deepcopy({key: state[key] for key in ("party", "storage", "inventory", "credits", "scan")})
    for mode in ("digilab", "digifarm", "story", "season"):
        engine.handle(state, mode, {"action": "enter"})
        engine.handle(state, mode, {"action": "return"})
        assert {key: state[key] for key in location} == location, mode
        assert {key: state[key] for key in possessions} == possessions, mode
    story = copy.deepcopy(state["story"])
    season = copy.deepcopy(state["season"])
    old_area = next(key for key in engine.maps if key.startswith("map_"))
    engine.handle(state, "travel", {"map_id": old_area})
    assert state["map_id"] == old_area
    engine.handle(state, "travel", {"map_id": area["id"]})
    assert state["story"] == story and state["season"] == season
    restored = json.loads(json.dumps(state))
    GameEngine(ROOT, seed=1023)._refresh(restored)
    assert restored == state


def test_existing_3000_saved_rivals_expand_into_world_ds_without_identity_or_career_reset(tmp_path):
    database = Database({"driver": "sqlite", "path": str(tmp_path / "rival_upgrade.sqlite3")}, dev=True)
    try:
        database.initialize()
        store = CommunityStore(database)
        store.initialize()
        old_engine = GameEngine(ROOT, seed=915)
        old_engine.maps = {mid: area for mid, area in old_engine.maps.items() if mid.startswith("map_")}
        old = BotManager(old_engine, store, config={"count": 3000, "seed": 445, "min_dwell": 30, "max_dwell": 60})
        old.initialize(now=100.0)
        # Explicit mature-save fixture: existing owned veterans can visit every
        # difficulty. No levels are granted by startup, migration or travel.
        for bot in old.bots.values():
            monster = bot["state"]["party"][0]
            monster.update(level=99, abi=65, cam=90)
            stats = old_engine.stats_for(old_engine.species[monster["species_id"]], 99, 65)
            monster.update(**stats, max_hp=stats["hp"], max_sp=stats["sp"])
            old_engine._refresh(bot["state"])
            old.dirty.add(bot["id"])
        old.flush(force=True, now=100.0)
        before = {row["id"]: row for row in store.bot_load_all()}
        assert len(before) == 3000

        upgraded = BotManager(GameEngine(ROOT, seed=915), store,
                              config={"count": 3000, "seed": 445, "min_dwell": 30, "max_dwell": 60})
        upgraded.initialize(now=1000.0)
        new_ids = {area["id"] for area in ds_maps(upgraded.engine)}
        assert set(upgraded.bots) == set(before)
        assert all(not upgraded.by_map[mid] for mid in new_ids), "Existing rivals must not teleport during startup"
        for ident, bot in upgraded.bots.items():
            assert bot["state"] == before[ident]["state"], ident
            assert bot["stats"] == before[ident]["stats"], ident

        # Dispatch the ordinary exploration phase after the real saved dwell
        # interval. It executes canonical travel and then a collision-safe walk.
        for bot in upgraded.bots.values():
            upgraded._explore(bot, now=1100.0)
        assert all(upgraded.by_map[mid] for mid in upgraded.engine.maps), "The same population must cover both regions"
        assert sum(map(len, upgraded.by_map.values())) == 3000
        assert set().union(*upgraded.by_map.values()) == set(before)
        for ident, bot in upgraded.bots.items():
            for key in ("party", "storage", "inventory", "credits", "scan", "wins", "losses"):
                assert bot["state"][key] == before[ident]["state"][key], (ident, key)
            state = bot["state"]
            assert upgraded.navigation.walkable(state["map_id"], state["x"], state["y"])
            assert bot["runtime"]["path"], ident
            assert bot["stats"]["travels"] == before[ident]["stats"]["travels"] + 1
        upgraded.flush(force=True, now=1100.0)
        migrated = {row["id"]: row for row in store.bot_load_all()}
        restored = BotManager(GameEngine(ROOT, seed=916), store,
                              config={"count": 3000, "seed": 445, "min_dwell": 30, "max_dwell": 60})
        restored.initialize(now=9000.0)
        assert set(restored.bots) == set(before)
        for ident, bot in restored.bots.items():
            assert bot["state"] == migrated[ident]["state"], ident
            assert bot["stats"] == migrated[ident]["stats"], ident
            assert bot["runtime"]["route_after_map"] == migrated[ident]["runtime"]["route_after_map"]
        assert all(restored.by_map[mid] for mid in restored.engine.maps)
    finally:
        database.close()


class WorldDSProtocolAcceptance(unittest.IsolatedAsyncioTestCase):
    """Actual SQLite restart and WebSocket play, including shared-map presence."""

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.directory.name) / "world_ds.sqlite3")
        self.rid = 0
        await self.start_server()

    async def start_server(self):
        self.db = Database({"driver": "sqlite", "path": self.database_path}, dev=True)
        self.db.initialize()
        self.engine = GameEngine(ROOT, seed=1859)
        self.world = WorldServer(self.engine, self.db, {
            "allow_registration": True, "rivals": {"enabled": False, "count": 0}})
        self.listener = await serve(self.world.connection, "127.0.0.1", 0, max_size=65536)
        self.url = f"ws://127.0.0.1:{self.listener.sockets[0].getsockname()[1]}"

    async def stop_server(self):
        self.listener.close()
        await self.listener.wait_closed()
        if self.world.community:
            await asyncio.to_thread(self.world.community.shutdown)
        self.db.close()

    async def asyncTearDown(self):
        await self.stop_server()
        self.directory.cleanup()

    async def receive(self, ws, op, rid=None):
        while True:
            packet = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if packet.get("op") == op and (rid is None or packet.get("rid") == rid):
                return packet

    async def action(self, ws, op, **fields):
        if op in GAME_OPS:
            await asyncio.sleep(.175)
        self.rid += 1
        await ws.send(json.dumps({"op": op, "rid": self.rid, **fields}))
        packet = await self.receive(ws, "result", self.rid)
        self.assertTrue(packet["ok"], packet)
        return packet.get("state")

    async def register(self, ws, username):
        await self.receive(ws, "hello")
        return await self.action(ws, "register", username=username,
                                 password="World-DS-acceptance-73", tamer=next(iter(self.engine.tamers)),
                                 starter="agumon")

    async def test_shared_region_live_fight_and_exact_battle_restore_after_server_restart(self):
        async with connect(self.url, max_size=8 * 1024 * 1024) as alice, connect(self.url, max_size=8 * 1024 * 1024) as bob:
            await self.register(alice, "DSAlice")
            await self.register(bob, "DSBob")
            area = ds_maps(self.engine)[0]
            state = await self.action(alice, "travel", map_id=area["id"])
            await self.action(bob, "travel", map_id=area["id"])
            await self.world.broadcast_once()
            snapshot = await self.receive(alice, "world")
            self.assertEqual({"DSAlice", "DSBob"}, {row["username"] for row in snapshot["players"]})
            self.assertTrue(all(row["map_id"] == area["id"] for row in snapshot["players"]))
            state = await self.action(alice, "encounter")
            self.assertTrue(state["battle"])
            self.assertNotIn(state["battle"].get("kind"), ("story", "season"))
            saved_battle = copy.deepcopy(state["battle"])
            saved_party = copy.deepcopy(state["party"])
            saved_wallet = copy.deepcopy({key: state[key] for key in ("scan", "credits", "inventory")})
        await self.stop_server()
        await self.start_server()
        async with connect(self.url, max_size=8 * 1024 * 1024) as alice:
            await self.receive(alice, "hello")
            state = await self.action(alice, "login", username="DSAlice", password="World-DS-acceptance-73")
            self.assertEqual(area["id"], state["map_id"])
            self.assertEqual(saved_battle, state["battle"])
            self.assertEqual(saved_party, state["party"])
            self.assertEqual(saved_wallet, {key: state[key] for key in saved_wallet})
            controls = 0
            while state.get("battle"):
                state = await self.action(alice, "battle", **command_for(state))
                controls += 1
                self.assertLess(controls, 100)
            self.assertGreater(controls, 0)
            self.assertGreater(state["wins"] + state["losses"], 0)
            if state["wins"]:
                self.assertTrue(state["scan"])
                self.assertGreater(state["credits"], saved_wallet["credits"])
            await self.action(alice, "digilab", action="enter")
            state = await self.action(alice, "digilab", action="return")
            self.assertEqual(area["id"], state["map_id"])
            state = await self.action(alice, "digifarm", action="enter")
            state = await self.action(alice, "digifarm", action="return")
            self.assertEqual(area["id"], state["map_id"])
            saved, _revision = self.db.load("dsalice")
            self.assertEqual(state, saved)
