"""Compare complete world-frame sizes with the production compression settings.

Runs entirely on a disposable in-memory fixture: no player save is read or written.
The crowded map uses real BotManager rows and collision-checked moving patrols.
Bytes include WebSocket framing, but exclude TLS/TCP/IP overhead and other traffic.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class DisposableStore:
    """The fixture needs no durable records or invented ranked outcomes."""
    def bot_load_all(self):
        return []

    def bot_save_batch(self, rows):
        pass


def build_fixture(count=160):
    from venom.common.game import GameEngine
    from venom.server.bots import BotManager

    engine = GameEngine(ROOT, seed=823)
    map_count = len(engine.maps)
    area = engine.maps["map_004_a"]
    engine.maps = {area["id"]: area}
    manager = BotManager(engine, DisposableStore(), config={"count": count, "seed": 217})
    manager.initialize(now=1000.0)
    for bot in manager.bots.values():
        state = bot["state"]
        bot["runtime"]["path"] = manager.navigation.patrol(
            area["id"], state["x"], state["y"], bot["rng"], 1000.0, seconds=60)
    return engine, manager, map_count


def server_extension():
    from venom.server.main import transport_extensions
    # This is the offer made by the unchanged native websockets client.
    _, extension = transport_extensions()[0].process_request_params(
        [("client_max_window_bits", None)], [])
    return extension


async def measure(samples=100):
    from websockets.frames import Frame, OP_TEXT
    from venom.server.main import Session, WorldServer

    engine, manager, map_count = build_fixture()
    map_id = next(iter(engine.maps))
    occupancy = {}
    for population in (3000, 5000):
        distribution = Counter(index % map_count for index in range(population))
        occupancy[str(population)] = {
            "minimum": min(distribution.values()), "maximum": max(distribution.values()),
            "mean": round(population / map_count, 3)}
    counts = sorted({occupancy["3000"]["maximum"], occupancy["5000"]["maximum"], 100, 160})
    state = engine.new_player("BandwidthFixture", next(iter(engine.tamers)), engine.starters[0])
    state.update(in_farm=False, in_lab=False, map_id=map_id)
    session = Session(None, "bandwidthfixture", "temporary-fixture", state, 0)
    world = WorldServer(engine, None)
    world.sessions[session.key] = session
    queued = []
    world._queue_world = lambda session, group, encoded: queued.append(encoded)
    scenarios = []
    for count in counts:
        extension = server_extension()
        plain_sizes, compressed_sizes, encode_seconds = [], [], []
        moving_counts = []
        for tick in range(samples):
            rows = manager.snapshot(map_id, now=1000 + tick * .1)[:count]
            moving_counts.append(sum(row["moving"] for row in rows))
            world.community = SimpleNamespace(ready=True, snapshots=lambda fields, now: {map_id: rows})
            await world.broadcast_once()
            payload = queued.pop().encode("utf-8")
            plain_sizes.append(len(Frame(OP_TEXT, payload).serialize(mask=False)))
            started = time.perf_counter()
            compressed_sizes.append(len(Frame(OP_TEXT, payload).serialize(mask=False, extensions=[extension])))
            encode_seconds.append(time.perf_counter() - started)
        scenarios.append({
            "rivals_on_map": count, "human_players_on_map": 1, "snapshots": samples,
            "moving_rivals_mean": round(statistics.fmean(moving_counts), 2),
            "uncompressed_websocket_bytes_per_second": round(statistics.fmean(plain_sizes) * 10),
            "compressed_websocket_bytes_per_second": round(statistics.fmean(compressed_sizes) * 10),
            "reduction_percent": round((1 - sum(compressed_sizes) / sum(plain_sizes)) * 100, 2),
            "compression_mean_ms_per_frame": round(statistics.fmean(encode_seconds) * 1000, 4),
        })
    return {
        "platform": platform.platform(), "python": platform.python_version(),
        "method": "Production broadcast_once JSON and WebSocket frame serializer; real BotManager actors on a crowded disposable map, following collision-checked patrols; 10Hz snapshots.",
        "limits": ["Frame sizes include WebSocket framing, not TLS/TCP/IP overhead, acknowledgements or other game traffic.",
                   "Initial occupancy is the exact ordinal-modulo-map-count allocation, not a claim about mature roaming populations.",
                   "Compression timings are this machine's isolated per-frame encoder cost, not a Windows hosting capacity guarantee."],
        "compression": {"server_no_context_takeover": True, "client_no_context_takeover": True,
                        "window_bits": 12, "level": 1, "memLevel": 5},
        "catalog_map_count": map_count, "initial_population_occupancy": occupancy,
        "scenarios": scenarios,
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in [ROOT / "venom/server/main.py", ROOT / "venom/server/bots.py"]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 2 <= args.samples <= 10000:
        parser.error("--samples must be between 2 and 10000")
    encoded = json.dumps(asyncio.run(measure(args.samples)), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
