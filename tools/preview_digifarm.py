"""Render isolated DigiFarm QA previews, optionally benchmark 100 residents.

Uses synthetic local state only. No connection, save, or player configuration is
written. Run: python tools/preview_digifarm.py --output ui-review/digifarm --benchmark
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.preview_ui_screens import make_app, game_fixture, capture
from venom.common.game import SHOP
from venom.common.farm import FARM_SPAWN
import pygame


def farm_fixture(app, count=28):
    app.state = game_fixture(app)
    monsters = app.state['storage']
    app.state.update(in_farm=True, in_lab=False, shop=copy.deepcopy(SHOP), credits=80000,
                     farm_position={'x': FARM_SPAWN[0], 'y': FARM_SPAWN[1], 'direction': 'down'},
                     storage=[dict(copy.deepcopy(monsters[i % len(monsters)]), uid=f'farm-qa-{i}')
                              for i in range(count)])
    app.state['inventory'].update({k: 3 for k, v in SHOP.items() if v.get('category') == 'digimeat'})
    app.farm_screen.age = 18.
    app.position.update(FARM_SPAWN)
    app.follower.update(app.position+pygame.Vector2(-34, 26))
    app.direction, app.moving = 'down', False
    app.menu = None
    app.farm_screen.close_manager()
    app.farm_screen.set_zoom(1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'ui-review/digifarm')
    parser.add_argument('--sizes', nargs='+', default=['1280x800', '1920x1080', '3840x2160'])
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'fixture': 'Synthetic offline QA; no account progress.', 'captures': [], 'performance': {}}
    try:
        for size in args.sizes:
            app = make_app(size)
            farm_fixture(app)
            report['captures'].append(capture(app, args.output/f'farm_{size}.png'))
            app.farm_screen.set_zoom(2)
            # Walk through the scene into the open southeast grass so the
            # selected tamer and following partner are clear in the capture.
            with patch('pygame.key.get_pressed', return_value=defaultdict(bool, {pygame.K_d: True, pygame.K_s: True})):
                for _ in range(24):
                    app.update(.05)
            report['captures'].append(capture(app, args.output/f'walk_zoom_2x_{size}.png'))
            app.moving = False
            app.farm_screen.select(app.state['storage'][0]['uid'])
            report['captures'].append(capture(app, args.output/f'care_{size}.png'))
            farm_fixture(app, 100)
            report['captures'].append(capture(app, args.output/f'full_{size}.png'))
            app.farm_screen.set_zoom(8)
            report['captures'].append(capture(app, args.output/f'full_zoom_8x_{size}.png'))
            app.farm_screen.set_zoom(1)
            if args.benchmark:
                for _ in range(15):
                    app.now += 1/60
                    app.farm_screen.update(1/60)
                    app.draw()
                times = []
                for _ in range(120):
                    start = time.perf_counter()
                    app.now += 1/60
                    app.farm_screen.update(1/60)
                    app.draw()
                    times.append((time.perf_counter()-start)*1000)
                report['performance'][size] = {'median_frame_ms': round(sorted(times)[60], 2),
                                                'p95_frame_ms': round(sorted(times)[114], 2),
                                                'residents_drawn': len(app.farm_screen.resident_rects)}
            farm_fixture(app, 0)
            report['captures'].append(capture(app, args.output/f'empty_{size}.png'))
            if app.assets.errors:
                raise RuntimeError(app.assets.errors)
            pygame.quit()
    finally:
        pygame.quit()
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    if any(c['actions_outside_display'] for c in report['captures']):
        raise SystemExit('Out-of-bounds control; inspect report.json')
    print(f'Rendered {len(report["captures"])} DigiFarm previews.')
    print(json.dumps(report['performance'], indent=2))


if __name__ == '__main__':
    main()
