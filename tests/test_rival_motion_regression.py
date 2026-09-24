"""Delayed live scheduling must not erase the rivals' visible walking phase."""
import math
import os
from pathlib import Path
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pytest
from PIL import Image

from venom.common.game import GameEngine
from venom.server.navigation import Navigation
from test_bots import make_manager


ROOT = Path(__file__).resolve().parents[1]


def test_slow_startup_does_not_skip_every_rivals_first_walk():
    manager = make_manager(count=4, explore_seconds=16)
    # Disk/SQL initialization or a paused host can consume the entire old phase
    # deadline before the first live worker dispatch, unlike a simulation clock.
    manager.tick(45, .1, budget=1000)
    for bot in manager.bots.values():
        assert bot["runtime"]["phase"] == "explore"
        assert bot["runtime"]["path"]
        assert bot["runtime"]["phase_until"] > 45
        assert not bot["state"]["battle"]
        first = manager.navigation.sample(bot["runtime"]["path"], 45)
        later = manager.navigation.sample(bot["runtime"]["path"], 45.01)
        assert math.dist(first[:2], later[:2]) == pytest.approx(1.8)


def test_delayed_post_ranked_dispatch_still_walks_before_next_wild_battle():
    manager = make_manager(count=2, explore_seconds=16)
    bot = manager.bots["bot:00001"]
    bot["runtime"].update(phase="ranked", path=None)
    manager._ranked_step(bot, 60)
    # The exploration job entered the queue earlier than it actually ran.
    manager._explore(bot, 150)
    assert bot["stats"]["ranked_started"] == 1
    assert bot["runtime"]["phase"] == "explore"
    assert bot["runtime"]["phase_until"] > 150
    assert bot["runtime"]["path"]
    assert not bot["state"]["battle"]


def test_backlogged_exploration_keeps_walking_and_stops_where_players_saw_it():
    manager = make_manager(count=1, explore_seconds=16)
    manager.tick(0, .1)
    bot = manager.bots["bot:00001"]
    path = bot["runtime"]["path"]
    late = path["end"] + (path["end"] - path["start"]) * 2 + .23
    actor = manager.snapshot(bot["state"]["map_id"], late)[0]
    assert actor["moving"] and math.hypot(actor["dx"], actor["dy"]) == pytest.approx(1, abs=1e-5)
    manager._stop(bot, late)
    assert (bot["state"]["x"], bot["state"]["y"]) == pytest.approx((actor["x"], actor["y"]))
    assert bot["stats"]["walking_distance"] == pytest.approx(180 * (late - path["start"]), abs=.001)
    assert bot["runtime"]["path"] is None


def test_closed_patrol_repeats_continuously_without_crossing_a_wall(tmp_path):
    mask = Image.new("L", (128, 128), 255)
    for y in range(128):
        mask.putpixel((64, y), 0)
    mask.save(tmp_path / "wall.png")
    maps = {"test": {"width": 128, "height": 128, "walkable": "wall.png", "spawn": [32, 64]}}
    nav = Navigation(tmp_path, maps)
    path = nav.patrol("test", 32, 64, random.Random(918), 40, seconds=2)
    assert path["loop"]
    assert path["from"] == path["to"]
    period = path["end"] - path["start"]
    for lap in (1, 2, 8):
        boundary = path["start"] + period * lap
        left, right = nav.sample(path, boundary - .0001), nav.sample(path, boundary + .0001)
        assert math.dist(left[:2], right[:2]) <= 180 * .0002 + 1e-6
        assert nav.sample(path, boundary)[:2] == pytest.approx(path["from"])
    previous = nav.sample(path, 40)
    for step in range(1, math.ceil(period * 3 * 50)):
        sample = nav.sample(path, 40 + step / 50)
        assert nav.walkable("test", *sample[:2])
        assert sample[0] < 64
        assert math.dist(previous[:2], sample[:2]) <= 180 / 50 + 1e-6
        assert math.hypot(*sample[2:]) == pytest.approx(1)
        previous = sample


def test_finite_routes_still_stop_instead_of_looping():
    path = {"from": (20, 30), "to": (200, 30), "start": 100, "end": 101}
    assert Navigation.sample(path, 200) == (200, 30, 0, 0)


def test_cross_map_arrivals_spread_twenty_rivals_on_every_imported_map():
    engine = GameEngine(ROOT)
    nav = Navigation(ROOT, engine.maps)
    for map_id in engine.maps:
        occupied = []
        for ordinal in range(20):
            arrival = nav.arrival(map_id, occupied, ordinal)
            assert nav.walkable(map_id, *arrival), map_id
            assert all(math.dist(arrival, other) >= 16 for other in occupied), map_id
            occupied.append(arrival)
        assert len(set(occupied)) == 20


def test_real_sector_transitions_do_not_stack_at_the_player_spawn():
    manager = make_manager(count=20)
    source, target = tuple(manager.by_map)
    arrivals = list(manager.by_map[source])
    for ident in arrivals:
        bot = manager.bots[ident]
        before = manager.snapshot(target, 40)
        manager._relocate(bot, 40)
        assert bot["state"]["map_id"] == target
        shown = {actor["id"]: actor for actor in manager.snapshot(target, 40)}
        arrival = shown[ident]
        assert manager.navigation.walkable(target, arrival["x"], arrival["y"])
        assert all(math.dist((arrival["x"], arrival["y"]), (peer["x"], peer["y"])) >= 8
                   for peer in before)
        # No existing player-visible rival may be moved to make room.
        assert all(shown[peer["id"]] == peer for peer in before)
    assert len(manager.by_map[target]) == 20
    assert not manager.by_map[source]


def test_arriving_in_a_new_sector_starts_a_full_visible_walk_before_battling():
    manager = make_manager(count=1, explore_seconds=16)
    manager.tick(0, .1)
    bot = manager.bots["bot:00001"]
    original = bot["state"]["map_id"]
    # Both the old walking phase and the old map visit finish on this dispatch.
    bot["runtime"].update(phase_until=1, leave_at=1)
    manager._explore(bot, 2)
    assert bot["state"]["map_id"] != original
    assert bot["runtime"]["phase"] == "explore"
    assert bot["runtime"]["phase_until"] > 2
    assert bot["runtime"]["path"]
    assert not bot["state"]["battle"]


def test_native_rival_interpolation_drives_real_walking_frames_on_both_clients():
    import pygame
    from venom.client.assets import Assets
    from venom.client.motion import RemoteMotion
    from venom.client.world import WorldRenderer

    pygame.init()
    pygame.display.set_mode((160, 160))
    try:
        manager = make_manager(count=1, explore_seconds=16)
        manager.tick(0, .1)
        bot = manager.bots["bot:00001"]
        map_id = bot["state"]["map_id"]
        remotes = [RemoteMotion(), RemoteMotion()]
        for now in (0., .1, .2):
            actor = manager.snapshot(map_id, now)[0]
            packet = {actor["username"]: actor}
            # Clients can have completely different local clocks.
            for offset, remote in zip((0., 8000.), remotes):
                remote.push(now + offset, packet)
        name = actor["username"]
        earlier = remotes[0].positions(.22)[name]
        shown = remotes[0].positions(.25)[name]
        assert math.dist(earlier, shown) > 0
        assert shown == pytest.approx(remotes[1].positions(8000.25)[name])
        app = SimpleNamespace(players=packet, state={"map_id": map_id, "username": "Human", "party": []},
                              position=pygame.Vector2(10, 10), follower=pygame.Vector2(10, 10),
                              player_render={name: pygame.Vector2(shown)}, tamer=actor["tamer"],
                              moving=False, direction="down")
        renderer = WorldRenderer(app)
        rendered = next(row for row in renderer._actors() if row[-1] == bot["id"])
        assert rendered[2] == pygame.Vector2(shown)
        assert rendered[4] is True
        assets = Assets(ROOT)
        frames = [pygame.image.tobytes(assets.tamer(actor["tamer"], rendered[5], rendered[4], t), "RGBA")
                  for t in (.01, .15, .28, .42)]
        assert len(set(frames)) > 1, "Walking must advance the supplied NDS sprite frames."
        assert not assets.errors
    finally:
        pygame.quit()
