"""The native cyber-blue battle stage; static artwork, no gameplay state.

The HUD retains one finished plate. Gradients are sampled only while building
that plate; every grid edge and circuit trace is drawn at native resolution.
No scrolling, flashes or particles compete with combat cues.
"""
from __future__ import annotations

import math
import pygame

from .render import draw


CACHE_BYTES = 32 * 1024 * 1024


def _mix(a, b, t):
    return tuple(round(x + (y-x)*t) for x, y in zip(a, b))


def _wash(canvas, rect, *, allow_surface=True):
    """Soft blue light underneath crisp geometry, never a scaled UI image."""
    physical = canvas.to_physical_rect(rect)
    if physical.width <= 0 or physical.height <= 0:
        return
    if not allow_surface or physical.width * physical.height * 4 > CACHE_BYTES:
        # Extremely large displays use bounded geometry instead of allocating
        # another full-window gradient. This is also the HUD's uncached path.
        for i in range(96):
            y0 = rect.y + rect.height*i/96
            y1 = rect.y + rect.height*(i+1)/96
            glow = math.exp(-((i/96-.06)/.18)**2)
            draw.rect(canvas, _mix((5, 18, 39), (8, 42, 79), glow),
                      (rect.x, y0, rect.width, max(1, y1-y0)))
        return
    light = pygame.Surface((128, 96))
    for y in range(96):
        depth = y/95
        horizon = math.exp(-((depth-.065)/.11)**2)
        floor = math.exp(-((depth-.52)/.53)**2)
        for x in range(128):
            center = max(0., 1-abs(x/127-.5)*2)**.65
            light.set_at((x, y), (round(4+3*center+2*horizon),
                                 round(13+12*floor*center+22*horizon*center),
                                 round(31+26*floor*center+39*horizon*center)))
    wash = pygame.transform.smoothscale(light, physical.size)
    canvas.surface.blit(wash, physical.topleft)


def _trace(canvas, points, core=(38, 149, 200), halo=(12, 54, 90)):
    draw.lines(canvas, halo, False, points, 4)
    draw.aalines(canvas, core, False, points)


def paint(canvas, area):
    """Paint one logical arena, preserving the caller's exact physical clip."""
    area = pygame.Rect(area)
    if area.width <= 0 or area.height <= 0:
        return
    surface = canvas.surface
    original_clip = surface.get_clip()
    surface.set_clip(original_clip.clip(canvas.to_physical_rect(area)))
    try:
        x, y, w, h = area
        draw.rect(canvas, (5, 15, 32), area)
        # Calm opaque bands keep headings and commands independent of the art.
        head = min(70, max(1, h//4))
        foot = min(59, max(1, h//5))
        field = pygame.Rect(x+1, y+head, max(1, w-2), max(1, h-head-foot))
        arena_pixels = canvas.to_physical_rect(area)
        _wash(canvas, field, allow_surface=arena_pixels.width*arena_pixels.height*4 <= CACHE_BYTES)
        original_field_clip = surface.get_clip()
        surface.set_clip(original_field_clip.clip(canvas.to_physical_rect(field)))
        try:
            cx = x+w*.5
            horizon = field.y+field.height*.045
            floor_bottom = field.bottom+field.height*.04
            depth = floor_bottom-horizon

            # Real perspective spacing: rows converge rather than staying at
            # a constant screen distance. Major lines anchor the digital floor.
            for row in range(31, -1, -1):
                t = 1/(1+row*.29)
                gy = horizon+depth*t
                color = _mix((13, 43, 76), (22, 78, 119), t)
                if row % 4 == 0:
                    color = _mix(color, (35, 112, 158), .30)
                color = _mix((9, 29, 56), color, min(1., max(0., (t-.09)/.36)))
                draw.aaline(canvas, color, (x, gy), (x+w, gy))
            for column in range(-19, 20):
                end_x = cx+column*w/12
                depths = (.065, .12, .20, .34, .54, .75, 1.)
                color = (21, 71, 112) if column % 3 == 0 else (12, 48, 84)
                for a, b in zip(depths, depths[1:]):
                    far = (cx+(end_x-cx)*a, horizon+depth*a)
                    near = (cx+(end_x-cx)*b, horizon+depth*b)
                    draw.aaline(canvas, _mix((9, 29, 56), color, min(1., b*1.5)), far, near)

            # Sparse inlaid tracks, projected onto the same floor. Brighter
            # marks live towards the sides, away from names, bars and sprites.
            def project(column, row):
                t = 1/(1+row*.29)
                return cx+column*w/12*t, horizon+depth*t

            for side in (-1, 1):
                for column, row, length in ((7, 1, 2), (10, 4, 2), (13, 8, 3), (16, 13, 4)):
                    a = project(side*column, row)
                    b = project(side*column, row+length)
                    c = project(side*(column+1), row+length)
                    _trace(canvas, (a, b, c), (25, 114, 161), (9, 38, 68))
                    draw.circle(canvas, (57, 169, 204), c, 1.5)

            # Low horizon light gives depth without a white strip or glare.
            for offset, color in ((-3, (11, 47, 80)), (-1, (19, 80, 119)),
                                  (0, (38, 131, 170)), (2, (13, 56, 91))):
                draw.line(canvas, color, (x+w*.13, horizon+offset),
                          (x+w*.87, horizon+offset))
            for side in (-1, 1):
                origin = cx+side*w*.11
                draw.aalines(canvas, (26, 98, 143), False,
                             [(origin, horizon), (origin+side*w*.035, horizon-8),
                              (origin+side*w*.15, horizon-8)])

            # Recessed side rails and short cyan emitters frame the play space.
            for side in (-1, 1):
                def point(u, v):
                    return (x+w*u if side == -1 else x+w*(1-u), y+h*v)
                plate = [point(0, .17), point(.055, .205), point(.107, .38),
                         point(.035, .86), point(0, .92)]
                draw.polygon(canvas, (6, 21, 43), plate)
                draw.aalines(canvas, (16, 64, 107), False, plate[1:4])
                _trace(canvas, [point(.014, .23), point(.038, .25), point(.058, .32)],
                       (44, 162, 204), (11, 49, 82))
                _trace(canvas, [point(.018, .76), point(.028, .70), point(.044, .70)],
                       (33, 122, 178), (9, 38, 68))
                for tick in range(5):
                    v = .47+tick*.023
                    draw.aaline(canvas, (24, 88, 131), point(.014, v), point(.023, v+.006))
                draw.circle(canvas, (68, 180, 218), point(.038, .25), 2)

            # A restrained floor seal occupies the gap between the two teams.
            # It is decoration only: no rings imply extra target/click regions.
            sprite_height = 86 if h < 500 else 104
            gap_top = y+h*.42+35
            gap_bottom = y+h*.78-sprite_height-43
            # Smaller layouts have little room between bars and party labels;
            # omit this decoration there rather than drawing through the text.
            if gap_bottom-gap_top >= 24:
                seal_y = (gap_top+gap_bottom)/2
                seal_w = min(w*.28, 350)
                seal_h = min(h*.068, 48, (gap_bottom-gap_top)*.65)
                for factor, color in ((1., (15, 54, 91)), (.86, (22, 76, 114))):
                    ring = pygame.FRect(cx-seal_w*factor/2, seal_y-seal_h*factor/2,
                                        seal_w*factor, seal_h*factor)
                    draw.ellipse(canvas, color, ring, 1)
                for side in (-1, 1):
                    a = cx+side*seal_w*.58
                    draw.aaline(canvas, (32, 96, 140), (a, seal_y), (a+side*w*.06, seal_y))
                    draw.aaline(canvas, (29, 91, 128), (a, seal_y-3), (a, seal_y+3))
                inset = min(8, seal_h*.22)
                diamond = [(cx, seal_y-inset), (cx+19, seal_y), (cx, seal_y+inset), (cx-19, seal_y)]
                draw.aalines(canvas, (30, 93, 132), True, diamond)
        finally:
            surface.set_clip(original_field_clip)

        # Precise machined frame. Cyan establishes the arena theme; gold and
        # green are reserved for the existing target and active-turn controls.
        edge = [(x+12, y+1), (x+w-12, y+1), (x+w-1, y+12),
                (x+w-1, y+h-12), (x+w-12, y+h-1), (x+12, y+h-1),
                (x+1, y+h-12), (x+1, y+12)]
        draw.aalines(canvas, (35, 82, 116), True, edge)
        draw.line(canvas, (24, 63, 97), (x+18, y+head-5), (x+w-18, y+head-5))
        draw.line(canvas, (16, 48, 80), (x+18, y+h-foot), (x+w-18, y+h-foot))
        _trace(canvas, [(x+18, y+1), (x+min(194, w*.34), y+1),
                        (x+min(207, w*.36), y+7)], (69, 195, 234), (14, 62, 95))
        for side in (0, 1):
            corner_x = x+9 if side == 0 else x+w-9
            direction = 1 if side == 0 else -1
            draw.lines(canvas, (39, 117, 162), False,
                       [(corner_x, y+h-24), (corner_x, y+h-15),
                        (corner_x+direction*8, y+h-7), (corner_x+direction*32, y+h-7)], 1)
    finally:
        surface.set_clip(original_clip)
