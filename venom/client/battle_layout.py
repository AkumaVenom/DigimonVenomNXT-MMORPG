"""Measured battle cards: complete labels, padded highlights and clear rows."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re

import pygame


@lru_cache(maxsize=512)
def wrapped_lines(font, value, width):
    """Wrap at spaces or name components, splitting oversized tokens as needed.

    Unlike the general one-line UI helper, this never replaces a name with an
    ellipsis. Font objects and widths are native-pixel values, including DPI.
    """
    value = str(value).strip()
    if not value:
        return ('',)
    lines = []
    while value:
        if font.size(value)[0] <= width:
            lines.append(value)
            break
        end = 1
        while end < len(value) and font.size(value[:end+1])[0] <= width:
            end += 1
        # Camel-case source names such as ImperialdramonDragonModeBlack have
        # useful breakpoints even though the catalog contains no spaces.
        breaks = [m.start() for m in re.finditer(
            r'\s+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', value)]
        cut = max((point for point in breaks if 0 < point <= end), default=end)
        lines.append(value[:cut].rstrip())
        value = value[cut:].lstrip()
    return tuple(lines)


@dataclass(frozen=True)
class BattleCard:
    anchor: tuple
    sprite_size: tuple
    rect: pygame.Rect
    labels: tuple
    name_lines: tuple
    name_size: int
    hp_rect: pygame.Rect
    sp_rect: pygame.Rect
    turn_y: float
    badge_center: tuple


def layout_row(screen, assets, view, monsters, side):
    """Lay out one live team without overlapping its neighbours or commands."""
    if not monsters:
        return []
    view = pygame.Rect(view)
    scale = screen.scale
    enemy = side == 'enemy'
    pitch = view.width/(len(monsters)+1)
    max_width = max(40, math.floor(pitch-12))
    inner_width = max(20, max_width-20)
    native_width = max(1, math.floor(inner_width*scale))
    top, bottom = view.y+73, view.bottom-57
    # Player cards need a little more room for SP and the turn indicator.
    split = top+(bottom-top-12)/2-8
    row_top, row_bottom = (top, split) if enemy else (split+12, bottom)
    row_height = row_bottom-row_top
    detail_font = assets.font(max(1, round(11*scale)))
    badge_font = assets.font(max(1, round(9*scale)), True)
    badge_height = badge_font.get_height()/scale if enemy else 0
    metadata = []
    for mon in monsters:
        size = 15
        font = assets.font(max(1, round(size*scale)), True)
        names = wrapped_lines(font, str(mon.get('name', 'Digimon')), native_width)
        if len(names) > 2 and row_height < 230:
            size = 14
            font = assets.font(max(1, round(size*scale)), True)
            names = wrapped_lines(font, str(mon.get('name', 'Digimon')), native_width)
        details = f"Lv.{mon.get('level', 1)} · {mon.get('type', '?')} / {mon.get('attribute', '?')}"
        detail_lines = wrapped_lines(detail_font, details, native_width)
        metadata.append((size, font, names, detail_lines))

    name_height = max(len(names)*(font.get_height()/scale+2)-2
                      for _, font, names, _ in metadata)
    detail_height = max(len(lines)*(detail_font.get_height()/scale+1)-1
                        for _, _, _, lines in metadata)
    # Use the same label bands and sprite dimensions for the whole team.
    above_sprite = 8+(badge_height+3 if enemy else 0)+name_height+2+detail_height+3
    below_sprite = 35 if enemy else 64
    preferred = (112, 86) if view.height < 500 else (135, 104)
    sprite_height = max(12, min(preferred[1], math.floor(row_height-above_sprite-below_sprite)))
    sprite_width = min(preferred[0], inner_width)
    default_y = view.y+view.height*(.42 if enemy else .78)
    foot_y = min(row_bottom-below_sprite,
                 max(default_y, row_top+above_sprite+sprite_height))
    # Round once so sprites, bars and the highlight share the same anchor.
    foot_y = round(foot_y)
    details_top = foot_y-sprite_height-3-detail_height
    names_top = details_top-2-name_height
    badge_top = names_top-3-badge_height
    cards = []
    for index, (size, font, names, details) in enumerate(metadata):
        cx = round(view.x+pitch*(index+1))
        labels = []
        block_height = len(names)*(font.get_height()/scale+2)-2
        line_y = names_top+(name_height-block_height)/2
        for line in names:
            height = font.get_height()/scale
            labels.append((line, (cx, line_y+height/2), size, True, 'name'))
            line_y += height+2
        line_y = details_top
        for line in details:
            height = detail_font.get_height()/scale
            labels.append((line, (cx, line_y+height/2), 11, False, 'details'))
            line_y += height+1
        width = max(130, sprite_width,
                    *(font.size(line)[0]/scale for line in names),
                    *(detail_font.size(line)[0]/scale for line in details))
        width = min(max_width, math.ceil(width)+20)
        card_top = math.floor((badge_top if enemy else names_top)-8)
        card_bottom = math.ceil(foot_y+below_sprite)
        rect = pygame.Rect(math.floor(cx-width/2), card_top, width, card_bottom-card_top)
        cards.append(BattleCard(
            (cx, foot_y), (sprite_width, sprite_height), rect, tuple(labels), names, size,
            pygame.Rect(cx-65, foot_y+20, 130, 7),
            pygame.Rect(cx-65, foot_y+32, 130, 4), foot_y+49,
            (cx, badge_top+badge_height/2)))
    return cards
