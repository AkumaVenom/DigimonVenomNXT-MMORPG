"""Exercise latency reconciliation, frame input boundaries and real server collision."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pygame
import pytest
from PIL import Image

from venom.client.motion import MoveInput, MovementPredictor, RemoteMotion, move_position
from venom.server.main import Session, WorldServer


OPEN_MAP = {'id': 'test', 'width': 1000, 'height': 1000}


def test_delayed_ack_replays_all_newer_inputs_instead_of_snapping_back():
    predictor = MovementPredictor()
    position = (100, 100)
    for rid in range(1, 9):
        position = predictor.advance(position, 1, 0, .05, OPEN_MAP)
        movement, = predictor.take_buffer()
        predictor.track(rid, movement.payload())
    # 350ms worth of prediction (63px) is newer than this acknowledgement.
    assert position == pytest.approx((172, 100))
    corrected = predictor.reconcile(1, (109, 100), OPEN_MAP)
    assert corrected == pytest.approx(position)
    assert list(predictor.pending) == list(range(2, 9))
    # Also retain a frame not yet submitted to the network.
    position = predictor.advance(corrected, 1, 0, .016, OPEN_MAP)
    assert predictor.reconcile(2, (118, 100), OPEN_MAP) == pytest.approx(position)


def test_authoritative_correction_and_teleport_still_take_effect():
    predictor = MovementPredictor()
    predictor.track(1, {'dx': 1, 'dy': 0, 'dt': .05})
    predictor.track(2, {'dx': 1, 'dy': 0, 'dt': .05})
    # The server rejected some travel; only the still-unacknowledged input replays.
    assert predictor.reconcile(1, (103, 100), OPEN_MAP) == pytest.approx((112, 100))
    assert predictor.reconcile(2, (800, 500), OPEN_MAP, reset=True) == (800, 500)
    assert not predictor.pending
    assert not predictor.buffer


def test_direction_changes_and_key_release_preserve_each_input_interval():
    predictor = MovementPredictor()
    position = predictor.advance((100, 100), 1, 0, .02, OPEN_MAP)
    position = predictor.advance(position, 0, 1, .025, OPEN_MAP)
    position = predictor.advance(position, 0, 0, .005, OPEN_MAP)
    outgoing = predictor.take_buffer()
    assert [(m.dx, m.dy, m.dt) for m in outgoing] == [(1, 0, .02), (0, 1, .025), (0, 0, .005)]
    replayed = (100, 100)
    for movement in outgoing:
        replayed = move_position(replayed, movement, OPEN_MAP)
    assert replayed == pytest.approx(position)


@pytest.mark.parametrize('direction', [(1, 0), (1, 1), (-1, -1), (0, 1)])
def test_client_collision_matches_authoritative_server_at_half_size_mask(tmp_path, direction):
    # A deliberately smaller mask tests coordinate conversion as well as a thin wall.
    mask = Image.new('L', (50, 50), 255)
    for y in range(50):
        mask.putpixel((25, y), 0)
    mask.save(tmp_path / 'mask.png')
    client_mask = pygame.image.load(str(tmp_path / 'mask.png'))
    entry = {'id': 'test', 'width': 100, 'height': 100, 'walkable': 'mask.png', 'encounters': False}
    engine = SimpleNamespace(maps={'test': entry})
    world = WorldServer(engine, None, {})
    world.root = Path(tmp_path)
    state = {'map_id': 'test', 'x': 45.0, 'y': 45.0, 'events': [], 'battle': None, 'in_lab': False}
    session = Session(None, 'tester', 'token', state, 0)
    movement = MoveInput(*direction, .1)
    predicted = move_position((state['x'], state['y']), movement, entry, client_mask)
    session.move_credit = .15
    with patch('venom.server.main.time.monotonic', return_value=session.last_move):
        world.move(session, movement.payload())
    assert tuple(round(v, 3) for v in predicted) == (state['x'], state['y'])
    assert predicted[0] < 50


def test_client_cannot_predict_through_thin_wall_or_map_margin():
    mask = pygame.Surface((100, 100))
    mask.fill('white')
    pygame.draw.line(mask, 'black', (50, 0), (50, 99))
    entry = {'width': 100, 'height': 100}
    assert move_position((45, 45), MoveInput(1, 0, .1), entry, mask)[0] == 49
    assert move_position((13, 13), MoveInput(-1, -1, .1), entry) == pytest.approx((12, 12))


def test_remote_snapshots_interpolate_between_ticks_and_bound_missing_packet_motion():
    remote = RemoteMotion(delay=.1)
    for now, x in ((0.0, 100), (.1, 118), (.2, 136)):
        remote.push(now, {'Peer': {'map_id': 'test', 'x': x, 'y': 100, 'dx': 1, 'dy': 0}})
    assert remote.positions(.25)['Peer'] == pytest.approx((127, 100))
    assert remote.positions(.275)['Peer'] == pytest.approx((131.5, 100))
    assert remote.positions(10)['Peer'] == pytest.approx((145, 100))
    remote.push(10.1, {'Peer': {'map_id': 'other', 'x': 800, 'y': 500}})
    assert remote.positions(10.1)['Peer'] == (800, 500)
    remote.push(10.2, {})
    assert remote.positions(10.2) == {}
