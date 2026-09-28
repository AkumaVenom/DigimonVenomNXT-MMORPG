"""ABI DigiMeat joins the real wallet, farm/party use and durable player save."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from test_digiruby_transactions import Account
from venom.common.game import GameEngine, GameError
from venom.server.community_store import CommunityStore
from venom.server.database import Database


ROOT = Path(__file__).resolve().parents[1]
ITEM = "digimeat_abi"


@pytest.fixture(scope="module")
def engine():
    return GameEngine(ROOT, seed=734)


@pytest.fixture
def account(tmp_path, engine):
    db = Database({"driver": "sqlite", "path": str(tmp_path / "abi.sqlite3")}, dev=True)
    db.initialize()
    store = CommunityStore(db)
    store.initialize()
    actor = Account(engine, db, store, name="AbiRubyAlice", balance=100)
    yield actor
    db.close()


def test_abi_checkout_uses_real_thirty_ruby_price_despite_spoofed_quotes(account):
    account.state["digirubies"] = 999999999
    account.state["shop"][ITEM].update(price=0, ruby_price=0, amount=200)
    credits = account.state["credits"]
    before = account.state["inventory"].get(ITEM, 0)
    result = account.accept(account.transact(
        item=ITEM, quantity=2, currency="digirubies", price=0, ruby_price=0,
        cost=0, balance=999999999, amount=200, username="SomeOtherPlayer"))

    assert result["receipt"]["rubies_spent"] == 60
    assert account.wallet() == 40
    assert account.state["inventory"][ITEM] == before + 2
    assert account.state["credits"] == credits
    assert account.state["shop"][ITEM]["price"] == 6000
    assert account.state["shop"][ITEM]["ruby_price"] == 30
    saved, revision = account.db.load(account.key)
    assert saved["inventory"][ITEM] == before + 2
    assert revision == result["revision"]
    assert "digirubies" not in saved


@pytest.mark.parametrize("balance,quantity", [(29, 1), (59, 2)])
def test_abi_insufficient_wallet_changes_neither_save_receipt_nor_goods(account, balance, quantity):
    account.set_wallet(balance)
    before, live = account.snapshot(), copy.deepcopy(account.state)
    with pytest.raises(ValueError, match="Not enough DigiRubies"):
        account.transact(item=ITEM, quantity=quantity, currency="digirubies")
    assert account.snapshot() == before
    assert account.state == live


def test_abi_purchase_retry_grants_and_debits_exactly_once(account):
    reference = "abi-purchase-retry-01"
    first = account.accept(account.transact(
        transaction_id=reference, item=ITEM, quantity=1, currency="digirubies"))
    original_revision = first["revision"]
    repeated = account.accept(account.transact(
        transaction_id=reference, item=ITEM, quantity=1, currency="digirubies",
        price=1, ruby_price=1))
    assert first["receipt"]["duplicate"] is False
    assert repeated["receipt"]["duplicate"] is True
    assert repeated["revision"] == original_revision
    assert account.wallet() == 70
    assert account.state["inventory"][ITEM] == 1
    assert len(account.snapshot()[2]) == 1


@pytest.mark.parametrize("location", ["party", "storage"])
def test_abi_purchase_use_restart_and_retry_preserve_unblocked_paradox_route(account, location):
    monster = account.engine._monster("fanglongmon_paradox", level=60, abi=49, cam=40)
    assert not account.engine.devolutions.get("fanglongmon_paradox")
    before_route = next(route for route in account.engine.evolution_options(monster)
                        if route["to"] == "examon_paradox")
    assert before_route["missing"] == ["ABI 50"]
    account.state[location].append(monster)
    account.engine._refresh(account.state)
    account.persist()
    reference = "abi-purchase-restart-" + location
    account.accept(account.transact(transaction_id=reference, item=ITEM,
                                    quantity=1, currency="digirubies"))
    monster = next(m for m in account.state[location] if m["uid"] == monster["uid"])
    if location == "party":
        account.engine.handle(account.state, "item", {"item": ITEM, "quantity": 1,
            "party_index": len(account.state["party"]) - 1, "uid": monster["uid"]})
    else:
        account.engine.handle(account.state, "digifarm", {"action": "feed",
            "item": ITEM, "quantity": 1, "uid": monster["uid"]})
    assert monster["abi"] == 50 and account.state["inventory"][ITEM] == 0
    account.persist()
    expected, expected_revision = account.db.load(account.key)
    account.db.release_session(account.key, account.token)
    account.db.close()

    # A fresh connection and engine represent restarting the process, not just
    # reading the same in-memory objects through another reference.
    restarted = Database(account.db.config, dev=True)
    restored_engine = GameEngine(ROOT, seed=735)
    try:
        restored, revision = restarted.load(account.key)
        restored_engine._refresh(restored)
        resident = next(m for m in restored[location] if m["uid"] == monster["uid"])
        assert resident["abi"] == 50
        assert resident["level"] == 60
        assert restored["inventory"][ITEM] == 0
        assert revision == expected_revision
        assert restarted.wallet_balance(account.key) == 70
        route = next(route for route in restored_engine.evolution_options(resident)
                     if route["to"] == "examon_paradox")
        assert route["eligible"] and not route["missing"]

        token = "abi-session-after-restart"
        assert restarted.acquire_session(account.key, token)
        repeated = restarted.economy_transaction(account.key, restored, revision, token,
            reference, "shop", {"item": ITEM, "quantity": 1, "currency": "digirubies"}, restored_engine)
        assert repeated["receipt"]["duplicate"] is True
        assert repeated["state"]["inventory"][ITEM] == 0, "A retry cannot recreate an eaten treat"
        assert repeated["state"][location] == restored[location]
        assert restarted.wallet_balance(account.key) == 70
        assert restarted.load(account.key) == (expected, expected_revision)
    finally:
        restarted.close()


@pytest.mark.parametrize("operation", ["item", "digifarm", "battle"])
def test_abi_cannot_be_consumed_through_any_item_entry_during_battle(account, operation):
    account.state["storage"].append(account.engine._monster("fanglongmon_paradox", abi=49))
    account.accept(account.transact(item=ITEM, quantity=1, currency="digirubies"))
    account.engine.handle(account.state, "digifarm", {"action": "return"})
    account.engine.handle(account.state, "encounter", {})
    assert account.state["battle"]
    payload = {"item": ITEM, "quantity": 1, "party_index": 0,
               "uid": account.state["party"][0]["uid"]}
    if operation == "digifarm":
        payload.update(action="feed", uid=account.state["storage"][0]["uid"])
    elif operation == "battle":
        payload["action"] = "item"
    before = {key: copy.deepcopy(account.state[key]) for key in ("inventory", "party", "storage", "battle")}
    with pytest.raises(GameError):
        account.engine.handle(account.state, operation, payload)
    for key, value in before.items():
        assert account.state[key] == value
    assert account.wallet() == 70
