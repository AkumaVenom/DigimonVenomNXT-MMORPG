"""Shared, finite network deadlines. All values are seconds.

Optional overrides live in a ``network`` object in client.json/server.json.
The client and server must each receive their own configuration changes.
"""
from __future__ import annotations

import math


DEFAULT_NETWORK_SETTINGS = {
    'ping_interval': 20.0,
    'ping_timeout': 120.0,
    'open_timeout': 30.0,
    'close_timeout': 5.0,
    'send_timeout': 30.0,
    'login_timeout': 120.0,
}


def network_settings(config: dict) -> dict[str, float]:
    """Return validated settings without modifying the caller's config.

    Keep deadlines finite: disabling heartbeat or send timeouts can retain
    dead sessions indefinitely. JSON booleans aren't valid durations.
    """
    values = config.get('network', {})
    if not isinstance(values, dict):
        raise ValueError('The network configuration must be a JSON object.')
    settings = {}
    for name, default in DEFAULT_NETWORK_SETTINGS.items():
        value = values.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'network.{name} must be a positive, finite number of seconds.')
        try:
            valid = math.isfinite(value) and value > 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f'network.{name} must be a positive, finite number of seconds.')
        settings[name] = float(value)
    return settings
