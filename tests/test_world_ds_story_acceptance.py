"""Played World DS acceptance against the production engine and native services.

The full campaign uses normal talk/quest/travel and manual battle controls. Its
level-10 owned-partner fixture is never replaced, healed by direct mutation or
awarded a client-supplied win during the played route.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from venom.common import story
from venom.common.game import GameEngine, GameError
from venom.server.database import Database
from test_story_acceptance import CampaignPilot

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = "world_ds_paradox"


class WorldDSPilot(CampaignPilot):
    """Reuse the existing manual combat and collision-aware walking pilot."""

    def __init__(self, seed=611, starter="agumon", level=10):
        super().__init__(seed=seed, starter=starter)
        # Character fixture represents an existing low-level account, matching
        # the intended level-10 campaign entry. Entry itself grants no levels.
        self.state["party"][0] = self.engine._monster(starter, level, cam=10)
        self.engine._refresh(self.state)

    @property
    def data(self):
        return story.content(self.engine, CAMPAIGN)

    def enter(self):
        return self.story("enter", campaign_id=CAMPAIGN)

    def meet(self, npc_id):
        npc = self.data["npcs"][npc_id]
        region = next(row for row in self.data["regions"] if npc["map_id"] in row["maps"])
        if self.state["map_id"] != npc["map_id"]:
            self.story("travel", chapter=region["index"], map_id=npc["map_id"])
        self.walk_to(npc)
        self.story("talk", npc_id=npc_id)
        while True:
            dialogue = self.state["story"]["view"]["dialogue"]
            assert dialogue and dialogue["text"].strip(), f"Missing dialogue for {npc_id}"
            self.dialogue_pages += 1
            if not any(choice["id"] == "next" for choice in dialogue["choices"]):
                return dialogue
            self.story("dialogue", token=dialogue["token"], choice="next")

    def choose(self, choice):
        dialogue = self.state["story"]["view"]["dialogue"]
        assert choice in {row["id"] for row in dialogue["choices"]}, dialogue
        self.story("dialogue", token=dialogue["token"], choice=choice)

    def challenge(self, npc_id):
        self.meet(npc_id)
        self.choose("challenge")
        battle = self.state["battle"]
        assert battle and battle["kind"] == "story"
        return self.data["npcs"][npc_id]

    def quest(self, npc_id, action):
        self.meet(npc_id)
        self.choose(action)

    def field_roles(self, region):
        return {self.data["npcs"][ident]["role"]: ident for ident in region["npc_ids"]
                if self.data["npcs"][ident]["role"] in ("quest", "trainer", "warden")}

    def win_with_recovery(self, npc_id):
        self.challenge(npc_id)
        scan_before = copy.deepcopy(self.state["scan"])
        result = self.fight()
        assert self.state["scan"] == scan_before, "Scripted NPC partners must not grant wild scans"
        # A normal player can recover, buy supplies, train and retry. Requiring
        # bounded retries catches unreasonable chapter spikes and softlocks.
        for _ in range(6):
            if result["won"]:
                return result
            self.recover_and_supply()
            self.story("train")
            self.fight()
            self.recover_and_supply()
            self.challenge(npc_id)
            scan_before = copy.deepcopy(self.state["scan"])
            result = self.fight()
            assert self.state["scan"] == scan_before, "Scripted NPC partners must not grant wild scans"
        assert result["won"], f"Cannot clear {npc_id} through normal play: {self.results[-8:]}"
        return result

    def clear_field(self, region):
        roles = self.field_roles(region)
        self.quest(roles["quest"], "accept_quest")
        self.win_with_recovery(roles["trainer"])
        self.quest(roles["quest"], "complete_quest")
        self.recover_and_supply()
        self.win_with_recovery(roles["warden"])
        self.recover_and_supply()


def test_eighteen_authentic_ds_maps_seventeen_paradox_crests_and_level_curve():
    pilot = WorldDSPilot()
    data = pilot.data
    regions = data["regions"]
    assert len(regions) == 18
    assert [row["index"] for row in regions] == list(range(18))
    map_ids = [ident for region in regions for ident in region["maps"]]
    assert len(map_ids) == len(set(map_ids)) == 18
    assert all(ident.startswith("world_ds_") for ident in map_ids)
    imported = json.loads((ROOT / "data/world_ds_maps.json").read_text(encoding="utf8"))
    source_maps = {area["id"]: area for area in imported["maps"]}
    assert all(ident in source_maps for ident in map_ids)
    assert not regions[0].get("badge")
    assert len([row for row in regions if row.get("badge")]) == 17
    assert len({row["badge"]["id"] for row in regions[1:]}) == 17
    levels = []
    for region in regions[1:]:
        roles = pilot.field_roles(region)
        assert set(roles) == {"quest", "trainer", "warden"}
        trainer = data["npcs"][roles["trainer"]]
        warden = data["npcs"][roles["warden"]]
        assert roles["quest"] in trainer["requires_accepted"]
        assert set((roles["quest"], roles["trainer"])) <= set(warden["requires"])
        assert all(pilot.engine.species[partner["species"]]["paradox"] for partner in warden["team"])
        levels.append(max(partner["level"] for partner in warden["team"]))
        assert max(partner["level"] for partner in trainer["team"]) <= levels[-1]
    assert 10 <= levels[0] <= 15 and levels[-1] < 100
    assert levels == sorted(set(levels)), "Each field must advance its boss level"
    finale = next(npc for npc in data["npcs"].values() if npc["role"] == "final")
    assert finale["map_id"] != regions[0]["maps"][0]
    assert len(finale["team"]) == 3
    assert all(partner["level"] == 100 for partner in finale["team"])
    assert all(pilot.engine.species[partner["species"]].get("paradox") and
               pilot.engine.species[partner["species"]]["stage"] == "mega"
               for partner in finale["team"])


def test_hub_is_peaceful_and_all_progression_prerequisites_are_authoritative():
    pilot = WorldDSPilot()
    pilot.enter()
    state = pilot.state
    assert state["story"]["campaign_id"] == CAMPAIGN
    assert state["story"]["view"]["badge_count"] == 0
    assert not state["story"]["view"]["training_available"]
    assert not any(npc.get("team") for npc in pilot.data["npcs"].values()
                   if npc["map_id"] == state["map_id"])
    for op, payload in (("story", {"action": "train"}), ("encounter", {}),
                        ("story", {"action": "travel", "chapter": 2}),
                        ("story", {"action": "travel", "chapter": 17})):
        with pytest.raises(GameError):
            pilot.engine.handle(state, op, payload)
    roles = pilot.field_roles(pilot.data["regions"][1])
    for ident in (roles["trainer"], roles["warden"]):
        dialogue = pilot.meet(ident)
        assert "challenge" not in {row["id"] for row in dialogue["choices"]}
        with pytest.raises(GameError):
            pilot.story("challenge", npc_id=ident, token=dialogue["token"])
    pilot.meet(roles["quest"])
    old_token = state["story"]["view"]["dialogue"]["token"]
    pilot.choose("accept_quest")
    with pytest.raises(GameError):
        pilot.story("dialogue", token=old_token, choice="accept_quest")
    dialogue = pilot.meet(roles["quest"])
    assert "complete_quest" not in {row["id"] for row in dialogue["choices"]}
    with pytest.raises(GameError):
        pilot.story("dialogue", token=dialogue["token"], choice="complete_quest")
    assert state["battle"] is None and state["story"]["badges"] == []
    assert not state.get("permanent_rewards", {}).get("paradox_scan_mastery")


def test_native_lab_farm_shop_materialization_evolution_and_inventory_stay_shared():
    pilot = WorldDSPilot(level=30)
    state = pilot.state
    # Existing account ownership fixture makes native evolution/materialization
    # available; all service actions themselves use production handlers.
    state["party"][0] = pilot.engine._monster("agumon", 30, abi=30, cam=100)
    state["scan"]["gabumon"] = 100
    world = {key: copy.deepcopy(state.get(key)) for key in story.LOCATION_FIELDS}
    pilot.enter()
    pilot.story("travel", chapter=1)
    roles = pilot.field_roles(pilot.data["regions"][1])
    pilot.meet(roles["quest"])
    location = {key: state[key] for key in ("map_id", "x", "y")}
    original_uid = state["party"][0]["uid"]
    credits, capsules = state["credits"], state["inventory"]["hp_s"]
    pilot.engine.handle(state, "digilab", {"action": "enter"})
    assert state["in_story"] and state["in_lab"]
    pilot.engine.handle(state, "shop", {"item": "hp_s", "quantity": 1})
    assert state["credits"] < credits and state["inventory"]["hp_s"] == capsules + 1
    pilot.engine.handle(state, "materialize", {"species_id": "gabumon"})
    assert state["scan"]["gabumon"] == 0 and len(state["party"]) == 2
    materialized_uid = state["party"][1]["uid"]
    option = next(row for row in state["evolution_options"][0] if row["eligible"] and not row["devolve"])
    pilot.engine.handle(state, "evolve", {"party_index": 0, "to": option["to"]})
    assert state["party"][0]["uid"] == original_uid
    assert state["party"][0]["species_id"] == option["to"] and state["party"][0]["level"] == 1
    pilot.engine.handle(state, "party", {"action": "deposit", "index": 1})
    pilot.engine.handle(state, "digifarm", {"action": "enter"})
    resident = next(row for row in state["storage"] if row["uid"] == materialized_uid)
    cam = resident["cam"]
    pilot.engine.handle(state, "digifarm", {"action": "feed", "uid": materialized_uid,
                                            "item": "digimeat_cam", "quantity": 1})
    assert resident["cam"] > cam and state["in_story"] and state["in_farm"]
    pilot.engine.handle(state, "party", {"action": "withdraw", "index": 0})
    pilot.engine.handle(state, "digifarm", {"action": "return"})
    assert {key: state[key] for key in location} == location
    owned = copy.deepcopy({key: state[key] for key in ("party", "storage", "scan", "inventory", "credits")})
    pilot.story("return")
    assert {key: state.get(key) for key in story.LOCATION_FIELDS} == world
    assert {key: state[key] for key in owned} == owned
    pilot.enter()
    assert {key: state[key] for key in location} == location
    assert {key: state[key] for key in owned} == owned


def test_sqlite_midbattle_reload_loss_recovery_and_retry_keep_quest_binding(tmp_path):
    pilot = WorldDSPilot(seed=713)
    pilot.enter()
    roles = pilot.field_roles(pilot.data["regions"][1])
    pilot.quest(roles["quest"], "accept_quest")
    pilot.challenge(roles["trainer"])
    state = pilot.state
    battle = state["battle"]
    pilot.engine.handle(state, "battle", {"action": "guard", "battle_id": battle["id"],
                                           "expected_turn": battle["turn"]})
    assert state["battle"], "The opening battle must allow a genuine midbattle save"
    db = Database({"driver": "sqlite", "path": str(tmp_path / "ds-story.sqlite3")}, dev=True)
    db.initialize()
    try:
        key = db.register(state["username"], "ds-acceptance-password-2026", state)
        restored, revision = db.load(key)
        before = copy.deepcopy(restored)
        pilot.engine = GameEngine(ROOT, seed=999)
        pilot.engine._refresh(restored)
        assert restored["battle"] == before["battle"]
        assert restored["story"]["active_battle"] == before["story"]["active_battle"]
        pilot.state = restored
        assert not pilot.fight(deliberately_lose=True)["won"]
        assert roles["trainer"] not in restored["story"]["completed"]
        assert restored["story"]["badges"] == []
        assert not restored.get("permanent_rewards", {}).get("paradox_scan_mastery")
        pilot.recover_and_supply()
        assert pilot.win_with_recovery(roles["trainer"])["won"]
        pilot.quest(roles["quest"], "complete_quest")
        assert roles["quest"] in restored["story"]["completed"]
        db.save(key, restored, revision)
        final, _ = db.load(key)
        assert final["story"] == restored["story"]
        assert final["party"] == restored["party"]
    finally:
        db.close()


def test_dawn_and_ds_progress_are_independent_and_return_to_their_own_locations():
    pilot = WorldDSPilot()
    # Actually earn the first Dawn trial, then park that campaign.
    pilot.story("enter")
    dawn_campaign = pilot.state["story"]["campaign_id"]
    dawn_data = story.content(pilot.engine)
    dawn_trainer = next(npc for npc in dawn_data["npcs"].values() if npc["role"] == "trainer")
    CampaignPilot.challenge(pilot, dawn_trainer["id"])
    assert pilot.fight()["won"]
    dawn_id = pilot.state["story"]["id"]
    dawn_completed = copy.deepcopy(pilot.state["story"]["completed"])
    dawn_location = copy.deepcopy(pilot.state["story"]["location"])
    pilot.story("return")
    pilot.enter()
    assert pilot.state["story"]["id"] != dawn_id
    assert not pilot.state["story"]["badges"] and not pilot.state["story"]["completed"]
    pilot.clear_field(pilot.data["regions"][1])
    ds_id = pilot.state["story"]["id"]
    ds_location = copy.deepcopy(pilot.state["story"]["location"])
    assert len(pilot.state["story"]["badges"]) == 1
    pilot.story("return")
    pilot.story("enter", campaign_id=dawn_campaign)
    assert pilot.state["story"]["id"] == dawn_id
    assert pilot.state["story"]["completed"] == dawn_completed
    assert pilot.state["story"]["location"] == dawn_location
    assert pilot.state["story"]["badges"] == []
    pilot.story("return")
    pilot.enter()
    assert pilot.state["story"]["id"] == ds_id
    assert pilot.state["story"]["location"] == ds_location
    assert len(pilot.state["story"]["badges"]) == 1


@pytest.mark.parametrize(("starter", "seed"), [("agumon", 611), ("betamon", 913)])
def test_low_level_owned_team_can_play_all_seventeen_crests_and_finale(starter, seed):
    pilot = WorldDSPilot(seed=seed, starter=starter)
    original_uid = pilot.state["party"][0]["uid"]
    pilot.enter()
    assert pilot.state["party"][0]["level"] == 10
    for region in pilot.data["regions"][1:]:
        pilot.clear_field(region)
        profile = pilot.state["story"]
        assert len(profile["badges"]) == region["index"]
        assert region["badge"]["id"] in profile["badges"]
        assert pilot.state["party"][0]["uid"] == original_uid
        assert not pilot.state.get("permanent_rewards", {}).get("paradox_scan_mastery")
    finale = next(npc for npc in pilot.data["npcs"].values() if npc["role"] == "final")
    pilot.challenge(finale["id"])
    enemies = pilot.state["battle"]["enemies"]
    assert len(enemies) == 3 and all(enemy["level"] == 100 and enemy["paradox"] for enemy in enemies)
    scan_before = copy.deepcopy(pilot.state["scan"])
    assert pilot.fight()["won"], f"Finale failed after the naturally played campaign: {pilot.results[-8:]}"
    assert pilot.state["scan"] == scan_before, "The scripted finale must not grant wild scans"
    assert pilot.state["permanent_rewards"]["paradox_scan_mastery"] is True
    assert pilot.state["story"]["view"]["completed"]
    assert pilot.state["story"]["view"]["scan_bonus"] == 20
    assert len(pilot.state["story"]["badges"]) == 17
    assert pilot.controls >= 35 and pilot.dialogue_pages >= 68
    assert all(monster["level"] <= 99 for monster in pilot.state["party"])
    before = copy.deepcopy(pilot.state)
    with pytest.raises(GameError):
        pilot.engine.handle(pilot.state, "battle", pilot.last_command)
    assert pilot.state["permanent_rewards"] == before["permanent_rewards"]
    assert pilot.state["credits"] == before["credits"]
    # The finale is replayable; its permanent benefit cannot stack or disappear.
    pilot.recover_and_supply()
    pilot.challenge(finale["id"])
    assert not pilot.fight(deliberately_lose=True)["won"]
    assert pilot.state["permanent_rewards"]["paradox_scan_mastery"] is True
    assert pilot.state["story"]["view"]["completed"]
    pilot.recover_and_supply()
    replay_wallet = pilot.state["credits"]
    replay_inventory = copy.deepcopy(pilot.state["inventory"])
    pilot.challenge(finale["id"])
    replay = pilot.fight()
    assert replay["won"] and replay["replay"] and not replay["first_clear"]
    assert replay["credits"] == 0 and pilot.state["credits"] == replay_wallet
    # Fighting can consume medicine; a replay must never add reward items.
    assert all(quantity <= replay_inventory.get(ident, 0) for ident, quantity in pilot.state["inventory"].items())
    assert pilot.state["permanent_rewards"] == before["permanent_rewards"]
    assert len(pilot.state["story"]["badges"]) == 17
    restored = json.loads(json.dumps(pilot.state))
    engine = GameEngine(ROOT, seed=73)
    engine._refresh(restored)
    assert restored["story"] == pilot.state["story"]
    assert restored["permanent_rewards"] == pilot.state["permanent_rewards"]


def test_real_socket_ds_instances_exclude_bots_and_keep_personal_progress(tmp_path):
    """Even with real persistent rivals running, DS belongs to its owner."""
    import asyncio
    from websockets.asyncio.client import connect
    from websockets.asyncio.server import serve
    from venom.server.main import GAME_OPS, WorldServer

    async def run():
        db = Database({"driver": "sqlite", "path": str(tmp_path / "ds-socket.sqlite3")}, dev=True)
        db.initialize()
        engine = GameEngine(ROOT, seed=821)
        world = WorldServer(engine, db, {"allow_registration": True,
                                        "rivals": {"enabled": True, "count": 2, "seed": 817}})
        await world.initialize_community()
        assert world.community.ready and len(world.community.bots.bots) == 2
        listener = await serve(world.connection, "127.0.0.1", 0, max_size=65536)
        url = f"ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}"
        request_id = 0
        pending = {}

        async def receive(ws, op, rid=None):
            def matches(row):
                return row.get("op") == op and (rid is None or row.get("rid") == rid)
            queue = pending.setdefault(ws, [])
            for index, row in enumerate(queue):
                if matches(row):
                    return queue.pop(index)
            while True:
                packet = json.loads(await asyncio.wait_for(ws.recv(), 5))
                if matches(packet):
                    return packet
                queue.append(packet)

        async def request(ws, op, **fields):
            nonlocal request_id
            if op in GAME_OPS:
                await asyncio.sleep(.175)
            request_id += 1
            await ws.send(json.dumps({"op": op, "rid": request_id, **fields}))
            return await receive(ws, "result", request_id)

        async def action(ws, op, **fields):
            packet = await request(ws, op, **fields)
            assert packet["ok"], packet
            return packet.get("state")

        try:
            async with connect(url, max_size=8 * 1024 * 1024) as alice, connect(url, max_size=8 * 1024 * 1024) as bob:
                for ws, name in ((alice, "DSPrivateAlice"), (bob, "DSPrivateBob")):
                    await receive(ws, "hello")
                    await action(ws, "register", username=name, password="ds-private-password-2026",
                                 tamer=next(iter(engine.tamers)), starter="agumon")
                    await action(ws, "story", action="enter", campaign_id=CAMPAIGN)
                a, b = world.sessions["dsprivatealice"], world.sessions["dsprivatebob"]
                assert not world.same_place(a, b)
                assert world.place(a) == (a.state["map_id"], "story", "dsprivatealice")
                await world.broadcast_once()
                for ws, name in ((alice, "DSPrivateAlice"), (bob, "DSPrivateBob")):
                    packet = await receive(ws, "world")
                    assert [row["username"] for row in packet["players"]] == [name]
                    assert not any(row.get("is_bot") for row in packet["players"])
                assert a.state["story"]["id"] != b.state["story"]["id"]
                bob_before = copy.deepcopy(b.state["story"])
                changed = await action(alice, "story", action="travel", chapter=1)
                assert changed["story"]["chapter"] == 1
                assert b.state["story"] == bob_before
                assert b.state["story"]["chapter"] == 0
                assert world.community.ready and len(world.community.bots.bots) == 2
        finally:
            listener.close()
            await listener.wait_closed()
            if world.community:
                await asyncio.to_thread(world.community.shutdown)
            db.close()

    asyncio.run(run())


def test_mastery_applies_to_an_actual_paradox_field_training_victory():
    pilot = WorldDSPilot(seed=428, starter="palmon")
    # An account which has already earned mastery keeps it for all later wild
    # battles. Production reward issuance is exercised by the full campaign.
    pilot.state["permanent_rewards"] = {"paradox_scan_mastery": True}
    pilot.enter()
    pilot.story("travel", chapter=1)
    pilot.story("train")
    battle = pilot.state["battle"]
    assert battle["story_training"] and len(battle["enemies"]) == 1
    enemy = battle["enemies"][0]
    assert enemy["paradox"], "First-field Palmon practice should expose its type-safe Paradox opponent"
    assert pilot.fight()["won"]
    assert pilot.state["scan"][enemy["species_id"]] == 6
    assert pilot.state["story"]["badges"] == []
