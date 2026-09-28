"""Canonical active rival population and explicitly retired legacy identities."""

DEFAULT_BOTS = 3000
MAX_BOTS = 3000
LEGACY_MAX_BOTS = 5000


def retired_bot_ids():
    """Only the 2,000 canonical legacy bot IDs; never a human account ID."""
    return tuple(f'bot:{ordinal:05d}' for ordinal in range(MAX_BOTS + 1, LEGACY_MAX_BOTS + 1))
