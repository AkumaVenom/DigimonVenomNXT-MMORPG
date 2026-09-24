"""Exercise the playable farm through real client input, transport and rendering."""
import copy
from collections import defaultdict
from itertools import count
import math
import os
import queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
import pytest

from tools.preview_ui_screens import ROOT, game_fixture, make_app
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas
from venom.common.farm import farm_walkable


pytestmark = pytest.mark.skipif(not (ROOT/'data/catalog.json').exists(), reason='Imported assets required')


@pytest.fixture
def app():
    client = make_app('1180x800')
    client.state = game_fixture(client)
    client.state.update(in_farm=True, in_lab=False, farm_position={'x': 836., 'y': 470., 'direction': 'down'})
    client.position.update(836, 470)
    client.follower.update(802, 496)
    client.menu = None
    client.args.demo = False
    client.connection = SimpleNamespace(connected=True, incoming=queue.Queue(),
                                        send=Mock(side_effect=lambda *a, **k: next(request_ids)))
    request_ids = count(1)
    with patch.object(client.display, 'save'), patch('pygame.key.get_pressed', return_value=defaultdict(bool)):
        client.update(0)
        yield client
    pygame.quit()


def step(app, keys, dt=.1):
    pressed = defaultdict(bool, {key: True for key in keys})
    with patch('pygame.key.get_pressed', return_value=pressed):
        app.update(dt)


def response(app, rid, **payload):
    app.connection.incoming.put({'op': 'result', 'rid': rid, 'ok': True, **payload})
    app.poll()


def key(app, value):
    app.key(pygame.event.Event(pygame.KEYDOWN, key=value, mod=0))


def test_wasd_and_arrows_predict_all_eight_directions_at_normal_map_speed(app):
    directions = [((pygame.K_w,), (0, -1), 'up'), ((pygame.K_s,), (0, 1), 'down'),
                  ((pygame.K_LEFT,), (-1, 0), 'left'), ((pygame.K_RIGHT,), (1, 0), 'right'),
                  ((pygame.K_w, pygame.K_d), (1, -1), 'up_right'),
                  ((pygame.K_UP, pygame.K_LEFT), (-1, -1), 'up_left'),
                  ((pygame.K_s, pygame.K_d), (1, 1), 'down_right'),
                  ((pygame.K_DOWN, pygame.K_LEFT), (-1, 1), 'down_left')]
    field = app.state['x'], app.state['y'], app.state['map_id']
    for pressed, direction, facing in directions:
        app.position.update(836, 470)
        app._motion.reset()
        start = app.position.copy()
        step(app, pressed)
        expected = pygame.Vector2(direction).normalize()*18
        assert tuple(app.position-start) == pytest.approx(tuple(expected))
        assert app.direction == facing
        assert app.moving
        packet = app.connection.send.call_args
        assert packet.args == ('move',)
        assert packet.kwargs['space'] == 'farm'
        assert math.hypot(packet.kwargs['dx'], packet.kwargs['dy']) == pytest.approx(1)
        assert (app.state['x'], app.state['y'], app.state['map_id']) == field
    step(app, ())
    assert not app.moving
    assert app.connection.send.call_args.kwargs['dx'] == 0
    assert app.connection.send.call_args.kwargs['dy'] == 0


@pytest.mark.parametrize('blocker', ['care', 'search', 'shop', 'settings', 'exchange', 'transition'])
def test_held_movement_stops_while_interacting_with_ui(app, blocker):
    step(app, (pygame.K_d,))
    start = app.position.copy()
    if blocker == 'care':
        app.farm_screen.select(app.state['storage'][0]['uid'])
    elif blocker == 'search':
        app.ui.focus = 'farm_search'
    elif blocker == 'shop':
        app.menu = 'shop'
    elif blocker == 'settings':
        app.settings_open = True
    elif blocker == 'exchange':
        app.partner_screen.pending_exchange = ('party-mon', 'farm-mon')
    elif blocker == 'transition':
        app._motion.transition_pending = 999
    step(app, (pygame.K_d,))
    assert app.position == start
    assert not app.moving


def test_farm_acknowledgements_preserve_field_coordinates_and_replay_newer_input(app):
    field = app.state['map_id'], app.state['x'], app.state['y']
    step(app, (pygame.K_d,), .05)
    first = next(iter(app.requests))
    step(app, (pygame.K_d,), .05)
    predicted = app.position.copy()
    response(app, first, position={'space': 'farm', 'x': 845., 'y': 470., 'direction': 'right'})
    assert app.position == predicted
    assert app.state['farm_position']['x'] == 845
    assert app.state['farm_position']['y'] == 470
    assert app.state['farm_position']['direction'] == 'right'
    assert (app.state['map_id'], app.state['x'], app.state['y']) == field


def test_client_prediction_cannot_walk_into_water_or_off_cliffs(app):
    for direction in ((pygame.K_w,), (pygame.K_s,), (pygame.K_a,), (pygame.K_d,),
                      (pygame.K_w, pygame.K_a), (pygame.K_s, pygame.K_d)):
        app.position.update(836, 470)
        app._motion.reset()
        for _ in range(100):
            step(app, direction)
            assert farm_walkable(app.position.x, app.position.y)
        # Holding a direction must eventually stop at the shore, not wrap.
        assert 0 < app.position.x < 1672
        assert 0 < app.position.y < 941


def test_return_restores_field_and_late_farm_ack_cannot_teleport_player(app):
    field = app.state['x'], app.state['y']
    step(app, (pygame.K_d,))
    old_rid = next(iter(app.requests))
    return_rid = app.send('digifarm', action='return')
    state = copy.deepcopy(app.state)
    state['in_farm'] = False
    response(app, return_rid, state=state)
    assert tuple(app.position) == field
    response(app, old_rid, position={'space': 'farm', 'x': 1490., 'y': 600., 'direction': 'left'})
    assert tuple(app.position) == field
    assert not app.state['in_farm']


def test_late_field_ack_cannot_move_the_tamer_inside_farm(app):
    before = app.position.copy()
    field = app.state['x'], app.state['y'], app.state['map_id']
    app.requests[999] = 'move'
    app._motion.track(999, {'dx': 1, 'dy': 0, 'dt': .1, 'space': 'field'})
    response(app, 999, position={'space': 'field', 'map_id': 'stale-map', 'x': 12., 'y': 12.})
    assert app.position == before
    assert (app.state['x'], app.state['y'], app.state['map_id']) == field
    assert 999 not in app._motion.pending


def test_mouse_wheel_plus_minus_and_fit_use_independent_farm_zoom(app):
    app.world.set_zoom(3)
    app.draw()
    farm = app.farm_screen
    farm.set_zoom(1)
    point = app.screen.to_physical_point(farm.viewport.center)
    with patch('pygame.mouse.get_pos', return_value=point):
        app.key(pygame.event.Event(pygame.MOUSEWHEEL, y=1, x=0))
    assert farm.zoom == 1.5
    key(app, pygame.K_EQUALS)
    assert farm.zoom == 2
    key(app, pygame.K_MINUS)
    assert farm.zoom == 1.5
    key(app, pygame.K_0)
    assert farm.zoom == 1
    assert app.world.zoom == 3
    assert app.display.settings['zoom'] == 3
    for _ in range(20):
        key(app, pygame.K_KP_PLUS)
    assert farm.zoom == 8
    assert app.world.zoom == 3


def test_zoom_never_steals_scroll_or_keys_from_care_search_and_side_panel(app):
    farm = app.farm_screen
    app.draw()
    farm.set_zoom(2)
    side = app.screen.to_physical_point((farm.viewport.right+30, farm.viewport.centery))
    with patch('pygame.mouse.get_pos', return_value=side):
        app.key(pygame.event.Event(pygame.MOUSEWHEEL, y=1, x=0))
    assert farm.zoom == 2
    app.ui.focus = 'farm_search'
    key(app, pygame.K_MINUS)
    assert farm.zoom == 2
    app.farm_screen.select(app.state['storage'][0]['uid'])
    point = app.screen.to_physical_point(farm.viewport.center)
    with patch('pygame.mouse.get_pos', return_value=point):
        app.key(pygame.event.Event(pygame.MOUSEWHEEL, y=1, x=0))
    key(app, pygame.K_MINUS)
    assert farm.zoom == 2


@pytest.mark.parametrize('size', [(1180, 800), (3840, 2160)])
def test_zoomed_resident_targets_follow_camera_are_clipped_and_open_correct_mon(app, size):
    app.screen = NativeCanvas(pygame.display.set_mode(size), effective_ui_scale(size))
    app.ui.screen = app.screen
    farm = app.farm_screen
    app.draw()
    farm.set_zoom(3)
    # Follow one known resident so a camera pan changes the hit positions.
    mon = app.state['storage'][13]
    x, y, _, _ = farm.resident_position(mon['uid'], 13, len(app.state['storage']))
    app.position.update(x*1672, y*941)
    farm.camera.update(10, farm.focus)
    app.draw()
    assert farm.resident_rects
    for rect in farm.resident_rects.values():
        assert farm.viewport.contains(rect)
    target = farm.resident_rects[mon['uid']]
    physical = app.screen.to_physical_point(target.center)
    # Use the same topmost hit target as actual mouse dispatch when sprites overlap.
    uid = next(uid for uid, rect in reversed(list(farm.resident_rects.items()))
               if rect.collidepoint(target.center))
    with patch.object(farm, 'select') as select:
        assert app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=physical))
        select.assert_called_once_with(uid)
    assert pygame.Rect(farm.camera.viewport).collidepoint(physical)
