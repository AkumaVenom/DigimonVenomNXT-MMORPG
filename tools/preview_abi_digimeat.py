"""Native ABI growth UI previews using isolated, unsaved QA partners."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.preview_ui_screens import make_app, game_fixture, capture
from venom.common.game import SHOP
from venom.common.economy import ruby_price
from venom.common.farm import FARM_SPAWN
import pygame


def abi_fixture(app):
    app.state = game_fixture(app)
    engine = app._qa_engine
    mon = engine._monster('fanglongmon_paradox', level=30, abi=0, cam=96)
    mon['uid'] = 'qa-abi-only-partner'
    app.state.update(party=[mon], storage=[], in_lab=True, in_farm=False, battle=None,
                     credits=60000, digirubies=300, economy={'enabled': True},
                     shop={key: dict(item, ruby_price=ruby_price(item['price'])) for key, item in SHOP.items()})
    app.state['inventory']['digimeat_abi'] = 3
    engine._refresh(app.state)
    app.menu = 'shop'
    app.shop_screen.filter('abi')
    app.action_pending = False
    app.selected_party = 0
    return app


def select_abi_view(app, view):
    abi_fixture(app)
    if view.startswith('shop'):
        app.shop_screen.currency = 'digirubies' if view == 'shop_rubies' else 'credits'
    elif view.startswith('evolution'):
        app.menu = 'party'
        app.partner_screen.mode = 'evolution'
        app.partner_screen.route_filter = 'down' if view == 'evolution_no_devolve' else 'all'
        if view == 'evolution_cap':
            app.state['party'][0]['abi'] = 200
    elif view == 'farm':
        mon = copy.deepcopy(app.state['party'][0])
        mon['uid'] = 'qa-abi-farm-resident'
        mon['farm_bonuses'] = {'hp': 100, 'sp': 100, 'atk': 100, 'def': 0, 'int': 0, 'spd': 0}
        app.state.update(storage=[mon], in_lab=False, in_farm=True,
                         farm_position={'x': FARM_SPAWN[0], 'y': FARM_SPAWN[1], 'direction': 'down'})
        app.position.update(FARM_SPAWN)
        app.follower.update(app.position+pygame.Vector2(-34, 26))
        app.menu = None
        app.farm_screen.selected_uid = mon['uid']
        app.farm_screen.open_manager(item='digimeat_abi')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/validation/release_v101')
    parser.add_argument('--sizes', nargs='+', default=['960x600', '2047x1155'])
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'fixture': 'Unsaved QA. Only party partner has ABI 0 and no de-digivolution route.', 'captures': []}
    for size in args.sizes:
        app = make_app(size)
        for view in ('shop_credits', 'shop_rubies', 'evolution', 'evolution_no_devolve', 'evolution_cap', 'farm'):
            select_abi_view(app, view)
            report['captures'].append(capture(app, args.output/f'abi_{view}_{size}.png'))
        if app.assets.errors:
            raise RuntimeError(app.assets.errors)
        pygame.quit()
    (args.output/'abi_ui_report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    if any(row['actions_outside_display'] for row in report['captures']):
        raise SystemExit('An ABI control extends beyond the display.')
    print(f'Rendered {len(report["captures"])} native ABI previews.')


if __name__ == '__main__':
    main()
