"""Money and goods cross one durable transaction, with adversarial retries.

These checks use real SQLite connections, player CAS/leases, and ranked season
settlement. Only explicit database fault tests replace the connection commit.
"""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import threading
import time
from unittest.mock import patch

import pytest

from venom.common.game import GameEngine, GameError
from venom.server.community_store import CommunityStore
from venom.server.database import Database, DatabaseError
from venom.server.ranked import RankedService

ROOT = Path(__file__).resolve().parents[1]
CREDIT_CAP = 2 ** 53 - 1


class Account:
    def __init__(self, engine, db, store, name="RubyAlice", balance=100):
        self.engine, self.db, self.store = engine, db, store
        self.state = engine.new_player(name, next(iter(engine.tamers)), "agumon")
        self.state["party"] = [engine._monster("agumon", 45)]
        engine._refresh(self.state)
        self.key = db.register(name, "ruby-transaction-password", self.state)
        self.token = "lease-for-" + self.key
        assert db.acquire_session(self.key, self.token)
        self.state, self.revision = db.load(self.key)
        self.ordinal = 0
        self.player_id = "player:" + self.key
        store.register_many([self.profile()], time.time())
        self.set_wallet(balance)

    def profile(self):
        return {"id": self.player_id, "kind": "player", "name": self.state["username"],
                "tamer": self.state["tamer"], "party": copy.deepcopy(self.state["party"])}

    def set_wallet(self, value):
        # Fixture only: production credits are earned through real ranked
        # settlement in the dedicated joined-path and interleaving tests.
        self.db.connection.execute("UPDATE venom_competitors SET digirubies=? WHERE id=?", (value, self.player_id))
        self.db.connection.commit()

    def wallet(self):
        return self.store.competitor(self.player_id)["digirubies"]

    def transact(self, operation="shop", transaction_id=None, **payload):
        self.ordinal += 1
        transaction_id = transaction_id or f"test-transaction-{self.ordinal:04d}"
        return self.db.economy_transaction(self.key, self.state, self.revision, self.token,
                                           transaction_id, operation, payload, self.engine)

    def accept(self, result):
        self.state, self.revision = result["state"], result["revision"]
        return result

    def persist(self):
        self.revision = self.db.save(self.key, self.state, self.revision, self.token)
        self.state, self.revision = self.db.load(self.key)

    def snapshot(self):
        save = self.db.load(self.key)
        balance = self.wallet()
        receipts = self.db.connection.execute(
            "SELECT transaction_id,intent_json,receipt_json FROM venom_economy_transactions WHERE username=? ORDER BY transaction_id",
            (self.key,)).fetchall()
        lease = self.db.connection.execute("SELECT session_token,lease_until FROM venom_accounts WHERE username=?", (self.key,)).fetchone()
        return save, balance, receipts, lease


@pytest.fixture(scope="module")
def engine():
    return GameEngine(ROOT, seed=734)


@pytest.fixture
def account(tmp_path, engine):
    db = Database({"driver": "sqlite", "path": str(tmp_path / "rubies.sqlite3")}, dev=True)
    db.initialize()
    store = CommunityStore(db)
    store.initialize()
    actor = Account(engine, db, store)
    yield actor
    db.close()


def test_shop_uses_authoritative_wallet_and_price_and_never_persists_display_mirror(account):
    actor = account
    actor.state["digirubies"] = 10 ** 20  # A stale display cannot become spendable money.
    actor.state["shop"]["hp_l"]["price"] = 0
    before = copy.deepcopy(actor.state)
    capsules = before["inventory"].get("hp_l", 0)
    result = actor.accept(actor.transact(item="hp_l", quantity=2, currency="digirubies",
                                       price=0, cost=0, balance=999999, username="SomebodyElse",
                                       player_id="player:somebodyelse"))
    assert actor.wallet() == 94, "Large capsules cost three authoritative DigiRubies each"
    assert actor.state["inventory"]["hp_l"] == capsules + 2
    assert actor.state["credits"] == before["credits"]
    assert actor.state["digirubies"] == 94
    saved, revision = actor.db.load(actor.key)
    assert "digirubies" not in saved and revision == result["revision"]
    assert saved["inventory"]["hp_l"] == capsules + 2
    assert len(actor.snapshot()[2]) == 1
    actor.persist()
    assert "digirubies" not in actor.db.load(actor.key)[0]


@pytest.mark.parametrize("operation,payload", [
    ("shop", {"item": "hp_l", "quantity": 34, "currency": "digirubies"}),
    ("exchange", {"amount": 101}),
])
def test_insufficient_wallet_rolls_back_save_lease_receipt_and_goods(account, operation, payload):
    before, state = account.snapshot(), copy.deepcopy(account.state)
    with pytest.raises((GameError, ValueError)):
        account.transact(operation, **payload)
    assert account.snapshot() == before
    assert account.state == state


def test_credit_cap_rejects_whole_exchange_and_exact_cap_is_possible(account):
    account.state["credits"] = CREDIT_CAP - 99
    account.persist()
    before = account.snapshot()
    with pytest.raises((GameError, ValueError)):
        account.transact("exchange", amount=1)
    assert account.snapshot() == before
    account.state["credits"] = CREDIT_CAP - 100
    account.persist()
    account.accept(account.transact("exchange", amount=1, rate=10 ** 9, credits=10 ** 12))
    assert account.state["credits"] == CREDIT_CAP
    assert account.wallet() == 99


def test_full_bag_cannot_consume_currency(account):
    account.state["inventory"]["hp_s"] = 999
    account.persist()
    before = account.snapshot()
    with pytest.raises((GameError, ValueError)):
        account.transact(item="hp_s", quantity=1, currency="digirubies")
    assert account.snapshot() == before


@pytest.mark.parametrize("operation,payload", [
    ("exchange", {"amount": amount}) for amount in (True, False, 0, -1, 100001, 1.5, "1", None)
] + [
    ("shop", {"item": "hp_s", "currency": "digirubies", "quantity": quantity})
    for quantity in (True, False, 0, -1, 100, 1.5, "1", None)
] + [
    ("shop", {"item": "missing", "quantity": 1, "currency": "digirubies"}),
    ("shop", {"item": "hp_s", "quantity": 1, "currency": "rubies"}),
])
def test_invalid_spend_inputs_never_change_either_balance(account, operation, payload):
    before = account.snapshot()
    with pytest.raises((GameError, ValueError)):
        account.transact(operation, **payload)
    assert account.snapshot() == before


@pytest.mark.parametrize("transaction_id", ["tiny", "x" * 65, "x" * 15, "bad id contains spaces", "x" * 16 + "/", 123, True, [], {}])
def test_invalid_receipt_keys_cannot_bypass_authoritative_payment(account, transaction_id):
    before = account.snapshot()
    with pytest.raises((GameError, ValueError)):
        account.db.economy_transaction(account.key, account.state, account.revision, account.token,
                                       transaction_id, "exchange", {"amount": 1}, account.engine)
    assert account.snapshot() == before


def test_stale_revision_and_wrong_or_expired_lease_roll_back_every_table(account):
    stale_state, stale_revision = copy.deepcopy(account.state), account.revision
    account.state["inventory"]["hp_s"] += 1
    account.persist()
    before = account.snapshot()
    with pytest.raises(DatabaseError):
        account.db.economy_transaction(account.key, stale_state, stale_revision, account.token,
                                       "stale-revision-key", "exchange", {"amount": 1}, account.engine)
    assert account.snapshot() == before
    with pytest.raises(DatabaseError):
        account.db.economy_transaction(account.key, account.state, account.revision, "wrong-session-owner",
                                       "wrong-session-key", "exchange", {"amount": 1}, account.engine)
    assert account.snapshot() == before
    account.db.connection.execute("UPDATE venom_accounts SET lease_until=? WHERE username=?", (time.time() - 10, account.key))
    account.db.connection.commit()
    before = account.snapshot()
    with pytest.raises(DatabaseError):
        account.transact("exchange", amount=1)
    assert account.snapshot() == before


def test_replay_after_later_progress_and_reconnect_returns_current_state_without_spending(account):
    original, revision = copy.deepcopy(account.state), account.revision
    receipt_id = "durable-purchase-01"
    first = account.accept(account.transact(transaction_id=receipt_id, item="hp_l", quantity=2, currency="digirubies"))
    assert first["state"]["digirubies"] == 94
    # Later gameplay consumes one bought item and acquires unrelated progress.
    account.state["inventory"]["hp_l"] -= 1
    account.state["party"][0]["cam"] += 7
    account.state["credits"] += 123
    account.persist()
    latest, latest_revision = account.db.load(account.key)
    account.db.release_session(account.key, account.token)
    account.token = "replacement-authenticated-session"
    assert account.db.acquire_session(account.key, account.token)
    before_wallet = account.wallet()
    replay = account.db.economy_transaction(account.key, original, revision, account.token,
                                            receipt_id, "shop", {"item": "hp_l", "quantity": 2,
                                            "currency": "digirubies"}, account.engine)
    assert replay["revision"] == latest_revision
    for key in ("inventory", "party", "credits"):
        assert replay["state"][key] == latest[key]
    assert replay["state"].get("events", []) == [], "Retry must not replay stale heal/battle events"
    assert account.wallet() == before_wallet
    assert account.db.load(account.key) == (latest, latest_revision)
    assert len(account.snapshot()[2]) == 1
    with pytest.raises(DatabaseError):
        account.db.economy_transaction(account.key, original, revision, "expired-original-session",
                                       receipt_id, "shop", {"item": "hp_l", "quantity": 2,
                                       "currency": "digirubies"}, account.engine)


@pytest.mark.parametrize("operation,payload", [
    ("shop", {"item": "hp_s", "quantity": 1, "currency": "digirubies"}),
    ("shop", {"item": "hp_l", "quantity": 2, "currency": "digirubies"}),
    ("exchange", {"amount": 1}),
])
def test_receipt_key_conflicts_reject_a_different_purchase(account, operation, payload):
    receipt_id = "purchase-conflict-01"
    account.accept(account.transact(transaction_id=receipt_id, item="hp_l", quantity=1, currency="digirubies"))
    before = account.snapshot()
    with pytest.raises((GameError, ValueError)):
        account.transact(operation, transaction_id=receipt_id, **payload)
    assert account.snapshot() == before


def test_same_receipt_id_is_scoped_to_authenticated_owner(account):
    bob = Account(account.engine, account.db, account.store, name="RubyBobby", balance=20)
    ident = "same-client-key-01"
    account.accept(account.transact("exchange", transaction_id=ident, amount=2, username="RubyBobby"))
    bob.accept(bob.transact("exchange", transaction_id=ident, amount=2, username="RubyAlice"))
    assert account.wallet() == 98 and bob.wallet() == 18
    assert account.state["credits"] == 850 and bob.state["credits"] == 850
    assert len(account.snapshot()[2]) == len(bob.snapshot()[2]) == 1


def test_receipt_insert_failure_rolls_back_wallet_inventory_save_and_lease(account):
    account.db.connection.execute("""CREATE TRIGGER fail_economy_receipt BEFORE INSERT ON venom_economy_transactions
        BEGIN SELECT RAISE(ABORT, 'injected receipt write failure'); END""")
    account.db.connection.commit()
    before, state = account.snapshot(), copy.deepcopy(account.state)
    with pytest.raises((sqlite3.Error, DatabaseError)):
        account.transact(item="hp_l", quantity=2, currency="digirubies")
    assert account.snapshot() == before and account.state == state
    account.db.connection.execute("DROP TRIGGER fail_economy_receipt")
    account.db.connection.commit()
    account.accept(account.transact(item="hp_l", quantity=2, currency="digirubies"))
    assert account.wallet() == 94


class CommitFault:
    def __init__(self, connection, after_commit=False):
        self.connection, self.after_commit = connection, after_commit

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def commit(self):
        if self.after_commit:
            self.connection.commit()
        raise sqlite3.OperationalError("injected commit acknowledgement failure")


@pytest.mark.parametrize("after_commit", [False, True])
def test_commit_failure_or_lost_acknowledgement_cannot_duplicate_a_retry(account, after_commit):
    before, state = account.snapshot(), copy.deepcopy(account.state)
    receipt_id = "uncertain-commit-01"
    real_connect = account.db._connect
    with patch.object(account.db, "_connect", return_value=CommitFault(real_connect(), after_commit)):
        with pytest.raises((sqlite3.Error, DatabaseError)):
            account.transact("exchange", transaction_id=receipt_id, amount=2)
    assert account.state == state, "Never mutate the live session before a successful commit response"
    if not after_commit:
        assert account.snapshot() == before
    else:
        assert account.wallet() == 98
        assert account.db.load(account.key)[0]["credits"] == state["credits"] + 200
    replay = account.accept(account.transact("exchange", transaction_id=receipt_id, amount=2))
    assert account.wallet() == 98
    assert account.state["credits"] == state["credits"] + 200
    assert len(account.snapshot()[2]) == 1
    assert replay["revision"] == before[0][1] + 1


def ranked_fixture(account, store=None, clock=None):
    clock = clock or [1_800_000_000.0]
    service = RankedService(account.engine, store or account.store,
                            {"season_seconds": 600, "match_cooldown": 0, "opponent_cooldown": 0},
                            clock=lambda: clock[0])
    service.register_many([account.profile(), {"id": "bot:transaction-test", "kind": "bot", "name": "Training Rival",
                                              "tamer": account.state["tamer"],
                                              "party": [account.engine._monster("agumon", 1)]}])
    return service, clock


def test_actual_ranked_rewards_fund_both_spends_and_later_season_adds_to_remainder(account):
    account.set_wallet(0)
    ranked, clock = ranked_fixture(account)
    result = ranked.start_match(account.player_id, "bot:transaction-test", "earned-first-season")
    assert result["attacker_won"] and result["ranked"]
    assert any(event["kind"] == "damage" for event in result["replay"]["events"])
    assert account.wallet() == 0, "A season pays at settlement, not merely when a match ends"
    first_season = ranked.tick()
    clock[0] = first_season["ends_at"] + 1
    ranked.tick()
    earned = ranked.reward_for(1, 20, 0)
    assert account.wallet() == earned and earned > 5
    account.accept(account.transact(item="hp_l", quantity=1, currency="digirubies"))
    account.accept(account.transact("exchange", amount=2))
    assert account.wallet() == earned - 5 and account.state["credits"] == 850
    assert ranked.start_match(account.player_id, "bot:transaction-test", "earned-second-season")["attacker_won"]
    clock[0] = ranked.tick()["ends_at"] + 1
    ranked.tick()
    assert account.wallet() == earned * 2 - 5
    ranked.tick()
    assert account.wallet() == earned * 2 - 5, "Settling the same season cannot pay twice"
    assert account.db.connection.execute("SELECT COUNT(*) FROM venom_ranked_rewards WHERE participant_id=?", (account.player_id,)).fetchone()[0] == 2
    # Subsequent profile publication must preserve the earned/spent wallet.
    ranked.register_participant(account.player_id, account.profile())
    assert account.wallet() == earned * 2 - 5


def test_season_settlement_and_spend_on_independent_connections_do_not_lose_either_update(account):
    ranked, clock = ranked_fixture(account)
    assert ranked.start_match(account.player_id, "bot:transaction-test", "concurrent-season-01")["attacker_won"]
    other_db = Database(account.db.config, dev=True)
    other_store = CommunityStore(other_db)
    other_store.initialize()
    other_ranked, _ = ranked_fixture(account, store=other_store, clock=clock)
    clock[0] = ranked.tick()["ends_at"] + 1
    barrier = threading.Barrier(2)

    def settle():
        barrier.wait(timeout=5)
        return other_ranked.tick()

    def spend():
        barrier.wait(timeout=5)
        return account.transact(item="hp_l", quantity=2, currency="digirubies")

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            reward_future = executor.submit(settle)
            spend_future = executor.submit(spend)
            reward_future.result(timeout=15)
            account.accept(spend_future.result(timeout=15))
        earned = ranked.reward_for(1, 20, 0)
        assert account.wallet() == 100 + earned - 6
        assert account.db.load(account.key)[0]["inventory"]["hp_l"] == 2
        assert len(account.snapshot()[2]) == 1
    finally:
        other_db.close()
