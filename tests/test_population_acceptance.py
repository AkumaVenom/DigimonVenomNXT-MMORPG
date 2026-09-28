"""Independent acceptance checks for the real imported world and rival population.

These tests exercise real collision assets, canonical game rules and temporary
SQLite persistence. Performance measurements live in tools/benchmark_rivals.py;
CI does not make machine-dependent frame-time assertions.
"""
from __future__ import annotations

import math
from pathlib import Path
import random
import tempfile
import unittest

from venom.common.game import GameEngine
from venom.server.bots import BotManager
from venom.server.community_store import CommunityStore
from venom.server.database import Database
from venom.server.navigation import Navigation


ROOT = Path(__file__).resolve().parents[1]


class NavigationAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = GameEngine(ROOT, seed=1907)
        cls.navigation = Navigation(ROOT, cls.engine.maps)

    def test_every_imported_map_has_safe_distributed_spawn_points(self):
        self.assertEqual(sum(mid.startswith("map_") for mid in self.engine.maps), 254)
        self.assertGreater(len(self.engine.maps), 254)
        for map_id in self.engine.maps:
            with self.subTest(map_id=map_id):
                points = [self.navigation.spawn(map_id, index) for index in range(20)]
                self.assertTrue(all(self.navigation.walkable(map_id, *point) for point in points))
                # Distribution must not collapse every tamer onto the same pixel.
                self.assertGreater(len(set(points)), 1)

    def test_sampled_walks_stay_on_collision_and_at_human_speed(self):
        rng = random.Random(282)
        for map_id in self.engine.maps:
            start = self.navigation.spawn(map_id, 2)
            end = self.navigation.plan(map_id, *start, rng)
            if end is None:
                continue
            duration = math.dist(start, end) / Navigation.SPEED
            path = {"from": start, "to": end, "start": 100.0, "end": 100.0 + duration}
            previous = self.navigation.sample(path, 100.0)
            with self.subTest(map_id=map_id):
                for index in range(1, 21):
                    now = 100.0 + duration * index / 20
                    sample = self.navigation.sample(path, now)
                    self.assertEqual(sample, self.navigation.sample(path, now))
                    self.assertTrue(self.navigation.walkable(map_id, *sample[:2]), (map_id, now, sample))
                    self.assertLessEqual(math.dist(previous[:2], sample[:2]),
                                         Navigation.SPEED * duration / 20 + 1e-6)
                    previous = sample
                self.assertAlmostEqual(previous[0], end[0], places=7)
                self.assertAlmostEqual(previous[1], end[1], places=7)
                self.assertEqual(previous[2:], (0.0, 0.0))

    def test_cached_multi_segment_routes_keep_corners_continuous(self):
        rng = random.Random(4781)
        for map_id in self.engine.maps:
            start = self.navigation.spawn(map_id, 7)
            route = self.navigation.route(map_id, *start, rng, 250.0, seconds=12)
            with self.subTest(map_id=map_id):
                self.assertIsNotNone(route)
                segments = route.get("segments", [route])
                for before, after in zip(segments, segments[1:]):
                    self.assertEqual(before["to"], after["from"])
                    self.assertEqual(before["end"], after["start"])
                    left = self.navigation.sample(route, before["end"] - .0001)
                    right = self.navigation.sample(route, before["end"] + .0001)
                    self.assertLessEqual(math.dist(left[:2], right[:2]), Navigation.SPEED * .0002 + 1e-6)
                duration = route["end"] - route["start"]
                previous = self.navigation.sample(route, route["start"])
                count = math.ceil(duration * 20)
                for index in range(1, count + 1):
                    now = route["start"] + duration * index / count
                    sample = self.navigation.sample(route, now)
                    self.assertTrue(self.navigation.walkable(map_id, *sample[:2]), (map_id, now, sample))
                    self.assertLessEqual(math.dist(previous[:2], sample[:2]), Navigation.SPEED * duration / count + 1e-6)
                    previous = sample


class PopulationAcceptanceTests(unittest.TestCase):
    def test_real_3000_population_seeds_all_sectors_and_scheduler_reaches_every_bot(self):
        with tempfile.TemporaryDirectory(prefix="venom-population-test-") as directory:
            database = Database({"driver": "sqlite", "path": str(Path(directory) / "population.sqlite3")}, dev=True)
            try:
                database.initialize()
                store = CommunityStore(database)
                store.initialize()
                engine = GameEngine(ROOT, seed=440)
                manager = BotManager(engine, store, config={"count": 3000, "seed": 880})
                manager.initialize(now=1000.0)
                self.assertEqual(len(manager.bots), 3000)
                self.assertEqual(set(manager.by_map), set(engine.maps))
                self.assertEqual(sum(mid.startswith("map_") for mid in manager.by_map), 254)
                occupancy = [len(ids) for ids in manager.by_map.values()]
                low, remainder = divmod(3000, len(engine.maps))
                self.assertEqual(set(occupancy), {low, low + 1} if remainder else {low})
                self.assertEqual(sum(occupancy), 3000)
                self.assertEqual(set().union(*manager.by_map.values()), set(manager.bots))
                for bot in manager.bots.values():
                    state = bot["state"]
                    self.assertEqual(len(state["party"]), 1)
                    self.assertEqual(state["party"][0]["stage"], "rookie")
                    self.assertEqual(state["party"][0]["xp"], 0)
                    self.assertEqual(state["party"][0]["level"], bot["runtime"]["seed_level"])
                    self.assertEqual(state["wins"], 0)
                    self.assertEqual(state["losses"], 0)
                    self.assertFalse(state["scan"])
                    self.assertTrue(all(value == 0 for value in bot["stats"].values()))
                for map_id in manager.by_map:
                    actors = manager.snapshot(map_id, now=1000.0)
                    self.assertEqual(actors, manager.snapshot(map_id, now=1000.0))
                    self.assertLessEqual(len(actors), math.ceil(3000 / len(engine.maps)))
                    self.assertTrue(all(actor["map_id"] == map_id and actor["is_bot"] for actor in actors))
                self.assertEqual(len(manager.directory(limit=100000)["entries"]), 100)
                self.assertEqual(manager.directory(offset=3000)["entries"], [])
                # A bounded heap must eventually service high IDs too. This is a
                # simulation fairness assertion, not a CPU/FPS performance gate.
                for index in range(1, 601):
                    manager.tick(now=1000.0 + index * .1, dt=.1)
                    if all(bot["stats"]["exploration_steps"] for bot in manager.bots.values()):
                        break
                self.assertTrue(all(bot["stats"]["exploration_steps"] > 0 for bot in manager.bots.values()))
                self.assertGreater(manager.processed, 2999)
                self.assertTrue(all(bot["runtime"]["next_at"] > 0 for bot in manager.bots.values()))
                self.assertLessEqual(len(manager.activity()["events"]), 100)
                self.assertEqual(manager.counters["wild_wins"], sum(bot["state"]["wins"] for bot in manager.bots.values()))
                self.assertEqual(manager.counters["wild_losses"], sum(bot["state"]["losses"] for bot in manager.bots.values()))
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
