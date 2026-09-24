"""Compare warm native menu frame costs with identical synthetic QA records.

Uses tools/preview_ui_screens.py fixtures and a selected source tree's real App.
Example: python tools/benchmark_ui_fps.py --project ../baseline_fps1 --json old.json
Results describe headless CPU frame preparation, not Windows display FPS.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from types import SimpleNamespace


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=root)
    parser.add_argument('--frames', type=int, default=360)
    parser.add_argument('--warmup', type=int, default=240)
    parser.add_argument('--size', default='2048x1152')
    parser.add_argument('--ui-scale', type=float, default=4/3)
    parser.add_argument('--views', nargs='+', default=['shop', 'ranked', 'rivals', 'activity'])
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    if args.frames < 1 or args.warmup < 0:
        parser.error('frames must be positive and warmup must be nonnegative')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
    sys.path.insert(0, str(args.project.resolve()))
    import pygame
    # Bind the selected checkout first. The shared preview fixture imports the
    # same already-loaded package, so a baseline run cannot use new client code.
    from venom.client.app import App
    spec = importlib.util.spec_from_file_location('venom_ui_benchmark_fixture', root/'tools/preview_ui_screens.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    available = {name for name, _, _ in fixture.VIEWS} | set(getattr(fixture, 'UI2_VIEWS', ()))
    if any(view not in available for view in args.views):
        parser.error('unknown view; choose from '+', '.join(sorted(available)))
    results = []
    real_get_ticks = pygame.time.get_ticks
    real_image_load = pygame.image.load
    simulated_time = [0.]
    loads = [0]
    def counted_load(*load_args, **load_kwargs):
        loads[0] += 1
        return real_image_load(*load_args, **load_kwargs)
    pygame.time.get_ticks = lambda: round(simulated_time[0]*1000)
    pygame.image.load = counted_load
    try:
        with tempfile.TemporaryDirectory(prefix='venom-menu-benchmark-') as settings:
            for view in args.views:
                simulated_time[0] = 0.
                app_args = SimpleNamespace(demo=True, demo_battle=False, dev=False,
                    config=None, settings=str(Path(settings)/(view+'.json')),
                    size=args.size, ui_scale=args.ui_scale, zoom=1.5, fps=0,
                    fullscreen=False, frames=0, screenshot=None)
                app = App(args.project.resolve(), app_args)
                fixture.select_view(app, view)
                app.community.last_query = float('inf')
                times = []
                update_times = []
                initial_loads = loads[0]
                warmup_loads = initial_loads
                for frame in range(args.warmup+args.frames):
                    simulated_time[0] = frame/60
                    if frame == args.warmup:
                        warmup_loads = loads[0]
                    started = time.perf_counter()
                    pygame.event.pump()
                    app.update(1/60)
                    app.world.update(1/60)
                    updated = time.perf_counter()
                    app.draw()
                    ended = time.perf_counter()
                    if frame >= args.warmup:
                        times.append((ended-started)*1000)
                        update_times.append((updated-started)*1000)
                ordered = sorted(times)
                bounds = app.screen.get_rect()
                # Read footprints after timing; no cache introspection is added
                # to measured frames. These are component caches, not total RSS.
                caches = {
                    'source_images': {'bytes': app.assets.cache_bytes, 'limit': app.assets.IMAGE_CACHE_BYTES},
                    'fitted_images': {'bytes': app.assets.scaled_bytes, 'limit': app.assets.SCALED_CACHE_BYTES},
                    'native_canvas': {'bytes': app.screen._cache_bytes, 'limit': app.screen.cache_limit},
                    'world_sprites': {'bytes': app.world._sprite_bytes, 'limit': app.world.SPRITE_CACHE_BYTES},
                }
                if hasattr(app, 'presentation'):
                    caches['presentation'] = {'bytes': app.presentation._cache_bytes,
                                              'limit': app.presentation.CACHE_BYTES}
                if hasattr(app, 'cyber'):
                    caches['cyber'] = {'bytes': app.cyber.cache_bytes, 'limit': app.cyber.CACHE_BYTES}
                result = {
                    'view': view, 'frames': args.frames, 'warmup_frames': args.warmup,
                    'size': list(app.display.surface.get_size()), 'ui_scale': app.screen.scale,
                    'mean_ms': statistics.mean(times), 'median_ms': statistics.median(times),
                    'p95_ms': ordered[math.ceil(len(times)*.95)-1],
                    'p99_ms': ordered[math.ceil(len(times)*.99)-1], 'max_ms': max(times),
                    'mean_update_ms': statistics.mean(update_times),
                    'warmup_png_loads': warmup_loads-initial_loads,
                    'measured_png_loads': loads[0]-warmup_loads,
                    'actions': len(app.ui.actions),
                    'out_of_bounds_actions': [list(rect) for rect, _ in app.ui.actions if not bounds.contains(rect)],
                    'asset_errors': list(app.assets.errors),
                    'component_caches': caches,
                    'cache_limits_ok': all(item['bytes'] <= item['limit'] for item in caches.values()),
                }
                results.append(result)
                pygame.quit()
        report = {
            'description': 'Headless CPU frame preparation, unprofiled and uncapped; not measured Windows FPS.',
            'project': str(args.project.resolve()),
            'client_module': str(Path(sys.modules[App.__module__].__file__).resolve()),
            'fixture': 'Identical synthetic server_fixture/select_view from tools/preview_ui_screens.py',
            'simulation_hz': 60, 'pygame': pygame.version.ver,
            'notes': 'No real server/account; fixture construction, initial App startup and warmup are excluded. Community polling is disabled for equal preloaded data.',
            'results': results,
        }
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        pygame.time.get_ticks = real_get_ticks
        pygame.image.load = real_image_load
        pygame.quit()


if __name__ == '__main__':
    main()
