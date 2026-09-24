"""App background entry point retains the native cached cyber artwork."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from types import SimpleNamespace
import pygame
from venom.client.app import App
from venom.client.cyber import CyberBackdrop
from venom.client.render import NativeCanvas


def test_app_background_reuses_native_pixels_after_resize_and_dpi_changes():
    pygame.init()
    pygame.display.set_mode((32, 32))
    app = SimpleNamespace(now=4.5)
    app.cyber = CyberBackdrop(app)
    previous = None
    try:
        for size, scale in (((1280, 800), 1), ((2048, 1152), 4/3), ((1920, 1080), 1.25)):
            target = pygame.Surface(size).convert()
            app.screen = NativeCanvas(target, scale)
            App.draw_background(app)
            expected = pygame.image.tobytes(target, 'RGB')
            cached = app.cyber._background_surface
            assert cached.get_size() == size
            assert cached is not previous
            target.fill('red')
            App.draw_background(app)
            assert app.cyber._background_surface is cached
            assert pygame.image.tobytes(target, 'RGB') == expected
            assert app.cyber.cache_bytes <= app.cyber.CACHE_BYTES
            previous = cached
    finally:
        pygame.quit()
