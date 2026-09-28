"""Authoritative, deterministic-testable gameplay. All numerical balance is server owned.

Catalog art is authoritative for available species, not for Cyber Sleuth numerical data.
See docs/MECHANICS.md for the intentionally original rules and provenance boundary.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import re
import uuid
from pathlib import Path
from typing import Any

from venom.common.farm import normalize_farm_position
from venom.common import season as solo_season
from venom.common import story as story_mode
from venom.common.economy import CREDITS_PER_RUBY, MAX_CREDITS, normalize_intent, ruby_price


class GameError(ValueError):
    """A safe, user-readable rejection of a gameplay operation."""


SHOP = {
    "hp_s": {"name": "Small HP Capsule", "price": 60, "resource": "hp", "amount": 250},
    "hp_m": {"name": "Medium HP Capsule", "price": 180, "resource": "hp", "amount": 650},
    "hp_l": {"name": "Large HP Capsule", "price": 420, "resource": "hp", "amount": 2000},
    "sp_s": {"name": "Small SP Capsule", "price": 90, "resource": "sp", "amount": 25},
    "sp_m": {"name": "Medium SP Capsule", "price": 260, "resource": "sp", "amount": 65},
    "sp_l": {"name": "Large SP Capsule", "price": 600, "resource": "sp", "amount": 200},
}
FARM_CAPACITY = 100
FARM_BONUS_PER_STAT = 100
FARM_BONUS_TOTAL = 300
FARM_STATS = ("hp", "sp", "atk", "def", "int", "spd")
FARM_MEAT_DROP_CHANCE = .18
SHOP["digimeat_cam"] = {
    "name": "Friendship DigiMeat", "price": 150, "resource": "cam", "amount": 5,
    "category": "digimeat", "rarity": "common", "icon": "assets/ui/digifarm/digimeat.png",
    "description": "Feed a DigiFarm resident to gain 5 CAM (up to 100). An optional treat.",
}
SHOP["digimeat_abi"] = {
    "name": "ABI DigiMeat", "price": 6000, "resource": "abi", "amount": 1,
    "category": "digimeat", "rarity": "rare", "icon": "assets/ui/digifarm/digimeat.png",
    "description": "Permanently adds 1 ABI, up to 200. Use on a party partner at the DigiLab or "
                   "DigiFarm, or feed a farm resident. Kept through evolution; no de-digivolution needed.",
}
for _stat, _flavor in (("hp", "Vitality"), ("sp", "Spirit"), ("atk", "Power"),
                        ("def", "Guard"), ("int", "Wisdom"), ("spd", "Swift")):
    for _amount in (1, 5):
        SHOP[f"digimeat_{_stat}_{_amount}"] = {
            "name": f"{'Rare ' if _amount == 5 else ''}{_flavor} DigiMeat +{_amount}",
            "price": 25000 if _amount == 5 else 2500, "resource": _stat, "amount": _amount,
            "category": "digimeat", "rarity": "rare" if _amount == 5 else "uncommon",
            "icon": "assets/ui/digifarm/digimeat.png",
            "description": f"Permanently adds {_amount} {_stat.upper()} to a DigiFarm resident. "
                           "Kept through evolution. Limit: +100 per stat, +300 total.",
        }
TYPE_ADVANTAGE = {"vaccine": "virus", "virus": "data", "data": "vaccine"}
ATTRIBUTE_ADVANTAGE = {
    "fire": {"plant"}, "plant": {"water"}, "water": {"fire"},
    "electric": {"wind"}, "wind": {"earth"}, "earth": {"electric"},
    "light": {"dark"}, "dark": {"light"},
}
STAGE_RANK = {"fresh": 0, "in_training": 1, "rookie": 2, "champion": 3,
              "armor": 3, "hybrid": 3, "ultimate": 4, "mega": 5, "ultra": 6, "unknown": 2}
STAGE_LEVEL = {0: 1, 1: 1, 2: 1, 3: 15, 4: 30, 5: 45, 6: 60}
SKILL_NAMES = {"fire": "Flare Burst", "water": "Aqua Pulse", "plant": "Thorn Surge",
               "electric": "Volt Arc", "wind": "Gale Cutter", "earth": "Terra Impact",
               "light": "Radiant Lance", "dark": "Void Pulse", "neutral": "Data Burst"}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _integer(payload: dict, key: str, default: int = 0, minimum: int = 0,
             maximum: int = 10**9) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise GameError(f"{key.replace('_', ' ').title()} is out of range.")
    return value


def type_multiplier(attacker: str, defender: str) -> float:
    a, d = str(attacker).lower(), str(defender).lower()
    if TYPE_ADVANTAGE.get(a) == d:
        return 2.0
    if TYPE_ADVANTAGE.get(d) == a:
        return 0.5
    return 1.0


def attribute_multiplier(attack_attribute: str, defender_attribute: str) -> float:
    # Cyber Sleuth's attribute triangle grants a bonus, not Pokemon-style resistance.
    return 1.5 if str(defender_attribute).lower() in ATTRIBUTE_ADVANTAGE.get(
        str(attack_attribute).lower(), set()) else 1.0


def effectiveness(attacker: dict, defender: dict, attribute: str | None = None) -> float:
    return type_multiplier(attacker.get("type", "free"), defender.get("type", "free")) * attribute_multiplier(
        attribute if attribute is not None else attacker.get("attribute", "neutral"),
        defender.get("attribute", "neutral"))


def xp_required(level: int) -> int:
    """XP needed to move from this level to the next; xp is progress within level."""
    return 35 + int(12 * level ** 1.45)


class GameEngine:
    def __init__(self, root: str | Path, seed: int | None = None):
        self.root = Path(root)
        data_dir = self.root if (self.root / "catalog.json").exists() else self.root / "data"
        self.catalog = json.loads((data_dir / "catalog.json").read_text(encoding="utf-8"))
        mechanics_path = data_dir / "mechanics.json"
        self.rules = json.loads(mechanics_path.read_text(encoding="utf-8")) if mechanics_path.exists() else {}
        self.rng = random.Random(seed)
        self.species = {s["id"]: s for s in self.catalog.get("species", [])}
        self.maps = {m["id"]: m for m in self.catalog.get("maps", [])}
        self.tamers = {t["id"]: t for t in self.catalog.get("tamers", [])}
        if not self.species or not self.maps or not self.tamers:
            raise GameError("Asset catalog must contain species, maps and tamers. Run asset verification.")
        self._prepare_catalog()
        self.starters = [s["id"] for s in self.species.values()
                         if s.get("stage") == "rookie" and not s.get("paradox")]
        if not self.starters:
            raise GameError("No non-Paradox Rookie starters were imported.")
        self._pools: dict[str, tuple[list[str], list[str]]] = {}
        self._prepare_encounter_pools()

    def _prepare_catalog(self) -> None:
        by_name = {_key(s.get("name", s["id"])): s for s in self.species.values() if not s.get("paradox")}
        for name, override in self.rules.get("species_overrides", {}).items():
            species = by_name.get(_key(name))
            if species:
                species.update(override)
                species["mechanics_provenance"] = "Venom NXT curated type/attribute; original balanced stats"
        for species in self.species.values():
            if species.get("paradox"):
                base = self.species.get(species.get("base_id", ""))
                if base:
                    species["type"] = base.get("type", "free")
                    species["attribute"] = base.get("attribute", "neutral")
            species.setdefault("type", "free")
            species.setdefault("attribute", "neutral")
            species["type"] = str(species["type"]).lower()
            species["attribute"] = str(species["attribute"]).lower()
            species.setdefault("evolutions", [])
        # Curated family routes, with custom balance requirements, plus a clearly
        # labelled data-splice route for every uncharted species in the pack.
        for chain in self.rules.get("evolution_chains", []):
            for left, right in zip(chain, chain[1:]):
                a, b = by_name.get(_key(left)), by_name.get(_key(right))
                if a and b:
                    self._add_evolution(a, b, "curated_family")
        tiers: dict[int, list[dict]] = {}
        for species in self.species.values():
            if not species.get("paradox"):
                tiers.setdefault(STAGE_RANK.get(species.get("stage"), 2), []).append(species)
        for group in tiers.values():
            group.sort(key=lambda s: s["id"])
        for species in self.species.values():
            rank = STAGE_RANK.get(species.get("stage"), 2)
            valid = [x for x in species["evolutions"] if x.get("to") in self.species]
            species["evolutions"] = valid
            if not valid and rank < 6 and not species.get("paradox"):
                candidates = tiers.get(rank + 1, [])
                related = [c for c in candidates if c.get("attribute") == species.get("attribute")]
                candidates = related or candidates
                if candidates:
                    n = int.from_bytes(hashlib.sha256(species["id"].encode()).digest()[:4], "big")
                    self._add_evolution(species, candidates[n % len(candidates)], "original_data_splice")
        # Paradox partners retain their variant throughout the same evolution family.
        variants = {s.get("base_id"): s for s in self.species.values() if s.get("paradox")}
        for base_id, variant in variants.items():
            base = self.species.get(base_id)
            if not base:
                continue
            for route in base.get("evolutions", []):
                target = variants.get(route.get("to"))
                if target and not any(r.get("to") == target["id"] for r in variant["evolutions"]):
                    variant["evolutions"].append({**copy.deepcopy(route), "to": target["id"],
                                                   "provenance": "original_paradox_route"})
        # Reverse routes are recorded separately and preserve the monster's identity/CAM.
        self.devolutions: dict[str, list[dict]] = {}
        for species in self.species.values():
            for route in species["evolutions"]:
                self.devolutions.setdefault(route["to"], []).append({
                    "to": species["id"], "level": 5, "abi": 0, "cam": 0,
                    "devolve": True, "provenance": route.get("provenance", "catalog")})
        self.catalog["shop"] = copy.deepcopy(SHOP)
        self.catalog["rules"] = {"party_limit": 6, "active_limit": 3, "scan_cap": 200,
                                  "farm_capacity": FARM_CAPACITY,
                                  "farm_bonus_per_stat": FARM_BONUS_PER_STAT,
                                  "farm_bonus_total": FARM_BONUS_TOTAL,
                                  "farm_meat_drop_chance": FARM_MEAT_DROP_CHANCE,
                                  "paradox_encounter_chance": self.rules.get("paradox_encounter_chance", .025)}

    def _add_evolution(self, source: dict, target: dict, provenance: str) -> None:
        if any(x.get("to") == target["id"] for x in source["evolutions"]):
            return
        rank = STAGE_RANK.get(target.get("stage"), 2)
        level = {0: 3, 1: 5, 2: 8, 3: 15, 4: 30, 5: 45, 6: 60}[rank]
        abi = {0: 0, 1: 0, 2: 0, 3: 0, 4: 10, 5: 25, 6: 50}[rank]
        # Stats are evaluated against the current form at its required level.
        stat = "int" if target.get("attribute") in ("light", "dark", "water") else "atk"
        projected = self.stats_for(source, level, 0)
        source["evolutions"].append({"to": target["id"], "level": level, "abi": abi,
                                    "cam": max(0, (rank - 2) * 10),
                                    "stats": {stat: max(1, int(projected[stat] * .9))},
                                    "provenance": provenance})

    def _prepare_encounter_pools(self) -> None:
        # A new region must not move previously discoverable Dawn species. Keep
        # the original assignment against the original map set, then build the
        # expansion independently. Neither pool builder consumes gameplay RNG.
        self._pools.clear()
        legacy = [m for m in self.maps.values() if m.get("region_id") != "world_ds"]
        expansion = [m for m in self.maps.values() if m.get("region_id") == "world_ds"]
        if legacy:
            self._prepare_legacy_encounter_pools(legacy)
        if expansion:
            self._prepare_world_ds_encounter_pools(expansion)

    def _prepare_legacy_encounter_pools(self, maps: list[dict]) -> None:
        # Assign every normal species to at least one appropriate area. A compact
        # stable local pool makes scan collection possible even with thousands of sprites.
        maps = sorted(maps, key=lambda m: (int(m.get("level", 1)), m["id"]))
        pools: dict[str, list[str]] = {m["id"]: [] for m in maps}
        for species in self.species.values():
            if species.get("paradox"):
                continue
            level = STAGE_LEVEL[STAGE_RANK.get(species.get("stage"), 2)]
            candidates = sorted(maps, key=lambda m: abs(int(m.get("level", 1)) - level))
            band = [m for m in candidates if abs(int(m.get("level", 1)) - level) <= 12]
            band = band or candidates[:max(1, len(maps) // 8)]
            n = int.from_bytes(hashlib.sha256(species["id"].encode()).digest()[:4], "big")
            pools[band[n % len(band)]["id"]].append(species["id"])
        all_normal = [s for s in self.species.values() if not s.get("paradox")]
        paradoxes = [s for s in self.species.values() if s.get("paradox")]
        for area in maps:
            normal = pools[area["id"]]
            if not normal:
                near = sorted(all_normal, key=lambda s: abs(STAGE_LEVEL[STAGE_RANK.get(s.get("stage"), 2)] - int(area.get("level", 1))))
                normal = [s["id"] for s in near[:12]]
            p = [s["id"] for s in paradoxes if s.get("base_id") in normal]
            self._pools[area["id"]] = (normal, p)
        # Paradox-only imported species also remain discoverable.
        assigned = {sid for _, ps in self._pools.values() for sid in ps}
        for species in paradoxes:
            if species["id"] in assigned:
                continue
            level = STAGE_LEVEL[STAGE_RANK.get(species.get("stage"), 2)]
            area = min(maps, key=lambda m: abs(int(m.get("level", 1)) - level))
            self._pools[area["id"]][1].append(species["id"])
        fallback = [s["id"] for s in paradoxes]
        for area in maps:
            normal, rare = self._pools[area["id"]]
            if not rare and fallback:
                minimum = min(abs(STAGE_LEVEL[STAGE_RANK.get(self.species[s].get("stage"), 2)] - int(area.get("level", 1))) for s in fallback)
                self._pools[area["id"]] = normal, [s for s in fallback if abs(STAGE_LEVEL[STAGE_RANK.get(self.species[s].get("stage"), 2)] - int(area.get("level", 1))) == minimum]
            area["encounters"] = list(normal)
            area["paradox_encounters"] = list(self._pools[area["id"]][1])

    def _prepare_world_ds_encounter_pools(self, maps: list[dict]) -> None:
        """Stable, varied encounter habitats for the independent level 1–99 route.

        These are Venom NXT encounter placements, not a claim about the original
        DS game's encounter tables. Each stage spans a suitable progression band;
        per-map hashes avoid identical late-game fallback pools on every map.
        """
        maps = sorted(maps, key=lambda m: (int(m.get("level", 1)), m["id"]))
        bands = {0: (1, 10, 1), 1: (1, 14, 3), 2: (1, 24, 8),
                 3: (12, 40, 22), 4: (28, 59, 38),
                 5: (45, 99, 62), 6: (75, 99, 90)}
        normal_species = sorted((s for s in self.species.values() if not s.get("paradox")),
                                key=lambda s: s["id"])
        paradoxes = sorted((s for s in self.species.values() if s.get("paradox")),
                           key=lambda s: s["id"])

        def rank(species: dict) -> int:
            return STAGE_RANK.get(species.get("stage"), 2)

        def stable_order(namespace: str, identifier: str) -> bytes:
            return hashlib.sha256(f"world_ds:{namespace}:{identifier}".encode()).digest()

        def habitat(species: dict) -> list[dict]:
            low, high, preferred = bands[rank(species)]
            suitable = [m for m in maps if low <= int(m.get("level", 1)) <= high]
            near = [m for m in suitable if abs(int(m.get("level", 1)) - preferred) <= 12]
            return near or suitable or [min(maps, key=lambda m: abs(int(m.get("level", 1)) - preferred))]

        pools: dict[str, list[str]] = {m["id"]: [] for m in maps}
        # Give every imported species a home even if it is not selected among a
        # map's common visitors. Future species additions cannot change Dawn.
        for species in normal_species:
            candidates = habitat(species)
            area = min(candidates, key=lambda m: stable_order(species["id"], m["id"]))
            pools[area["id"]].append(species["id"])
        for area in maps:
            level = int(area.get("level", 1))
            candidates = [s for s in normal_species if bands[rank(s)][0] <= level <= bands[rank(s)][1]]
            if not candidates:
                nearest = min(abs(bands[rank(s)][2] - level) for s in normal_species)
                candidates = [s for s in normal_species if abs(bands[rank(s)][2] - level) == nearest]
            candidates.sort(key=lambda s: stable_order(area["id"], s["id"]))
            normal = pools[area["id"]]
            # At overlapping stage bands, keep both stages visible instead of
            # allowing the much larger Mega roster to crowd out all Ultras.
            for stage in sorted({rank(s) for s in candidates}):
                if not any(rank(self.species[sid]) == stage for sid in normal):
                    normal.append(next(s["id"] for s in candidates if rank(s) == stage))
            for species in candidates:
                if len(normal) >= 12:
                    break
                if species["id"] not in normal:
                    normal.append(species["id"])
            rare = [s["id"] for s in paradoxes if s.get("base_id") in normal]
            self._pools[area["id"]] = (normal, rare)
        assigned = {sid for area in maps for sid in self._pools[area["id"]][1]}
        for species in paradoxes:
            if species["id"] not in assigned:
                area = min(habitat(species), key=lambda m: stable_order(species["id"], m["id"]))
                self._pools[area["id"]][1].append(species["id"])
        for area in maps:
            normal, rare = self._pools[area["id"]]
            if not rare and paradoxes:
                level = int(area.get("level", 1))
                nearest = min(abs(bands[rank(s)][2] - level) for s in paradoxes)
                rare.extend(s["id"] for s in paradoxes if abs(bands[rank(s)][2] - level) == nearest)
            area["encounters"] = list(normal)
            area["paradox_encounters"] = list(rare)

    @staticmethod
    def wild_level_range(area: dict) -> tuple[int, int]:
        """Server-owned ranges; legacy maps retain their exact +/-2 rule."""
        level = max(1, min(99, int(area.get("level", 1))))
        low = max(1, min(99, int(area.get("level_min", level - 2))))
        high = max(low, min(99, int(area.get("level_max", level + 2))))
        return low, high

    @staticmethod
    def stats_for(species: dict, level: int, abi: int = 0,
                  bonuses: dict[str, int] | None = None) -> dict[str, int]:
        base = species.get("base_stats", {})
        rank = STAGE_RANK.get(species.get("stage"), 2)
        defaults = {"hp": 180, "sp": 35, "atk": 28, "def": 22, "int": 24, "spd": 24}
        growth = {"hp": 18 + rank * 2, "sp": 2, "atk": 3 + rank * .3,
                  "def": 2.5 + rank * .3, "int": 3 + rank * .3, "spd": 2 + rank * .2}
        bonus = 1 + min(200, max(0, abi)) / 1000
        return {k: max(1, int((int(base.get(k, defaults[k])) + (level - 1) * growth[k]) * bonus))
                   + max(0, int((bonuses or {}).get(k, 0)))
                for k in defaults}

    def _monster(self, species_id: str, level: int = 1, abi: int = 0, cam: int = 0,
                 farm_bonuses: dict[str, int] | None = None) -> dict:
        species = self.species[species_id]
        stat = self.stats_for(species, level, abi, farm_bonuses)
        monster = {"uid": uuid.uuid4().hex, "species_id": species_id, "name": species["name"],
                   "stage": species.get("stage", "unknown"), "level": level, "xp": 0,
                   "next_xp": xp_required(level), "abi": abi, "cam": cam,
                   "type": species["type"], "attribute": species["attribute"],
                   "paradox": bool(species.get("paradox")), "history": [],
                   "farm_bonuses": copy.deepcopy(farm_bonuses or {}),
                   **stat, "max_hp": stat["hp"], "max_sp": stat["sp"]}
        monster["skills"] = self._skills(monster)
        return monster

    @staticmethod
    def _skills(monster: dict) -> list[dict]:
        attribute = monster.get("attribute", "neutral")
        rank = STAGE_RANK.get(monster.get("stage"), 2)
        return [{"id": "burst", "name": SKILL_NAMES.get(attribute, "Data Burst"),
                 "sp": 5 + rank, "power": 1.55, "attribute": attribute, "kind": "magic"},
                {"id": "strike", "name": "Power Strike", "sp": 4 + rank,
                 "power": 1.45, "attribute": "neutral", "kind": "physical"}]

    def new_player(self, username: str, tamer: str, starter: str) -> dict:
        if tamer not in self.tamers:
            raise GameError("Choose one of the imported tamers.")
        if starter not in self.starters:
            raise GameError("Your first partner must be a regular Rookie Digimon.")
        # Expansion ordering or a new level-one map cannot silently change the
        # established home/first field for newly created characters.
        home_maps = [m for m in self.maps.values() if m.get("region_id") != "world_ds"]
        area = min(home_maps or self.maps.values(), key=lambda m: (int(m.get("level", 1)), m["id"]))
        x, y = area.get("spawn", [area.get("width", 1024) / 2, area.get("height", 768) / 2])
        state = {"username": str(username), "tamer": tamer, "map_id": area["id"],
                 "x": float(x), "y": float(y), "credits": 650,
                 "party": [self._monster(starter, cam=10)], "storage": [], "scan": {},
                 "inventory": {"hp_s": 5, "hp_m": 0, "hp_l": 0, "sp_s": 3, "sp_m": 0, "sp_l": 0,
                               "digimeat_cam": 3},
                 "in_lab": False, "in_farm": True, "battle": None, "events": [], "catalog_version": "0.1.0",
                 "wins": 0, "losses": 0, "shop": copy.deepcopy(SHOP)}
        self._refresh(state)
        self._event(state, "message", text="Welcome home to your private DigiFarm! Explore to collect scan data, "
                    "materialize partners, and let stored Digimon relax here. Feeding is always optional.")
        return state

    def handle(self, state: dict, op: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise GameError("Malformed gameplay request.")
        handlers = {"encounter": self._encounter, "battle": self._battle, "digilab": self._digilab,
                    "materialize": self._materialize, "evolve": self._evolve, "party": self._party,
                    "shop": self._shop, "item": self._item, "travel": self._travel,
                    "digifarm": self._digifarm, "season": self._season, "story": self._story}
        if op not in handlers:
            raise GameError("Unknown gameplay operation.")
        if state.get("in_season") and op not in ("season", "battle"):
            raise GameError("Use Save & Return to World before another activity.")
        if state.get("in_story") and op in ("season", "travel", "encounter"):
            raise GameError("Use the Story journal for training and travel, or Save & Return to World for another activity.")
        state["events"] = []
        try:
            handlers[op](state, payload)
        except (solo_season.SeasonError, story_mode.StoryError) as exc:
            raise GameError(str(exc)) from exc
        self._refresh(state)
        return state

    def _refresh(self, state: dict) -> None:
        # Additive save migration: never move existing players or discard old storage.
        state.setdefault("in_farm", False)
        state.setdefault("in_season", False)
        state.setdefault("in_story", False)
        if state.get("season"):
            solo_season.update_views(state["season"], state)
        normalize_farm_position(state)
        if state.get("story"):
            story_mode.update_view(self, state)
        state.setdefault("storage", [])
        state["farm"] = {"capacity": FARM_CAPACITY,
                         "residents": min(FARM_CAPACITY, len(state["storage"])),
                         "legacy_overflow": max(0, len(state["storage"]) - FARM_CAPACITY),
                         "bonus_per_stat": FARM_BONUS_PER_STAT, "bonus_total": FARM_BONUS_TOTAL,
                         "feeding_optional": True}
        for monster in state["party"] + state["storage"]:
            if not monster.get("uid"):
                monster["uid"] = uuid.uuid4().hex
            monster.setdefault("farm_bonuses", {})
        state["evolution_options"] = [self.evolution_options(m) for m in state["party"]]
        state["shop"] = copy.deepcopy(SHOP)
        for item in state["shop"].values():
            item["ruby_price"] = ruby_price(item["price"])
        for monster in state["party"]:
            monster["next_xp"] = xp_required(monster["level"])
            monster["skills"] = self._skills(monster)

    def evolution_options(self, monster: dict) -> list[dict]:
        species_id = monster["species_id"]
        routes = self.species[species_id].get("evolutions", []) + self.devolutions.get(species_id, [])
        seen = set()
        result = []
        for route in routes:
            target = route.get("to")
            if target not in self.species or target in seen:
                continue
            seen.add(target)
            requirements = {k: int(route.get(k, 0)) for k in ("level", "abi", "cam")}
            unmet = [f"{k.upper()} {v}" for k, v in requirements.items() if monster.get(k, 0) < v]
            for stat, value in route.get("stats", {}).items():
                actual = monster.get("max_" + stat, monster.get(stat, 0))
                if actual < value:
                    unmet.append(f"{stat.upper()} {value}")
            result.append({**route, "name": self.species[target]["name"], "eligible": not unmet,
                           "missing": unmet, "devolve": bool(route.get("devolve"))})
        # Keep data-splice de-evolution UI manageable. Known previous forms always first.
        history = monster.get("history", [])
        result.sort(key=lambda r: (r.get("devolve", False), r["to"] not in history, r["name"]))
        return result[:30]

    @staticmethod
    def _event(state: dict, kind: str, side: str = "player", index: int = 0,
               amount: float = 0, effectiveness: float = 1, text: str = "", **extra: Any) -> None:
        state.setdefault("events", []).append({"kind": kind, "side": side, "index": index,
                                               "amount": amount, "effectiveness": effectiveness,
                                               "text": text, **extra})

    @staticmethod
    def _peace(state: dict) -> None:
        if state.get("battle"):
            raise GameError("Finish or escape the current battle first.")

    def _lab_only(self, state: dict) -> None:
        self._peace(state)
        if not state.get("in_lab"):
            raise GameError("Return to the DigiLab for this action.")

    def _hub_only(self, state: dict) -> None:
        self._peace(state)
        if not (state.get("in_lab") or state.get("in_farm")):
            raise GameError("Return to your DigiFarm or the DigiLab for this action.")

    @staticmethod
    def _party_member(state: dict, payload: dict, key: str = "party_index") -> tuple[int, dict]:
        index = _integer(payload, key, maximum=max(0, len(state["party"]) - 1))
        if index >= len(state["party"]):
            raise GameError("That party slot is empty.")
        return index, state["party"][index]

    def _encounter(self, state: dict, payload: dict) -> None:
        self._peace(state)
        if state.get("in_lab") or state.get("in_farm"):
            raise GameError("Return to the world before searching for wild Digimon.")
        active = [i for i, m in enumerate(state["party"][:3]) if m["hp"] > 0]
        if not active:
            raise GameError("Your battle team needs healing at the DigiLab.")
        area = self.maps[state["map_id"]]
        normal, paradox = self._pools[area["id"]]
        count = self.rng.choices([1, 2, 3], weights=[70, 25, 5] if len(active) == 1 else [25, 40, 35])[0]
        enemy_level = max(1, min(99, int(area.get("level", 1))))
        low, high = self.wild_level_range(area)
        # Preserve the legacy edge-level probability distribution (clamping a
        # +/-2 roll) while expansion maps honor their displayed explicit ranges.
        explicit_range = "level_min" in area or "level_max" in area
        enemies = [self._monster(self.rng.choice(normal),
                    self.rng.randint(low, high) if explicit_range else
                    max(1, min(99, enemy_level + self.rng.randint(-2, 2)))) for _ in range(count)]
        if paradox and self.rng.random() < self.rules.get("paradox_encounter_chance", .025):
            slot = self.rng.randrange(count)
            enemies[slot] = self._monster(self.rng.choice(paradox), enemies[slot]["level"])
        # Solo players can still meet 2/3 enemies; smaller wild HP keeps the opening playable.
        for enemy in enemies:
            enemy["hp"] = enemy["max_hp"] = max(20, int(enemy["max_hp"] * .72))
        state["battle"] = {"id": uuid.uuid4().hex, "enemies": enemies, "active": active,
                           "turn": 0, "actor": active[0], "clock": 0.0, "queue": [], "scanned": []}
        queue = state["battle"]["queue"]
        for i in active:
            queue.append({"side": "player", "index": i, "at": 500 / max(1, state["party"][i]["spd"])})
        for i, enemy in enumerate(enemies):
            queue.append({"side": "enemy", "index": i, "at": 500 / max(1, enemy["spd"]) + .001})
        names = ", ".join(e["name"] for e in enemies)
        self._event(state, "message", text=f"Wild encounter: {names}!")
        self._advance(state)

    def _battle(self, state: dict, payload: dict) -> None:
        battle = state.get("battle")
        if not battle:
            raise GameError("There is no battle in progress.")
        if battle.get("kind") in ("season", "story"):
            if (payload.get("battle_id") != battle["id"] or
                    isinstance(payload.get("expected_turn"), bool) or
                    not isinstance(payload.get("expected_turn"), int) or
                    payload["expected_turn"] != battle["turn"]):
                raise GameError("This battle turn has changed. Wait for the current battle controls.")
        action = payload.get("action", "attack")
        if not isinstance(action, str) or action not in {"attack", "skill", "item", "flee", "guard", "swap"}:
            raise GameError("Unknown battle action.")
        actor_index = battle["actor"]
        actor = state["party"][actor_index]
        if action == "flee":
            if battle.get("kind") == "season" or (battle.get("kind") == "story" and not battle.get("story_training")):
                raise GameError("Tamer matches cannot be fled. Finish this match; disconnecting safely pauses it.")
            if battle.get("kind") == "story":
                story_mode.cancel_training(state)
            state["battle"] = None
            for monster in state["party"]:
                monster.pop("guard", None)
            self._event(state, "flee", text="You withdrew safely. Defeated enemies' scan data is retained.")
            return
        if action == "item":
            self._use_item(state, payload)
        elif action == "guard":
            actor["guard"] = True
            self._event(state, "message", index=actor_index, text=f"{actor['name']} braces for incoming damage.")
        elif action == "swap":
            reserve_index = _integer(payload, "party_index", maximum=len(state["party"]) - 1)
            if reserve_index in battle["active"] or state["party"][reserve_index]["hp"] <= 0:
                raise GameError("Choose a healthy reserve partner.")
            pos = battle["active"].index(actor_index)
            battle["active"][pos] = reserve_index
            battle["queue"] = [q for q in battle["queue"] if not (q["side"] == "player" and q["index"] == actor_index)]
            self._queue(battle, "player", reserve_index, state["party"][reserve_index])
            self._event(state, "message", text=f"{state['party'][reserve_index]['name']} joins the battle.")
            self._advance(state)
            return
        else:
            target_index = _integer(payload, "target", maximum=len(battle["enemies"]) - 1)
            target = battle["enemies"][target_index]
            if target["hp"] <= 0:
                raise GameError("That enemy has already been defeated.")
            skill = None
            if action == "skill":
                skills = actor.get("skills") or self._skills(actor)
                skill_index = _integer(payload, "skill_index", maximum=len(skills) - 1)
                skill = skills[skill_index]
                if actor["sp"] < skill["sp"]:
                    raise GameError("Not enough SP. Attack is free, or use an SP Capsule.")
                actor["sp"] -= skill["sp"]
            actor.pop("guard", None)
            self._strike(state, actor, target, "player", actor_index, target_index, action, skill)
            if target["hp"] <= 0:
                self._scan_defeat(state, target_index)
        if self._check_end(state):
            return
        self._queue(battle, "player", actor_index, actor)
        self._advance(state)

    def _queue(self, battle: dict, side: str, index: int, monster: dict) -> None:
        battle["queue"].append({"side": side, "index": index,
                                "at": battle["clock"] + 1000 / max(1, monster["spd"])})

    def _advance(self, state: dict) -> None:
        # Process enemy turns until the next living player decision. Queue survives reconnect.
        for _ in range(100):
            if self._check_end(state):
                return
            battle = state["battle"]
            battle["queue"].sort(key=lambda q: (q["at"], q["side"] == "enemy", q["index"]))
            if not battle["queue"]:
                raise GameError("Battle timeline is empty. Please reconnect.")
            node = battle["queue"].pop(0)
            side, index = node["side"], node["index"]
            roster = state["party"] if side == "player" else battle["enemies"]
            actor = roster[index]
            if actor["hp"] <= 0 or (side == "player" and index not in battle["active"]):
                continue
            battle["clock"] = node["at"]
            battle["turn"] += 1
            if side == "player":
                battle["actor"] = index
                # Guard lasts until this partner's next action opportunity.
                actor.pop("guard", None)
                return
            living = [i for i in battle["active"] if state["party"][i]["hp"] > 0]
            target_index = self.rng.choice(living)
            target = state["party"][target_index]
            skill = actor["skills"][0]
            use_skill = actor["sp"] >= skill["sp"] and self.rng.random() < .45
            if use_skill:
                actor["sp"] -= skill["sp"]
            self._strike(state, actor, target, "enemy", index, target_index,
                         "skill" if use_skill else "attack", skill if use_skill else None)
            self._queue(battle, "enemy", index, actor)
        raise GameError("Battle timeline exceeded its safety limit.")

    def _strike(self, state: dict, attacker: dict, defender: dict, side: str,
                attacker_index: int, target_index: int, action: str, skill: dict | None = None) -> None:
        magic = skill is not None and skill.get("kind") == "magic"
        power = skill["power"] if skill else 1.0
        attack = attacker["int"] if magic else attacker["atk"]
        defense = defender["int"] if magic else defender["def"]
        attribute = skill["attribute"] if skill else "neutral"
        multiplier = effectiveness(attacker, defender, attribute)
        damage = max(1, int((8 + attack * .72 - defense * .28) * power * multiplier * self.rng.uniform(.92, 1.08)))
        if side == "enemy":
            damage = max(1, int(damage * .72))
        combo = False
        if side == "player" and attacker.get("cam", 0) >= 20:
            allies = [state["party"][i] for i in state["battle"]["active"]
                      if i != attacker_index and state["party"][i]["hp"] > 0]
            if allies and self.rng.random() < attacker["cam"] / 500:
                damage = int(damage * 1.25)
                combo = True
        if defender.get("guard"):
            damage = max(1, damage // 2)
        actual = min(defender["hp"], damage)
        defender["hp"] -= actual
        target_side = "enemy" if side == "player" else "player"
        move = skill["name"] if skill else "Attack"
        label = "Super effective!" if multiplier > 1 else "Not very effective." if multiplier < 1 else ""
        text = f"{attacker['name']} uses {move}: {actual} damage. {label}"
        if combo:
            text += " CAM Cross Combo!"
        self._event(state, "damage", target_side, target_index, actual, multiplier, text.strip(),
                    attacker_side=side, attacker_index=attacker_index, attribute=attribute,
                    move=move, combo=combo, defeated=defender["hp"] <= 0)

    def _scan_defeat(self, state: dict, enemy_index: int) -> None:
        battle = state["battle"]
        if battle.get("kind") == "season" or (battle.get("kind") == "story" and not battle.get("story_training")):
            return  # Trainer partners are never collectible wild scan data.
        if enemy_index in battle["scanned"]:
            return
        battle["scanned"].append(enemy_index)
        enemy = battle["enemies"][enemy_index]
        gain = self.rules.get("paradox_scan_gain", 5) if enemy.get("paradox") else self.rules.get("normal_scan_gain", 20)
        # Keep ordinary defeat scans intact; mastery is earned only when the
        # whole wild encounter is won. This pending amount survives reconnects
        # with the battle and disappears naturally on fleeing or defeat.
        if enemy.get("paradox") and state.get("permanent_rewards", {}).get("paradox_scan_mastery"):
            pending = battle.setdefault("paradox_mastery_pending", {})
            sid = enemy["species_id"]
            pending[sid] = round(pending.get(sid, 0) + gain * .20, 6)
        sid = enemy["species_id"]
        old = state["scan"].get(sid, 0)
        state["scan"][sid] = min(200, old + gain)
        self._event(state, "scan", "enemy", enemy_index, state["scan"][sid] - old,
                    text=f"{enemy['name']}: {state['scan'][sid]}% scan data (+{state['scan'][sid] - old}%).",
                    species_id=sid, total=state["scan"][sid])

    def _award_paradox_mastery(self, state: dict) -> None:
        """Pay the permanent 20% wild-victory bonus once, without rounding up.

        Story guardians, quest tamers and Season opponents never call the scan
        defeat path. Popping pending rewards also makes repeated settlement
        harmless. Fractional custom scan rates retain their exact bonus.
        """
        battle = state.get("battle") or {}
        pending = battle.pop("paradox_mastery_pending", {})
        if not state.get("permanent_rewards", {}).get("paradox_scan_mastery"):
            return
        for sid, bonus in pending.items():
            old = state["scan"].get(sid, 0)
            total = round(min(200, old + bonus), 6)
            if total == int(total):
                total = int(total)
            state["scan"][sid] = total
            gained = round(total - old, 6)
            if gained > 0:
                index = next((i for i, enemy in enumerate(battle.get("enemies", []))
                              if enemy["species_id"] == sid), 0)
                self._event(state, "scan", "enemy", index, amount=gained, species_id=sid, total=total,
                            text=f"Paradox Scan Mastery: {self.species[sid]['name']} +{gained:g}% bonus scan ({total:g}% total).")

    def _check_end(self, state: dict) -> bool:
        battle = state.get("battle")
        if not battle:
            return True
        if battle.get("kind") in ("season", "story"):
            won = not any(e["hp"] > 0 for e in battle["enemies"])
            lost = not any(state["party"][i]["hp"] > 0 for i in battle["active"])
            if won or lost:
                if battle.get("kind") == "story":
                    if won and battle.get("story_training"):
                        self._award_paradox_mastery(state)
                    story_mode.settle(self, state, won)
                else:
                    self._finish_season_battle(state, won)
                return True
            return False
        if not any(e["hp"] > 0 for e in battle["enemies"]):
            self._award_paradox_mastery(state)
            enemies = battle["enemies"]
            xp = sum(24 + e["level"] * 12 + STAGE_RANK.get(e.get("stage"), 2) * 8 for e in enemies)
            credits = sum(25 + e["level"] * 7 for e in enemies)
            state["credits"] += credits
            state["wins"] = state.get("wins", 0) + 1
            for index, monster in enumerate(state["party"]):
                monster["cam"] = min(100, monster["cam"] + (2 if index in battle["active"] else 1))
                self._add_xp(state, monster, xp if index in battle["active"] else max(1, xp // 2), index)
                monster.pop("guard", None)
            state["battle"] = None
            self._event(state, "win", amount=credits, text=f"Victory! +{credits} credits and {xp} XP. Scan data secured.", xp=xp)
            if self.rng.random() < FARM_MEAT_DROP_CHANCE and state["inventory"].get("digimeat_cam", 0) < 999:
                state["inventory"]["digimeat_cam"] = state["inventory"].get("digimeat_cam", 0) + 1
                self._event(state, "loot", amount=1, item="digimeat_cam",
                            text="Battle reward: Friendship DigiMeat ×1. An optional +5 CAM treat for a DigiFarm resident.")
            return True
        if not any(state["party"][i]["hp"] > 0 for i in battle["active"]):
            state["losses"] = state.get("losses", 0) + 1
            state["battle"] = None
            self._enter_lab(state)
            self._event(state, "lose", text="Your battle team was defeated. DigiLab emergency recovery restored all partners; no credits or scan data lost.")
            return True
        return False

    def _story(self, state: dict, payload: dict) -> None:
        story_mode.handle(self, state, payload)

    def _season(self, state: dict, payload: dict) -> None:
        action = payload.get("action", "enter")
        if action == "enter":
            if state.get("in_season"):
                self._event(state, "message", text="Your private Season is ready to continue.")
                return
            self._peace(state)
            if not state.get("season"):
                state["season"] = solo_season.create_career(state, self.species, self.tamers, self.starters)
            state["season_return_location"] = {key: copy.deepcopy(state.get(key)) for key in
                                                ("map_id", "x", "y", "in_lab", "in_farm")}
            state.update(in_season=True, in_lab=False, in_farm=False)
            self._event(state, "message", text="Welcome to your private World Circuit. Your career advances only when you play.")
            return
        if action not in ("return", "start", "next"):
            raise GameError("Unknown Season Mode action.")
        if not state.get("in_season") or not state.get("season"):
            raise GameError("Enter Season Mode to continue your private career.")
        if action == "return":
            if state.get("battle"):
                raise GameError("Finish your Season match before returning to the world. Disconnecting safely pauses the match.")
            location = state.pop("season_return_location", {})
            if location.get("map_id") in self.maps:
                state.update(location)
            state["in_season"] = False
            self._event(state, "message", text="Season saved. Your calendar, champion and booked matches will wait for your return.")
            return
        self._peace(state)
        if action == "next":
            solo_season.next_week(state, payload.get("token"))
            self._event(state, "message", text=f"Week {state['season']['week']} is booked. Your next match is ready now.")
            return
        season = state["season"]
        solo_season.update_views(season, state)
        fixture = solo_season.begin_match(season, payload.get("token"))
        opponent_id = fixture["away_id"] if fixture["home_id"] == solo_season.PLAYER_ID else fixture["home_id"]
        opponent = solo_season.member(season, opponent_id)
        # League recovery is independent of the farm/lab and preserves partner identities.
        for monster in state["party"]:
            monster["hp"], monster["sp"] = monster["max_hp"], monster["max_sp"]
            monster.pop("guard", None)
        active = list(range(min(3, len(state["party"]))))
        enemies = [self._monster(partner["species_id"], partner["level"],
                                 abi=min(200, opponent["development"] // 6),
                                 cam=min(100, 10 + opponent["development"] // 3))
                   for partner in opponent["team"][:len(active)]]
        battle = {"id": uuid.uuid4().hex, "kind": "season", "season": True,
                  "season_card_token": season["card"]["token"], "season_match_id": fixture["id"],
                  "opponent_id": opponent_id, "opponent_name": opponent["name"],
                  "title_match": fixture["title_match"], "enemies": enemies, "active": active,
                  "turn": 0, "actor": active[0], "clock": 0.0, "queue": [], "scanned": []}
        state["battle"] = battle
        for index in active:
            battle["queue"].append({"side": "player", "index": index,
                                    "at": 500 / max(1, state["party"][index]["spd"])})
        for index, enemy in enumerate(enemies):
            battle["queue"].append({"side": "enemy", "index": index,
                                    "at": 500 / max(1, enemy["spd"]) + .001})
        self._event(state, "message", text=f"Season match: {state['username']} versus {opponent['name']}. Fight with your normal controls. No fleeing!")
        self._advance(state)

    def _finish_season_battle(self, state: dict, won: bool) -> None:
        battle = state["battle"]
        season = state["season"]
        fixture = solo_season.human_match(season)
        if (battle.get("season_card_token") != season["card"]["token"] or
                battle.get("season_match_id") != fixture["id"]):
            raise GameError("The saved Season fixture does not match this battle.")
        solo_season.finish_human(season, won, self.species)
        credits = xp = 0
        if won:
            xp = sum(24 + e["level"] * 12 + STAGE_RANK.get(e.get("stage"), 2) * 8 for e in battle["enemies"])
            credits = sum(25 + e["level"] * 7 for e in battle["enemies"])
            state["credits"] += credits
            state["wins"] = state.get("wins", 0) + 1
            for index, monster in enumerate(state["party"]):
                monster["cam"] = min(100, monster["cam"] + (2 if index in battle["active"] else 1))
                self._add_xp(state, monster, xp if index in battle["active"] else max(1, xp // 2), index)
        else:
            state["losses"] = state.get("losses", 0) + 1
        for monster in state["party"]:
            monster["hp"], monster["sp"] = monster["max_hp"], monster["max_sp"]
            monster.pop("guard", None)
        state["battle"] = None
        text = (f"Season victory! +{credits} credits and {xp} XP. " if won else "Season defeat. Your career continues. ")
        self._event(state, "win" if won else "lose", amount=credits, xp=xp,
                    text=text + "Partners recovered. The complete weekly results are ready.")
        self._event(state, "season_result", won=won, week=season["week"],
                    text="Review this week's card, then continue immediately to the next fictional week.")

    def _add_xp(self, state: dict, monster: dict, amount: int, index: int) -> None:
        monster["xp"] += amount
        original_level = monster["level"]
        while monster["level"] < 99 and monster["xp"] >= xp_required(monster["level"]):
            monster["xp"] -= xp_required(monster["level"])
            monster["level"] += 1
        if monster["level"] == 99:
            monster["xp"] = 0
        if monster["level"] > original_level:
            old_hp, old_sp = monster["max_hp"], monster["max_sp"]
            stats = self.stats_for(self.species[monster["species_id"]], monster["level"], monster["abi"],
                                   monster.get("farm_bonuses"))
            for stat in ("atk", "def", "int", "spd"):
                monster[stat] = stats[stat]
            monster["max_hp"], monster["max_sp"] = stats["hp"], stats["sp"]
            # Level-up restores the increase only; a defeated partner remains defeated.
            if monster["hp"] > 0:
                monster["hp"] += stats["hp"] - old_hp
            monster["sp"] += stats["sp"] - old_sp
            self._event(state, "message", index=index, text=f"{monster['name']} reached level {monster['level']}!")

    def _enter_lab(self, state: dict) -> None:
        if not (state.get("in_lab") or state.get("in_farm")):
            state["return_location"] = {"map_id": state["map_id"], "x": state["x"], "y": state["y"]}
        state["in_lab"] = True
        state["in_farm"] = False
        for monster in state["party"]:
            monster["hp"], monster["sp"] = monster["max_hp"], monster["max_sp"]
            monster.pop("guard", None)

    def _digilab(self, state: dict, payload: dict) -> None:
        self._peace(state)
        action = payload.get("action", "enter")
        if action == "enter":
            self._enter_lab(state)
            self._event(state, "heal", text="DigiLab recovery complete. Your entire party's HP and SP are restored.")
        elif action == "heal":
            self._lab_only(state)
            self._enter_lab(state)
            self._event(state, "heal", text="All party HP and SP restored.")
        elif action == "return":
            self._lab_only(state)
            location = state.get("return_location")
            if location and location.get("map_id") in self.maps:
                state.update(location)
            state["in_lab"] = False
            self._event(state, "message", text="Returned to the exact point where you left the world.")
        else:
            raise GameError("Unknown DigiLab action.")

    def _digifarm(self, state: dict, payload: dict) -> None:
        action = payload.get("action", "enter")
        if action == "enter":
            if state.get("battle"):
                if payload.get("forfeit") is not True:
                    raise GameError("Confirm leaving this battle before returning home. No victory rewards will be earned.")
                self._battle(state, {"action": "flee", "battle_id": state["battle"].get("id"),
                                     "expected_turn": state["battle"].get("turn")})
            if not (state.get("in_farm") or state.get("in_lab")):
                state["return_location"] = {"map_id": state["map_id"], "x": state["x"], "y": state["y"]}
            state.update(in_farm=True, in_lab=False)
            self._event(state, "message", text="Welcome home. Your stored Digimon are relaxing in your private DigiFarm.")
        elif action == "return":
            self._peace(state)
            if not state.get("in_farm"):
                raise GameError("You are not at your DigiFarm.")
            location = state.get("return_location", {})
            if location.get("map_id") in self.maps:
                state.update({key: location[key] for key in ("map_id", "x", "y")})
            state.update(in_farm=False, in_lab=False)
            self._event(state, "message", text="Returned to the field. Your DigiFarm residents are safe at home.")
        elif action == "feed":
            self._feed(state, payload)
        else:
            raise GameError("Unknown DigiFarm action.")

    def _feed(self, state: dict, payload: dict) -> None:
        self._peace(state)
        if not state.get("in_farm"):
            raise GameError("Feed stored Digimon at your DigiFarm.")
        uid = payload.get("uid")
        if not isinstance(uid, str) or not 1 <= len(uid) <= 64:
            raise GameError("Choose a DigiFarm resident to feed.")
        monster = next((m for m in state.get("storage", [])[:FARM_CAPACITY] if m.get("uid") == uid), None)
        if monster is None:
            raise GameError("That Digimon is not a resident of your DigiFarm. Store a party member here first.")
        item_id = payload.get("item")
        if not isinstance(item_id, str) or item_id not in SHOP or SHOP[item_id].get("category") != "digimeat":
            raise GameError("Choose a DigiMeat treat from your inventory.")
        quantity = _integer(payload, "quantity", 1, 1, 99)
        if state["inventory"].get(item_id, 0) < quantity:
            raise GameError("You do not have enough of that DigiMeat.")
        item = SHOP[item_id]
        resource, gain = item["resource"], item["amount"] * quantity
        if resource == "abi":
            self._increase_abi(monster, gain)
        elif resource == "cam":
            missing = 100 - monster.get("cam", 0)
            if missing <= 0:
                raise GameError("This Digimon already has 100 CAM. No treat was consumed.")
            if quantity > math.ceil(missing / item["amount"]):
                raise GameError("Choose fewer treats: that quantity would waste DigiMeat at the 100 CAM limit.")
            gain = min(gain, missing)
            monster["cam"] = monster.get("cam", 0) + gain
        else:
            bonuses = monster.get("farm_bonuses", {})
            if bonuses.get(resource, 0) + gain > FARM_BONUS_PER_STAT:
                raise GameError(f"DigiFarm bonuses are limited to +{FARM_BONUS_PER_STAT} per stat. No treat was consumed.")
            if sum(bonuses.get(stat, 0) for stat in FARM_STATS) + gain > FARM_BONUS_TOTAL:
                raise GameError(f"DigiFarm bonuses are limited to +{FARM_BONUS_TOTAL} total. No treat was consumed.")
            bonuses = dict(bonuses)
            bonuses[resource] = bonuses.get(resource, 0) + gain
            monster["farm_bonuses"] = bonuses
            if resource in ("hp", "sp"):
                monster["max_" + resource] += gain
                if resource == "sp" or monster[resource] > 0:
                    monster[resource] += gain
            else:
                monster[resource] += gain
        state["inventory"][item_id] -= quantity
        self._event(state, "feed", amount=gain, uid=uid, item=item_id, resource=resource, quantity=quantity,
                    text=f"{monster['name']} enjoyed {quantity} × {item['name']}: +{gain} {resource.upper()}" +
                    (" permanently!" if resource != "cam" else "!"))

    def _increase_abi(self, monster: dict, gain: int) -> None:
        """ABI is a partner attribute, never part of the separate farm stat pool.

        Validate and calculate every value before mutating the partner. Raising
        its maxima restores only the increase, just like levelling, and never
        revives a defeated partner or resets its training progress.
        """
        abi = monster.get("abi", 0)
        if abi >= 200:
            raise GameError("This Digimon already has 200 ABI. No treat was consumed.")
        if abi + gain > 200:
            raise GameError("Choose fewer treats: that quantity would waste DigiMeat at the 200 ABI limit.")
        abi += gain
        stats = self.stats_for(self.species[monster["species_id"]], monster["level"], abi,
                               monster.get("farm_bonuses"))
        hp = (min(stats["hp"], max(1, monster["hp"] + stats["hp"] - monster["max_hp"]))
              if monster["hp"] > 0 else 0)
        sp = min(stats["sp"], max(0, monster["sp"] + stats["sp"] - monster["max_sp"]))
        monster.update(abi=abi, max_hp=stats["hp"], max_sp=stats["sp"], hp=hp, sp=sp,
                       **{key: stats[key] for key in ("atk", "def", "int", "spd")})

    def _materialize(self, state: dict, payload: dict) -> None:
        self._hub_only(state)
        sid = payload.get("species_id")
        if sid not in self.species:
            raise GameError("Unknown Digimon species.")
        scan = state["scan"].get(sid, 0)
        if scan < 100:
            raise GameError("Materialization needs at least 100% scan data. Defeat more of this species.")
        if len(state["storage"]) >= FARM_CAPACITY and len(state["party"]) >= 6:
            raise GameError("Your DigiFarm is full (100 residents). Make room before materializing another partner.")
        # Consume the entire accumulated scan, rewarding 200% with ABI 5.
        monster = self._monster(sid, abi=min(5, int((scan - 100) / 20)))
        state["scan"][sid] = 0
        dest = state["party"] if len(state["party"]) < 6 else state["storage"]
        dest.append(monster)
        where = "party" if dest is state["party"] else "DigiFarm"
        self._event(state, "message", text=f"{monster['name']} materialized into your {where} with ABI {monster['abi']}.")

    def _evolve(self, state: dict, payload: dict) -> None:
        self._hub_only(state)
        index, monster = self._party_member(state, payload)
        target = payload.get("to")
        route = next((r for r in self.evolution_options(monster) if r["to"] == target), None)
        if not route:
            raise GameError("That evolution route is not available for this partner.")
        if not route["eligible"]:
            raise GameError("Evolution needs " + ", ".join(route["missing"]) + ".")
        old_name = monster["name"]
        down = route.get("devolve", False)
        gain = (5 + monster["level"] // 5) if down else (2 + monster["level"] // 10)
        abi = min(200, monster["abi"] + gain)
        evolved = self._monster(target, abi=abi, cam=monster["cam"], farm_bonuses=monster.get("farm_bonuses"))
        evolved["uid"] = monster["uid"]
        evolved["history"] = list(dict.fromkeys(monster.get("history", []) + [monster["species_id"]]))[-50:]
        state["party"][index] = evolved
        verb = "de-digivolved" if down else "digivolved"
        self._event(state, "message", index=index, text=f"{old_name} {verb} into {evolved['name']}! Level reset to 1; ABI is now {abi}, CAM retained.")

    def _party(self, state: dict, payload: dict) -> None:
        self._peace(state)
        action = payload.get("action")
        if action in ("lead", "deposit"):
            index, monster = self._party_member(state, payload, "index")
            if action == "lead":
                state["party"].insert(0, state["party"].pop(index))
                self._event(state, "message", text=f"{monster['name']} is your lead partner and will follow you.")
            else:
                self._hub_only(state)
                if len(state["party"]) <= 1:
                    raise GameError("Keep at least one partner in your party.")
                if len(state["storage"]) >= FARM_CAPACITY:
                    raise GameError("Your DigiFarm is full (100 residents). Withdraw a resident to make room.")
                state["storage"].append(state["party"].pop(index))
                self._event(state, "message", text=f"{monster['name']} moved to your DigiFarm.")
        elif action == "withdraw":
            self._hub_only(state)
            index = _integer(payload, "index", maximum=max(0, len(state["storage"]) - 1))
            if index >= len(state["storage"]):
                raise GameError("That DigiFarm slot is empty.")
            if len(state["party"]) >= 6:
                raise GameError("Your party already has six members.")
            monster = state["storage"].pop(index)
            monster["hp"], monster["sp"] = monster["max_hp"], monster["max_sp"]
            state["party"].append(monster)
            self._event(state, "message", text=f"{monster['name']} joined your party.")
        elif action == "exchange":
            # A full farm (including protected legacy overflow) must never lock
            # players out of their roster when the six party slots are occupied.
            self._hub_only(state)
            party_index, outgoing = self._party_member(state, payload)
            uid = payload.get("uid")
            if not isinstance(uid, str) or not 1 <= len(uid) <= 64:
                raise GameError("Choose one of your stored Digimon to exchange.")
            storage_index = next((i for i, m in enumerate(state["storage"]) if m.get("uid") == uid), None)
            if storage_index is None:
                raise GameError("That Digimon is not in your storage.")
            incoming = state["storage"][storage_index]
            incoming["hp"], incoming["sp"] = incoming["max_hp"], incoming["max_sp"]
            state["party"][party_index], state["storage"][storage_index] = incoming, outgoing
            self._event(state, "message", text=f"{incoming['name']} joined party slot {party_index + 1}; "
                        f"{outgoing['name']} moved to storage. DigiFarm occupancy is unchanged.")
        else:
            raise GameError("Unknown party action.")

    def _shop(self, state: dict, payload: dict) -> None:
        self._hub_only(state)
        currency = payload.get("currency", "credits")
        if currency == "digirubies":
            raise GameError("DigiRuby purchases require the server's secure checkout.")
        if currency != "credits":
            raise GameError("Choose credits or DigiRubies for this purchase.")
        item_id = payload.get("item")
        if not isinstance(item_id, str) or item_id not in SHOP:
            raise GameError("That item is not sold here.")
        quantity = _integer(payload, "quantity", 1, 1, 99)
        cost = SHOP[item_id]["price"] * quantity
        if state["credits"] < cost:
            raise GameError("Not enough credits for this purchase.")
        if state["inventory"].get(item_id, 0) + quantity > 999:
            raise GameError("You can carry at most 999 of each item.")
        state["credits"] -= cost
        state["inventory"][item_id] = state["inventory"].get(item_id, 0) + quantity
        self._event(state, "message", text=f"Purchased {quantity} x {SHOP[item_id]['name']} for {cost} credits.")

    def apply_digiruby_transaction(self, state: dict, operation: str, payload: dict) -> dict:
        """Prepare a grant inside Database.economy_transaction's SQL transaction.

        This is not a gameplay operation: only the database checkout calls it,
        and only that checkout may debit the canonical SQL wallet and publish
        the candidate state. No balance in player JSON authorizes a purchase.
        """
        intent = normalize_intent(operation, payload, SHOP)
        if state.get("in_season"):
            raise GameError("Use Save & Return to World before another activity.")
        if operation == "shop":
            self._hub_only(state)
            item, quantity = intent["item"], intent["quantity"]
            if state["inventory"].get(item, 0) + quantity > 999:
                raise GameError("You can carry at most 999 of each item.")
            cost = ruby_price(SHOP[item]["price"]) * quantity
            state["inventory"][item] = state["inventory"].get(item, 0) + quantity
            self._event(state, "message", text=f"Purchased {quantity} x {SHOP[item]['name']} for {cost} DigiRubies.")
            receipt = {"operation": operation, "item": item, "quantity": quantity,
                       "rubies_spent": cost, "credits_gained": 0}
        else:
            self._peace(state)
            if state.get("in_story") or state.get("in_season"):
                raise GameError("Save & Return to World before using the Ranked Arena exchange.")
            amount = intent["amount"]
            gained = amount * CREDITS_PER_RUBY
            if state.get("credits", 0) > MAX_CREDITS - gained:
                raise GameError("This exchange would exceed your credit limit. Spend some credits first.")
            state["credits"] = state.get("credits", 0) + gained
            self._event(state, "message", text=f"Exchanged {amount:,} DigiRubies for {gained:,} credits.")
            receipt = {"operation": operation, "rubies_spent": amount, "credits_gained": gained}
        self._refresh(state)
        return receipt

    def _item(self, state: dict, payload: dict) -> None:
        self._peace(state)
        if payload.get("item") == "digimeat_abi":
            self._hub_only(state)
            index, monster = self._party_member(state, payload)
            # The selected index may now contain another partner after a party
            # reorder. A current client sends its expected UID as a safeguard.
            if "uid" in payload and (not isinstance(payload["uid"], str) or payload["uid"] != monster.get("uid")):
                raise GameError("That party selection has changed. Choose the partner again.")
            quantity = _integer(payload, "quantity", 1, 1, 99)
            item_id = "digimeat_abi"
            if state["inventory"].get(item_id, 0) < quantity:
                raise GameError("You do not have enough ABI DigiMeat.")
            item = SHOP[item_id]
            gain = item["amount"] * quantity
            self._increase_abi(monster, gain)
            state["inventory"][item_id] -= quantity
            self._event(state, "feed", index=index, amount=gain, uid=monster["uid"], item=item_id,
                        resource="abi", quantity=quantity,
                        text=f"{monster['name']} enjoyed {quantity} × {item['name']}: +{gain} ABI permanently!")
            return
        self._use_item(state, payload)

    def _use_item(self, state: dict, payload: dict) -> None:
        item_id = payload.get("item")
        if not isinstance(item_id, str) or item_id not in SHOP or SHOP[item_id].get("category") == "digimeat":
            raise GameError("Unknown recovery capsule.")
        if state["inventory"].get(item_id, 0) <= 0:
            raise GameError("You do not have that capsule.")
        index, monster = self._party_member(state, payload)
        if monster["hp"] <= 0:
            raise GameError("Capsules cannot revive a defeated partner. Use free DigiLab recovery.")
        item = SHOP[item_id]
        key = item["resource"]
        amount = min(item["amount"], monster["max_" + key] - monster[key])
        if amount <= 0:
            raise GameError(f"{monster['name']} already has full {key.upper()}.")
        monster[key] += amount
        state["inventory"][item_id] -= 1
        self._event(state, "heal", index=index, amount=amount,
                    text=f"{monster['name']} recovered {amount} {key.upper()}.", resource=key)

    def _travel(self, state: dict, payload: dict) -> None:
        self._peace(state)
        if state.get("in_lab"):
            raise GameError("Return to the world before traveling.")
        map_id = payload.get("map_id")
        if not isinstance(map_id, str) or map_id not in self.maps:
            raise GameError("Unknown world area.")
        area = self.maps[map_id]
        x, y = area.get("spawn", [area.get("width", 1024) / 2, area.get("height", 768) / 2])
        state.update(map_id=map_id, x=float(x), y=float(y))
        state["in_farm"] = False
        low, high = self.wild_level_range(area)
        level_label = str(low) if low == high else f"{low}–{high}"
        self._event(state, "message", text=f"Arrived at {area['name']}. Wild levels {level_label}.")
