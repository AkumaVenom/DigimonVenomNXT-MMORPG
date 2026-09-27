"""Render actual DS maps through the native atlas with isolated QA player state."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.preview_ui_screens import capture, game_fixture, make_app
import pygame


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'world-ds-previews')
    parser.add_argument('--sizes', nargs='+', default=['960x600', '1280x800', '1920x1080'])
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'fixture': 'Offline native client QA; actual imported maps, isolated synthetic player state.', 'captures': []}
    try:
        for size in args.sizes:
            app = make_app(size)
            app.state = game_fixture(app)
            app.animations, app.toasts, app.players = [], [], {}
            atlas = app.world_screen
            maps = atlas.region_entries('world_ds')
            if not maps:
                raise SystemExit('World DS maps must be imported first.')
            app.menu = 'maps'
            atlas.on_open()
            atlas.select_region('world_ds')
            report['captures'].append(capture(app, args.output/f'world_ds_atlas_{size}.png'))
            atlas.filter_levels((76, 99))
            report['captures'].append(capture(app, args.output/f'world_ds_endgame_{size}.png'))
            current = maps[len(maps)//2]
            app.state.update(map_id=current['id'], x=current['spawn'][0], y=current['spawn'][1])
            app.reset_scene_position()
            atlas.on_open()
            report['captures'].append(capture(app, args.output/f'world_ds_current_map_{size}.png'))
            app.menu = None
            report['captures'].append(capture(app, args.output/f'world_ds_field_{size}.png'))
            if app.assets.errors:
                raise RuntimeError(app.assets.errors)
            pygame.quit()
    finally:
        pygame.quit()
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    invalid = [row for row in report['captures'] if row['actions_outside_display']]
    if invalid:
        raise SystemExit(f'Out-of-bounds UI controls in {len(invalid)} previews.')
    print(f'Rendered {len(report["captures"])} native previews to {args.output}')


if __name__ == '__main__':
    main()
