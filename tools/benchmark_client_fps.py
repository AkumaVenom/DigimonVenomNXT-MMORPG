"""Reproducible crowded-world renderer benchmark using the actual client.

Run from the source folder, for example::

    python -m tools.benchmark_client_fps --bots 160 --frames 360 --json result.json

The SDL dummy display measures CPU frame preparation, not Windows/monitor FPS.
It retains native pixels, the real map/sprites/UI, and all requested rivals and
partners. Synthetic 10 Hz snapshots keep interpolation and animation active.
Use --project to run the *same* workload against another source checkout.
"""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import random
import statistics
import sys
import tempfile
import time
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--bots', type=int, default=160)
    parser.add_argument('--frames', type=int, default=360)
    parser.add_argument('--warmup', type=int, default=960)
    parser.add_argument('--size', default='2048x1152')
    parser.add_argument('--ui-scale', type=float, default=1.3333333333333333)
    parser.add_argument('--zoom', type=float, default=1.5)
    parser.add_argument('--map', default='map_004_a')
    parser.add_argument('--pan', action='store_true', help='Move the local camera through a repeatable path')
    parser.add_argument('--json', type=Path)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--screenshot', type=Path)
    args = parser.parse_args()
    if args.bots < 0 or args.frames < 1 or args.warmup < 0:
        parser.error('bots/warmup must be nonnegative and frames must be positive')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
    sys.path.insert(0, str(args.project.resolve()))
    import pygame
    from venom.client.app import App

    temporary_settings = tempfile.TemporaryDirectory(prefix='venom-fps-benchmark-')
    app_args = SimpleNamespace(demo=True, demo_battle=False, config=None, dev=False,
                               settings=str(Path(temporary_settings.name)/'display.json'),
                               size=args.size, ui_scale=args.ui_scale,
                               zoom=args.zoom, fps=0, fullscreen=False, frames=0,
                               screenshot=None)
    app = App(args.project.resolve(), app_args)
    real_get_ticks = pygame.time.get_ticks
    simulated_time = [0.0]
    pygame.time.get_ticks = lambda: round(simulated_time[0] * 1000)
    app.connection = SimpleNamespace(incoming=queue.Queue(), connected=True)
    app.state.update(username='CrowdBenchmark', map_id=args.map)
    entry = app.assets.maps[args.map]
    app.position.update(entry.get('spawn', [764, 380]))
    origin = app.position.copy()
    app.follower.update(app.position + pygame.Vector2(-34, 26))
    app.state.update(x=app.position.x, y=app.position.y)
    tamers = sorted(app.assets.tamers)
    # Stable, spread-out selections exercise small and large sprites, all stages,
    # all 64 tamer appearances and a large variety of active animation frames.
    species = sorted(app.assets.species)
    lead_ids = [species[(i * 17) % len(species)] for i in range(min(128, len(species)))]
    randomizer = random.Random(4096)
    bases = [(app.position.x + randomizer.uniform(-350, 350),
              app.position.y + randomizer.uniform(-175, 175)) for _ in range(args.bots)]
    dxdy = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)]

    def snapshot(now):
        players = []
        for i, (x, y) in enumerate(bases):
            angle = now * .45 + i * .7
            dx, dy = dxdy[(i + int(now / 2)) % len(dxdy)]
            players.append({'username': f'AI Crowd{i:04}', 'name': f'Crowd{i:04}',
                            'id': f'bot:benchmark-{i}', 'is_bot': True,
                            'tamer': tamers[i % len(tamers)],
                            'lead': lead_ids[i % len(lead_ids)], 'map_id': args.map,
                            'x': x + math.sin(angle)*12, 'y': y + math.cos(angle)*12,
                            'dx': dx, 'dy': dy})
        return {'op': 'world', 'players': players}

    durations, update_times, draw_times = [], [], []
    profiler = cProfile.Profile() if args.profile else None
    image_loads = [0]
    real_image_load = pygame.image.load
    def counted_image_load(*load_args, **load_kwargs):
        image_loads[0] += 1
        return real_image_load(*load_args, **load_kwargs)
    pygame.image.load = counted_image_load
    warmup_loads = 0
    try:
        for frame in range(args.warmup + args.frames):
            simulated_time[0] = frame / 60
            if frame % 6 == 0:
                # Exclude fixture construction from the timed client workload;
                # the real network thread already deserializes incoming JSON.
                app.connection.incoming.put(snapshot(simulated_time[0]))
            if frame == args.warmup:
                warmup_loads = image_loads[0]
                if profiler:
                    profiler.enable()
            start = time.perf_counter()
            pygame.event.pump()
            app.update(1/60)
            if args.pan:
                app.position.update(origin.x + math.sin(simulated_time[0]*.7)*120,
                                    origin.y + math.sin(simulated_time[0]*.45)*80)
                app.follower.update(app.position + pygame.Vector2(-34, 26))
                app.moving = True
            app.world.update(1/60)
            updated = time.perf_counter()
            app.draw()
            ended = time.perf_counter()
            if frame >= args.warmup:
                durations.append((ended-start)*1000)
                update_times.append((updated-start)*1000)
                draw_times.append((ended-updated)*1000)
        if profiler:
            profiler.disable()
            args.profile.parent.mkdir(parents=True, exist_ok=True)
            profiler.dump_stats(str(args.profile))
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(app.display.surface, str(args.screenshot))
        ordered = sorted(durations)
        def percentile(fraction):
            return ordered[min(len(ordered)-1, math.ceil(len(ordered)*fraction)-1)]
        result = {
            'description': 'CPU frame preparation; SDL dummy, no vsync or limiter; not measured Windows FPS',
            'profiled': bool(profiler), 'panning': args.pan,
            'project': str(args.project.resolve()), 'pygame': pygame.version.ver,
            'size': list(app.display.surface.get_size()), 'ui_scale': app.screen.scale,
            'zoom': args.zoom, 'map': args.map, 'bots': len(app.players),
            'world_actors': len(app.world._actors()), 'unique_tamers': min(args.bots, len(tamers)),
            'unique_leads': min(args.bots, len(lead_ids)), 'frames': args.frames,
            'warmup_frames': args.warmup, 'simulation_hz': 60, 'snapshot_hz': 10,
            'warmup_png_loads': warmup_loads, 'measured_png_loads': image_loads[0]-warmup_loads,
            'mean_ms': statistics.mean(durations), 'median_ms': statistics.median(durations),
            'p95_ms': percentile(.95), 'p99_ms': percentile(.99), 'max_ms': max(durations),
            'mean_update_ms': statistics.mean(update_times), 'mean_draw_ms': statistics.mean(draw_times),
            'cpu_frames_per_second': 1000/statistics.mean(durations),
            'final_frame_sha256': hashlib.sha256(pygame.image.tobytes(app.display.surface, 'RGB')).hexdigest(),
            'asset_errors': app.assets.errors,
        }
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        pygame.time.get_ticks = real_get_ticks
        pygame.image.load = real_image_load
        pygame.quit()
        temporary_settings.cleanup()


if __name__ == '__main__':
    main()
