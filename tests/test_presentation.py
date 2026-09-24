"""Destination art remains native and cheap after the initial composition."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from types import SimpleNamespace
from unittest.mock import patch
import hashlib
from pathlib import Path

import pygame
import pytest

from venom.client.presentation import Presentation, colors, PALETTES
from venom.client.assets import Assets
from venom.client.render import NativeCanvas


class Art:
    def __init__(self):
        self.loads = []
        self.requested_fonts = []
        self.fonts = {}
        self.source = pygame.Surface((256, 256), pygame.SRCALPHA)
        self.source.fill((22, 76, 107, 255), (0, 0, 256, 192))
        self.source.fill((255, 0, 255, 255), (0, 192, 256, 64))

    def image(self, name):
        self.loads.append(name)
        return self.source

    def font(self, size, bold=False):
        self.requested_fonts.append(size)
        if (size, bold) not in self.fonts:
            font = pygame.font.Font(None, size)
            font.set_bold(bold)
            self.fonts[size, bold] = font
        return self.fonts[size, bold]


@pytest.fixture
def destination():
    pygame.init()
    pygame.display.set_mode((32, 32))
    app = SimpleNamespace(screen=NativeCanvas(pygame.Surface((1600, 1200)), 2),
                          assets=Art(), now=1.5)
    app.presentation = Presentation(app)
    yield app
    pygame.quit()


def test_repeated_shell_never_reloads_or_rescales_art(destination):
    app = destination
    rect = pygame.Rect(10, 10, 780, 580)
    body = app.presentation.shell(rect, 'ranked', 'RANKED ARENA', 'Build your legacy.')
    before = pygame.image.tobytes(app.screen.surface, 'RGB')
    initial_loads = len(app.assets.loads)
    with patch('pygame.transform.scale', side_effect=AssertionError('per-frame rescale')):
        for _ in range(10):
            app.presentation.shell(rect, 'ranked', 'RANKED ARENA', 'Build your legacy.')
    assert pygame.image.tobytes(app.screen.surface, 'RGB') == before
    assert len(app.assets.loads) == initial_loads
    assert body == pygame.Rect(32, 158, 736, 410)
    assert 64 in app.assets.requested_fonts  # 32 logical px title is native 64px.


def test_resize_releases_old_native_backdrop_variants(destination):
    app = destination
    app.presentation.shell((10, 10, 780, 580), 'shop', 'SUPPLY SHOP')
    old_keys = {key for key in app.presentation._cache if key[0] == 'shell'}
    app.screen.set_surface(pygame.Surface((1800, 1250)), 1.25)
    app.presentation.shell((10, 10, 1300, 900), 'shop', 'SUPPLY SHOP')
    assert old_keys.isdisjoint(app.presentation._cache)
    shell = next(value for key, value in app.presentation._cache.items() if key[0] == 'shell')
    assert shell.get_size() == app.screen.to_physical_rect((10, 10, 1300, 900)).size
    assert 40 in app.assets.requested_fonts


def test_presentation_cache_has_an_enforced_byte_budget(destination):
    app = destination
    app.presentation.CACHE_BYTES = 10*1024*1024
    for theme in ('shop', 'ranked', 'rivals', 'activity'):
        app.presentation.shell((10, 10, 780, 580), theme, theme.upper())
        assert app.presentation._cache_bytes <= app.presentation.CACHE_BYTES
    actual = sum(surface.get_pitch()*surface.get_height() for surface in app.presentation._cache.values())
    assert actual == app.presentation._cache_bytes


def test_hero_art_crops_atlas_to_character_region(destination):
    app = destination
    app.screen.surface.fill('black')
    app.presentation._stamp(app.screen, 't_charaall.png', (20, 20, 256, 192), (0, 0, 256, 192))
    assert app.screen.surface.get_at((45, 45))[:3] == (22, 76, 107)
    assert app.screen.surface.get_at((45, 422))[:3] == (22, 76, 107)
    assert app.screen.surface.get_at((45, 425))[:3] == (0, 0, 0)
    # Cropping prevents unrelated artwork below row 192 leaking into the hero.
    assert colors('shop')['accent'] != colors('ranked')['accent']


def test_partner_art_trims_empty_padding_and_caches_flipped_native_pixels(destination):
    app = destination
    app.assets.source = pygame.Surface((512, 512), pygame.SRCALPHA)
    app.assets.source.fill((250, 80, 50), (200, 250, 4, 4))
    app.assets.source.fill((40, 180, 240), (204, 250, 4, 4))
    app.assets.sprite_path = lambda species, motion, now: 'assets/test_partner.png'
    original = pygame.image.tobytes(app.assets.source, 'RGBA')
    app.screen.surface.fill('black')
    assert app.presentation.sprite((20, 20, 80, 80), 'partner')
    # Visible 8x4 artwork fills an 80x40 logical box, anchored to its bottom.
    assert app.screen.surface.get_at((45, 125))[:3] == (250, 80, 50)
    assert app.screen.surface.get_at((195, 125))[:3] == (40, 180, 240)
    assert app.screen.surface.get_at((45, 118))[:3] == (0, 0, 0)
    assert app.presentation.sprite((20, 20, 80, 80), 'partner', flip=True)
    assert app.screen.surface.get_at((45, 125))[:3] == (40, 180, 240)
    loads = len(app.assets.loads)
    with patch('pygame.transform.scale', side_effect=AssertionError('per-frame sprite scale')):
        for _ in range(20):
            app.presentation.sprite((20, 20, 80, 80), 'partner', flip=True)
    assert len(app.assets.loads) == loads
    assert pygame.image.tobytes(app.assets.source, 'RGBA') == original


def test_new_destination_art_resolves_and_shopkeeper_is_the_exact_upload(destination):
    root = Path(__file__).resolve().parents[1]
    app = destination
    app.assets = Assets(root)
    for theme in ('lab', 'scan', 'dex', 'party', 'evolution', 'storage',
                  'maps', 'skills', 'battle', 'auth', 'settings', 'shop'):
        assert theme in PALETTES
        app.presentation.shell((10, 10, 780, 580), theme, theme.upper())
        assert app.presentation._cache_bytes <= app.presentation.CACHE_BYTES
    assert app.assets.errors == []
    merchant = root/'assets/ui/extracted/shopkeeper.png'
    assert hashlib.sha256(merchant.read_bytes()).hexdigest() == 'b541c8b2e5e99ee83d44dc03a3472efa9676e9616c115f3752867001ba0e3788'
