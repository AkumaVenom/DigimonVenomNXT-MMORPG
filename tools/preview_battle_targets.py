"""Render and audit real battle target cards with synthetic, offline data.

This is a reproducible visual check only; no account or save is opened/written.
Run: python tools/preview_battle_targets.py --output battle-target-review
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.preview_ui_screens import capture, game_fixture, make_app
import pygame
from venom.client.render import NativeCanvas
from venom.client import widgets

CASES = (
    ('960x600', .75),
    ('1280x800', 1.),
    ('2047x1155', 1.0625),
    ('2047x1155', 1.25),
    ('1920x1080', 1.25),
    ('3840x2160', 2.5),
)


def target_fixture(app, *, longest=False):
    """Three real enemy species and a Fanglongmon party, rendered by App."""
    app.state = game_fixture(app)
    engine = app._qa_engine
    names = sorted(engine.species, key=lambda sid: len(engine.species[sid]['name']), reverse=True)
    enemy_ids = [names[0], names[1], names[2]] if longest else ['fanglongmon_paradox', names[0], names[1]]
    app.state['party'] = [engine._monster(sid, 99, abi=100, cam=100)
                          for sid in ('fanglongmon', 'omnimon', 'fanglongmon_paradox')]
    engine._refresh(app.state)
    app.state['battle'] = {'id': 'offline-target-layout-qa', 'kind': 'wild', 'turn': 1,
                           'enemies': [engine._monster(sid, 100) for sid in enemy_ids],
                           'active': [0, 1, 2], 'actor': 0}
    app.state['in_farm'] = app.state['in_lab'] = False
    app.menu = None
    app.target = 0
    app.action_pending = False
    app.animations = []
    app.now = 8.5
    app.logs = [('Offline battle layout preview. All account data is synthetic.', widgets.CYAN)]
    width, height = app.screen.get_size()
    app.viewport = pygame.Rect(20, 94, width-352, height-262)
    return app.state['battle']['enemies']


def use_display(app, size, scale):
    physical = tuple(map(int, size.split('x')))
    app.display.surface = pygame.display.set_mode(physical)
    app.screen = NativeCanvas(app.display.surface, scale)
    app.ui.screen = app.screen


def audit_render(app):
    """Observe exact native font surfaces and real clickable target geometry.

    Measurement independently follows pygame's rendered surface dimensions,
    including centering and fractional scaling, instead of trusting a layout
    helper's own claimed bounds.
    """
    text_rows = []
    outlines = []
    original_text = widgets.text
    original_rect = widgets.draw.rect

    def record_text(screen, assets, value, position, size=18, color=widgets.WHITE,
                    bold=False, max_width=None, center=False, **kwargs):
        result = original_text(screen, assets, value, position, size, color, bold,
                               max_width, center, **kwargs)
        scale = screen.scale if isinstance(screen, NativeCanvas) else 1.
        font = assets.font(max(1, round(size*scale)), bold)
        fitted = str(value) if max_width is None else widgets._fit_text(font, str(value), max_width*scale)
        surface = font.render(fitted, True, color)
        point = screen.to_physical_point(position) if isinstance(screen, NativeCanvas) else position
        rect = surface.get_rect(center=point) if center else surface.get_rect(topleft=point)
        glyphs = surface.get_bounding_rect(min_alpha=1).move(rect.topleft)
        text_rows.append({'requested': str(value), 'rendered': fitted, 'rect': list(rect),
                          'glyphs': list(glyphs), 'color': list(color), 'bold': bold,
                          'size': size})
        return result

    def record_rect(screen, color, rect, width=0, *args, **kwargs):
        if tuple(color)[:3] == widgets.GOLD and width == 2:
            outlines.append(list(screen.to_physical_rect(rect)))
        return original_rect(screen, color, rect, width, *args, **kwargs)

    # Catch module-local aliases as well as widgets.text itself.
    text_modules = [module for name, module in tuple(sys.modules.items())
                    if name.startswith('venom.client.') and getattr(module, 'text', None) is original_text]
    app.ui.begin()
    with ExitStack() as stack:
        for module in text_modules:
            stack.enter_context(patch.object(module, 'text', side_effect=record_text))
        stack.enter_context(patch.object(widgets.draw, 'rect', side_effect=record_rect))
        app.draw_battle()
    count = len(app.state['battle']['enemies'])
    targets = [list(app.screen.to_physical_rect(rect)) for rect, _ in app.ui.actions[:count]]
    return {'pixels': list(app.screen.surface.get_size()), 'ui_scale': app.screen.scale,
            'viewport': list(app.screen.to_physical_rect(app.viewport)),
            'target': app.target, 'targets': targets, 'outlines': outlines, 'text': text_rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'fixture': 'Offline synthetic account; real catalog species and native client rendering',
              'captures': []}
    app = make_app('1280x800')
    try:
        for size, scale in CASES:
            use_display(app, size, scale)
            for longest in (False, True):
                enemies = target_fixture(app, longest=longest)
                stem = f"{'longest' if longest else 'fanglongmon'}_{size}_{scale:g}"
                entry = audit_render(app)
                entry['species'] = [mon['name'] for mon in enemies]
                entry.update(capture(app, args.output/f'{stem}.png'))
                report['captures'].append(entry)
        (args.output/'target_geometry.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    finally:
        pygame.quit()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
