"""The private home's player, camera, and clickable residents share one space."""
import os
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
import pytest

from tools.preview_digifarm import farm_fixture
from tools.preview_ui_screens import ROOT, make_app


@pytest.fixture
def home():
    if not (ROOT/'data/catalog.json').exists():
        pytest.skip('Imported assets required')
    app = make_app('1180x800')
    farm_fixture(app, 100)
    app.position.update(836, 470)
    app.follower.update(790, 510)
    app.draw()
    yield app
    pygame.quit()


def test_player_and_lead_partner_are_present_even_in_an_empty_farm(home):
    home.state['storage'] = []
    home.draw()
    farm = home.farm_screen
    assert farm.player_rect and farm.player_rect.height >= 45
    assert farm.follower_rect and farm.follower_rect.height >= 40
    assert farm.viewport.contains(farm.player_rect)
    assert farm.viewport.contains(farm.follower_rect)
    assert not farm.resident_rects


def test_selected_tamer_walks_in_all_eight_directions(home):
    # The same real animation provider and selected appearance as a field map.
    selected = list(home.assets.tamers)[-1]
    home.state['tamer'] = selected
    home.moving = True
    for direction in ('up', 'down', 'left', 'right', 'up_left', 'up_right', 'down_left', 'down_right'):
        home.direction = direction
        with patch.object(home.assets, 'tamer', wraps=home.assets.tamer) as tamer:
            home.draw()
            tamer.assert_called_once_with(selected, direction, True, home.now, (64, 80))
        assert home.farm_screen.player_rect


def test_every_resident_and_the_party_actors_sort_by_their_world_feet(home):
    farm = home.farm_screen
    with patch.object(farm, '_draw_farm_actor', wraps=farm._draw_farm_actor) as actor:
        home.draw()
    calls = [call.args for call in actor.call_args_list]
    assert len(calls) == 102
    assert [call[1].y for call in calls] == sorted(call[1].y for call in calls)
    assert sum(call[0] == 'tamer' for call in calls) == 1
    assert sum(call[0] == 'follower' for call in calls) == 1


def test_farm_zoom_follows_player_without_changing_field_preference(home):
    farm = home.farm_screen
    field_zoom = home.world.zoom
    saved_zoom = home.display.settings.get('zoom')
    farm.set_zoom(4)
    home.position.update(1050, 570)
    for _ in range(90):
        farm.update(1/60)
    home.draw()
    focus = farm.camera.world_to_screen(farm.focus)
    assert focus.distance_to(farm.camera.viewport.center) < 1
    assert home.world.zoom == field_zoom
    assert home.display.settings.get('zoom') == saved_zoom
    farm.set_zoom(99)
    assert farm.zoom == 8
    farm.reset_zoom()
    assert farm.zoom == 1
    assert farm.camera.source_crop() == pygame.Rect(0, 0, 1672, 941)


def test_zoom_culls_resident_buttons_and_bounds_the_scaled_island_cache(home):
    farm = home.farm_screen
    assert len(farm.resident_rects) == 100
    farm.set_zoom(8)
    home.draw()
    assert 0 < len(farm.resident_rects) < 100
    assert all(farm.viewport.contains(hit) for hit in farm.resident_rects.values())
    _, _, scaled = farm._layers['farm']
    # Viewport plus the shared renderer's 128px scrolling margin and rounding.
    assert scaled.get_width() <= farm.camera.viewport.width+280
    assert scaled.get_height() <= farm.camera.viewport.height+280
    assert farm._sprite_bytes <= farm.SPRITE_CACHE_BYTES
    source = home.assets.tamer(home.state['tamer'], home.direction, home.moving, home.now, (64, 80))
    expected_height = round(source.get_height()*farm.COMPANION_SCALE*farm.camera.scale)
    assert farm.player_rect.height == expected_height  # Entire body survives 8x.


def test_farm_hud_panels_block_clicks_to_a_resident_behind_them(home):
    farm = home.farm_screen
    farm.set_zoom(8)
    home.state['storage'] = home.state['storage'][:1]
    for point in ((farm.viewport.x+85, farm.viewport.y+25),
                  (farm.viewport.x+98, farm.viewport.bottom-34)):
        # Arrange one resident's sprite across the HUD's label/readout gap.
        foot = farm.camera.screen_to_world(home.screen.to_physical_point((point[0], point[1]+20)))
        with patch.object(farm, 'resident_position', return_value=(foot.x/1672, foot.y/941, False, False)):
            home.draw()
        assert any(rect.collidepoint(point) for rect in farm.resident_rects.values())
        with patch.object(farm, 'select') as select:
            assert home.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                                   pos=home.screen.to_physical_point(point)))
            select.assert_not_called()


def test_care_freezes_residents_without_repositioning_tamer_or_camera(home):
    farm = home.farm_screen
    farm.set_zoom(2)
    home.draw()
    mon = home.state['storage'][0]
    before = farm.resident_position(mon['uid'], 0, 100)
    position, follower = home.position.copy(), home.follower.copy()
    farm.select(mon['uid'])
    for _ in range(60):
        farm.update(1/60)
    assert farm.resident_position(mon['uid'], 0, 100) == before
    assert home.position == position and home.follower == follower
    home.draw()
    assert farm.player_rect and farm.follower_rect
