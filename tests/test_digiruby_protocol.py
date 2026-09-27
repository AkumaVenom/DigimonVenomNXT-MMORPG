"""Real ranked rewards spent through WebSockets and atomic SQLite transactions.

The funded fixture plays an authoritative ranked match and closes its season;
it never fabricates a wallet balance or sends a client-supplied battle outcome.
Boundary fixtures alter only ordinary saved credits/inventory, not the wallet.
"""
from __future__ import annotations

import asyncio
import copy
import time
import unittest
from unittest.mock import patch

from venom.common.game import SHOP
import test_story_protocol as _protocol

PASSWORD = _protocol.PASSWORD
MAX_CREDITS = 2 ** 53 - 1


class DigiRubyProtocolTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = _protocol.StoryProtocolTests.asyncSetUp
    asyncTearDown = _protocol.StoryProtocolTests.asyncTearDown
    stop_server = _protocol.StoryProtocolTests.stop_server
    connection = _protocol.StoryProtocolTests.connection
    receive = _protocol.StoryProtocolTests.receive
    action = _protocol.StoryProtocolTests.action
    register = _protocol.StoryProtocolTests.register
    wait_for_logout = _protocol.StoryProtocolTests.wait_for_logout
    battle_fields = staticmethod(_protocol.StoryProtocolTests.battle_fields)

    async def start_server(self):
        await _protocol.StoryProtocolTests.start_server(self)
        await self.world.initialize_community()
        self.store = self.world.community.store
        ranked = self.world.community.ranked
        self.ranked_now = time.time()
        ranked.clock = lambda: self.ranked_now
        ranked.register_participant("bot:economy_fixture", {
            "name": "Economy Sparring Tamer", "tamer": next(iter(self.engine.tamers)),
            "kind": "bot", "party": [self.engine._monster(self.engine.starters[0], 1)]})

    async def request(self, ws, op, **fields):
        # Keep real request throttles enabled. A throttle error cannot pass a
        # validation or atomicity test by masking the requested operation.
        if op == "community":
            await asyncio.sleep(.52)
        return await _protocol.StoryProtocolTests.request(self, ws, op, **fields)

    def wallet(self, key):
        return self.store.competitor("player:" + key)["digirubies"]

    async def funded_player(self, ws, username, seasons=1):
        initial = await self.register(ws, username)
        self.assertEqual(0, initial["digirubies"])
        key = username.lower()
        ranked = self.world.community.ranked
        for _ in range(seasons):
            result = await self.request(ws, "community", action="match",
                                        opponent_id="bot:economy_fixture")
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["community"]["data"]["replay"]["events"])
            self.ranked_now = ranked.tick()["ends_at"] + 1
            ranked.tick()
        balance = self.wallet(key)
        self.assertGreater(balance, 0)
        with self.store.transaction() as cursor:
            cursor.execute("SELECT SUM(amount) FROM venom_ranked_rewards WHERE participant_id=?",
                           ("player:" + key,))
            self.assertEqual(balance, cursor.fetchone()[0])
        result = await self.request(ws, "community", action="ranked")
        self.assertTrue(result["ok"], result)
        self.assertEqual(balance, result["wallet"]["digirubies"])
        return initial, balance

    async def rejected(self, ws, key, op, **fields):
        before_db = self.db.load(key)
        before_live = copy.deepcopy(self.world.sessions[key].state)
        before_wallet = self.wallet(key)
        response = await self.request(ws, op, **fields)
        self.assertFalse(response["ok"], response)
        self.assertNotIn("wait a moment", response.get("error", "").lower(), response)
        self.assertEqual(before_db, self.db.load(key))
        self.assertEqual(before_wallet, self.wallet(key))
        self.assertEqual(before_live, self.world.sessions[key].state)
        return response

    async def exchange(self, ws, amount, **fields):
        result = await self.request(ws, "community", action="exchange", amount=amount, **fields)
        self.assertTrue(result["ok"], result)
        return result

    async def test_earned_wallet_buys_every_catalog_item_and_default_credit_shop_is_unchanged(self):
        async with self.connection() as ws:
            initial, balance = await self.funded_player(ws, "RubyCatalog", seasons=4)
            self.assertEqual(100, initial["economy"]["credits_per_ruby"])
            self.assertEqual(100000, initial["economy"]["max_exchange_rubies"])
            state = await self.action(ws, "shop", item="hp_s", quantity=1)
            self.assertEqual(initial["credits"] - SHOP["hp_s"]["price"], state["credits"])
            self.assertEqual(balance, self.wallet("rubycatalog"))
            expected_credits = state["credits"]
            for item, spec in SHOP.items():
                with self.subTest(item=item):
                    price = max(1, (spec["price"] + 199) // 200)
                    self.assertEqual(price, state["shop"][item]["ruby_price"])
                    previous = state["inventory"].get(item, 0)
                    state = await self.action(ws, "shop", item=item, quantity=1, currency="digirubies")
                    balance -= price
                    self.assertEqual(previous + 1, state["inventory"][item])
                    self.assertEqual(expected_credits, state["credits"])
                    self.assertEqual(balance, state["digirubies"])
                    self.assertEqual(balance, self.wallet("rubycatalog"))
            expected_inventory = copy.deepcopy(state["inventory"])
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout("rubycatalog")
        stored, _ = self.db.load("rubycatalog")
        self.assertNotIn("digirubies", stored, "The SQL wallet must remain the sole balance authority")
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            state = await self.action(ws, "login", username="RUBYCATALOG", password=PASSWORD)
            self.assertEqual(balance, state["digirubies"])
            self.assertEqual(expected_credits, state["credits"])
            self.assertEqual(expected_inventory, state["inventory"])

    async def test_invalid_amounts_currency_and_transaction_ids_never_debit_or_grant(self):
        async with self.connection() as ws:
            await self.funded_player(ws, "RubyValidation")
            for quantity in (0, -1, True, False, 1.5, 100, 2 ** 80, "2"):
                with self.subTest(shop_quantity=quantity):
                    await self.rejected(ws, "rubyvalidation", "shop", item="hp_s",
                                        quantity=quantity, currency="digirubies")
            for currency in ("rubies", "gold", None, False, {"digirubies": True}):
                with self.subTest(currency=currency):
                    await self.rejected(ws, "rubyvalidation", "shop", item="hp_s",
                                        quantity=1, currency=currency)
            for amount in (0, -1, True, 1.5, 100001, 2 ** 80, "2"):
                with self.subTest(exchange_amount=amount):
                    await self.rejected(ws, "rubyvalidation", "community", action="exchange", amount=amount)
            for transaction_id in ("short", "!" * 20, "a" * 65, True, ["a" * 20]):
                with self.subTest(transaction_id=transaction_id):
                    await self.rejected(ws, "rubyvalidation", "shop", item="hp_s", quantity=1,
                                        currency="digirubies", transaction_id=transaction_id)
            await self.rejected(ws, "rubyvalidation", "shop", item="not_a_shop_item", quantity=1,
                                currency="digirubies", price=0)
            await self.rejected(ws, "rubyvalidation", "community", action="exchange",
                                amount=self.wallet("rubyvalidation") + 1, digirubies=999999999)

    async def test_server_prices_identity_and_durable_retries_prevent_double_grants(self):
        exchange_id, purchase_id = "exchange_once_00000001", "purchase_once_00000001"
        async with self.connection() as ws, self.connection() as other:
            initial, balance = await self.funded_player(ws, "RubyRetry")
            await self.register(other, "RubyBystander")
            bystander = self.db.load("rubybystander")
            result = await self.exchange(ws, 3, transaction_id=exchange_id, rate=999999,
                credits_gained=999999, balance=999999, digirubies=999999,
                username="RubyBystander", player_id="player:rubybystander")
            state, receipt = result["state"], result["community"]["data"]
            self.assertEqual(3, receipt["rubies_spent"])
            self.assertEqual(300, receipt["credits_gained"])
            self.assertEqual(balance - 3, receipt["balance"])
            self.assertEqual(initial["credits"] + 300, state["credits"])
            self.assertEqual(balance - 3, state["digirubies"])
            self.assertEqual(bystander, self.db.load("rubybystander"))
            self.assertEqual(0, self.wallet("rubybystander"))
            count = state["inventory"]["hp_s"]
            state = await self.action(ws, "shop", item="hp_s", quantity=3, currency="digirubies",
                                      transaction_id=purchase_id, ruby_price=0, price=0, cost=0,
                                      digirubies=999999, username="RubyBystander")
            self.assertEqual(count + 3, state["inventory"]["hp_s"])
            self.assertEqual(balance - 6, state["digirubies"])
            self.assertEqual(initial["credits"] + 300, state["credits"])
            before = self.db.load("rubyretry")
            movement = await self.request(ws, "move", space="farm", dx=1, dy=0, dt=.1)
            self.assertTrue(movement["ok"], movement)
            position = copy.deepcopy(self.world.sessions["rubyretry"].state["farm_position"])
            self.assertNotEqual(before[0]["farm_position"], position)
            state = await self.action(ws, "shop", item="hp_s", quantity=3, currency="digirubies",
                                      transaction_id=purchase_id)
            self.assertEqual(position, state["farm_position"], "A receipt retry must not undo unsaved movement")
            self.assertEqual(before, self.db.load("rubyretry"))
            await self.rejected(ws, "rubyretry", "shop", item="hp_s", quantity=4,
                                currency="digirubies", transaction_id=purchase_id)
            repeated = await self.exchange(ws, 3, transaction_id=exchange_id)
            self.assertTrue(repeated["community"]["data"]["duplicate"])
            self.assertEqual(before, self.db.load("rubyretry"))
            await self.rejected(ws, "rubyretry", "community", action="exchange", amount=4,
                                transaction_id=exchange_id)
            await self.action(ws, "logout")
            await ws.wait_closed()
        await self.wait_for_logout("rubyretry")
        async with self.connection() as ws:
            await self.receive(ws, "hello")
            restored = await self.action(ws, "login", username="RubyRetry", password=PASSWORD)
            self.assertEqual(balance - 6, restored["digirubies"])
            self.assertEqual(count + 3, restored["inventory"]["hp_s"])
            before = self.db.load("rubyretry")
            repeated = await self.exchange(ws, 3, transaction_id=exchange_id)
            self.assertTrue(repeated["community"]["data"]["duplicate"])
            self.assertEqual(before, self.db.load("rubyretry"))
            self.assertEqual(balance - 6, repeated["state"]["digirubies"])
            self.assertEqual(count + 3, repeated["state"]["inventory"]["hp_s"])

    async def test_story_shops_work_while_ranked_mode_and_battle_restrictions_remain(self):
        async with self.connection() as ws:
            _, balance = await self.funded_player(ws, "RubyStory")
            with patch.object(self.world.community, "register_player",
                              wraps=self.world.community.register_player) as publish:
                await self.action(ws, "story", action="enter", campaign_id="world_ds_paradox")
                state = await self.action(ws, "digilab", action="enter")
                credits, count = state["credits"], state["inventory"]["hp_s"]
                state = await self.action(ws, "shop", item="hp_s", quantity=1, currency="digirubies")
                self.assertTrue(state["in_story"] and state["in_lab"])
                self.assertEqual(credits, state["credits"])
                self.assertEqual(count + 1, state["inventory"]["hp_s"])
                self.assertEqual(balance - 1, state["digirubies"])
                await self.rejected(ws, "rubystory", "community", action="exchange", amount=1)
                await self.rejected(ws, "rubystory", "community", action="ranked")
                publish.assert_not_called()
            await self.action(ws, "story", action="return")
            # Conversion is useful from either normal native service screen.
            farm_exchange = await self.exchange(ws, 1)
            self.assertTrue(farm_exchange["state"]["in_farm"])
            await self.action(ws, "digilab", action="enter")
            lab_exchange = await self.exchange(ws, 1)
            self.assertTrue(lab_exchange["state"]["in_lab"])
            await self.action(ws, "season", action="enter")
            await self.rejected(ws, "rubystory", "community", action="exchange", amount=1)
            await self.rejected(ws, "rubystory", "shop", item="hp_s", quantity=1, currency="digirubies")
            await self.action(ws, "season", action="return")
            await self.action(ws, "digilab", action="return")
            state = await self.action(ws, "encounter")
            await self.rejected(ws, "rubystory", "community", action="exchange", amount=1)
            await self.rejected(ws, "rubystory", "shop", item="hp_s", quantity=1, currency="digirubies")
            await self.rejected(ws, "rubystory", "battle", **self.battle_fields(state, "struggle", target=0))
            await self.action(ws, "battle", **self.battle_fields(state, "guard"))

    async def test_inventory_cap_and_credit_overflow_preserve_both_balances(self):
        async with self.connection() as ws:
            _, balance = await self.funded_player(ws, "RubyLimits")
            session = self.world.sessions["rubylimits"]
            async with session.lock:
                session.state["inventory"]["hp_s"] = 998
                session.state["credits"] = MAX_CREDITS - 50
                await self.world.save(session)
            await self.rejected(ws, "rubylimits", "shop", item="hp_s", quantity=2, currency="digirubies")
            state = await self.action(ws, "shop", item="hp_s", quantity=1, currency="digirubies")
            self.assertEqual(999, state["inventory"]["hp_s"])
            self.assertEqual(balance - 1, state["digirubies"])
            await self.rejected(ws, "rubylimits", "shop", item="hp_s", quantity=1, currency="digirubies")
            await self.rejected(ws, "rubylimits", "community", action="exchange", amount=1)
            async with session.lock:
                session.state["credits"] = MAX_CREDITS - 100
                await self.world.save(session)
            result = await self.exchange(ws, 1)
            self.assertEqual(MAX_CREDITS, result["state"]["credits"])
            self.assertEqual(balance - 2, result["state"]["digirubies"])

    async def test_passive_season_payout_pushes_wallet_only_inside_private_story(self):
        async with self.connection() as ws:
            await self.register(ws, "RubyNotice")
            match = await self.request(ws, "community", action="match",
                                       opponent_id="bot:economy_fixture")
            self.assertTrue(match["ok"], match)
            await self.action(ws, "story", action="enter", campaign_id="world_ds_paradox")
            await self.action(ws, "digilab", action="enter")
            session = self.world.sessions["rubynotice"]
            before = copy.deepcopy(session.state)
            before_db = self.db.load("rubynotice")
            self.assertEqual(0, before["digirubies"])
            ranked = self.world.community.ranked
            self.ranked_now = ranked.tick()["ends_at"] + 1
            ranked.tick()
            balance = self.wallet("rubynotice")
            self.assertGreater(balance, 0)
            with patch.object(self.world.community, "register_player",
                              wraps=self.world.community.register_player) as publish, \
                 patch.object(self.world, "result", wraps=self.world.result) as send_result:
                async with session.lock:
                    await self.world.refresh_wallet(session, notify=True)
                notice = await self.receive(ws, "result", 0)
                self.assertEqual({"digirubies": balance}, notice["wallet"])
                self.assertTrue(notice["economy"]["enabled"])
                self.assertNotIn("state", notice)
                self.assertNotIn("events", notice)
                self.assertEqual(1, send_result.call_count)
                async with session.lock:
                    await self.world.refresh_wallet(session, notify=True)
                self.assertEqual(1, send_result.call_count, "An unchanged wallet must not generate repeated notices")
                publish.assert_not_called()
            before["digirubies"] = balance
            self.assertEqual(before, session.state)
            self.assertEqual(before_db, self.db.load("rubynotice"))

    async def test_sql_write_failure_rolls_back_wallet_reward_and_retry_receipt(self):
        for operation in ("shop", "exchange"):
            with self.subTest(operation=operation):
                username = "RubyFail" + operation
                key = username.lower()
                transaction_id = "retry_after_failure_" + operation
                async with self.connection() as ws:
                    _, balance = await self.funded_player(ws, username)
                    session = self.world.sessions[key]
                    before_live, before_db = copy.deepcopy(session.state), self.db.load(key)
                    with self.db.lock:
                        self.db.connection.execute("CREATE TRIGGER fail_ruby_save BEFORE UPDATE ON venom_players "
                            "BEGIN SELECT RAISE(ABORT, 'injected economy write failure'); END")
                        self.db.connection.commit()
                    try:
                        fields = ({"item": "hp_s", "quantity": 2, "currency": "digirubies"}
                                  if operation == "shop" else {"action": "exchange", "amount": 2})
                        result = await self.request(ws, "shop" if operation == "shop" else "community",
                                                    transaction_id=transaction_id, **fields)
                        self.assertFalse(result["ok"], result)
                        self.assertEqual(before_live, session.state)
                        self.assertEqual(before_db, self.db.load(key))
                        self.assertEqual(balance, self.wallet(key))
                    finally:
                        with self.db.lock:
                            self.db.connection.execute("DROP TRIGGER fail_ruby_save")
                            self.db.connection.commit()
                    await ws.close()
                await self.wait_for_logout(key)
                async with self.connection() as ws:
                    await self.receive(ws, "hello")
                    restored = await self.action(ws, "login", username=username, password=PASSWORD)
                    self.assertEqual(balance, restored["digirubies"])
                    if operation == "shop":
                        state = await self.action(ws, "shop", transaction_id=transaction_id, **fields)
                        self.assertEqual(restored["inventory"]["hp_s"] + 2, state["inventory"]["hp_s"])
                    else:
                        state = (await self.exchange(ws, 2, transaction_id=transaction_id))["state"]
                        self.assertEqual(restored["credits"] + 200, state["credits"])
                    self.assertEqual(balance - 2, state["digirubies"])

    async def test_stale_account_lease_and_revision_cannot_spend_wallet(self):
        for fence in ("lease", "revision"):
            with self.subTest(fence=fence):
                username = "RubyFence" + fence
                key = username.lower()
                async with self.connection() as ws:
                    _, balance = await self.funded_player(ws, username)
                    session = self.world.sessions[key]
                    before_live = copy.deepcopy(session.state)
                    with self.db.lock:
                        if fence == "lease":
                            self.db.connection.execute(
                                "UPDATE venom_accounts SET session_token=?,lease_until=? WHERE username=?",
                                ("successor_owns_this_account", time.time() + 90, key))
                        else:
                            self.db.connection.execute("UPDATE venom_players SET revision=revision+1 WHERE username=?", (key,))
                        self.db.connection.commit()
                    before_db = self.db.load(key)
                    result = await self.request(ws, "shop", item="hp_s", quantity=1, currency="digirubies",
                                                transaction_id="fenced_purchase_" + fence)
                    self.assertFalse(result["ok"], result)
                    self.assertEqual(before_live, session.state)
                    self.assertEqual(before_db, self.db.load(key))
                    self.assertEqual(balance, self.wallet(key))


if __name__ == "__main__":
    unittest.main()
