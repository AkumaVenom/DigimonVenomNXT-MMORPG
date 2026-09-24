"""Repeated HUD text avoids measurement without changing native text layout."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
from venom.client.widgets import _fit_text, _TEXT_LAYOUT_CACHE


def test_cached_layout_matches_original_truncation_at_fractional_dpi():
    pygame.font.init()
    try:
        _TEXT_LAYOUT_CACHE.clear()
        font = pygame.font.Font(None, 21)
        for value in ('', 'A', 'AI RIVAL · RiftScout3846', 'Search for Digimon  E'):
            for width in (0, 6.25, 13.5, 65.25, 200, 900):
                expected = value
                while expected and font.size(expected)[0] > width:
                    expected = expected[:-2] + '…' if len(expected) > 2 else ''
                assert _fit_text(font, value, width) == expected
                assert _fit_text(font, value, width) == expected
    finally:
        _TEXT_LAYOUT_CACHE.clear()
        pygame.font.quit()


def test_repeating_labels_skip_measurement_and_layout_cache_is_bounded():
    class MeasuredFont:
        calls = 0

        def size(self, value):
            self.calls += 1
            return len(value) * 10, 20

    _TEXT_LAYOUT_CACHE.clear()
    font = MeasuredFont()
    try:
        first = _fit_text(font, 'DigiLab  F1', 65)
        measured = font.calls
        assert measured > 1
        for _ in range(120):
            assert _fit_text(font, 'DigiLab  F1', 65) == first
        assert font.calls == measured
        assert _fit_text(font, 'DigiLab  F1', 200) == 'DigiLab  F1'
        assert font.calls > measured
        for index in range(1100):
            _fit_text(font, str(index), 200)
        assert len(_TEXT_LAYOUT_CACHE) == 1024
        _fit_text(font, 'X' * 4097, 50000)
        assert len(_TEXT_LAYOUT_CACHE) == 1024
    finally:
        _TEXT_LAYOUT_CACHE.clear()
