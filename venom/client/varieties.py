"""Shared variety presentation for catalog entries and saved partner records."""
from __future__ import annotations


VARIETIES = ('all', 'normal', 'paradox', 'shiny', 'firewall')
SHINY_GOLD = (247, 199, 104)
FIREWALL_ORANGE = (255, 153, 104)
VARIETY_NAMES = {'normal': 'Normal', 'paradox': 'Paradox', 'shiny': 'Shiny', 'firewall': 'FireWall'}


def variety_of(entry, catalog=None):
    """Resolve variety from authoritative catalog metadata, then legacy fields.

    Partner snapshots need only their species ID: no extra synchronized client
    flag is required to show a Shiny in battle, storage or a replay.
    """
    entry = entry or {}
    ident = str(entry.get('species_id') or entry.get('id') or '')
    source = (catalog or {}).get(ident, entry)
    if source.get('firewall') or source.get('variety') == 'firewall' or ident.endswith('_firewall'):
        return 'firewall'
    if source.get('shiny') or source.get('variety') == 'shiny' or ident.endswith('_shiny'):
        return 'shiny'
    if source.get('paradox') or source.get('variety') == 'paradox' or ident.endswith('_paradox'):
        return 'paradox'
    return 'normal'


def normal_rookie(entry):
    return entry.get('stage') == 'rookie' and variety_of(entry) == 'normal'


def name_color(entry, catalog, default):
    """Identify rare forms without recoloring their supplied artwork."""
    return {'shiny': SHINY_GOLD, 'firewall': FIREWALL_ORANGE}.get(variety_of(entry, catalog), default)


def firewall_map_available(entry, catalog):
    """Only advertise FireWall encounters when a matching counterpart exists."""
    return _map_variety_available(entry, catalog, 'firewall')


def scan_hint(variety, state):
    """Share precise, independent mastery wording across discovery screens."""
    rewards = (state or {}).get('permanent_rewards', {})
    if variety in ('shiny', 'paradox', 'firewall'):
        name = VARIETY_NAMES[variety]
        rate = {'shiny': '1%', 'paradox': '2.5%', 'firewall': '0.7%'}[variety]
        return (f'{name} Mastery: {rate} chance · 5% → 6% on wild wins'
                if rewards.get(variety+'_scan_mastery') else
                f'{name}: {rate} encounter chance · +5% scan / defeat')
    active = [VARIETY_NAMES[k] for k in ('firewall','shiny','paradox') if rewards.get(k+'_scan_mastery')]
    return (f'{len(active)} scan masteries active · +20% on eligible wild wins' if len(active)>1 else
            f'{active[0]} Mastery: +20% scan on wild victories' if active else
            '100% unlocks reconstruction  ·  200% gives 5 ABI')


def shiny_map_available(entry, catalog):
    """A map advertises rare scans only if it has a matching Shiny encounter."""
    return _map_variety_available(entry, catalog, 'shiny')


def paradox_map_available(entry, catalog):
    """The atlas only advertises Paradox encounters with a catalog counterpart."""
    return _map_variety_available(entry, catalog, 'paradox')


def _map_variety_available(entry, catalog, variety):
    ids = entry.get(variety+'_encounters', [])
    if ids:
        return any(sid in catalog and variety_of(catalog[sid]) == variety for sid in ids)
    for sid in entry.get('encounters', []):
        species = catalog.get(sid, {})
        base_id = species.get('base_species') or species.get('base_id') or sid
        for suffix in ('_paradox', '_shiny', '_firewall'):
            if base_id.endswith(suffix):
                base_id = base_id[:-len(suffix)]
        if base_id + '_'+variety in catalog:
            return True
    return False
