"""Played acceptance with shipped Story maps, roster and normal fight controls.

The pilot never edits HP, submits a winner or invokes settlement. Movement uses
normal collision traces; independent protocol tests cover the actual packets.
"""
from __future__ import annotations

import copy
import heapq
import json
import math
from pathlib import Path

import pytest

from venom.common.game import GameEngine, GameError, SHOP, effectiveness
from venom.common import story
from venom.server.navigation import Navigation

ROOT = Path(__file__).resolve().parents[1]


class CampaignPilot:
    def __init__(self, seed=902, starter="agumon"):
        self.engine = GameEngine(ROOT, seed=seed)
        self.state = self.engine.new_player("RelayPilot", next(iter(self.engine.tamers)), starter)
        self.navigation = Navigation(ROOT, self.engine.maps)
        self.controls = 0
        self.dialogue_pages = 0
        self.last_command = None
        self.results = []

    def story(self, action, **fields):
        return self.engine.handle(self.state, "story", {"action": action, **fields})

    def walk_to(self, npc):
        """Walk a collision-checked route to ordinary NPC talking distance."""
        state = self.state
        assert state["map_id"] == npc["map_id"]
        origin = (float(state["x"]), float(state["y"]))
        target = (float(npc["x"]), float(npc["y"]))
        frontier = [(math.dist(origin, target), 0.0, (0, 0))]
        parents = {(0, 0): None}
        costs = {(0, 0): 0.0}

        def point(node):
            return origin[0] + 16 * node[0], origin[1] + 16 * node[1]

        destination = None
        while frontier:
            _, distance, current = heapq.heappop(frontier)
            if distance != costs[current]:
                continue
            here = point(current)
            if math.dist(here, target) <= story.TALK_RADIUS - 16:
                destination = current
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                neighbor = current[0] + dx, current[1] + dy
                there = point(neighbor)
                cost = distance + math.dist(here, there)
                if cost >= costs.get(neighbor, math.inf):
                    continue
                actual = self.navigation.trace(state["map_id"], here, there)
                if math.dist(actual, there) > .001:
                    continue
                costs[neighbor], parents[neighbor] = cost, current
                heapq.heappush(frontier, (cost + math.dist(there, target), cost, neighbor))
            assert len(parents) < 100000, "Story map route search exceeded its safety bound"
        assert destination is not None, f"Cannot walk to {npc['name']} on {npc['map_id']}"
        path = []
        while destination is not None:
            path.append(destination)
            destination = parents[destination]
        for node in reversed(path):
            state["x"], state["y"] = self.navigation.trace(state["map_id"],
                (state["x"], state["y"]), point(node))

    def challenge(self, npc_id):
        data = story.content(self.engine)
        npcs = {**data["npcs"], **{npc["id"]: npc for npc in data.get("challengers", [])}}
        npc = npcs[npc_id]
        region = next(row for row in data["regions"] if npc["map_id"] in row["maps"])
        if self.state["map_id"] != npc["map_id"]:
            self.story("travel", chapter=region["index"], map_id=npc["map_id"])
        self.walk_to(npc)
        self.story("talk", npc_id=npc_id)
        while True:
            dialogue = self.state["story"]["view"]["dialogue"]
            assert dialogue and dialogue["text"].strip(), f"Missing dialogue for {npc_id}"
            self.dialogue_pages += 1
            choices = {choice["id"] for choice in dialogue["choices"]}
            if "next" not in choices:
                assert "challenge" in choices, f"Story path blocked at {npc_id}: {dialogue}"
                self.story("dialogue", token=dialogue["token"], choice="challenge")
                break
            self.story("dialogue", token=dialogue["token"], choice="next")
        assert self.state["battle"] and self.state["battle"]["kind"] == "story"
        return npc

    def choose_action(self):
        state = self.state
        battle = state["battle"]
        actor = state["party"][battle["actor"]]
        living = [(index, state["party"][index]) for index in battle["active"]
                  if state["party"][index]["hp"] > 0]
        endangered = [(index, monster) for index, monster in living
                      if monster["hp"] < monster["max_hp"] * .32]
        if endangered:
            index, patient = min(endangered, key=lambda row: row[1]["hp"] / row[1]["max_hp"])
            capsules = [ident for ident in ("hp_l", "hp_m", "hp_s") if state["inventory"].get(ident, 0)]
            if capsules:
                missing = patient["max_hp"] - patient["hp"]
                adequate = [ident for ident in capsules if SHOP[ident]["amount"] >= missing * .8]
                ident = min(adequate, key=lambda item: SHOP[item]["amount"]) if adequate else capsules[0]
                return {"action": "item", "item": ident, "party_index": index}
        choices = []
        for target_index, enemy in enumerate(battle["enemies"]):
            if enemy["hp"] <= 0:
                continue
            attacks = [("attack", None)] + [("skill", index) for index, skill in enumerate(actor["skills"])
                if actor["sp"] >= skill["sp"]]
            for action, skill_index in attacks:
                skill = actor["skills"][skill_index] if skill_index is not None else None
                magic = skill and skill["kind"] == "magic"
                attack = actor["int"] if magic else actor["atk"]
                defense = enemy["int"] if magic else enemy["def"]
                damage = max(1, (8 + attack * .72 - defense * .28) * (skill["power"] if skill else 1)
                             * effectiveness(actor, enemy, skill["attribute"] if skill else "neutral"))
                fields = {"action": action, "target": target_index}
                if skill_index is not None:
                    fields["skill_index"] = skill_index
                choices.append((damage / enemy["hp"], damage, fields))
        return max(choices, key=lambda choice: (choice[0], choice[1]))[2]

    def fight(self, deliberately_lose=False):
        start = self.controls
        while self.state.get("battle"):
            battle = self.state["battle"]
            command = {"battle_id": battle["id"], "expected_turn": battle["turn"],
                       **({"action": "guard"} if deliberately_lose else self.choose_action())}
            self.last_command = copy.deepcopy(command)
            self.engine.handle(self.state, "battle", command)
            self.controls += 1
            assert self.controls - start < 2500, "Interactive Story battle did not resolve"
        assert self.controls > start, "The server must wait for actual player decisions"
        result = self.state["story"]["recent"][0]
        self.results.append(copy.deepcopy(result))
        return result

    def main_route(self):
        data = story.content(self.engine)
        return [npc_id for region in data["regions"] for npc_id in region["npc_ids"]
                if data["npcs"][npc_id].get("role") in ("trainer", "warden", "champion")]

    def recover_and_supply(self):
        self.story("camp")
        for item in ("hp_m", "hp_s"):
            wanted = max(0, 8 - self.state["inventory"].get(item, 0))
            quantity = min(wanted, self.state["credits"] // SHOP[item]["price"])
            if quantity:
                self.engine.handle(self.state, "shop", {"item": item, "quantity": quantity})
        self.story("field")


def test_existing_owned_team_and_world_location_are_preserved_on_first_entry():
    pilot = CampaignPilot()
    state = pilot.state
    # Established account fixture, never used as a played-campaign shortcut.
    state["party"][0] = pilot.engine._monster("agumon", 99, abi=72, cam=88)
    original = copy.deepcopy({key: state[key] for key in ("party", "storage", "inventory", "credits", "scan")})
    location = copy.deepcopy({key: state[key] for key in ("map_id", "x", "y", "in_lab", "in_farm")})
    pilot.story("enter")
    assert state["in_story"]
    assert {key: state[key] for key in original} == original
    assert state["story"]["badges"] == []
    pilot.story("return")
    assert not state["in_story"]
    assert {key: state[key] for key in location} == location
    assert {key: state[key] for key in original} == original


@pytest.mark.parametrize(("starter", "seed"), [("agumon", 902), ("bearmon", 204), ("betamon", 911)])
def test_fresh_owned_rookie_can_play_every_badge_and_championship_loop(starter, seed):
    pilot = CampaignPilot(seed=seed, starter=starter)
    state = pilot.state
    pilot.story("enter")
    assert state["party"][0]["level"] == 1
    original_uid = state["party"][0]["uid"]
    route = pilot.main_route()
    for npc_id in route:
        assert not state.get("permanent_rewards", {}).get("firewall_scan_mastery")
        npc = pilot.challenge(npc_id)
        assert npc["name"] in state["story"]["view"]["objective"], "Journal must name the next accessible tamer"
        if npc.get("role") == "champion":
            assert len(state["story"]["badges"]) == 8
            levels = [enemy["level"] for enemy in state["battle"]["enemies"]]
            assert min(levels) >= 80 and max(levels) <= 100
        result = pilot.fight()
        retries = 0
        while not result["won"] and retries < 4:
            # Recovery, purchased supplies and manual training are exactly the
            # fallback available to an ordinary player after a real loss.
            pilot.recover_and_supply()
            pilot.story("train")
            pilot.fight()
            pilot.challenge(npc_id)
            result = pilot.fight()
            retries += 1
        assert result["won"], f"Fresh account cannot clear {npc['name']}: {pilot.results[-8:]}"
        assert all(monster["level"] <= 99 for monster in state["party"])
        assert state["party"][0]["uid"] == original_uid
        if npc.get("role") == "warden":
            assert npc["badge"] in state["story"]["badges"]
        pilot.recover_and_supply()
    assert len(state["story"]["badges"]) == 8
    assert state["story"]["champion"]["holder_id"] == "player"
    assert state["story"]["champion"]["reigns"] == 1
    assert state["permanent_rewards"]["firewall_scan_mastery"] is True
    assert result["scan_mastery_unlocked"] is True
    assert result["scan_mastery_variety"] == "firewall"
    assert pilot.controls > 25 and pilot.dialogue_pages >= len(route)
    assert state["story"]["stats"]["credits_earned"] > 0
    before = copy.deepcopy(state)
    with pytest.raises(GameError):
        pilot.engine.handle(state, "battle", pilot.last_command)
    assert state["credits"] == before["credits"]
    assert state["story"] == before["story"]
    # Postgame stays playable: defend, honestly lose, and reclaim that same NPC's title.
    champion = next(npc for npc in state["story"]["view"]["npcs"] if npc["role"] == "champion")
    pilot.challenge(champion["id"])
    assert pilot.fight()["won"]
    assert state["story"]["champion"]["defenses"] == 1
    assert state["permanent_rewards"]["firewall_scan_mastery"] is True
    assert state["story"]["recent"][0]["scan_mastery_unlocked"] is False
    champion = next(npc for npc in state["story"]["view"]["npcs"] if npc["role"] == "champion")
    pilot.challenge(champion["id"])
    assert not pilot.fight(deliberately_lose=True)["won"]
    assert state["story"]["champion"]["status"] == "reclaim"
    assert state["permanent_rewards"]["firewall_scan_mastery"] is True
    assert state["story"]["champion"]["holder_id"] == champion["id"]
    pilot.challenge(champion["id"])
    assert pilot.fight()["won"]
    assert state["story"]["champion"]["holder_id"] == "player"
    assert state["story"]["champion"]["reigns"] == 2
    assert state["permanent_rewards"]["firewall_scan_mastery"] is True
    assert state["story"]["recent"][0]["scan_mastery_unlocked"] is False
    assert len(state["story"]["badges"]) == 8
    restored = json.loads(json.dumps(state))
    engine = GameEngine(ROOT, seed=999)
    saved = copy.deepcopy(restored)
    engine._refresh(restored)
    assert restored == saved


def test_all_imported_rookie_starters_can_clear_the_opening_with_available_training():
    reference = CampaignPilot()
    starters = list(reference.engine.starters)
    assert len(starters) >= 70
    for ordinal, starter in enumerate(starters):
        pilot = CampaignPilot(seed=200 + ordinal, starter=starter)
        pilot.story("enter")
        pilot.challenge(pilot.main_route()[0])
        won = pilot.fight()["won"]
        if not won:
            for _ in range(6):
                if pilot.state["party"][0]["level"] >= 5:
                    break
                pilot.story("train")
                pilot.fight()
            pilot.challenge(pilot.main_route()[0])
            won = pilot.fight()["won"]
        assert won, f"Opening or available training blocks a normally played {starter}"
        assert len(pilot.state["party"]) == 2, "First clear must supply the second real owned partner"


def test_normal_digivolution_and_optional_training_keep_the_campaign_playable():
    pilot = CampaignPilot(seed=734)
    pilot.story("enter")
    for npc_id in pilot.main_route()[:6]:
        pilot.challenge(npc_id)
        assert pilot.fight()["won"]
        pilot.recover_and_supply()
    state = pilot.state
    assert len(state["story"]["badges"]) == 2
    identity = state["party"][0]["uid"]
    story_before = copy.deepcopy(state["story"]["completed"])
    pilot.story("camp")
    pilot.engine.handle(state, "evolve", {"party_index": 0, "to": "greymon"})
    assert state["party"][0]["species_id"] == "greymon"
    assert state["party"][0]["level"] == 1
    assert state["party"][0]["uid"] == identity
    pilot.story("field")
    pilot.story("travel", chapter=2)
    target = state["story"]["view"]["training_level"]
    for _ in range(8):
        if state["party"][0]["level"] >= target:
            break
        pilot.story("train")
        assert pilot.fight()["won"], "Evolved partner cannot use its unlocked recovery training"
    assert state["party"][0]["level"] >= target
    assert state["story"]["completed"] == story_before
    assert len(state["story"]["badges"]) == 2
    assert state["story"]["stats"]["training_wins"] > 0
    pilot.challenge(pilot.main_route()[6])
    assert pilot.fight()["won"]
    earned = copy.deepcopy(state["party"])
    pilot.story("return")
    assert state["party"] == earned
    assert state["party"][0]["species_id"] == "greymon"


def test_story_locks_and_tamer_combat_cannot_be_bypassed_by_normal_controls():
    pilot = CampaignPilot()
    pilot.story("enter")
    state = pilot.state
    for chapter in (1, 8):
        with pytest.raises(GameError):
            pilot.story("travel", chapter=chapter)
    data = story.content(pilot.engine)
    warden = next(npc for npc in data["npcs"].values() if npc.get("role") == "warden")
    pilot.story("travel", chapter=0, map_id=warden["map_id"])
    pilot.walk_to(warden)
    pilot.story("talk", npc_id=warden["id"])
    while any(choice["id"] == "next" for choice in state["story"]["view"]["dialogue"]["choices"]):
        dialogue = state["story"]["view"]["dialogue"]
        pilot.story("dialogue", token=dialogue["token"], choice="next")
    dialogue = state["story"]["view"]["dialogue"]
    assert "challenge" not in {choice["id"] for choice in dialogue["choices"]}
    with pytest.raises(GameError):
        pilot.story("dialogue", token=dialogue["token"], choice="challenge")
    assert state["story"]["badges"] == [] and state["battle"] is None
    pilot.challenge(pilot.main_route()[0])
    battle = copy.deepcopy(state["battle"])
    controls = {"battle_id": battle["id"], "expected_turn": battle["turn"]}
    for op, payload in (("battle", {"action": "flee", **controls}),
                        ("story", {"action": "return"}),
                        ("digifarm", {"action": "enter", "forfeit": True}),
                        ("story", {"action": "travel", "chapter": 0}),
                        ("story", {"action": "heal"})):
        with pytest.raises(GameError):
            pilot.engine.handle(state, op, payload)
        assert state["battle"] == battle
    assert pilot.fight()["won"]
    assert state["scan"] == {}, "Named tamer partners must not grant wild scan data"


def test_physical_relay_gates_walk_between_maps_and_require_the_earned_badge():
    pilot = CampaignPilot(seed=912)
    pilot.story("enter")
    state = pilot.state
    local = next(gate for gate in state["story"]["view"]["exits"] if not gate.get("requires_badge"))
    if math.hypot(state["x"] - local["x"], state["y"] - local["y"]) > story.TALK_RADIUS:
        with pytest.raises(GameError):
            pilot.story("exit", exit_id=local["id"])
    pilot.walk_to(local)
    pilot.story("exit", exit_id=local["id"])
    assert state["map_id"] == local["to_map"]
    onward = next(gate for gate in state["story"]["view"]["exits"] if gate.get("requires_badge"))
    pilot.walk_to(onward)
    with pytest.raises(GameError):
        pilot.story("exit", exit_id=onward["id"])
    assert state["story"]["chapter"] == 0
    for ident in pilot.main_route()[:3]:
        pilot.challenge(ident)
        assert pilot.fight()["won"]
        pilot.recover_and_supply()
    assert len(state["story"]["badges"]) == 1
    if state["map_id"] != onward["map_id"]:
        pilot.story("travel", chapter=0, map_id=onward["map_id"])
    pilot.walk_to(onward)
    pilot.story("exit", exit_id=onward["id"])
    assert state["map_id"] == onward["to_map"]
    assert state["story"]["chapter"] == 1
    with pytest.raises(GameError):
        pilot.story("exit", exit_id=onward["id"])
    assert state["map_id"] == onward["to_map"]
