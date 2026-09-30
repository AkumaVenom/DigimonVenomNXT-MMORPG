"""Validated game-state operations for the host console, never a network API.

The console dispatcher owns authorization, target lookup, confirmations, locking,
audit and atomic persistence. This module only edits its supplied candidate state.
It deliberately has no access to a database, session, socket, or chat handler.
"""
from __future__ import annotations

import copy
import re
import uuid

from venom.common.game import FARM_CAPACITY, SHOP, GameError, variety_of, xp_required
from venom.server.navigation import Navigation


MAX_CREDITS = 2**53 - 1
READ_ONLY = frozenset({"digimon", "team", "bag", "money", "balance", "digimoninfo"})
GAME_COMMANDS = READ_ONLY | frozenset({
    "givedigimon", "removedigimon", "heal", "evolve", "devolve", "setlevel", "setexp",
    "setabi", "setcam", "setfriendshiplevel", "setparadox", "setshiny", "setfirewall", "clonedigimon", "giveitem",
    "removeitem", "setitem", "clearinventory", "givemoney", "removemoney", "setmoney",
    "teleportplayer", "spawn",
})


def _number(text: str, minimum: int, maximum: int, label: str) -> int:
    # Reject floats, booleans, exponents and pathological integer strings before
    # conversion. Never silently clamp a command's requested amount.
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]{1,16}", text):
        raise GameError(f"{label} must be a whole number from {minimum} to {maximum}.")
    value = int(text)
    if not minimum <= value <= maximum:
        raise GameError(f"{label} must be from {minimum} to {maximum}.")
    return value


class AdminGame:
    def __init__(self, engine):
        self.engine = engine
        self.navigation = Navigation(engine.root, engine.maps)

    @staticmethod
    def _no_args(args):
        if args:
            raise GameError("This command takes no extra arguments after the player name.")

    @staticmethod
    def _editable(state):
        if state.get("battle"):
            raise GameError("Finish the player's current battle before changing game state.")
        if state.get("in_season") or state.get("in_story"):
            raise GameError("The player must Save & Return to World before this command.")
        if isinstance(state.get("admin_jail"), dict):
            raise GameError("Release the player's jail restriction before this command.")

    @staticmethod
    def _catalog_match(catalog, text, label):
        query = text.strip().casefold()
        if not query:
            raise GameError(f"Specify a {label} ID or exact name; quote names containing spaces.")
        ids = [entry for key, entry in catalog.items() if key.casefold() == query]
        matches = ids or [entry for entry in catalog.values()
                          if str(entry.get("name", "")).casefold() == query]
        if not matches:
            raise GameError(f"Unknown {label}: {text}.")
        if len(matches) > 1:
            raise GameError(f"Ambiguous {label} name; use an ID: " + ", ".join(m["id"] for m in matches))
        return matches[0]

    def _species(self, text):
        return self._catalog_match(self.engine.species, text, "Digimon species")

    @staticmethod
    def _owned(state, selector):
        query = selector.strip().casefold()
        if not query:
            raise GameError("Select a Digimon by UID, party:1, storage:1, or unique exact name.")
        slot = re.fullmatch(r"(party|storage):([0-9]{1,4})", query)
        if slot:
            source, number = slot.group(1), int(slot.group(2))
            roster = state.get(source, [])
            if not 1 <= number <= len(roster):
                raise GameError(f"That {source} slot is empty (slots start at 1).")
            return source, number - 1, roster[number - 1]
        roster = [(source, index, partner)
                  for source in ("party", "storage")
                  for index, partner in enumerate(state.get(source, []))]
        matches = [entry for entry in roster if str(entry[2].get("uid", "")).casefold() == query]
        if not matches:
            matches = [entry for entry in roster if query in {
                str(entry[2].get("name", "")).casefold(),
                str(entry[2].get("species_id", "")).casefold()}]
        if not matches:
            raise GameError("That player does not own the selected Digimon. Use /digimon to list UIDs and slots.")
        if len(matches) != 1:
            slots = ", ".join(f"{source}:{index + 1}" for source, index, _ in matches)
            raise GameError(f"Ambiguous Digimon selection ({slots}); use a UID or an explicit slot.")
        return matches[0]

    @staticmethod
    def _describe(partner, location=""):
        return (f"{location}{partner['name']} [{partner['species_id']}] UID={partner['uid']} | "
                f"Lv {partner['level']} XP {partner.get('xp', 0)}/{xp_required(partner['level'])} | "
                f"ABI {partner.get('abi', 0)} CAM {partner.get('cam', 0)} | "
                f"HP {partner['hp']}/{partner['max_hp']} SP {partner['sp']}/{partner['max_sp']}" +
                (" | FIREWALL" if partner.get("firewall") else " | SHINY" if partner.get("shiny") else " | PARADOX" if partner.get("paradox") else ""))

    def species_info(self, args):
        species = self._species(" ".join(args))
        evolutions = [r["to"] for r in species.get("evolutions", [])]
        devolutions = [r["to"] for r in self.engine.devolutions.get(species["id"], [])]
        return (f"{species['name']} [{species['id']}] | {species.get('stage', 'unknown')} | "
                f"{species.get('type', 'free')} / {species.get('attribute', 'neutral')} | "
                f"Paradox: {'yes' if species.get('paradox') else 'no'} | "
                f"Shiny: {'yes' if species.get('shiny') else 'no'} | "
                f"FireWall: {'yes' if species.get('firewall') else 'no'}\n"
                f"Level 1 stats: {self.engine.stats_for(species, 1)}\n"
                f"Evolve: {', '.join(evolutions) or 'none'}\n"
                f"Devolve: {', '.join(devolutions) or 'none'}")

    def execute(self, command: str, state: dict, args: list[str]) -> str:
        """Run a canonical command with its player target already removed.

        Names with spaces can be passed as one shell-quoted argument. Setters
        accept a joined name followed by the value. Invalid requests raise
        GameError; the dispatcher discards that candidate without saving it.
        """
        command = command.lower().lstrip("/")
        if command not in GAME_COMMANDS:
            raise GameError("Unknown game-state console command.")
        if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
            raise GameError("Command arguments must be text.")
        if command in READ_ONLY:
            return self._inspect(command, state, args)
        self._editable(state)
        # Deliver only events from this administrative operation, not replayed
        # damage animations left over from the player's last saved action.
        state["events"] = []
        if command in {"giveitem", "removeitem", "setitem", "clearinventory"}:
            result = self._inventory(command, state, args)
        elif command in {"givemoney", "removemoney", "setmoney"}:
            result = self._money(command, state, args)
        elif command == "teleportplayer":
            result = self._teleport(state, args)
        elif command == "spawn":
            result = self._spawn(state, args)
        else:
            result = self._partners(command, state, args)
        self.engine._refresh(state)
        if command != "spawn":
            self.engine._event(state, "message", text=f"Administrator: {result}")
        return result

    def _inspect(self, command, state, args):
        if command in {"digimon", "team"}:
            self._no_args(args)
            lines = [f"{state.get('username', 'Player')} — {'party and DigiFarm' if command == 'digimon' else 'party'}"]
            for source in (("party", "storage") if command == "digimon" else ("party",)):
                for index, partner in enumerate(state.get(source, [])):
                    lines.append(self._describe(partner, f"{source}:{index + 1} "))
            return "\n".join(lines)
        if command == "digimoninfo":
            selector = " ".join(args)
            _, _, partner = self._owned(state, selector)
            return (self._describe(partner) + f"\nHistory: {', '.join(partner.get('history', [])) or 'none'}"
                    + f"\nFarm bonuses: {partner.get('farm_bonuses', {})}\n" + self.species_info([partner["species_id"]]))
        self._no_args(args)
        if command in {"money", "balance"}:
            return f"{state.get('username', 'Player')}: {state.get('credits', 0):,} credits."
        inventory = state.get("inventory", {})
        lines = [f"{key}: {SHOP.get(key, {}).get('name', key)} x{quantity}"
                 for key, quantity in sorted(inventory.items())]
        return "\n".join(lines) or "The inventory is empty."

    def _species_level(self, args, default=1):
        if not args:
            raise GameError("Specify a Digimon species ID or exact name, optionally followed by a level (1–99).")
        # Prefer an exact catalog name before treating a numeric last token as a
        # level: imported species names are allowed to contain numbers.
        try:
            return self._species(" ".join(args)), default
        except GameError:
            if len(args) < 2:
                raise
        level = _number(args[-1], 1, 99, "Level")
        return self._species(" ".join(args[:-1])), level

    @staticmethod
    def _destination(state):
        if len(state.get("party", [])) < 6:
            return "party"
        if len(state.get("storage", [])) < FARM_CAPACITY:
            return "storage"
        raise GameError("The party and DigiFarm are full (6 party / 100 stored).")

    def _recompute(self, partner):
        species = self.engine.species[partner["species_id"]]
        hp_deficit = max(0, partner.get("max_hp", 0) - partner.get("hp", 0))
        sp_deficit = max(0, partner.get("max_sp", 0) - partner.get("sp", 0))
        defeated = partner.get("hp", 0) <= 0
        stats = self.engine.stats_for(species, partner["level"], partner.get("abi", 0),
                                      partner.get("farm_bonuses"))
        partner.update(name=species["name"], stage=species.get("stage", "unknown"),
                       type=species["type"], attribute=species["attribute"],
                       paradox=bool(species.get("paradox")), shiny=bool(species.get("shiny")),
                       firewall=bool(species.get("firewall")),
                       variety=variety_of(species),
                       max_hp=stats["hp"], max_sp=stats["sp"],
                       hp=0 if defeated else max(1, stats["hp"] - hp_deficit),
                       sp=max(0, stats["sp"] - sp_deficit), next_xp=xp_required(partner["level"]))
        partner.update({key: stats[key] for key in ("atk", "def", "int", "spd")})
        partner["skills"] = self.engine._skills(partner)
        partner.pop("guard", None)

    def _set_variety(self, partner, variety, value):
        """Select a real catalog counterpart; never paint a flag onto a base form."""
        if value.casefold() not in {"true", "false"}:
            raise GameError(f"{variety.title()} status must be true or false.")
        enabled = value.casefold() == "true"
        current = self.engine.species[partner["species_id"]]
        if enabled == bool(current.get(variety)):
            return
        base_id = current.get("base_id", current["id"])
        base = self.engine.species.get(base_id)
        if not base or variety_of(base) != "normal":
            raise GameError("This species does not have a supported regular form.")
        if enabled:
            choices = [species["id"] for species in self.engine.species.values()
                       if species.get(variety) and species.get("base_id") == base_id
                       and variety_of(species) == variety
                       and not any(species.get(other) for other in ("paradox", "shiny", "firewall")
                                   if other != variety)]
            if len(choices) != 1:
                raise GameError(f"This species does not have one supported {variety.title()} variant.")
            target = choices[0]
        else:
            target = base_id
        previous = partner["species_id"]
        partner["species_id"] = target
        partner["history"] = list(dict.fromkeys(partner.get("history", []) + [previous]))[-50:]

    def _evolution_selection(self, state, args, down):
        if not args:
            raise GameError("Specify a Digimon selector and, if needed, a target species ID.")
        # One quoted name, a UID/slot, or an unquoted unique full name without a
        # target all work. Explicit targets are split only when both sides are
        # real selections, preventing fuzzy/partial matches.
        try:
            owned = self._owned(state, " ".join(args))
        except GameError as original:
            candidates = []
            for split in range(1, len(args)):
                try:
                    selected = self._owned(state, " ".join(args[:split]))
                    target = self._species(" ".join(args[split:]))
                    candidates.append((selected, target["id"]))
                except GameError:
                    pass
            if len(candidates) != 1:
                if len(candidates) > 1:
                    raise GameError("Ambiguous evolution command. Use a UID and exact target ID.")
                raise original
            owned, target = candidates[0]
        else:
            target = None
        monster = owned[2]
        routes = (self.engine.devolutions.get(monster["species_id"], []) if down else
                  self.engine.species[monster["species_id"]].get("evolutions", []))
        targets = sorted({route["to"] for route in routes if route.get("to") in self.engine.species})
        if not targets:
            raise GameError("This form has no supported " + ("de-digivolution" if down else "digivolution") + " route.")
        if target is None:
            if len(targets) != 1:
                raise GameError("Select an explicit target ID from: " + ", ".join(targets))
            target = targets[0]
        if target not in targets:
            raise GameError("That target is not a supported route. Allowed IDs: " + ", ".join(targets))
        return owned, target

    def _partners(self, command, state, args):
        if command == "heal":
            self._no_args(args)
            for partner in state.get("party", []):
                partner["hp"], partner["sp"] = partner["max_hp"], partner["max_sp"]
                partner.pop("guard", None)
            return "Party HP and SP fully restored."
        if command == "givedigimon":
            species, level = self._species_level(args)
            where = self._destination(state)
            monster = self.engine._monster(species["id"], level=level)
            state.setdefault(where, []).append(monster)
            return f"Added {monster['name']} (Lv {level}, UID {monster['uid']}) to {where}."
        if command in {"evolve", "devolve"}:
            (source, index, partner), target = self._evolution_selection(state, args, command == "devolve")
            previous = partner["species_id"]
            gain = (5 + partner["level"] // 5) if command == "devolve" else (2 + partner["level"] // 10)
            evolved = self.engine._monster(target, abi=min(200, partner.get("abi", 0) + gain),
                                           cam=partner.get("cam", 0), farm_bonuses=partner.get("farm_bonuses"))
            evolved["uid"] = partner["uid"]
            evolved["history"] = list(dict.fromkeys(partner.get("history", []) + [previous]))
            # Preserve any additive save metadata introduced by other systems.
            partner.update(evolved)
            partner.pop("guard", None)
            return f"{source}:{index + 1} changed to {partner['name']}; Lv 1, ABI {partner['abi']}, CAM retained."
        setters = {"setlevel", "setexp", "setabi", "setcam", "setfriendshiplevel", "setparadox", "setshiny", "setfirewall"}
        if command in setters:
            if len(args) < 2:
                raise GameError("Specify a Digimon selector followed by the new value.")
            source, index, partner = self._owned(state, " ".join(args[:-1]))
            value = args[-1]
            if command in {"setparadox", "setshiny", "setfirewall"}:
                self._set_variety(partner, command[3:], value)
            else:
                field = {"setlevel": "level", "setexp": "xp", "setabi": "abi", "setcam": "cam",
                         "setfriendshiplevel": "cam"}[command]
                maximum = {"level": 99, "abi": 200, "cam": 100,
                           "xp": 0 if partner["level"] == 99 else xp_required(partner["level"]) - 1}[field]
                partner[field] = _number(value, 1 if field == "level" else 0, maximum, field.upper())
                if field == "level":
                    partner["xp"] = 0
            self._recompute(partner)
            return self._describe(partner, f"{source}:{index + 1} ")
        source, index, partner = self._owned(state, " ".join(args))
        if command == "removedigimon":
            if source == "party" and len(state["party"]) <= 1:
                raise GameError("Keep at least one Digimon in the player's party.")
            state[source].pop(index)
            return f"Removed {partner['name']} (UID {partner['uid']}) from {source}."
        if command == "clonedigimon":
            where = self._destination(state)
            clone = copy.deepcopy(partner)
            clone["uid"] = uuid.uuid4().hex
            clone.pop("guard", None)
            state.setdefault(where, []).append(clone)
            return f"Cloned {partner['name']} into {where}; new UID {clone['uid']}."
        raise GameError("Unknown partner command.")

    def _inventory(self, command, state, args):
        if command == "clearinventory":
            self._no_args(args)
            # Preserve known and legacy slots; clear their quantities, not the
            # surrounding character state or party/storage data.
            state["inventory"] = {key: 0 for key in set(SHOP) | set(state.get("inventory", {}))}
            return "Inventory cleared."
        if len(args) < 2:
            raise GameError("Specify an item ID or quoted exact item name followed by an amount.")
        item_catalog = {key: {**item, "id": key} for key, item in SHOP.items()}
        item = self._catalog_match(item_catalog, " ".join(args[:-1]), "item")
        amount = _number(args[-1], 0 if command == "setitem" else 1, 999, "Item amount")
        old = state.get("inventory", {}).get(item["id"], 0)
        new = amount if command == "setitem" else old + (amount if command == "giveitem" else -amount)
        if not 0 <= new <= 999:
            raise GameError("The resulting item quantity must be between 0 and 999.")
        state.setdefault("inventory", {})[item["id"]] = new
        return f"{item['name']} ({item['id']}): {new}."

    @staticmethod
    def _money(command, state, args):
        if len(args) != 1:
            raise GameError("Specify exactly one whole credit amount.")
        amount = _number(args[0], 0 if command == "setmoney" else 1, MAX_CREDITS, "Credit amount")
        old = state.get("credits", 0)
        new = amount if command == "setmoney" else old + (amount if command == "givemoney" else -amount)
        if not 0 <= new <= MAX_CREDITS:
            raise GameError(f"The resulting balance must be between 0 and {MAX_CREDITS} credits.")
        state["credits"] = new
        return f"Balance is now {new:,} credits."

    def _teleport(self, state, args):
        area = self._catalog_match(self.engine.maps, " ".join(args), "map")
        position = area.get("spawn", [area.get("width", 1024) / 2, area.get("height", 768) / 2])
        try:
            x, y = map(float, position)
            if not self.navigation.walkable(area["id"], x, y):
                raise GameError("This map's entry point is blocked; verify its collision assets.")
        except (OSError, TypeError, ValueError, KeyError) as exc:
            if isinstance(exc, GameError):
                raise
            raise GameError("This map's collision data or entry point is unavailable.") from exc
        state.update(map_id=area["id"], x=x, y=y, in_lab=False, in_farm=False)
        state.pop("return_location", None)
        return f"Teleported to {area['name']} ({area['id']}) at its safe entry point."

    def _spawn(self, state, args):
        if state.get("in_lab") or state.get("in_farm"):
            raise GameError("The player must return to the world before a wild battle can start.")
        species, level = self._species_level(args)
        active = [index for index, partner in enumerate(state.get("party", [])[:3]) if partner["hp"] > 0]
        if not active:
            raise GameError("The player's active team needs healing before a wild battle can start.")
        enemy = self.engine._monster(species["id"], level=level)
        enemy["hp"] = enemy["max_hp"] = max(20, int(enemy["max_hp"] * .72))
        battle = {"id": uuid.uuid4().hex, "enemies": [enemy], "active": active,
                  "turn": 0, "actor": active[0], "clock": 0.0, "queue": [], "scanned": []}
        for index in active:
            battle["queue"].append({"side": "player", "index": index,
                                    "at": 500 / max(1, state["party"][index]["spd"])})
        battle["queue"].append({"side": "enemy", "index": 0, "at": 500 / max(1, enemy["spd"]) + .001})
        state["battle"] = battle
        self.engine._event(state, "message", text=f"Wild encounter: {enemy['name']}! (Administrator encounter)")
        self.engine._advance(state)
        return f"Started a live wild battle against {enemy['name']} at Lv {level}; the player uses normal fight controls."
