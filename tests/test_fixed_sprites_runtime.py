"""Real pygame rendering/cache checks; explicitly skipped without pygame-ce."""
import json
import os
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pytest
pygame = pytest.importorskip('pygame', reason='pygame-ce is required for real SDL sprite rendering checks')
from venom.client.assets import Assets

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / 'data/fixed_sprites_v110.json').read_text(encoding='utf-8'))
if (ROOT / 'data/fixed_sprites_v111.json').is_file():
    latest = json.loads((ROOT / 'data/fixed_sprites_v111.json').read_text(encoding='utf-8'))
    merged = {item['id']: item for item in RECORD['species']}
    merged.update({item['id']: item for item in latest['species']})
    RECORD['species'] = list(merged.values())



@pytest.fixture(scope='module')
def assets():
    pygame.init()
    pygame.display.set_mode((32, 32))
    yield Assets(ROOT)
    pygame.quit()


@pytest.mark.parametrize('item', RECORD['species'], ids=lambda item: item['id'])
def test_fixed_poses_render_in_portrait_world_and_battle_boxes_and_reuse_cache(assets, item):
    sid = item['id']
    entry = assets.species[sid]
    motions = {**entry['animations']}
    if 'front' in entry['sprites']:
        motions['front'] = [entry['sprites']['front']]
    for motion, paths in motions.items():
        for index, expected_path in enumerate(paths):
            moment = index / 8
            assert assets.sprite_path(sid, motion, moment) == expected_path
            for box in ((42, 39), (64, 80), (110, 70), (200, 213)):
                for flip in (False, True):
                    image = assets.sprite(sid, box, motion, moment, flip=flip)
                    assert image is not None
                    assert 0 < image.get_width() <= box[0]
                    assert 0 < image.get_height() <= box[1]
                    assert image.get_flags() & pygame.SRCALPHA
                    assert image.get_bounding_rect().width > 0
                    assert assets.sprite(sid, box, motion, moment, flip=flip) is image
    assert not assets.errors
    assert assets.cache_bytes <= assets.IMAGE_CACHE_BYTES
    assert assets.scaled_bytes <= assets.SCALED_CACHE_BYTES
