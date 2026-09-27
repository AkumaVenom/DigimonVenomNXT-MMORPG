"""Shared presentation rules for the server-owned DigiRuby wallet.

The balance lives only in venom_competitors; these constants never create or
persist a second wallet in a character save.
"""
import re

CREDITS_PER_RUBY = 100
RUBY_SHOP_CREDIT_UNIT = 200
MAX_EXCHANGE_RUBIES = 100_000
MAX_CREDITS = 2 ** 53 - 1
TRANSACTION_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def ruby_price(credit_price):
    return max(1, (int(credit_price) + RUBY_SHOP_CREDIT_UNIT - 1) // RUBY_SHOP_CREDIT_UNIT)


def economy_view(enabled=False):
    return {"enabled": bool(enabled), "credits_per_ruby": CREDITS_PER_RUBY,
            "max_exchange_rubies": MAX_EXCHANGE_RUBIES, "max_credits": MAX_CREDITS}


def normalize_intent(operation, payload, shop):
    """Whitelist business fields; quoted balances, prices and rewards are ignored."""
    if operation == "shop":
        if payload.get("currency", "credits") != "digirubies":
            raise ValueError("Choose DigiRubies for this checkout.")
        item = payload.get("item")
        quantity = payload.get("quantity", 1)
        if not isinstance(item, str) or item not in shop:
            raise ValueError("That item is not sold here.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 99:
            raise ValueError("Choose a quantity from 1 to 99.")
        return {"operation": "shop", "currency": "digirubies", "item": item, "quantity": quantity}
    if operation == "exchange":
        amount = payload.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= MAX_EXCHANGE_RUBIES:
            raise ValueError(f"Exchange between 1 and {MAX_EXCHANGE_RUBIES:,} DigiRubies at a time.")
        return {"operation": "exchange", "amount": amount}
    raise ValueError("Choose a valid DigiRuby transaction.")
