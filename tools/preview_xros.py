"""Render the shipped Super Xros Wars region in the real native client.

All account and population data is isolated synthetic QA data. No server is
contacted or player save changed. Map art, collisions and encounters are the
release assets. Run: python tools/preview_xros.py --output docs/validation/release_v130/ui
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

from tools.preview_ui_screens import game_fixture, make_app
from venom.client.widgets import text, GOLD
from venom.server.navigation import Navigation


def render(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for resolution in ('960x600', '1280x800'):
        app = make_app(resolution)
        app.state = game_fixture(app)
        app.animations, app.toasts = [], []
        areas = app.world_screen.region_entries('xros_wars')
        if not areas:
            raise RuntimeError('Import and merge Super Xros Wars maps before rendering previews.')
        # Explicitly synthetic occupancy is marked in every output image.
        app.community.data['activity'] = {'maps': [{'id': area['id'], 'count': 6} for area in app.assets.maps.values()]}
        app.community.received_at['activity'] = app.now
        app.logs = [('OFFLINE QA PREVIEW / Synthetic tamer and rival data.', GOLD)]
        navigation = Navigation(ROOT, app.assets.maps)
        variants = [('atlas_low', areas[0], True), ('atlas_high', areas[-1], True),
                    ('field_low', areas[0], False), ('field_mid', areas[len(areas)//2], False),
                    ('field_high', areas[-1], False)]
        for name, area, atlas in variants:
            app.state.update(map_id=area['id'], x=area['spawn'][0], y=area['spawn'][1],
                             in_farm=False, in_lab=False, in_story=False)
            app.reset_scene_position()
            app.world.set_zoom(1)
            app.menu = 'maps' if atlas else None
            app.world_screen.show_current(cue=False, remember=False)
            app.players, app.player_render = {}, {}
            if not atlas:
                # Genuine actor rendering, without claiming a live server session.
                base = area['encounters'][0]
                leads = [base, base+'_paradox', base+'_shiny']
                for index in range(3):
                    name_key = f'QA_Rival_{index+1}'
                    point = pygame.Vector2(navigation.spawn(area['id'], 4+index*7))
                    app.players[name_key] = dict(id=f'bot:qa-{index}', name=name_key, username=name_key,
                        is_bot=True, map_id=area['id'], x=point.x, y=point.y,
                        tamer=list(app.assets.tamers)[index], lead=leads[index])
                    app.player_render[name_key] = point
            app.draw()
            text(app.screen, app.assets, 'OFFLINE QA / SYNTHETIC ACCOUNT AND RIVAL DATA',
                 (app.screen.get_width()//2, app.screen.get_height()-7), 8, GOLD, center=True)
            filename = f'xros_{name}_{resolution}.png'
            pygame.image.save(app.screen.surface, output/filename)
            records.append({'file': filename, 'map_id': area['id'], 'map_name': area['name'],
                            'level_range': list(app.world_screen.levels(area)), 'resolution': resolution,
                            'synthetic_account_and_rivals': True, 'asset_errors': list(app.assets.errors)})
            if app.assets.errors:
                raise RuntimeError(str(app.assets.errors))
        pygame.quit()
    (output/'previews.json').write_text(json.dumps(records, indent=2)+'\n', encoding='utf-8')
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/validation/release_v130/ui')
    args = parser.parse_args()
    print(json.dumps({'output': str(args.output), 'previews': len(render(args.output))}))
