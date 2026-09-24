"""Home walking uses normal authoritative physics without changing the field."""
import asyncio
import copy
import json
import math
import time

import pytest

from venom.common.farm import (FARM_ENTRY, FARM_SPAWN, farm_walkable,
                               move_farm_position, normalize_farm_position)
from venom.common.game import GameEngine
from venom.server.database import Database
from venom.server.main import Session, WorldServer


@pytest.fixture
def walking_home(tmp_path):
    (tmp_path / "catalog.json").write_text(json.dumps({
        "species": [{"id": "rookie", "name": "Rookie", "stage": "rookie", "type": "free", "attribute": "neutral"}],
        "maps": [{"id": "field", "name": "Field", "level": 1, "width": 600, "height": 400, "spawn": [100, 100]}],
        "tamers": [{"id": "tamer", "name": "Tamer"}],
    }))
    engine = GameEngine(tmp_path, seed=12)
    state = engine.new_player("Farmer", "tamer", "rookie")
    return engine, WorldServer(engine, None, {}), Session(None, "farmer", "token", state, 0)


def test_island_geometry_includes_grass_and_excludes_water_and_cliffs():
    assert FARM_ENTRY == {"id": "digifarm", "width": 1672, "height": 941}
    for point in (FARM_SPAWN, (200, 250), (1500, 470), (400, 720), (1120, 730), (800, 160)):
        assert farm_walkable(*point), point
    for point in ((0, 0), (1672, 941), (836, 60), (836, 900), (80, 370), (450, 790), (1500, 650),
                  (150, 207), (225, 671)):
        assert not farm_walkable(*point), point


@pytest.mark.parametrize("direction", [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)])
def test_full_island_walk_never_crosses_shore_or_warps(direction):
    point = FARM_SPAWN
    for _ in range(120):
        moved = move_farm_position(point, *direction, .1)
        assert farm_walkable(*moved)
        assert math.dist(point, moved) <= 18.000001
        point = moved
    assert point != FARM_SPAWN


def test_equal_cardinal_diagonal_speed_and_actual_wall_sliding():
    straight = move_farm_position(FARM_SPAWN, 1, 0, .1)
    diagonal = move_farm_position(FARM_SPAWN, 1, 1, .1)
    assert math.dist(FARM_SPAWN, straight) == pytest.approx(18)
    assert math.dist(FARM_SPAWN, diagonal) == pytest.approx(18)
    # Near the north shore, upward motion blocks while horizontal motion slides.
    start = (840, 147.5)
    assert farm_walkable(*start)
    end = move_farm_position(start, 1, -1, .1)
    assert end[0] > start[0] + 10 and start[1] - end[1] < 2
    assert farm_walkable(*end)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1", None, 10**400])
def test_invalid_coordinates_migrate_safely_without_touching_field(value):
    state = {"map_id": "field", "x": 110, "y": 140,
             "return_location": {"map_id": "field", "x": 110, "y": 140},
             "farm_position": {"x": value, "y": 400, "direction": "down"}}
    before = copy.deepcopy(state)
    saved = normalize_farm_position(state)
    assert (saved["x"], saved["y"], saved["direction"]) == (*FARM_SPAWN, "down")
    assert {k: state[k] for k in ("map_id", "x", "y", "return_location")} == {
        k: before[k] for k in ("map_id", "x", "y", "return_location")}


def test_refresh_initializes_legacy_home_and_preserves_valid_home_facing(walking_home):
    engine, _, session = walking_home
    state = session.state
    state.pop("farm_position")
    engine._refresh(state)
    assert state["farm_position"] == {"x": 836, "y": 470, "direction": "down"}
    state["farm_position"] = {"x": 600, "y": 550, "direction": "up_left"}
    engine._refresh(state)
    assert state["farm_position"] == {"x": 600, "y": 550, "direction": "up_left"}
    for bad in (None, [], {"x": 5, "y": 6}, {"x": 700, "y": 900}):
        state["farm_position"] = bad
        engine._refresh(state)
        assert (state["farm_position"]["x"], state["farm_position"]["y"]) == FARM_SPAWN


def test_home_movement_preserves_return_and_never_triggers_encounter(walking_home):
    engine, world, session = walking_home
    state = session.state
    engine.handle(state, "digifarm", {"action": "return"})
    state.update(x=123.5, y=221.5)
    engine.handle(state, "digifarm", {"action": "enter"})
    before = copy.deepcopy(state["return_location"])
    session.walked = session.next_encounter
    assert not world.move(session, {"space": "farm", "dx": 1, "dy": -1, "dt": .1})
    farm = state["farm_position"]
    assert farm["x"] > FARM_SPAWN[0] and farm["y"] < FARM_SPAWN[1]
    assert farm["direction"] == "up_right"
    assert state["return_location"] == before and not state["battle"]
    assert session.walked == session.next_encounter
    engine.handle(state, "digifarm", {"action": "return"})
    assert {k: state[k] for k in before} == before
    engine.handle(state, "digifarm", {"action": "enter"})
    assert state["farm_position"] == farm


def test_stale_inputs_cannot_move_across_home_return_transition(walking_home):
    engine, world, session = walking_home
    before = copy.deepcopy(session.state)
    world.move(session, {"space": "field", "dx": 1, "dy": 0, "dt": .1})
    assert session.state["farm_position"] == before["farm_position"]
    engine.handle(session.state, "digifarm", {"action": "return"})
    world.move(session, {"space": "farm", "dx": 1, "dy": 0, "dt": .1})
    assert (session.state["x"], session.state["y"]) == (before["x"], before["y"])


def test_farm_uses_server_time_budget_and_rejects_bad_inputs(walking_home):
    _, world, session = walking_home
    start = time.monotonic()
    for _ in range(1000):
        world.move(session, {"space": "farm", "dx": 1, "dy": 0, "dt": .1})
    elapsed = time.monotonic() - start
    assert session.state["farm_position"]["x"] - FARM_SPAWN[0] <= 180 * (elapsed + .1) + 1
    before = copy.deepcopy(session.state["farm_position"])
    for payload in ({"dx": float("nan")}, {"dy": float("inf")}, {"dt": -1}, {"dt": .11},
                    {"dx": 10}, {"dy": True}, {"space": "unknown"}):
        with pytest.raises(ValueError):
            world.move(session, {"space": "farm", "dx": 1, "dy": 0, "dt": .1, **payload})
    assert session.state["farm_position"] == before


def test_live_farm_position_ack_save_logout_and_login(walking_home, tmp_path):
    from websockets.asyncio.client import connect
    from websockets.asyncio.server import serve

    engine, _, _ = walking_home
    database = Database({"driver": "sqlite", "path": str(tmp_path / "walk.sqlite3")}, dev=True)
    database.initialize()
    world = WorldServer(engine, database, {"allow_registration": True})

    async def scenario():
        async with serve(world.connection, "127.0.0.1", 0) as listener:
            address = f"ws://127.0.0.1:{listener.sockets[0].getsockname()[1]}"

            async def request(ws, op, **payload):
                await ws.send(json.dumps({"op": op, "rid": 1, **payload}))
                response = json.loads(await ws.recv())
                assert response["ok"], response
                return response

            async with connect(address) as socket:
                await socket.recv()
                registered = await request(socket, "register", username="Farmer", password="correct-horse",
                                           tamer="tamer", starter="rookie")
                original = registered["state"]
                moved = await request(socket, "move", space="farm", dx=1, dy=-1, dt=.1)
                home = moved["position"]
                assert set(home) == {"space", "x", "y", "direction"}
                assert home["space"] == "farm" and home["direction"] == "up_right"
                assert home["x"] > original["farm_position"]["x"]
                await request(socket, "logout")
                await socket.wait_closed()
            async with connect(address) as socket:
                await socket.recv()
                logged = await request(socket, "login", username="Farmer", password="correct-horse")
                assert logged["state"]["farm_position"] == {key: home[key] for key in ("x", "y", "direction")}
                assert (logged["state"]["x"], logged["state"]["y"]) == (original["x"], original["y"])
                returned = await request(socket, "digifarm", action="return")
                stale = await request(socket, "move", space="farm", dx=1, dy=0, dt=.1)
                assert stale["position"] == {"space": "field", **{
                    key: returned["state"][key] for key in ("map_id", "x", "y")}}
        saved, _ = database.load("farmer")
        assert saved["farm_position"]["x"] == home["x"]

    try:
        asyncio.run(scenario())
    finally:
        database.close()
