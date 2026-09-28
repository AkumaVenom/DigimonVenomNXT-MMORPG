"""Native-resolution drawing with logical UI coordinates.

Only individual pixel-art surfaces are enlarged. UI geometry and fonts are
drawn directly onto the display's actual pixels; there is no low-resolution
framebuffer that Windows or SDL has to stretch after rendering.
"""
from __future__ import annotations

from collections import OrderedDict
import math
import pygame


class NativeCanvas:
    """A logical-coordinate view over a real, native-resolution Surface.

    ``blit`` treats its source as logical-sized pixel art and uses nearest
    filtering. Sources retained in its bounded cache are assumed immutable;
    pass ``cache=False`` for surfaces whose pixels change in place, or call
    ``invalidate`` after modifying an existing cached source. ``blit_native``
    places already native-resolution content, including rendered text.
    """

    CACHE_ITEMS = 4096

    def __init__(self, surface, scale=1.0, cache_bytes=32 * 1024 * 1024):
        self.cache_limit = max(0, int(cache_bytes))
        self._scaled = OrderedDict()
        self._cache_bytes = 0
        self.set_surface(surface, scale)

    def set_surface(self, surface, scale=None):
        scale = float(self.scale if scale is None else scale)
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError('Canvas scale must be a positive finite number')
        self.surface, self.scale = surface, scale
        self.invalidate()

    def invalidate(self, source=None):
        if source is None:
            self._scaled.clear()
            self._cache_bytes = 0
            return
        for key in tuple(self._scaled):
            if key[0] is source:
                _, cost = self._scaled.pop(key)
                self._cache_bytes -= cost

    def get_size(self):
        return self.get_width(), self.get_height()

    def get_width(self):
        return math.floor(self.surface.get_width() / self.scale)

    def get_height(self):
        return math.floor(self.surface.get_height() / self.scale)

    def get_rect(self, **kwargs):
        rect = pygame.Rect((0, 0), self.get_size())
        for key, value in kwargs.items():
            setattr(rect, key, value)
        return rect

    def to_physical_point(self, point):
        return round(point[0] * self.scale), round(point[1] * self.scale)

    def to_logical_point(self, point):
        return point[0] / self.scale, point[1] / self.scale

    def to_physical_rect(self, rect):
        rect = pygame.FRect(rect)
        left, top = self.to_physical_point(rect.topleft)
        right, bottom = self.to_physical_point(rect.bottomright)
        return pygame.Rect(left, top, right - left, bottom - top)

    def to_logical_rect(self, rect):
        rect = pygame.Rect(rect)
        left, top = round(rect.left / self.scale), round(rect.top / self.scale)
        right, bottom = round(rect.right / self.scale), round(rect.bottom / self.scale)
        return pygame.Rect(left, top, right - left, bottom - top)

    def get_clip(self):
        return self.to_logical_rect(self.surface.get_clip())

    def set_clip(self, rect=None):
        self.surface.set_clip(None if rect is None else self.to_physical_rect(rect))

    def fill(self, color, rect=None, special_flags=0):
        changed = self.surface.fill(color, None if rect is None else self.to_physical_rect(rect), special_flags)
        return self.to_logical_rect(changed)

    def blit_native(self, source, dest, area=None, special_flags=0):
        position = dest.topleft if isinstance(dest, (pygame.Rect, pygame.FRect)) else dest[:2]
        changed = self.surface.blit(source, self.to_physical_point(position), area, special_flags)
        return self.to_logical_rect(changed)

    def blit(self, source, dest, area=None, special_flags=0, *, cache=True):
        if isinstance(source, NativeCanvas):
            # A canvas already contains native-resolution pixels.
            if source.scale != self.scale:
                raise ValueError('Canvas-to-canvas blits require matching scales')
            native_area = source.to_physical_rect(area) if area is not None else None
            return self.blit_native(source.surface, dest, native_area, special_flags)
        if area is not None:
            # Crop before scaling so a viewport never needs a full-map texture.
            area = pygame.Rect(area).clip(source.get_rect())
            if area.width <= 0 or area.height <= 0:
                position = dest.topleft if isinstance(dest, pygame.Rect) else dest[:2]
                return pygame.Rect(position, (0, 0))
            source = source.subsurface(area)
            cache = False
        size = tuple(max(1, round(n * self.scale)) for n in source.get_size())
        if size == source.get_size():
            return self.blit_native(source, dest, special_flags=special_flags)
        colorkey = source.get_colorkey()
        key = (source, size, source.get_alpha(), tuple(colorkey) if colorkey is not None else None)
        entry = self._scaled.get(key) if cache else None
        if entry is not None:
            self._scaled.move_to_end(key)
            scaled = entry[0]
        else:
            scaled = pygame.transform.scale(source, size)
            # Cache sprites, not transient full-window overlays. Account for
            # both surfaces because retaining a key retains the source too.
            cost = source.get_pitch() * source.get_height() + scaled.get_pitch() * scaled.get_height()
            if cache and cost <= min(self.cache_limit, 1024 * 1024):
                self._scaled[key] = scaled, cost
                self._cache_bytes += cost
                while self._cache_bytes > self.cache_limit or len(self._scaled) > self.CACHE_ITEMS:
                    _, (_, old_cost) = self._scaled.popitem(last=False)
                    self._cache_bytes -= old_cost
        return self.blit_native(scaled, dest, special_flags=special_flags)


class _NativeDraw:
    """The pygame.draw operations used by the game, with canvas support."""

    @staticmethod
    def _target(surface):
        return surface.surface if isinstance(surface, NativeCanvas) else surface

    @staticmethod
    def _point(surface, point):
        return surface.to_physical_point(point) if isinstance(surface, NativeCanvas) else point

    @staticmethod
    def _rect(surface, rect):
        return surface.to_physical_rect(rect) if isinstance(surface, NativeCanvas) else rect

    @staticmethod
    def _length(surface, value):
        if not isinstance(surface, NativeCanvas) or value <= 0:
            return value
        return max(1, round(value * surface.scale))

    @staticmethod
    def _result(surface, result):
        return surface.to_logical_rect(result) if isinstance(surface, NativeCanvas) else result

    def rect(self, surface, color, rect, width=0, border_radius=0, **kwargs):
        radii = {key: self._length(surface, value) for key, value in kwargs.items()}
        result = pygame.draw.rect(self._target(surface), color, self._rect(surface, rect),
                                  self._length(surface, width), self._length(surface, border_radius), **radii)
        return self._result(surface, result)

    def line(self, surface, color, start_pos, end_pos, width=1):
        return self._result(surface, pygame.draw.line(self._target(surface), color,
                            self._point(surface, start_pos), self._point(surface, end_pos), self._length(surface, width)))

    def lines(self, surface, color, closed, points, width=1):
        return self._result(surface, pygame.draw.lines(self._target(surface), color, closed,
                            [self._point(surface, p) for p in points], self._length(surface, width)))

    def aaline(self, surface, color, start_pos, end_pos, blend=1):
        # pygame-ce 2.5.8 always blends these edges; its old blend argument is
        # ignored and deprecated. Keep our call signature for existing users.
        return self._result(surface, pygame.draw.aaline(self._target(surface), color,
                            self._point(surface, start_pos), self._point(surface, end_pos)))

    def aalines(self, surface, color, closed, points, blend=1):
        return self._result(surface, pygame.draw.aalines(self._target(surface), color, closed,
                            [self._point(surface, p) for p in points]))

    def circle(self, surface, color, center, radius, width=0, **kwargs):
        return self._result(surface, pygame.draw.circle(self._target(surface), color,
                            self._point(surface, center), self._length(surface, radius), self._length(surface, width), **kwargs))

    def ellipse(self, surface, color, rect, width=0):
        return self._result(surface, pygame.draw.ellipse(self._target(surface), color,
                            self._rect(surface, rect), self._length(surface, width)))

    def polygon(self, surface, color, points, width=0):
        return self._result(surface, pygame.draw.polygon(self._target(surface), color,
                            [self._point(surface, p) for p in points], self._length(surface, width)))

    def arc(self, surface, color, rect, start_angle, stop_angle, width=1):
        return self._result(surface, pygame.draw.arc(self._target(surface), color,
                            self._rect(surface, rect), start_angle, stop_angle, self._length(surface, width)))


draw = _NativeDraw()
