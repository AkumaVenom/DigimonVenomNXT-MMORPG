"""Camera promises: whole-level fit, real zoom, stable following and bounded crops."""
import math
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from types import SimpleNamespace
import unittest

import pygame

from venom.client.world import MapCamera, WorldRenderer


class CameraTests(unittest.TestCase):
    def test_one_times_fits_every_map_corner_and_centers_letterboxing(self):
        for map_size in ((1536, 768), (128, 4096), (4096, 128), (320, 240)):
            for viewport in (pygame.Rect(20, 94, 928, 538), pygame.Rect(40, 188, 2960, 1440)):
                camera = MapCamera()
                camera.configure(map_size, viewport, (2, map_size[1] - 2))
                top_left = camera.world_to_screen((0, 0))
                bottom_right = camera.world_to_screen(map_size)
                self.assertGreaterEqual(top_left.x, viewport.left - .5)
                self.assertGreaterEqual(top_left.y, viewport.top - .5)
                self.assertLessEqual(bottom_right.x, viewport.right + .5)
                self.assertLessEqual(bottom_right.y, viewport.bottom + .5)
                self.assertEqual(camera.center, pygame.Vector2(map_size) / 2)
                self.assertEqual(camera.source_crop(), pygame.Rect((0, 0), map_size))

    def test_zoom_tracks_player_and_edges_never_reveal_space_beyond_map(self):
        camera = MapCamera(8)
        camera.configure((1536, 768), pygame.Rect(40, 188, 2960, 1440), (764, 380))
        self.assertLess(camera.source_crop().width, 1536 / 4)
        for target in ((-900, -900), (5000, 5000), (700, 350)):
            camera.update(10, target)
            visible_start = camera.screen_to_world(camera.viewport.topleft)
            visible_end = camera.screen_to_world(camera.viewport.bottomright)
            tolerance = 1 / camera.scale
            self.assertGreaterEqual(visible_start.x, -tolerance)
            self.assertGreaterEqual(visible_start.y, -tolerance)
            self.assertLessEqual(visible_end.x, 1536 + tolerance)
            self.assertLessEqual(visible_end.y, 768 + tolerance)

    def test_round_trip_transform_and_native_ui_scale_independence(self):
        camera = MapCamera(3)
        camera.configure((1536, 768), pygame.Rect(37, 81, 2701, 1483), (710, 345))
        for world in ((0, 0), (17.8, 36.9), (500.1, 250.5), (1536, 768)):
            restored = camera.screen_to_world(camera.world_to_screen(world))
            self.assertLess(restored.distance_to(world), 1e-8)
        normal = MapCamera(3)
        normal.configure((1536, 768), pygame.Rect(0, 0, 1280, 720), (710, 345))
        native_4k = MapCamera(3)
        native_4k.configure((1536, 768), pygame.Rect(0, 0, 3840, 2160), (710, 345))
        self.assertAlmostEqual(native_4k.scale, normal.scale * 3)
        self.assertEqual(native_4k.center, normal.center)

    def test_follow_is_frame_rate_independent(self):
        cameras = [MapCamera(4), MapCamera(4)]
        for camera in cameras:
            camera.configure((1536, 768), pygame.Rect(0, 0, 1280, 720), (550, 350))
        for _ in range(60):
            cameras[0].update(1 / 60, (850, 420))
        for _ in range(144):
            cameras[1].update(1 / 144, (850, 420))
        self.assertLess(cameras[0].center.distance_to(cameras[1].center), 1e-8)

    def test_zoom_crop_allocation_is_bounded_by_viewport_not_full_map(self):
        for map_size in ((1536, 768), (16384, 16384), (128, 128), (32768, 512)):
            for zoom in (1, 1.25, 3, 8):
                camera = MapCamera(zoom)
                camera.configure(map_size, pygame.Rect(0, 0, 3840, 2160), pygame.Vector2(map_size) / 2)
                destination = camera.crop_destination(camera.source_crop())
                self.assertLessEqual(destination.width, camera.viewport.width + math.ceil(2 * camera.scale) + 1)
                self.assertLessEqual(destination.height, camera.viewport.height + math.ceil(2 * camera.scale) + 1)

    def test_plus_minus_fit_and_persistence_respect_requested_range(self):
        settings = {'zoom': 1.0}
        app = SimpleNamespace(display=SimpleNamespace(settings=settings), position=pygame.Vector2(0, 0))
        renderer = WorldRenderer(app)
        for _ in range(30):
            renderer.change_zoom(1)
        self.assertEqual(renderer.zoom, 8.0)
        self.assertEqual(settings['zoom'], 8.0)
        renderer.change_zoom(-1)
        self.assertEqual(renderer.zoom, 7.0)
        renderer.reset_zoom()
        self.assertEqual(renderer.zoom, 1.0)
        renderer.set_zoom(float('nan'))
        self.assertEqual(renderer.zoom, 1.0)

    def test_close_view_frames_body_without_moving_authoritative_foot_position(self):
        app = SimpleNamespace(position=pygame.Vector2(764, 380))
        renderer = WorldRenderer(app)
        renderer.camera.configure((1536, 768), pygame.Rect(52, 238, 2956, 1500), renderer.focus)
        renderer.set_zoom(8)
        head = renderer.camera.world_to_screen(app.position - pygame.Vector2(0, 58))
        feet = renderer.camera.world_to_screen(app.position)
        self.assertTrue(renderer.camera.viewport.collidepoint(head))
        self.assertTrue(renderer.camera.viewport.collidepoint(feet))
        self.assertEqual(app.position, pygame.Vector2(764, 380))

    def test_map_scaling_keeps_palette_crisp_and_clips_the_physical_view(self):
        pygame.init()
        try:
            screen = pygame.Surface((600, 400))
            screen.fill((11, 12, 13))
            source = pygame.Surface((40, 40))
            source.fill((255, 0, 0))
            pygame.draw.rect(source, (0, 255, 0), (20, 0, 20, 40))
            app = SimpleNamespace(screen=screen, position=pygame.Vector2(20, 20))
            renderer = WorldRenderer(app)
            renderer.camera.configure(source.get_size(), pygame.Rect(100, 100, 300, 200), app.position)
            screen.set_clip(renderer.camera.viewport)
            renderer._draw_layer(source, 'background')
            self.assertEqual(screen.get_at((0, 0))[:3], (11, 12, 13))
            self.assertEqual(screen.get_at((200, 150))[:3], (255, 0, 0))
            self.assertEqual(screen.get_at((300, 150))[:3], (0, 255, 0))
            self.assertTrue(all(screen.get_at((x, 150))[:3] in ((255, 0, 0), (0, 255, 0)) for x in range(150, 350)))
        finally:
            pygame.quit()
