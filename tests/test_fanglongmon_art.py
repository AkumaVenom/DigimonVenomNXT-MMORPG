"""Supplied poses stay intact, directional and available through real caches."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from PIL import Image
import pygame
import pytest

from tools.import_assets import animation_override, species_catalog
from venom.client.assets import Assets

ROOT = Path(__file__).resolve().parents[1]
FORMS = ('fanglongmon', 'fanglongmon_paradox')


@pytest.fixture
def assets():
    pygame.init()
    pygame.display.set_mode((32, 32))
    yield Assets(ROOT)
    pygame.quit()


def test_supplied_png_bytes_and_alpha_preserved():
    sources = json.loads((ROOT / 'data/source_assets.json').read_text('utf-8'))
    record = next(entry for entry in sources if entry.get('kind') == 'fanglongmon_v100')
    assert len(record['frames']) == 12
    assert len({frame['sha256'] for frame in record['frames']}) == 12
    for frame in record['frames']:
        path = ROOT / frame['path']
        assert path.stat().st_size == frame['size']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == frame['sha256']
        with Image.open(path) as image:
            assert image.mode == 'RGBA'
            assert image.size == (1254, 1254)
            assert image.getchannel('A').getextrema()[0] == 0


def test_full_catalog_reimport_retains_labelled_pose_assignments():
    published = json.loads((ROOT / 'data/catalog.json').read_text('utf-8'))['species']
    expected = {entry['id']: entry for entry in published}
    rebuilt = {entry['id']: entry for entry in species_catalog()}
    assert len(rebuilt) == len(expected) == 1004
    for sid in FORMS:
        for key in ('sprites', 'animations', 'mirrored_frames', 'source_frame_count', 'art_provenance'):
            assert rebuilt[sid][key] == expected[sid][key]


@pytest.mark.parametrize('sid', FORMS)
def test_idle_and_attack_use_both_labelled_frames_and_caches(assets, sid):
    entry = assets.species[sid]
    assert entry['source_frame_count'] == 6
    assert entry['animations']['idle'] == [entry['sprites']['idle'], entry['sprites']['idle2']]
    assert entry['animations']['attack'] == [entry['sprites']['attack1'], entry['sprites']['attack2']]
    for box in ((58, 64), (200, 213)):
        for motion in ('idle', 'walk', 'attack'):
            for moment in (0., .125, .25, .375):
                frame = assets.sprite(sid, box, motion, moment)
                assert frame is not None
                assert frame.get_width() <= box[0] and frame.get_height() <= box[1]
                assert assets.sprite(sid, box, motion, moment) is frame
                assert frame.get_at((0, 0)).a == 0
    assert not assets.errors
    assert assets.cache_bytes <= assets.IMAGE_CACHE_BYTES
    assert assets.scaled_bytes <= assets.SCALED_CACHE_BYTES


@pytest.mark.parametrize('sid', FORMS)
def test_left_step_uses_supplied_art_without_double_flip(assets, sid):
    sprites = assets.species[sid]['sprites']
    with patch.object(assets, 'image', wraps=assets.image) as load:
        left = assets.sprite(sid, (200, 213), 'walk', .125, flip=True)
        load.assert_called_once_with(sprites['walk_left'])
    expected = pygame.transform.scale(assets.image(sprites['walk_left']), (200, 200))
    assert pygame.image.tobytes(left, 'RGBA') == pygame.image.tobytes(expected, 'RGBA')
    with patch.object(assets, 'image', wraps=assets.image) as load:
        assets.sprite(sid, (200, 213), 'walk', 0., flip=True)
        load.assert_called_once_with(sprites['idle'])
    assert (sprites['idle'], (200, 213), True) in assets.scaled


def test_unmodified_species_keep_existing_mirror_behavior(assets):
    sid = 'agumon'
    assert not assets.species[sid].get('mirrored_frames')
    normal = assets.sprite(sid, (80, 90), 'walk', .125)
    left = assets.sprite(sid, (80, 90), 'walk', .125, flip=True)
    expected = pygame.transform.flip(normal, True, False)
    assert pygame.image.tobytes(left, 'RGBA') == pygame.image.tobytes(expected, 'RGBA')


def test_animation_sidecar_cannot_escape_its_species_directory(tmp_path):
    directory = tmp_path / 'species'
    directory.mkdir()
    (directory / 'animation.json').write_text(json.dumps({
        'version': 1, 'sprites': {'idle': '../outside.png'},
    }), encoding='utf-8')
    with pytest.raises(ValueError, match='Invalid animation frame path'):
        animation_override(directory, tmp_path)
