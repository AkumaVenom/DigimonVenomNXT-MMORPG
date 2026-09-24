from __future__ import annotations
from collections import OrderedDict
import pygame
from .render import NativeCanvas, draw

BG = (9, 15, 27)
PANEL = (15, 26, 44)
CARD = (22, 37, 59)
LINE = (41, 62, 86)
WHITE = (231, 241, 249)
MUTED = (141, 164, 185)
CYAN = (67, 213, 231)
LIME = (190, 240, 107)
RED = (255, 117, 138)
GOLD = (247, 199, 104)

_TEXT_CACHE = OrderedDict()
_TEXT_CACHE_BYTES = 0
_TEXT_CACHE_LIMIT = 8 * 1024 * 1024
_TEXT_LAYOUT_CACHE = OrderedDict()


def _fit_text(font, value, width):
    """Measure a repeating label once, at its actual native-pixel width.

    The glyph cache alone does not avoid SDL_ttf layout: measuring/truncating
    every button and HUD label each frame was still work in the render loop.
    Include the font object and physical width so DPI/resize changes cannot
    reuse a layout from a different display size.
    """
    key = (font, value, width)
    cached = _TEXT_LAYOUT_CACHE.get(key)
    if cached is not None:
        _TEXT_LAYOUT_CACHE.move_to_end(key)
        return cached
    fitted = value
    while fitted and font.size(fitted)[0] > width:
        fitted = fitted[:-2] + '…' if len(fitted) > 2 else ''
    # Bound both the number of labels and the maximum retained string size.
    if len(value) <= 4096:
        _TEXT_LAYOUT_CACHE[key] = fitted
        while len(_TEXT_LAYOUT_CACHE) > 1024:
            _TEXT_LAYOUT_CACHE.popitem(last=False)
    return fitted


def _render_text(font, value, color):
    global _TEXT_CACHE_BYTES
    key = font, value, tuple(pygame.Color(color))
    if key in _TEXT_CACHE:
        _TEXT_CACHE.move_to_end(key)
        return _TEXT_CACHE[key][0]
    surface = font.render(value, True, color)
    cost = surface.get_pitch() * surface.get_height()
    if cost <= _TEXT_CACHE_LIMIT:
        _TEXT_CACHE[key] = surface, cost
        _TEXT_CACHE_BYTES += cost
        while _TEXT_CACHE_BYTES > _TEXT_CACHE_LIMIT or len(_TEXT_CACHE) > 512:
            _, (_, old_cost) = _TEXT_CACHE.popitem(last=False)
            _TEXT_CACHE_BYTES -= old_cost
    return surface


def text(screen, assets, value, position, size=18, color=WHITE, bold=False, max_width=None, center=False,
         *, alpha=None, outline=None, outline_width=1):
    scale = screen.scale if isinstance(screen, NativeCanvas) else 1.0
    font = assets.font(max(1, round(size * scale)), bold)
    value = str(value)
    if max_width is not None:
        value = _fit_text(font, value, max_width * scale)
    surface = _render_text(font, value, color)
    point = screen.to_physical_point(position) if isinstance(screen, NativeCanvas) else position
    rect = surface.get_rect(center=point) if center else surface.get_rect(topleft=point)
    target = screen.surface if isinstance(screen, NativeCanvas) else screen
    if outline is not None:
        edge = _render_text(font, value, outline)
        if alpha is not None:
            edge = edge.copy()
            edge.set_alpha(max(0, min(255, int(alpha))))
        stroke = max(1, round(outline_width * scale))
        for ox, oy in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
            target.blit(edge, rect.move(ox * stroke, oy * stroke))
    if alpha is not None:
        surface = surface.copy()
        surface.set_alpha(max(0, min(255, int(alpha))))
    target.blit(surface, rect)
    return screen.to_logical_rect(rect) if isinstance(screen, NativeCanvas) else rect


def wrap(screen, assets, value, position, width, size=16, color=MUTED, max_lines=5):
    x, y = position
    scale = screen.scale if isinstance(screen, NativeCanvas) else 1.0
    font = assets.font(max(1, round(size * scale)))
    line, lines = '', 0
    for word in str(value).split():
        candidate = f'{line} {word}'.strip()
        if font.size(candidate)[0] > width * scale and line:
            text(screen, assets, line, (x, y), size, color)
            y += size+7
            lines += 1
            line = word
            if lines >= max_lines:
                return y
        else:
            line = candidate
    if line:
        text(screen, assets, line, (x, y), size, color)
    return y+size+7


def outlined_text(screen, assets, value, position, size=18, color=WHITE, bold=True,
                  center=True, alpha=255, outline_color=(6, 12, 22), outline_width=2):
    """Native-resolution, fading battle text with a contrasting outline."""
    return text(screen, assets, value, position, size, color, bold, center=center,
                alpha=alpha, outline=outline_color, outline_width=outline_width)


def panel(screen, rect, color=PANEL, border=LINE, radius=14):
    draw.rect(screen, color, rect, border_radius=radius)
    if border:
        draw.rect(screen, border, rect, 1, border_radius=radius)


def bar(screen, rect, value, total, color=LIME, bg=(7, 14, 25)):
    draw.rect(screen, bg, rect, border_radius=max(2, rect.height//2))
    ratio = max(0, min(1, value/max(1, total)))
    if ratio:
        draw.rect(screen, color, (rect.x, rect.y, max(2, int(rect.width*ratio)), rect.height), border_radius=max(2, rect.height//2))


class UI:
    def __init__(self, screen, assets):
        self.screen, self.assets = screen, assets
        self.actions = []
        self.mouse = (0, 0)
        self.focus = None
        self.values = {}
        self.fields = []
        self.on_activate = None

    def begin(self):
        self.actions, self.fields = [], []
        position = pygame.mouse.get_pos()
        self.mouse = self.screen.to_logical_point(position) if isinstance(self.screen, NativeCanvas) else position

    def button(self, rect, label, callback, primary=False, selected=False, disabled=False, small=False,
               *, accent=None):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(self.mouse)
        fill = LIME if primary and not disabled else (32, 68, 82) if selected else (32, 48, 69) if hover else CARD
        color = BG if primary and not disabled else MUTED if disabled else WHITE
        if accent is not None:
            fill = accent if primary and not disabled else (27, 51, 67) if hover and not disabled else (19, 38, 53)
            color = BG if primary and not disabled else MUTED if disabled else WHITE
            edge = accent if (selected or hover or primary) and not disabled else (43, 66, 81)
            panel(self.screen, rect, fill, edge, 6)
            if not disabled:
                shine = tuple(min(255, int(c*.6+80)) for c in fill)
                draw.line(self.screen, shine, (rect.x+7, rect.y+1), (rect.right-8, rect.y+1))
                if selected:
                    draw.line(self.screen, accent, (rect.x+7, rect.bottom-2), (rect.right-8, rect.bottom-2), 2)
        else:
            panel(self.screen, rect, fill, CYAN if selected else LINE, 9)
        text(self.screen, self.assets, label, rect.center, 14 if small else 16, color, primary, rect.width-14, True)
        if not disabled:
            self.actions.append((rect, callback))

    def field(self, rect, key, placeholder='', password=False, size=18):
        rect = pygame.Rect(rect)
        selected = self.focus == key
        panel(self.screen, rect, BG, CYAN if selected else LINE, 8)
        value = self.values.get(key, '')
        show = '•'*len(value) if password else value
        if selected and (pygame.time.get_ticks()//500) % 2 == 0:
            show += '│'
        text(self.screen, self.assets, show or placeholder, (rect.x+12, rect.y+(rect.height-size)//2-1), size,
             WHITE if value or selected else MUTED, max_width=rect.width-24)
        self.fields.append((rect, key))

    def event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            position = self.screen.to_logical_point(event.pos) if isinstance(self.screen, NativeCanvas) else event.pos
            for rect, key in self.fields:
                if rect.collidepoint(position):
                    self.focus = key
                    pygame.key.start_text_input()
                    return True
            self.focus = None
            pygame.key.stop_text_input()
            for rect, callback in reversed(self.actions):
                if rect.collidepoint(position):
                    callback()
                    if self.on_activate:
                        self.on_activate()
                    return True
        if self.focus:
            if event.type == pygame.TEXTINPUT:
                value = self.values.get(self.focus, '')
                limit = 128 if self.focus == 'password' else 180 if self.focus == 'chat' else 48
                self.values[self.focus] = (value+event.text)[:limit]
                return True
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    self.values[self.focus] = self.values.get(self.focus, '')[:-1]
                    return True
                if event.key == pygame.K_TAB:
                    keys = [key for _, key in self.fields]
                    if self.focus in keys:
                        self.focus = keys[(keys.index(self.focus)+1) % len(keys)]
                    return True
                if event.key == pygame.K_ESCAPE:
                    self.focus = None
                    pygame.key.stop_text_input()
                    return True
        return False
