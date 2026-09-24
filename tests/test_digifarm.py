"""Private home, permanent treats and cap migration use authoritative gameplay."""
import asyncio
import copy
import json

import pytest

from venom.common.game import (FARM_CAPACITY, FARM_STATS, GameEngine, GameError, SHOP,
                               xp_required)
from venom.server.database import Database
from venom.server.main import Session, WorldServer


@pytest.fixture
def farm(tmp_path):
    species = [
        {"id": "rookie", "name": "Rookie", "stage": "rookie", "type": "free", "attribute": "neutral",
         "evolutions": [{"to": "champion", "level": 2, "cam": 0, "abi": 0}]},
        {"id": "champion", "name": "Champion", "stage": "champion", "type": "free", "attribute": "neutral"},
    ]
    (tmp_path / "catalog.json").write_text(json.dumps({"species": species,
        "maps": [{"id": "field", "name": "Field", "level": 1, "width": 600, "height": 400,
                  "spawn": [100, 100]}, {"id": "other", "name": "Other", "level": 2,
                  "width": 600, "height": 400, "spawn": [200, 200]}],
        "tamers": [{"id": "tamer", "name": "Tamer"}]}))
    engine = GameEngine(tmp_path, seed=12)
    state = engine.new_player("Farmer", "tamer", "rookie")
    state["storage"].append(engine._monster("rookie", cam=20))
    engine._refresh(state)
    return engine, state


def feed(engine, state, item, quantity=1, uid=None):
    return engine.handle(state, "digifarm", {"action": "feed", "item": item,
        "quantity": quantity, "uid": uid or state["storage"][0]["uid"]})


def test_new_player_home_has_optional_starter_treats_and_blocks_encounters(farm):
    engine, state = farm
    assert state["in_farm"] and not state["in_lab"]
    assert state["farm"]["capacity"] == 100
    assert state["farm"]["feeding_optional"]
    assert state["inventory"]["digimeat_cam"] == 3
    with pytest.raises(GameError, match="Return to the world"):
        engine.handle(state, "encounter", {})
    engine.handle(state, "digifarm", {"action": "return"})
    engine.handle(state, "encounter", {})
    assert state["battle"]


def test_world_lab_home_roundtrip_preserves_location_and_direct_travel(farm):
    engine, state = farm
    engine.handle(state, "digifarm", {"action": "return"})
    state.update(x=123.25, y=199.75)
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "digifarm", {"action": "enter"})
    assert state["in_farm"] and not state["in_lab"]
    engine.handle(state, "digilab", {"action": "enter"})
    engine.handle(state, "digilab", {"action": "return"})
    assert (state["map_id"], state["x"], state["y"]) == ("field", 123.25, 199.75)
    engine.handle(state, "digifarm", {"action": "enter"})
    engine.handle(state, "travel", {"map_id": "other"})
    assert not state["in_farm"]
    assert (state["map_id"], state["x"], state["y"]) == ("other", 200, 200)


def test_home_battle_exit_requires_explicit_forfeit_and_never_gives_loot(farm):
    engine, state = farm
    engine.handle(state, "digifarm", {"action": "return"})
    engine.handle(state, "encounter", {})
    original = copy.deepcopy(state)
    for invalid in (None, False, 1, "true"):
        with pytest.raises(GameError, match="Confirm"):
            engine.handle(state, "digifarm", {"action": "enter", "forfeit": invalid})
        assert state["battle"] == original["battle"]
    engine.handle(state, "digifarm", {"action": "enter", "forfeit": True})
    assert state["in_farm"] and not state["battle"]
    assert state["credits"] == original["credits"]
    assert state["inventory"] == original["inventory"]
    assert state["wins"] == original["wins"]
    assert not any(e["kind"] in ("win", "loot") for e in state["events"])


def test_home_forfeit_clears_guard_for_all_partners_before_next_battle(farm):
    engine, state = farm
    state["party"] += [engine._monster("rookie") for _ in range(3)]
    engine.handle(state, "digifarm", {"action": "return"})
    engine.handle(state, "encounter", {})
    for monster in state["party"]:
        monster["guard"] = True
    engine.handle(state, "digifarm", {"action": "enter", "forfeit": True})
    assert all("guard" not in monster for monster in state["party"])
    engine.handle(state, "digifarm", {"action": "return"})
    engine.handle(state, "encounter", {})
    assert state["battle"]
    assert all("guard" not in monster for monster in state["party"])


@pytest.mark.parametrize("quantity", [True, False, 0, -1, 100, 1.5, "1", None])
def test_feeding_rejects_invalid_quantity_without_consuming(farm, quantity):
    engine, state = farm
    original = copy.deepcopy(state)
    with pytest.raises(GameError):
        feed(engine, state, "digimeat_cam", quantity)
    assert state["storage"] == original["storage"]
    assert state["inventory"] == original["inventory"]


def test_feeding_uses_owned_resident_uid_and_cannot_feed_party_or_capsules(farm):
    engine, state = farm
    for uid in (state["party"][0]["uid"], "another-players-monster", 2, True):
        with pytest.raises(GameError):
            feed(engine, state, "digimeat_cam", uid=uid)
    with pytest.raises(GameError):
        feed(engine, state, "hp_s")
    with pytest.raises(GameError):
        engine.handle(state, "item", {"item": "digimeat_cam", "party_index": 0})
    assert state["inventory"]["digimeat_cam"] == 3
    resident = state["storage"][0]
    state["storage"].insert(0, engine._monster("rookie"))
    feed(engine, state, "digimeat_cam", uid=resident["uid"])
    assert resident["cam"] == 25
    assert state["storage"][0]["cam"] == 0
    engine.handle(state, "digifarm", {"action": "return"})
    with pytest.raises(GameError, match="DigiFarm"):
        feed(engine, state, "digimeat_cam", uid=resident["uid"])


def test_cam_clamps_final_treat_but_rejects_wasted_quantities(farm):
    engine, state = farm
    state["storage"][0]["cam"] = 98
    with pytest.raises(GameError, match="waste"):
        feed(engine, state, "digimeat_cam", 2)
    assert state["inventory"]["digimeat_cam"] == 3
    feed(engine, state, "digimeat_cam")
    assert state["storage"][0]["cam"] == 100
    assert state["inventory"]["digimeat_cam"] == 2
    with pytest.raises(GameError, match="already"):
        feed(engine, state, "digimeat_cam")
    assert state["inventory"]["digimeat_cam"] == 2


@pytest.mark.parametrize("stat", FARM_STATS)
def test_each_stat_increases_permanently_and_survives_level_evolution_and_devolution(farm, stat):
    engine, state = farm
    resident = state["storage"][0]
    item = f"digimeat_{stat}_5"
    state["inventory"][item] = 1
    before = resident.get("max_" + stat, resident[stat])
    feed(engine, state, item)
    assert resident.get("max_" + stat, resident[stat]) == before + 5
    assert resident["farm_bonuses"] == {stat: 5}
    engine.handle(state, "party", {"action": "withdraw", "index": 0})
    engine._add_xp(state, resident, xp_required(1), 1)
    expected = engine.stats_for(engine.species["rookie"], resident["level"], resident["abi"])[stat] + 5
    assert resident.get("max_" + stat, resident[stat]) == expected
    uid = resident["uid"]
    engine.handle(state, "evolve", {"party_index": 1, "to": "champion"})
    evolved = state["party"][1]
    assert evolved["farm_bonuses"] == {stat: 5} and evolved["uid"] == uid
    expected = engine.stats_for(engine.species["champion"], 1, evolved["abi"])[stat] + 5
    assert evolved.get("max_" + stat, evolved[stat]) == expected
    evolved["level"] = 5
    engine.handle(state, "evolve", {"party_index": 1, "to": "rookie"})
    assert state["party"][1]["farm_bonuses"] == {stat: 5}
    assert state["party"][1]["uid"] == uid


def test_stat_caps_are_atomic_and_defeated_resident_is_not_revived_by_food(farm):
    engine, state = farm
    monster = state["storage"][0]
    state["inventory"].update(digimeat_atk_5=5, digimeat_hp_1=1)
    monster["farm_bonuses"] = {"atk": 98}
    with pytest.raises(GameError, match="per stat"):
        feed(engine, state, "digimeat_atk_5")
    monster["farm_bonuses"] = {"hp": 100, "sp": 100, "spd": 98}
    with pytest.raises(GameError, match="total"):
        feed(engine, state, "digimeat_atk_5")
    assert state["inventory"]["digimeat_atk_5"] == 5
    monster["farm_bonuses"] = {}
    monster["hp"] = 0
    hp = monster["max_hp"]
    feed(engine, state, "digimeat_hp_1")
    assert monster["hp"] == 0 and monster["max_hp"] == hp + 1


def test_farm_cap_blocks_deposit_and_materialization_without_losing_scan(farm):
    engine, state = farm
    state["storage"] = [engine._monster("rookie") for _ in range(FARM_CAPACITY)]
    state["party"] += [engine._monster("rookie") for _ in range(5)]
    state["scan"]["rookie"] = 200
    with pytest.raises(GameError, match="full"):
        engine.handle(state, "party", {"action": "deposit", "index": 1})
    with pytest.raises(GameError, match="full"):
        engine.handle(state, "materialize", {"species_id": "rookie"})
    assert state["scan"]["rookie"] == 200
    assert len(state["party"]) == 6 and len(state["storage"]) == 100


def test_legacy_overflow_is_preserved_and_withdrawable_without_forcing_relocation(farm):
    engine, state = farm
    state.pop("in_farm")
    state["storage"] = [engine._monster("rookie") for _ in range(103)]
    state["storage"][0].pop("farm_bonuses")
    state["storage"][0].pop("uid")
    engine._refresh(state)
    assert not state["in_farm"]
    assert len(state["storage"]) == 103 and state["farm"]["legacy_overflow"] == 3
    assert state["storage"][0]["uid"] and state["storage"][0]["farm_bonuses"] == {}
    engine.handle(state, "digifarm", {"action": "enter"})
    overflow = state["storage"][102]
    with pytest.raises(GameError, match="not a resident"):
        feed(engine, state, "digimeat_cam", uid=overflow["uid"])
    engine.handle(state, "party", {"action": "withdraw", "index": 102})
    assert state["party"][-1]["uid"] == overflow["uid"]
    assert state["farm"]["legacy_overflow"] == 2


@pytest.mark.parametrize("storage_count", [100, 106])
def test_full_party_can_exchange_full_farm_and_legacy_overflow_without_data_loss(farm, storage_count):
    engine, state = farm
    state["party"] += [engine._monster("rookie") for _ in range(5)]
    state["storage"] = [engine._monster("rookie") for _ in range(storage_count)]
    all_uids = {m["uid"] for m in state["party"] + state["storage"]}
    incoming = state["storage"][-1]
    incoming.update(hp=1, sp=0, farm_bonuses={"atk": 5})
    outgoing = state["party"][2]
    engine.handle(state, "party", {"action": "exchange", "party_index": 2, "uid": incoming["uid"]})
    assert state["party"][2] is incoming and state["storage"][-1] is outgoing
    assert incoming["hp"] == incoming["max_hp"] and incoming["farm_bonuses"] == {"atk": 5}
    assert (len(state["party"]), len(state["storage"])) == (6, storage_count)
    assert all_uids == {m["uid"] for m in state["party"] + state["storage"]}
    before = copy.deepcopy(state)
    for slot, uid in ((True, incoming["uid"]), (6, outgoing["uid"]), (0, "foreign-uid")):
        with pytest.raises(GameError):
            engine.handle(state, "party", {"action": "exchange", "party_index": slot, "uid": uid})
        assert before["party"] == state["party"] and before["storage"] == state["storage"]


def test_shop_all_meats_allowed_at_home_and_inventory_cap_is_atomic(farm):
    engine, state = farm
    state["credits"] = 1_000_000
    meats = {key: value for key, value in SHOP.items() if value.get("category") == "digimeat"}
    assert len(meats) == 13
    for key, item in meats.items():
        before = state["inventory"].get(key, 0)
        credits = state["credits"]
        engine.handle(state, "shop", {"item": key, "quantity": 2})
        assert state["inventory"][key] == before + 2
        assert state["credits"] == credits - item["price"] * 2
    state["inventory"]["digimeat_cam"] = 999
    credits = state["credits"]
    with pytest.raises(GameError, match="999"):
        engine.handle(state, "shop", {"item": "digimeat_cam", "quantity": 1})
    assert state["credits"] == credits


def test_pve_reward_can_drop_once_and_respects_inventory_limit(farm, monkeypatch):
    engine, state = farm
    engine.handle(state, "digifarm", {"action": "return"})
    engine.handle(state, "encounter", {})
    for enemy in state["battle"]["enemies"]:
        enemy["hp"] = 0
    monkeypatch.setattr(engine.rng, "random", lambda: 0)
    before = state["inventory"]["digimeat_cam"]
    engine._check_end(state)
    engine._check_end(state)
    assert state["inventory"]["digimeat_cam"] == before + 1
    assert len([e for e in state["events"] if e["kind"] == "loot"]) == 1
    engine.handle(state, "encounter", {})
    for enemy in state["battle"]["enemies"]:
        enemy["hp"] = 0
    state["inventory"]["digimeat_cam"] = 999
    engine._check_end(state)
    assert state["inventory"]["digimeat_cam"] == 999


def test_food_bonus_and_home_survive_database_restart(farm, tmp_path):
    engine, state = farm
    state["inventory"]["digimeat_atk_5"] = 1
    feed(engine, state, "digimeat_atk_5")
    config = {"driver": "sqlite", "path": str(tmp_path / "farm.sqlite3")}
    db = Database(config, dev=True)
    db.initialize()
    db.register("Farmer", "correct-horse", state)
    db.close()
    reopened = Database(config, dev=True)
    try:
        restored, _ = reopened.load("farmer")
        engine._refresh(restored)
        assert restored["in_farm"]
        assert restored["storage"] == state["storage"]
        assert restored["inventory"] == state["inventory"]
    finally:
        reopened.close()


class Socket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(json.loads(message))


def test_world_snapshots_and_local_chat_are_private_per_farm_and_field_location_is_unchanged(farm):
    engine, state = farm
    world = WorldServer(engine, None, {})
    a = Session(Socket(), "alice", "a", copy.deepcopy(state), 0)
    b = Session(Socket(), "bob", "b", copy.deepcopy(state), 0)
    c = Session(Socket(), "charlie", "c", copy.deepcopy(state), 0)
    a.state["username"], b.state["username"], c.state["username"] = "Alice", "Bob", "Charlie"
    c.state["in_farm"] = False
    world.sessions = {s.key: s for s in (a, b, c)}
    assert not world.same_place(a, b) and not world.same_place(a, c)
    before = (a.state["x"], a.state["y"])
    farm_x = a.state["farm_position"]["x"]
    a.walked = a.next_encounter
    world.move(a, {"dx": 1, "dy": 0, "dt": .1})
    assert (a.state["x"], a.state["y"]) == before and not a.state["battle"]
    assert a.state["farm_position"]["x"] > farm_x
    asyncio.run(world.broadcast_once())
    for session in (a, b, c):
        assert [p["username"] for p in session.websocket.messages[-1]["players"]] == [session.state["username"]]
    asyncio.run(world.chat(a, {"text": "At home"}))
    assert a.websocket.messages[-1]["op"] == "chat"
    assert b.websocket.messages[-1]["op"] == "world"
    assert c.websocket.messages[-1]["op"] == "world"


def test_live_farm_protocol_rejects_cross_account_feeding_and_commits_bonus(farm, tmp_path):
    """Use the real wire handler and database, including transactional rejection."""
    from websockets.asyncio.client import connect
    from websockets.asyncio.server import serve

    engine, _ = farm
    db = Database({"driver": "sqlite", "path": str(tmp_path / "wire.sqlite3")}, dev=True)
    db.initialize()
    world = WorldServer(engine, db, {"allow_registration": True})

    async def scenario():
        async with serve(world.connection, "127.0.0.1", 0) as listener:
            address = f"ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}"
            async with connect(address) as alice, connect(address) as bob:
                assert "digifarm" in json.loads(await alice.recv())["features"]
                await bob.recv()

                async def request(ws, op, **payload):
                    await ws.send(json.dumps({"op": op, "rid": 1, **payload}))
                    return json.loads(await ws.recv())

                for socket, username in ((alice, "Alice"), (bob, "Bob")):
                    registered = await request(socket, "register", username=username,
                        password="correct-horse", tamer="tamer", starter="rookie")
                    assert registered["ok"] and registered["state"]["in_farm"]
                alice_session = world.sessions["alice"]
                resident = engine._monster("rookie")
                alice_session.state["storage"].append(resident)
                alice_session.state["inventory"]["digimeat_atk_5"] = 1
                engine._refresh(alice_session.state)
                await world.save(alice_session)
                bob_before = copy.deepcopy(world.sessions["bob"].state)
                rejected = await request(bob, "digifarm", action="feed",
                    uid=resident["uid"], item="digimeat_cam", quantity=1)
                assert not rejected["ok"]
                assert world.sessions["bob"].state == bob_before
                fed = await request(alice, "digifarm", action="feed", uid=resident["uid"],
                    item="digimeat_atk_5", quantity=1)
                assert fed["ok"] and fed["state"]["storage"][0]["farm_bonuses"] == {"atk": 5}
                persisted, _ = db.load("alice")
                assert persisted["storage"][0] == fed["state"]["storage"][0]
                before_invalid = copy.deepcopy(world.sessions["alice"].state)
                invalid = await request(alice, "digifarm", action="feed", uid=resident["uid"],
                    item="digimeat_cam", quantity=True)
                assert not invalid["ok"]
                assert world.sessions["alice"].state == before_invalid

    try:
        asyncio.run(scenario())
    finally:
        db.close()
