"""Ghostline acceptance with real owned partners and ordinary gameplay controls.

The campaign fixture owns an established team before entering. Every assignment,
NPC victory, proof and permanent reward is earned through production handlers.
Collision-checked walking reaches each NPC and all 30 forward portals; persistence
reloads cannot substitute for progression or regenerate the defeated antagonist.
"""
from __future__ import annotations

import copy
import heapq
import math
from pathlib import Path
from unittest.mock import patch

import pytest

from venom.common import story
from venom.common.game import GameEngine, GameError
from venom.server.database import Database
from test_story_acceptance import CampaignPilot

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = "xros_ghostline"
OWNED = ("party", "storage", "inventory", "credits", "scan")


class GhostlinePilot(CampaignPilot):
    def __init__(self, seed=1400, established=True):
        super().__init__(seed=seed)
        if established:
            self.state["party"] = [self.engine._monster(sid, 99, abi=100, cam=100)
                                   for sid in ("omnimon_shiny", "alphamon_paradox", "metalgarurumon")]
            self.state["credits"] = 50000
        self.engine._refresh(self.state)

    @property
    def data(self):
        return story.content(self.engine, CAMPAIGN)

    def enter(self):
        return self.story("enter", campaign_id=CAMPAIGN)

    def walk_to(self, npc):
        """Follow exact cardinal collision edges, including actual replay checks.

        The older Dawn pilot tolerates subpixel clipped diagonal endpoints. That
        makes a later edge depend on a slightly different pixel cell on intricate
        Xros masks. Exact cardinal routes match the authored placement proof.
        """
        state, nav = self.state, self.navigation
        assert state["map_id"] == npc["map_id"]
        origin, target = (state["x"], state["y"]), (npc["x"], npc["y"])
        frontier = [(math.dist(origin, target), 0, origin)]
        parents, costs, end = {origin: None}, {origin: 0}, None
        while frontier:
            _, distance, here = heapq.heappop(frontier)
            if distance != costs[here]:
                continue
            if math.dist(here, target) <= story.TALK_RADIUS - 16:
                end = here
                break
            for dx, dy in ((16, 0), (-16, 0), (0, 16), (0, -16)):
                there = (here[0] + dx, here[1] + dy)
                cost = distance + 16
                if cost >= costs.get(there, math.inf) or not nav.walkable(state["map_id"], *there):
                    continue
                if math.dist(nav.trace(state["map_id"], here, there), there) > 1e-8:
                    continue
                costs[there], parents[there] = cost, here
                heapq.heappush(frontier, (cost + math.dist(there, target), cost, there))
            assert len(parents) < 100000, "Collision route exceeded its safety bound"
        assert end is not None, f"Cannot reach {npc['name']} on {npc['map_id']}"
        route = []
        while end is not None:
            route.append(end)
            end = parents[end]
        for there in reversed(route):
            actual = nav.trace(state["map_id"], (state["x"], state["y"]), there)
            assert math.dist(actual, there) <= 1e-8, "A planned collision edge failed when walked"
            state["x"], state["y"] = actual
        assert math.dist((state["x"], state["y"]), target) <= story.TALK_RADIUS

    def meet(self, ident):
        npc = self.data["npcs"][ident]
        assert self.state["map_id"] == npc["map_id"], "Walk and portal through the itinerary"
        self.walk_to(npc)
        self.story("talk", npc_id=ident)
        while True:
            dialogue = self.state["story"]["view"]["dialogue"]
            assert dialogue and dialogue["text"].strip(), ident
            self.dialogue_pages += 1
            if "next" not in {row["id"] for row in dialogue["choices"]}:
                return dialogue
            self.choose("next")

    def choose(self, choice):
        dialogue = self.state["story"]["view"]["dialogue"]
        assert choice in {row["id"] for row in dialogue["choices"]}, dialogue
        return self.story("dialogue", token=dialogue["token"], choice=choice)

    def challenge(self, ident):
        self.meet(ident)
        self.choose("challenge")
        assert self.state["battle"]["kind"] == "story"
        assert self.state["battle"]["story_campaign_id"] == CAMPAIGN
        return self.data["npcs"][ident]

    def assignment(self, ident, action):
        self.meet(ident)
        self.choose(action)

    def roles(self, region):
        return {self.data["npcs"][ident]["role"]: ident for ident in region["npc_ids"]
                if self.data["npcs"][ident]["role"] in ("quest", "trainer", "final")}

    def portal(self, target_index):
        current = self.state["map_id"]
        target = self.data["regions"][target_index]["maps"][0]
        gate = next(row for row in self.data["maps"][current]["exits"] if row["to_map"] == target)
        self.walk_to({**gate, "map_id": current, "name": "Ghostline portal"})
        self.story("exit", exit_id=gate["id"])
        assert self.state["map_id"] == target
        assert self.state["story"]["chapter"] == target_index
        return gate


def checkpoint(pilot, database, key, revision):
    """Round-trip the played state through SQLite and a brand-new game engine."""
    before = copy.deepcopy(pilot.state)
    revision = database.save(key, pilot.state, revision)
    restored, loaded_revision = database.load(key)
    assert restored == before
    pilot.engine = GameEngine(ROOT, seed=1449)
    pilot.engine._refresh(restored)
    assert restored == before
    pilot.state = restored
    return loaded_revision


@pytest.fixture(scope="module")
def played_ghostline(tmp_path_factory):
    pilot = GhostlinePilot()
    before = copy.deepcopy({key: pilot.state[key] for key in OWNED})
    original_uids = [monster["uid"] for monster in pilot.state["party"]]
    pilot.enter()
    assert {key: pilot.state[key] for key in OWNED} == before
    database = Database({"driver": "sqlite", "path": str(tmp_path_factory.mktemp("ghostline") / "played.sqlite3")}, dev=True)
    database.initialize()
    key = database.register(pilot.state["username"], "ghostline-acceptance-password", pilot.state)
    _, revision = database.load(key)
    snapshots, portals, ally_maps, scans = {}, [], set(), copy.deepcopy(pilot.state["scan"])
    try:
        portals.append(pilot.portal(1))
        for region in pilot.data["regions"][1:]:
            index = region["index"]
            assert pilot.state["map_id"] == region["maps"][0]
            for npc in list(pilot.state["story"]["view"]["npcs"]):
                authored = pilot.data["npcs"][npc["id"]]
                if authored.get("hide_on_campaign_complete") and authored.get("role") != "final":
                    pilot.meet(npc["id"])
                    ally_maps.add(index)
            roles = pilot.roles(region)
            pilot.assignment(roles["quest"], "accept_quest")
            if "trainer" in roles:
                pilot.challenge(roles["trainer"])
                if index == 1:
                    battle = pilot.state["battle"]
                    pilot.engine.handle(pilot.state, "battle", {"action": "guard", "battle_id": battle["id"],
                                                               "expected_turn": battle["turn"]})
                    revision = checkpoint(pilot, database, key, revision)
                    snapshots["midbattle"] = copy.deepcopy(pilot.state)
                assert pilot.fight()["won"], f"Ordinary owned team could not clear map {index + 1}"
            pilot.assignment(roles["quest"], "complete_quest")
            profile = pilot.state["story"]
            assert roles["quest"] in profile["completed"]
            assert len(profile["badges"]) == index
            assert not pilot.state.get("permanent_rewards", {}).get("shiny_scan_mastery")
            assert pilot.state["scan"] == scans, "Scripted hacked tamers must never grant wild scan data"
            assert [monster["uid"] for monster in pilot.state["party"]] == original_uids
            if index in (25, 26, 29):
                revision = checkpoint(pilot, database, key, revision)
                snapshots[index] = copy.deepcopy(pilot.state)
            if "final" in roles:
                with pytest.raises(GameError):
                    pilot.portal(0)
                pilot.recover_and_supply()
                pilot.challenge(roles["final"])
                assert not pilot.fight(deliberately_lose=True)["won"]
                assert not pilot.state.get("permanent_rewards", {}).get("shiny_scan_mastery")
                assert roles["final"] in {row["id"] for row in pilot.state["story"]["view"]["npcs"]}
                assert len(pilot.state["story"]["badges"]) == 30
                snapshots["final_loss"] = copy.deepcopy(pilot.state)
                pilot.recover_and_supply()
                pilot.challenge(roles["final"])
                assert pilot.fight()["won"], "The final boss must resolve through actual battle decisions"
                snapshots["final_command"] = copy.deepcopy(pilot.last_command)
                assert pilot.state["scan"] == scans
                portals.append(pilot.portal(0))
            else:
                pilot.recover_and_supply()
                portals.append(pilot.portal(index + 1))
        revision = checkpoint(pilot, database, key, revision)
        snapshots["complete"] = copy.deepcopy(pilot.state)
    finally:
        database.close()
    return {"pilot": pilot, "snapshots": snapshots, "portals": portals, "ally_maps": ally_maps,
            "uids": original_uids}


def test_all_31_maps_are_unique_xros_maps_with_safe_hub_and_complete_portal_chain():
    pilot = GhostlinePilot()
    data = pilot.data
    regions = data["regions"]
    assert len(regions) == 31 and [row["index"] for row in regions] == list(range(31))
    maps = [region["maps"][0] for region in regions]
    assert len(set(maps)) == 31
    assert all(pilot.engine.maps[mid]["region_id"] == "xros_wars" for mid in maps)
    assert all(len(region["maps"]) == 1 for region in regions)
    assert not any(npc.get("team") for npc in data["npcs"].values() if npc["map_id"] == maps[0])
    hub_roles = {npc["role"] for npc in data["npcs"].values() if npc["map_id"] == maps[0]}
    assert {"shop", "healer", "lab", "farm"} <= hub_roles
    for index, current in enumerate(maps[:-1]):
        assert any(row["to_map"] == maps[index + 1] for row in data["maps"][current]["exits"])
    levels = [region["level_min"] for region in regions[1:]]
    assert levels == sorted(levels) and levels[0] <= 10 and levels[-1] >= 90


def test_full_campaign_earns_all_proofs_and_mastery_using_only_real_battle_controls(played_ghostline):
    played = played_ghostline
    pilot, state = played["pilot"], played["snapshots"]["complete"]
    assert len(played["portals"]) == 31, "All thirty forward portals and the final hub portal must function"
    assert pilot.controls >= 30 and pilot.dialogue_pages >= 60
    assert 8 <= len(played["ally_maps"]) < 30, "The trusted source must recur without occupying every mission"
    assert len(state["story"]["badges"]) == 30
    assert state["story"]["view"]["completed"]
    assert state["permanent_rewards"]["shiny_scan_mastery"] is True
    assert not state["permanent_rewards"].get("paradox_scan_mastery")
    assert state["story"]["view"]["scan_bonus"] == 20
    assert [monster["uid"] for monster in state["party"]] == played["uids"]
    assert all(monster["level"] <= 99 for monster in state["party"])


def test_final_boss_and_all_ally_instances_stay_gone_after_reload_and_replayed_requests(played_ghostline):
    pilot = GhostlinePilot()
    pilot.state = copy.deepcopy(played_ghostline["snapshots"]["complete"])
    pilot.engine._refresh(pilot.state)
    saved = copy.deepcopy(pilot.state)
    with pytest.raises(GameError):
        pilot.engine.handle(pilot.state, "battle", played_ghostline["snapshots"]["final_command"])
    assert pilot.state["credits"] == saved["credits"]
    assert pilot.state["permanent_rewards"] == saved["permanent_rewards"]
    for region in pilot.data["regions"]:
        pilot.story("travel", chapter=region["index"])
        removed = [npc for npc in pilot.data["npcs"].values()
                   if npc["map_id"] == pilot.state["map_id"] and npc.get("hide_on_campaign_complete")]
        visible = {npc["id"] for npc in pilot.state["story"]["view"]["npcs"]}
        for npc in removed:
            assert npc["id"] not in visible
            for action, fields in (("talk", {}), ("challenge", {"token": "stale-ally-token"})):
                with pytest.raises(GameError):
                    pilot.story(action, npc_id=npc["id"], **fields)
    pilot.story("return")
    pilot.enter()
    assert pilot.state["story"]["view"]["completed"]
    assert pilot.state["permanent_rewards"] == saved["permanent_rewards"]


def test_owned_resources_native_services_and_three_saved_campaigns_remain_independent():
    pilot = GhostlinePilot()
    state = pilot.state
    initial = copy.deepcopy({key: state[key] for key in OWNED})
    world = copy.deepcopy({key: state.get(key) for key in story.LOCATION_FIELDS})
    saved = {}
    for campaign in ("dawn_relay", "world_ds_paradox", CAMPAIGN):
        pilot.story("enter", campaign_id=campaign)
        assert {key: state[key] for key in OWNED} == initial
        if campaign == CAMPAIGN:
            pilot.portal(1)
            quest = pilot.roles(pilot.data["regions"][1])["quest"]
            pilot.assignment(quest, "accept_quest")
        saved[campaign] = copy.deepcopy(state["story"])
        pilot.story("return")
    for campaign in ("world_ds_paradox", "dawn_relay", CAMPAIGN):
        pilot.story("enter", campaign_id=campaign)
        for key in ("id", "location", "badges", "completed", "quest_accepted", "stats"):
            assert state["story"][key] == saved[campaign][key]
        assert {key: state[key] for key in OWNED} == initial
        pilot.story("return")
    pilot.enter()
    position = {key: state[key] for key in ("map_id", "x", "y")}
    pilot.engine.handle(state, "digilab", {"action": "enter"})
    assert state["in_story"] and state["in_lab"]
    credits, capsules = state["credits"], state["inventory"]["hp_s"]
    pilot.engine.handle(state, "shop", {"item": "hp_s", "quantity": 1})
    assert state["credits"] < credits and state["inventory"]["hp_s"] == capsules + 1
    pilot.engine.handle(state, "digilab", {"action": "return"})
    pilot.engine.handle(state, "digifarm", {"action": "enter"})
    assert state["in_story"] and state["in_farm"]
    pilot.engine.handle(state, "digifarm", {"action": "return"})
    assert {key: state[key] for key in position} == position
    earned = copy.deepcopy({key: state[key] for key in OWNED})
    pilot.story("return")
    assert {key: state.get(key) for key in story.LOCATION_FIELDS} == world
    assert {key: state[key] for key in OWNED} == earned


def test_earned_mastery_gives_six_shiny_scan_from_real_wild_victory(played_ghostline):
    pilot = GhostlinePilot()
    pilot.state = copy.deepcopy(played_ghostline["snapshots"]["complete"])
    pilot.engine._refresh(pilot.state)
    pilot.story("return")
    engine, state = pilot.engine, pilot.state
    area = min((area for area in engine.maps.values() if area.get("region_id") == "xros_wars"),
               key=lambda area: (area["level"], area["id"]))
    engine.handle(state, "travel", {"map_id": area["id"]})
    with patch.object(engine.rng, "random", return_value=.03), patch.object(engine.rng, "choices", return_value=[1]):
        engine.handle(state, "encounter", {})
    enemy = state["battle"]["enemies"][0]
    assert enemy["shiny"]
    sid = enemy["species_id"]
    before = state["scan"].get(sid, 0)
    while state["battle"]:
        engine.handle(state, "battle", pilot.choose_action())
    assert state["scan"][sid] == before + 6
    assert engine.rules["shiny_encounter_chance"] == .01
    assert engine.rules["shiny_scan_gain"] == 5


def test_locked_portals_hub_battles_and_forged_progress_are_rejected():
    pilot = GhostlinePilot()
    pilot.enter()
    hub_gate = pilot.data["maps"][pilot.state["map_id"]]["exits"][0]
    assert math.hypot(pilot.state["x"] - hub_gate["x"], pilot.state["y"] - hub_gate["y"]) > story.TALK_RADIUS
    with pytest.raises(GameError, match="Walk closer"):
        pilot.story("exit", exit_id=hub_gate["id"])
    for action, payload in (("train", {}), ("travel", {"chapter": 2}),
                            ("travel", {"chapter": 30}), ("complete", {"winner": "player"})):
        with pytest.raises(GameError):
            pilot.story(action, **payload)
    with pytest.raises(GameError):
        pilot.engine.handle(pilot.state, "encounter", {})
    gate = pilot.portal(1)
    with pytest.raises(GameError):
        pilot.story("exit", exit_id=gate["id"])
    region = pilot.data["regions"][1]
    roles = pilot.roles(region)
    next_gate = next(row for row in pilot.data["maps"][pilot.state["map_id"]]["exits"]
                     if row["to_map"] == pilot.data["regions"][2]["maps"][0])
    pilot.walk_to({**next_gate, "map_id": pilot.state["map_id"], "name": "Locked portal"})
    with pytest.raises(GameError):
        pilot.story("exit", exit_id=next_gate["id"])
    dialogue = pilot.meet(roles["trainer"])
    assert "challenge" not in {row["id"] for row in dialogue["choices"]}
    pilot.assignment(roles["quest"], "accept_quest")
    dialogue = pilot.meet(roles["quest"])
    assert "complete_quest" not in {row["id"] for row in dialogue["choices"]}
    with pytest.raises(GameError):
        pilot.story("dialogue", token=dialogue["token"], choice="complete_quest")


def test_defeat_and_forbidden_flee_cannot_hack_tamer_or_unlock_quest_but_retry_can():
    pilot = GhostlinePilot(seed=1447, established=False)
    pilot.enter()
    pilot.portal(1)
    roles = pilot.roles(pilot.data["regions"][1])
    pilot.assignment(roles["quest"], "accept_quest")
    pilot.challenge(roles["trainer"])
    battle = pilot.state["battle"]
    with pytest.raises(GameError, match="cannot be fled"):
        pilot.engine.handle(pilot.state, "battle", {"action": "flee", "battle_id": battle["id"],
                                                  "expected_turn": battle["turn"]})
    assert not pilot.state["story"]["hacked"]
    assert not pilot.fight(deliberately_lose=True)["won"]
    profile = pilot.state["story"]
    assert not profile["hacked"] and not profile["badges"] and not profile["completed"]
    assert roles["quest"] in profile["quest_accepted"]
    assert not pilot.state.get("permanent_rewards", {}).get("shiny_scan_mastery")
    for _ in range(12):
        pilot.recover_and_supply()
        pilot.challenge(roles["trainer"])
        if pilot.fight()["won"]:
            break
        pilot.recover_and_supply()
        pilot.story("train")
        pilot.fight()
    else:
        pytest.fail("An ordinary new Rookie could not recover, train and retry the first mission")
    assert roles["trainer"] in profile["hacked"]
    assert roles["trainer"] in profile["completed"]
    assert not profile["badges"], "A battle win cannot replace the required quest report"
    pilot.assignment(roles["quest"], "complete_quest")
    assert len(profile["badges"]) == 1


def test_shared_engine_keeps_fresh_players_ally_dialogue_and_plot_private(played_ghostline):
    completed = copy.deepcopy(played_ghostline["snapshots"]["complete"])
    engine = GameEngine(ROOT, seed=1453)
    data = story.content(engine, CAMPAIGN)
    authored = copy.deepcopy(data)
    fresh = engine.new_player("GhostlineFresh", next(iter(engine.tamers)), "agumon")
    engine.handle(fresh, "story", {"action": "enter", "campaign_id": CAMPAIGN})
    before = copy.deepcopy(fresh)
    engine._refresh(completed)
    engine.handle(completed, "story", {"action": "travel", "chapter": 0})
    engine._refresh(fresh)
    assert fresh == before and story.content(engine, CAMPAIGN) == authored
    hub = data["regions"][0]["maps"][0]
    mara = next(npc for npc in data["npcs"].values()
                if npc["map_id"] == hub and npc.get("hide_on_campaign_complete"))
    assert mara["id"] in {npc["id"] for npc in fresh["story"]["view"]["npcs"]}
    assert mara["id"] not in {npc["id"] for npc in completed["story"]["view"]["npcs"]}
    pilot = GhostlinePilot()
    pilot.engine, pilot.state = engine, fresh
    pilot.meet(mara["id"])
    assert not fresh["story"]["revealed"] and not fresh["story"]["hacked"]
    assert not fresh.get("permanent_rewards", {}).get("shiny_scan_mastery")
    view = fresh["story"]["view"]
    assert view["final_npc_id"] is None and view["final_name"] is None and view["final_team"] == []
    assert fresh["story"]["champion"]["holder_id"] is None
    for row in view["chapters"][2:]:
        assert row["name"].startswith("Encrypted") and row["synopsis"] == ""
        assert all(area["name"] == "Encrypted destination" for area in row["maps"])
    for row in view["badges"][1:]:
        assert row["name"].startswith("Encrypted Access Proof")
    assert story.content(engine, CAMPAIGN) == authored


def test_betrayal_happens_only_at_map_27_and_survives_a_fresh_engine_reload(played_ghostline):
    snapshots = played_ghostline["snapshots"]
    assert not snapshots[25]["story"]["revealed"]
    assert snapshots[26]["story"]["revealed"]
    assert snapshots[26]["story"]["view"]["revealed"]
    assert len(snapshots[26]["story"]["badges"]) == 26
    assert snapshots[26]["story"]["view"]["final_name"]
    assert not snapshots[26].get("permanent_rewards", {}).get("shiny_scan_mastery")
