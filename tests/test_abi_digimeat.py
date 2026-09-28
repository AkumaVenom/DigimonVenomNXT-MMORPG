"""ABI food removes the no-devolution dead end without changing evolution rules."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from venom.common.game import GameEngine, GameError, SHOP, xp_required
from venom.server.database import Database


ROOT = Path(__file__).resolve().parents[1]
ITEM = "digimeat_abi"


@pytest.fixture(scope="module")
def engine():
    return GameEngine(ROOT, seed=771)


@pytest.fixture
def state(engine):
    result = engine.new_player("AbiTamer", next(iter(engine.tamers)), "agumon")
    result["party"] = [engine._monster("fanglongmon_paradox", 60, cam=40)]
    result["storage"] = [engine._monster("fanglongmon", 60, cam=40)]
    result["inventory"][ITEM] = 99
    engine._refresh(result)
    return result


def feed(engine, state, location="party", **extra):
    if location == "storage":
        return engine.handle(state, "digifarm", {
            "action": "feed", "uid": state["storage"][0]["uid"], "item": ITEM, **extra})
    return engine.handle(state, "item", {
        "party_index": 0, "uid": state["party"][0]["uid"], "item": ITEM, **extra})


def progress(state):
    # A rejected request clears presentation events; no saved progress may change.
    return {key: copy.deepcopy(value) for key, value in state.items() if key != "events"}


def test_real_no_devolution_partner_can_buy_abi_and_unlock_existing_route(engine, state):
    monster = state["party"][0]
    assert monster["species_id"] == "fanglongmon_paradox"
    assert engine.devolutions.get(monster["species_id"], []) == []
    route = next(r for r in engine.evolution_options(monster) if r["to"] == "examon_paradox")
    assert route["missing"] == ["ABI 50"]
    state["inventory"].pop(ITEM)
    state["credits"] = 300_000
    engine.handle(state, "shop", {"item": ITEM, "quantity": 50, "currency": "credits",
                                  "price": 0, "amount": 200})
    assert state["credits"] == 0
    assert state["inventory"][ITEM] == 50
    feed(engine, state, quantity=49)
    assert not next(r for r in state["evolution_options"][0] if r["to"] == "examon_paradox")["eligible"]
    feed(engine, state)  # Defaults to one, including for callers without quantity.
    assert state["inventory"][ITEM] == 0
    assert monster["abi"] == 50
    assert next(r for r in state["evolution_options"][0] if r["to"] == "examon_paradox")["eligible"]
    uid = monster["uid"]
    engine.handle(state, "evolve", {"party_index": 0, "to": "examon_paradox"})
    assert state["party"][0]["uid"] == uid
    assert state["party"][0]["species_id"] == "examon_paradox"
    assert state["party"][0]["abi"] == 58


@pytest.mark.parametrize("location", ["party", "storage"])
@pytest.mark.parametrize("defeated", [False, True])
def test_abi_is_separate_from_full_farm_pool_and_refreshes_stats_without_healing_or_resets(engine, state, location, defeated):
    monster = engine._monster("fanglongmon_paradox", 60, abi=149, cam=75,
                              farm_bonuses={"hp": 100, "atk": 100, "spd": 100})
    monster.update(xp=1234, history=["agumon_paradox", "greymon_paradox"])
    monster["hp"] = 0 if defeated else monster["max_hp"] - 57
    monster["sp"] -= 13
    state[location][0] = monster
    before = copy.deepcopy(monster)
    feed(engine, state, location, quantity=7, amount=999, resource="cam", abi=200)
    assert monster["abi"] == 156
    for key in ("uid", "species_id", "name", "level", "xp", "next_xp", "cam", "history", "farm_bonuses"):
        assert monster[key] == before[key]
    expected = engine.stats_for(engine.species[monster["species_id"]], 60, 156, before["farm_bonuses"])
    for stat in ("atk", "def", "int", "spd"):
        assert monster[stat] == expected[stat]
    assert monster["max_hp"] == expected["hp"] and monster["max_sp"] == expected["sp"]
    assert monster["hp"] == (0 if defeated else monster["max_hp"] - 57)
    assert monster["sp"] == monster["max_sp"] - 13
    assert state["inventory"][ITEM] == 92
    event = state["events"][0]
    assert (event["kind"], event["resource"], event["amount"], event["quantity"], event["uid"]) == (
        "feed", "abi", 7, 7, monster["uid"])


@pytest.mark.parametrize("location", ["party", "storage"])
def test_cap_rejects_whole_batch_and_never_consumes_at_200(engine, state, location):
    monster = state[location][0]
    monster["abi"] = 199
    before = progress(state)
    with pytest.raises(GameError, match="waste"):
        feed(engine, state, location, quantity=2)
    assert progress(state) == before
    feed(engine, state, location)
    assert monster["abi"] == 200
    assert state["inventory"][ITEM] == 98
    before = progress(state)
    with pytest.raises(GameError, match="already has 200 ABI"):
        feed(engine, state, location)
    assert progress(state) == before


@pytest.mark.parametrize("location", ["party", "storage"])
@pytest.mark.parametrize("quantity", [True, False, 0, -1, 100, 1.5, "1", None])
def test_invalid_quantities_do_not_consume_or_mutate(engine, state, location, quantity):
    before = progress(state)
    with pytest.raises(GameError):
        feed(engine, state, location, quantity=quantity)
    assert progress(state) == before


@pytest.mark.parametrize("location", ["party", "storage"])
def test_missing_inventory_and_insufficient_quantity_are_atomic(engine, state, location):
    for owned, quantity in ((None, 1), (0, 1), (1, 2)):
        if owned is None:
            state["inventory"].pop(ITEM, None)
        else:
            state["inventory"][ITEM] = owned
        before = progress(state)
        with pytest.raises(GameError, match="enough"):
            feed(engine, state, location, quantity=quantity)
        assert progress(state) == before


def test_party_use_supports_only_partner_at_both_hubs_and_optional_uid(engine, state):
    assert len(state["party"]) == 1  # No deposit or second party member needed.
    engine.handle(state, "item", {"item": ITEM, "party_index": 0})
    assert state["party"][0]["abi"] == 1
    engine.handle(state, "digilab", {"action": "enter"})
    feed(engine, state)
    assert state["party"][0]["abi"] == 2
    assert state["inventory"][ITEM] == 97
    state["inventory"]["digimeat_atk_1"] = 1
    for item in ("digimeat_cam", "digimeat_atk_1"):
        before = progress(state)
        with pytest.raises(GameError, match="capsule"):
            engine.handle(state, "item", {"item": item, "party_index": 0})
        assert progress(state) == before


@pytest.mark.parametrize("location", ["party", "storage"])
def test_field_battle_and_season_reject_feeding_without_consumption(engine, state, location):
    state.update(in_farm=False, in_lab=False)
    before = progress(state)
    with pytest.raises(GameError, match="DigiFarm"):
        feed(engine, state, location)
    assert progress(state) == before
    state.update(in_farm=True, battle={"id": "still-in-battle"})
    before = progress(state)
    with pytest.raises(GameError, match="current battle"):
        feed(engine, state, location)
    assert progress(state) == before
    state.update(battle=None, in_season=True)
    before = progress(state)
    with pytest.raises(GameError, match="Save & Return"):
        feed(engine, state, location)
    assert progress(state) == before


def test_battle_capsule_path_cannot_bypass_abi_location_restrictions(engine, state):
    before = progress(state)
    with pytest.raises(GameError, match="capsule"):
        engine._use_item(state, {"item": ITEM, "party_index": 0})
    assert progress(state) == before


@pytest.mark.parametrize("payload", [
    {"uid": "foreign-monster"}, {"uid": None}, {"uid": True},
    {"party_index": True}, {"party_index": -1}, {"party_index": 1},
    {"item": "abi"}, {"item": {}}, {"item": []},
])
def test_stale_or_malformed_party_selection_rejects_atomically(engine, state, payload):
    before = progress(state)
    with pytest.raises(GameError):
        feed(engine, state, **payload)
    assert progress(state) == before


def test_party_reorder_does_not_feed_different_partner(engine, state):
    expected_uid = state["party"][0]["uid"]
    state["party"].insert(0, engine._monster("agumon"))
    before = progress(state)
    with pytest.raises(GameError, match="selection has changed"):
        feed(engine, state, uid=expected_uid)
    assert progress(state) == before


def test_credit_overspend_and_full_inventory_do_not_charge_player(engine, state):
    for credits, owned in ((5999, 0), (1_000_000, 999)):
        state["credits"] = credits
        state["inventory"][ITEM] = owned
        before = progress(state)
        with pytest.raises(GameError):
            engine.handle(state, "shop", {"item": ITEM, "quantity": 1})
        assert progress(state) == before


def test_abi_survives_database_reopen_and_evolution_cycle(engine, state, tmp_path):
    feed(engine, state, quantity=50)
    feed(engine, state, "storage", quantity=13)
    state["party"][0]["farm_bonuses"] = {"atk": 4}
    before_party = copy.deepcopy(state["party"])
    before_storage = copy.deepcopy(state["storage"])
    config = {"driver": "sqlite", "path": str(tmp_path / "abi.sqlite3")}
    db = Database(config, dev=True)
    db.initialize()
    db.register("AbiTamer", "abi-restart-password", state)
    db.close()
    reopened = Database(config, dev=True)
    try:
        restored, _ = reopened.load("abitamer")
        engine._refresh(restored)
        assert restored["party"] == before_party
        assert restored["storage"] == before_storage
        assert restored["inventory"][ITEM] == 36
        uid = restored["party"][0]["uid"]
        engine.handle(restored, "evolve", {"party_index": 0, "to": "examon_paradox"})
        evolved = restored["party"][0]
        assert evolved["abi"] == 58 and evolved["uid"] == uid
        engine._add_xp(restored, evolved, sum(xp_required(level) for level in range(1, 5)), 0)
        assert evolved["level"] == 5
        engine.handle(restored, "evolve", {"party_index": 0, "to": "fanglongmon_paradox"})
        devolved = restored["party"][0]
        assert devolved["abi"] == 64 and devolved["uid"] == uid
        assert devolved["farm_bonuses"] == {"atk": 4}
        assert devolved["cam"] == 40
    finally:
        reopened.close()


def test_existing_save_refresh_exposes_food_without_rewriting_partners(engine, state):
    state["shop"].pop(ITEM)
    state["inventory"].pop(ITEM)
    before = copy.deepcopy(state["party"] + state["storage"])
    engine._refresh(state)
    assert state["party"] + state["storage"] == before
    assert state["shop"][ITEM]["price"] == 6000
    assert state["shop"][ITEM]["ruby_price"] == 30
    assert state["shop"][ITEM]["amount"] == 1
    assert ITEM not in state["inventory"]
    assert SHOP[ITEM]["resource"] == "abi"
    assert max(r.get("abi", 0) for species in engine.species.values()
               for r in species.get("evolutions", [])) <= 200
