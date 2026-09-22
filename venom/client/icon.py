"""Original vector-drawn Venom V emblem for the window and executable icon."""
from __future__ import annotations

BACKGROUND = (10, 19, 34, 255)
BORDER = (37, 83, 102, 255)
CYAN = (74, 221, 239, 255)
LIME = (175, 246, 105, 255)


def get_icon(size: int = 64):
    """Render clean geometry directly at the requested icon resolution."""
    import pygame
    size = max(16, int(size))
    scale = size / 64
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    rect = pygame.Rect(round(2 * scale), round(2 * scale), round(60 * scale), round(60 * scale))
    pygame.draw.rect(surface, BACKGROUND, rect, border_radius=round(14 * scale))
    pygame.draw.rect(surface, BORDER, rect, width=max(1, round(scale)), border_radius=round(14 * scale))

    def polygon(color, points):
        pygame.draw.polygon(surface, color, [(round(x * scale), round(y * scale)) for x, y in points])

    polygon(CYAN, [(12, 17), (24, 17), (37, 49), (28, 54)])
    polygon(LIME, [(44, 17), (55, 17), (38, 54), (28, 54)])
    polygon((225, 255, 253, 255), [(14, 17), (23, 17), (25, 22), (17, 22)])
    return surface
