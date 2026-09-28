"""Native arena cache, exact clipping, and replay layering contracts."""
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
import pytest

from venom.client.hud import GameHUD
from venom.client.render import NativeCanvas


@pytest.fixture
def app():
    pygame.init()
    pygame.display.set_mode((32, 32))
    value = SimpleNamespace(screen=NativeCanvas(pygame.Surface((1200, 900)).convert(), 1.25))
    value.hud = GameHUD(value)
    yield value
    pygame.quit()


def outside_pixels(surface, rect):
    """Every pixel outside rect, not just selected sample corners."""
    w, h = surface.get_size()
    bands = (pygame.Rect(0, 0, w, rect.top),
             pygame.Rect(0, rect.bottom, w, h-rect.bottom),
             pygame.Rect(0, rect.top, rect.left, rect.height),
             pygame.Rect(rect.right, rect.top, w-rect.right, rect.height))
    return [pygame.image.tobytes(surface.subsurface(band), 'RGB') for band in bands]


def test_warm_arena_retains_exact_native_pixels_without_repainting(app):
    area = pygame.Rect(20, 94, 800, 540)
    app.hud.battle_stage(area)
    cached = app.hud._stage
    assert cached.get_size() == app.screen.to_physical_rect(area).size
    expected = pygame.image.tobytes(app.screen.surface.subsurface(app.screen.to_physical_rect(area)), 'RGB')
    app.screen.fill('red')
    with patch('venom.client.battle_arena.paint', side_effect=AssertionError('Repainted a warm arena')):
        app.hud.battle_stage(area)
    assert app.hud._stage is cached
    assert pygame.image.tobytes(app.screen.surface.subsurface(app.screen.to_physical_rect(area)), 'RGB') == expected
    assert cached.get_pitch()*cached.get_height() <= 32*1024*1024


def test_moved_arena_reuses_cache_but_size_and_dpi_changes_rebuild(app):
    area = pygame.Rect(20, 94, 800, 540)
    app.hud.battle_stage(area)
    previous = app.hud._stage
    # Eight logical pixels shift by ten native pixels, preserving .5 rounding.
    with patch('venom.client.battle_arena.paint', side_effect=AssertionError('Repainted moved arena')):
        app.hud.battle_stage(area.move(8, 8))
    assert app.hud._stage is previous
    for size, scale, logical_area in (((2047, 1155), 1.25, (20, 94, 1285, 662)),
                                      ((3840, 2160), 2.5, (20, 94, 1184, 602)),
                                      ((3840, 2160), 2., (20, 94, 1184, 602))):
        app.screen = NativeCanvas(pygame.Surface(size).convert(), scale)
        app.hud.battle_stage(logical_area)
        assert app.hud._stage is not previous
        assert app.hud._stage.get_size() == app.screen.to_physical_rect(logical_area).size
        assert app.hud._stage.get_pitch()*app.hud._stage.get_height() <= 32*1024*1024
        previous = app.hud._stage


@pytest.mark.parametrize('area', [(60, 40, 800, 600), (0, 0, 5000, 2500)])
def test_cached_and_oversize_arena_preserve_exact_fractional_clip(app, area):
    surface = app.screen.surface
    surface.fill((91, 7, 39))
    clip = pygame.Rect(101, 91, 803, 511)
    expected = outside_pixels(surface, clip)
    surface.set_clip(clip)
    app.hud.battle_stage(area)
    assert surface.get_clip() == clip
    assert outside_pixels(surface, clip) == expected
    assert surface.get_at(clip.center)[:3] != (91, 7, 39)


def test_failed_arena_build_restores_clip_and_can_retry(app):
    area = pygame.Rect(60, 40, 800, 600)
    clip = pygame.Rect(101, 91, 803, 511)
    app.screen.surface.set_clip(clip)
    with patch('venom.client.battle_arena.paint', side_effect=RuntimeError('Synthetic render failure')):
        with pytest.raises(RuntimeError, match='Synthetic render failure'):
            app.hud.battle_stage(area)
    assert app.screen.surface.get_clip() == clip
    app.hud.battle_stage(area)
    assert app.hud._stage is not None
    assert app.screen.surface.get_clip() == clip


@pytest.mark.parametrize('size', [(5000, 2500), (3040, 1800)])
def test_oversize_arena_uses_direct_paint_without_allocating_a_cache(app, size):
    from venom.client import battle_arena
    # The smaller case is just over budget, while its inset field is under it.
    # Neither uncached path may create a full-field gradient every frame.
    area = pygame.Rect((0, 0), size)
    with patch('pygame.Surface', side_effect=AssertionError('Allocated an oversized arena')):
        with patch('venom.client.battle_arena.paint', wraps=battle_arena.paint) as paint:
            app.hud.battle_stage(area)
    assert app.hud._stage is None
    paint.assert_called_once_with(app.screen, area)


def test_replay_paints_shared_arena_before_heading_and_title():
    from tools.preview_ui_screens import make_app, select_view
    import venom.client.community as community
    app = make_app('1280x800')
    try:
        select_view(app, 'ranked_replay')
        app.viewport = pygame.Rect(20, 94, 928, 538)
        events = []
        original_text = community.text
        def capture_text(*args, **kwargs):
            events.append(('text', args[2]))
            return original_text(*args, **kwargs)
        with patch.object(app.hud, 'battle_stage', side_effect=lambda area: events.append(('arena', tuple(area)))):
            with patch.object(community, 'text', side_effect=capture_text):
                app.community.replay.draw(pygame.Rect(35, 135, 1180, 610), lambda: None)
        assert events[0] == ('arena', (50, 185, 1150, 490))
        assert events[1] == ('text', 'RANKED BATTLE')
        assert ' vs ' in events[2][1]
    finally:
        pygame.quit()
