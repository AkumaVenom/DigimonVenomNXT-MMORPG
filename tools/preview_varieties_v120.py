"""Render real v1.2.0 artwork with synthetic accounts; never connects or saves a player.

Run from the release folder: python tools/preview_varieties_v120.py
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from tools.preview_ui_screens import make_app, select_ui2_view, capture


VIEWS = ('shiny_scan', 'shiny_dex', 'shiny_battle', 'shiny_roster',
         'shiny_storage', 'shiny_evolution', 'shiny_farm', 'shiny_maps', 'paradox_dex')


def prepare(app, name):
    base_view = {'shiny_scan': 'scan', 'shiny_dex': 'dex', 'shiny_battle': 'scan',
                 'shiny_roster': 'roster', 'shiny_storage': 'storage',
                 'shiny_evolution': 'evolution', 'shiny_farm': 'world',
                 'shiny_maps': 'maps', 'paradox_dex': 'dex'}[name]
    select_ui2_view(app, base_view)
    engine = app._qa_engine
    ids = [sid for sid in ('agumon_shiny', 'gabumon_shiny', 'patamon_shiny',
                           'greymon_shiny', 'garurumon_shiny', 'fanglongmon_shiny')
           if sid in engine.species]
    if len(ids) < 6:
        raise RuntimeError('The complete v1.2.0 Shiny catalog and assets are required.')
    app.state['party'] = [engine._monster(sid, level=35, abi=80, cam=100) for sid in ids]
    app.state['storage'] = [engine._monster(sid, level=25, abi=40, cam=75) for sid in ids]
    for group in ('party', 'storage'):
        for index, mon in enumerate(app.state[group]):
            mon['uid'] = f'qa-{group}-{index}'
    app.state['scan'].update({sid: data for sid, data in zip(ids, (200, 125, 100, 95, 50, 5))})
    engine._refresh(app.state)
    if name in ('shiny_scan', 'shiny_dex', 'paradox_dex'):
        app.scan_screen.variant = 'paradox' if name == 'paradox_dex' else 'shiny'
    if name == 'shiny_battle':
        app.menu = None
        app.state['in_lab'] = False
        app.state['battle'] = {'kind':'wild', 'enemies':[engine._monster(sid, level=35) for sid in ids[:3]],
                               'active':[0,1,2], 'actor':0, 'turn':1}
    if name == 'shiny_farm':
        app.state['in_farm'] = True
        app.state['in_lab'] = False
        app.farm_screen.reset()
    if name == 'shiny_maps':
        app.state['in_lab'] = False
    app.logs = [('Offline UI QA. Synthetic account; all sprites are supplied release assets.', (99, 203, 221))]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/validation/release_v120/previews')
    parser.add_argument('--sizes', nargs='+', default=['960x600','1920x1080'])
    parser.add_argument('--views', nargs='+', choices=VIEWS, default=list(VIEWS))
    args=parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report=[]
    for size in args.sizes:
        app=make_app(size)
        try:
            for name in args.views:
                prepare(app,name)
                item=capture(app,args.output/f'{name}_{size}.png')
                item['asset_errors']=list(app.assets.errors)
                report.append(item)
        finally:
            pygame.quit()
    (args.output/'preview_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'captures':len(report), 'actions_outside_display':sum(len(r['actions_outside_display']) for r in report),
                      'asset_errors':sum(len(r['asset_errors']) for r in report)},indent=2))
    return int(any(r['actions_outside_display'] or r['asset_errors'] for r in report))


if __name__=='__main__':
    raise SystemExit(main())
