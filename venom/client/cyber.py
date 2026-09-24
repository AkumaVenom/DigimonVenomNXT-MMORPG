"""Native-pixel circuit backdrop and sparse, time-based integer code streams.

The circuit art is generated once per display size/DPI. Animation blits only
small cached glyphs into side gutters, preserving the central reading area.
"""
from __future__ import annotations

from collections import OrderedDict
import math

import pygame

from .render import NativeCanvas, draw


class CyberBackdrop:
    CACHE_BYTES = 64 * 1024 * 1024
    GLYPH_CACHE_BYTES = 512 * 1024
    GLYPH_CACHE_ITEMS = 400
    DIGITS = '0123456789'
    TRAIL_LENGTH = 6
    _PALETTES = {
        None: (88, 183, 211),
        'shop': (141, 183, 171),
        'ranked': (99, 167, 205),
        'rivals': (99, 183, 224),
        'activity': (87, 196, 163),
        'lab': (120, 191, 142),
        'scan': (93, 190, 210),
        'dex': (112, 175, 213),
        'party': (104, 190, 168),
        'evolution': (166, 143, 214),
        'storage': (132, 163, 209),
        'maps': (94, 183, 180),
        'skills': (191, 146, 143),
        'battle': (192, 169, 130),
        'auth': (154, 191, 131),
        'settings': (123, 172, 194),
    }

    def __init__(self, app):
        self.app = app
        self._background_key = None
        self._background_surface = None
        self._background_bytes = 0
        self._glyphs = OrderedDict()
        self._glyph_bytes = 0

    @property
    def screen(self):
        return self.app.screen

    @property
    def scale(self):
        return self.screen.scale if isinstance(self.screen, NativeCanvas) else 1.

    @property
    def cache_bytes(self):
        return self._background_bytes+self._glyph_bytes

    def _target(self):
        return self.screen.surface if isinstance(self.screen, NativeCanvas) else self.screen

    def _paint_static(self, target):
        """Draw at the physical output resolution; never enlarge a framebuffer."""
        width, height = target.get_size()
        # A quiet navy gradient, with the center held dark beneath content.
        # Colors are low contrast; native-sized rectangles avoid temporary
        # overlays or full-screen intermediate pixel arrays.
        for row in range(32):
            top, bottom = row*height//32, (row+1)*height//32
            y_glow = .5+.5*math.cos((row/31.-.18)*math.pi)
            for column in range(48):
                left, right = column*width//48, (column+1)*width//48
                edge = abs(column/47.-.5)*2.
                blue = edge*.7+y_glow*.3
                color = (round(6+blue*3), round(14+blue*8), round(27+blue*12))
                target.fill(color, (left, top, right-left, bottom-top))
        canvas = NativeCanvas(target, self.scale)
        w, h = canvas.get_size()
        edge_width = min(290, w*.22)
        for side in (0, 1):
            def point(x, y):
                return (x if side == 0 else w-x, y)

            for index in range(9):
                x = 16+index*edge_width/10.
                bend = h*(.10+(index % 4)*.145)
                step = 20+(index % 3)*15
                end = min(h-24, bend+step+125+(index % 4)*35)
                points = [point(x, -12), point(x, bend),
                          point(x+step, bend+step), point(x+step, end)]
                draw.lines(canvas, (12, 29, 45), False, points, 5)
                fine = [point(px+9, py) for px, py in
                        ((x, -12), (x, bend), (x+step, bend+step), (x+step, end))]
                draw.lines(canvas, (18, 43, 59), False, fine, 1)
                draw.circle(canvas, (16, 39, 54), points[-1], 7, 2)
                draw.circle(canvas, (24, 63, 77), points[-1], 2)

                # Opposing paths grow upward from the lower edge, with empty
                # space between groups to avoid a dense wallpaper texture.
                bottom_x = 20+(8-index)*edge_width/10.
                lower = h*(.72+(index % 3)*.08)
                lower_points = [point(bottom_x, h+12), point(bottom_x, lower),
                                point(bottom_x+step, lower-step),
                                point(bottom_x+step, max(h*.50, lower-step-42))]
                draw.lines(canvas, (13, 31, 47), False, lower_points, 3)
                draw.circle(canvas, (17, 43, 58), lower_points[-1], 5, 2)

            for index in range(3):
                y = h*(.30+index*.25)
                span = edge_width*(.35+index*.16)
                route = [point(0, y), point(span*.65, y),
                         point(span, y-24), point(span+28, y-24)]
                draw.lines(canvas, (17, 39, 54), False, route, 1)
                draw.rect(canvas, (22, 52, 67), (*point(span+25, y-27), 5, 5))

    def draw(self):
        """Paint the fullscreen circuit backdrop and outer numeric streams."""
        target = self._target()
        key = target.get_size(), self.scale, target.get_bitsize(), target.get_masks()
        if self._background_key != key:
            self._background_surface = None
            self._background_bytes = 0
            self._background_key = key
            # Reserve a bounded budget for tiny glyphs as well as static art.
            cost = target.get_pitch()*target.get_height()
            if cost <= self.CACHE_BYTES-self.GLYPH_CACHE_BYTES:
                self._background_surface = pygame.Surface(target.get_size()).convert(target)
                self._background_bytes = (self._background_surface.get_pitch()
                                          *self._background_surface.get_height())
                self._paint_static(self._background_surface)
        if self._background_surface is not None:
            target.blit(self._background_surface, (0, 0))
        else:
            # Extremely large outputs retain native geometry without an
            # oversized cache allocation (normal 4K uses the cached path).
            self._paint_static(target)
        self.rain(self.screen.get_rect())

    def _glyph(self, digit, color, alpha):
        size = max(7, round(9*self.scale))
        key = size, digit, color, alpha
        cached = self._glyphs.get(key)
        if cached is not None:
            self._glyphs.move_to_end(key)
            return cached
        assets = getattr(self.app, 'assets', None)
        font = assets.font(size) if assets is not None else pygame.font.Font(None, size)
        glyph = font.render(digit, True, color)
        # Surface alpha keeps this consistent across SDL_ttf versions.
        glyph.set_alpha(alpha)
        cost = glyph.get_pitch()*glyph.get_height()
        if cost <= self.GLYPH_CACHE_BYTES:
            self._glyphs[key] = glyph
            self._glyph_bytes += cost
            while (self._glyph_bytes > self.GLYPH_CACHE_BYTES
                   or len(self._glyphs) > self.GLYPH_CACHE_ITEMS):
                _, old = self._glyphs.popitem(last=False)
                self._glyph_bytes -= old.get_pitch()*old.get_height()
        return glyph

    def rain(self, rect, theme=None, edges_only=True):
        """Draw subtle descending integers and restore the exact native clip.

        A themed shell reserves only its outer 18 logical pixels. Fullscreen
        rain can use 38-pixel gutters. The normal ``edges_only`` mode leaves
        the central reading area untouched; a caller can explicitly request
        sparse full-width streams for an otherwise empty decoration area.
        """
        rect = pygame.Rect(rect)
        if rect.width < 14 or rect.height < 12:
            return
        target = self._target()
        native = self.screen.to_physical_rect(rect) if isinstance(self.screen, NativeCanvas) else rect
        previous_clip = target.get_clip()
        clip = previous_clip.clip(native)
        if clip.width <= 0 or clip.height <= 0:
            return
        target.set_clip(clip)
        try:
            now = max(0., float(getattr(self.app, 'now', 0.)))
            color = self._PALETTES.get(theme, self._PALETTES[None])
            # Always keep themed columns strictly outside the x+22 content.
            if edges_only:
                inset = 7 if theme is not None else 10
                columns = [rect.left+inset, rect.right-inset-8]
                if theme is None and rect.width > 120:
                    columns += [rect.left+29, rect.right-37]
            else:
                count = min(12, max(2, rect.width//90))
                columns = [rect.left+(index+.5)*rect.width/count for index in range(count)]
            gap = 12
            travel = rect.height+self.TRAIL_LENGTH*gap+22
            for index, x in enumerate(columns):
                speed = 17+(index*7) % 19
                phase = (index*131+rect.left*3+rect.top*7) % travel
                head = rect.top+(now*speed+phase) % travel-gap
                for part in range(self.TRAIL_LENGTH):
                    y = head-part*gap
                    if y < rect.top-10 or y >= rect.bottom:
                        continue
                    # Only integers 0-9: no random unicode or letter noise.
                    digit = self.DIGITS[(index*7+part*3+int(now*.7)) % 10]
                    alpha = (91, 56, 43, 31, 22, 15)[part]
                    glyph = self._glyph(digit, color, alpha)
                    position = (round(x*self.scale), round(y*self.scale))
                    target.blit(glyph, position)
        finally:
            target.set_clip(previous_clip)
