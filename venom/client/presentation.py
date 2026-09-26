"""Shared destination art direction, at native display resolution.

Only supplied artwork is nearest-neighbour scaled. Geometry and typography stay
on the physical framebuffer, including at fractional Windows DPI. Expensive
backdrops are built once per size/theme; animation is a handful of small lines.
"""
from __future__ import annotations

from collections import OrderedDict
import math

import pygame

from .render import NativeCanvas, draw
from .widgets import text, WHITE


PALETTES = {
    'shop': dict(accent=(240, 215, 124), secondary=(114, 225, 229), ink=(9, 18, 31),
                 panel=(18, 36, 51), line=(46, 73, 89), muted=(168, 190, 205),
                 glow=(23, 62, 68), grid='m_snka.png', character='t_charaall.png'),
    'ranked': dict(accent=(250, 208, 121), secondary=(231, 117, 137), ink=(11, 17, 30),
                   panel=(21, 32, 48), line=(56, 66, 86), muted=(176, 183, 202),
                   glow=(39, 36, 61), grid='bt_me_bak.png', character='t_charaall.png'),
    'rivals': dict(accent=(111, 230, 248), secondary=(182, 150, 255), ink=(12, 17, 31),
                   panel=(24, 31, 50), line=(56, 70, 97), muted=(157, 177, 205),
                   glow=(42, 34, 81), grid='m_bg04.png', character='t_charaall_m.png'),
    'activity': dict(accent=(116, 244, 199), secondary=(108, 205, 242), ink=(9, 20, 30),
                     panel=(18, 35, 47), line=(43, 76, 83), muted=(159, 185, 196),
                     glow=(22, 56, 66), grid='m_bg01.png', character='t_charaall_m.png'),
}

# The original four destinations retain their approved colors. New screens use
# the same quiet navy foundations, with small accents indicating their purpose.
def _destination(accent, secondary, glow, grid='m_bg04.png'):
    return dict(accent=accent, secondary=secondary, ink=(9, 18, 31),
                panel=(18, 33, 49), line=(44, 68, 86), muted=(162, 185, 204),
                glow=glow, grid=grid, character='t_charaall_m.png')


PALETTES.update({
    'season': _destination((105, 229, 255), (211, 154, 255), (29, 36, 76), 'bt_me_bak.png'),
    'farm': _destination((166, 237, 140), (110, 222, 222), (23, 53, 60), 'm_bg01.png'),
    'lab': _destination((166, 237, 140), (100, 225, 210), (23, 53, 60), 'm_bg01.png'),
    'scan': _destination((109, 231, 247), (157, 238, 180), (19, 53, 70), 'm_bg03.png'),
    'dex': _destination((145, 207, 250), (177, 199, 255), (25, 43, 74)),
    'party': _destination((153, 237, 191), (243, 216, 147), (25, 53, 63), 'm_bg01.png'),
    'evolution': _destination((200, 164, 255), (110, 221, 248), (45, 34, 77), 'm_bg03.png'),
    'storage': _destination((165, 201, 248), (183, 170, 246), (29, 41, 67)),
    'maps': _destination((113, 226, 222), (183, 230, 154), (22, 53, 65), 'm_bg01.png'),
    'skills': _destination((244, 183, 147), (235, 149, 189), (51, 38, 62), 'm_snka.png'),
    'battle': _destination((246, 207, 131), (241, 137, 151), (53, 32, 58), 'bt_me_bak.png'),
    'auth': _destination((221, 241, 108), (107, 223, 242), (22, 51, 63)),
    'settings': _destination((162, 207, 234), (132, 228, 216), (25, 43, 58)),
})


def colors(theme='rivals'):
    """Return the shared palette without exposing mutable global state."""
    return dict(PALETTES.get(theme, PALETTES['rivals']))


def _mix(a, b, fraction):
    return tuple(round(x + (y-x)*fraction) for x, y in zip(a, b))


class Presentation:
    CACHE_BYTES = 64 * 1024 * 1024
    # Partner grids may retain several small animation frames beside a shell.
    # The byte budget, rather than a low entry count, should govern that art.
    CACHE_ITEMS = 256
    ART_ROOT = 'assets/ui/dawn/'

    def __init__(self, app):
        self.app = app
        self._cache = OrderedDict()
        self._cache_bytes = 0
        self._display_key = None
        self._art_bounds = OrderedDict()

    colors = staticmethod(colors)

    @property
    def screen(self):
        return self.app.screen

    @property
    def scale(self):
        return self.screen.scale if isinstance(self.screen, NativeCanvas) else 1.0

    def _remember(self, key, surface):
        cost = surface.get_pitch()*surface.get_height()
        if cost <= self.CACHE_BYTES:
            old = self._cache.pop(key, None)
            if old is not None:
                self._cache_bytes -= old.get_pitch()*old.get_height()
            self._cache[key] = surface
            self._cache_bytes += cost
            while self._cache_bytes > self.CACHE_BYTES or len(self._cache) > self.CACHE_ITEMS:
                _, old = self._cache.popitem(last=False)
                self._cache_bytes -= old.get_pitch()*old.get_height()
        return surface

    def _get(self, key):
        result = self._cache.get(key)
        if result is not None:
            self._cache.move_to_end(key)
        return result

    def _check_display(self):
        target = self.screen.surface if isinstance(self.screen, NativeCanvas) else self.screen
        key = target.get_size(), self.scale
        if key != self._display_key:
            self._cache.clear()
            self._cache_bytes = 0
            self._display_key = key

    def background(self):
        """Optional full-display circuit backdrop used behind destination panels."""
        self._check_display()
        w, h = self.screen.get_size()
        target = self.screen.surface if isinstance(self.screen, NativeCanvas) else self.screen
        key = 'background', target.get_size(), self.scale
        surface = self._get(key)
        if surface is None:
            surface = pygame.Surface(target.get_size()).convert()
            surface.fill((7, 15, 28))
            canvas = NativeCanvas(surface, self.scale)
            self._circuits(canvas, pygame.Rect(0, 0, w, h), (15, 31, 46), (18, 42, 57))
            for y in range(0, h, 4):
                draw.line(canvas, (9, 18, 31), (0, y), (w, y))
            self._remember(key, surface)
        if isinstance(self.screen, NativeCanvas):
            self.screen.blit_native(surface, (0, 0))
        else:
            self.screen.blit(surface, (0, 0))

    @staticmethod
    def _circuits(canvas, rect, dim, highlight):
        """Sparse traces/endpoints drawn once, never an animated full-frame layer."""
        w, h = rect.size
        x0, y0 = rect.topleft
        for index in range(10):
            x = x0+int(w*(index+.3)/10)
            start = y0 + (index%3)*32
            bend = y0 + int(h*(.2+(index%4)*.11))
            end = min(y0+h-22, bend+85+(index%3)*48)
            step = 28+index%3*12
            points = [(x,start),(x,bend),(x+step,bend+step),(x+step,end)]
            draw.lines(canvas,dim,False,points,5)
            draw.lines(canvas,highlight,False,[(px+9,py) for px,py in points],1)
            draw.circle(canvas,dim,points[-1],8,3)
            draw.circle(canvas,highlight,(points[-1][0]+9,points[-1][1]),3,1)
        for index in range(4):
            y = y0+h-38-index*29
            points=[(x0+w*.56,y),(x0+w*.68,y),(x0+w*.73,y-50),(x0+w-24,y-50)]
            draw.lines(canvas,dim,False,points,2)

    def _image(self, name, crop=None):
        source = self.app.assets.image(name if name.startswith('assets/') else self.ART_ROOT+name)
        if source is None:
            return None
        if crop is None:
            return source
        key = 'crop', name, tuple(crop)
        cached = self._get(key)
        if cached is None:
            safe = pygame.Rect(crop).clip(source.get_rect())
            if not safe.width or not safe.height:
                return None
            cached = self._remember(key, source.subsurface(safe).copy())
        return cached

    def _stamp(self, canvas, name, rect, crop=None, alpha=255, tint=None, *, flip=False):
        """Scale a clean atlas region directly to its final native pixel size."""
        rect = pygame.Rect(rect)
        if rect.width <= 0 or rect.height <= 0:
            return
        native = canvas.to_physical_rect(rect) if isinstance(canvas, NativeCanvas) else rect
        key = 'stamp', name, tuple(crop) if crop else None, native.size, alpha, tint, flip
        surface = self._get(key)
        if surface is None:
            source = self._image(name, crop)
            if source is None:
                return
            surface = pygame.transform.scale(source, native.size)
            if flip:
                surface = pygame.transform.flip(surface, True, False)
            if tint is not None:
                surface.fill((*tint, 255), special_flags=pygame.BLEND_RGBA_MULT)
            surface.set_alpha(alpha)
            self._remember(key, surface)
        if isinstance(canvas, NativeCanvas):
            canvas.blit_native(surface, rect.topleft)
        else:
            canvas.blit(surface, rect.topleft)

    def _stamp_fit(self, canvas, path, rect, alpha=255, *, flip=False):
        """Keep portrait proportions and trim transparent padding before sizing."""
        crop = self._art_bounds.get(path)
        if crop is None:
            source = self._image(path)
            if source is None:
                return False
            crop = source.get_bounding_rect()
            self._art_bounds[path] = crop
            while len(self._art_bounds) > 128:
                self._art_bounds.popitem(last=False)
        else:
            self._art_bounds.move_to_end(path)
        if not crop.width or not crop.height:
            return False
        rect = pygame.Rect(rect)
        if rect.width <= 0 or rect.height <= 0:
            return False
        factor = min(rect.width/crop.width, rect.height/crop.height)
        fitted = pygame.Rect(0, 0, max(1, round(crop.width*factor)), max(1, round(crop.height*factor)))
        fitted.midbottom = rect.midbottom
        self._stamp(canvas, path, fitted, crop, alpha, flip=flip)
        return True

    def image(self, rect, path, alpha=255, *, flip=False):
        """Render a supplied asset with transparent padding trimmed, at real DPI."""
        self._check_display()
        return self._stamp_fit(self.screen, path, rect, alpha, flip=flip)

    def sprite(self, rect, species_id, motion='idle', now=0., flip=False, alpha=255):
        """Large, correctly fitted partner art without changing catalog frames."""
        path = self.app.assets.sprite_path(species_id, motion, now)
        if not path:
            return False
        return self.image(rect, path, alpha, flip=flip)

    def _header_art(self, canvas, w, header_height, theme):
        p = colors(theme)
        box = pygame.Rect(w-284, 7, 192, header_height-12)
        if theme == 'shop':
            if self._stamp_fit(canvas, 'assets/ui/extracted/shopkeeper.png', box):
                return
        elif theme in ('rivals', 'activity'):
            pair = ('dawn_tamer_boy.png', 'dusk_tamer_girl.png') if theme == 'rivals' else ('dawn_tamer_girl.png', 'dusk_tamer_boy.png')
            for index, filename in enumerate(pair):
                portrait = pygame.Rect(box.x+index*96, box.y+5, 98, box.height-5)
                self._stamp_fit(canvas, 'assets/ui/extracted/'+filename, portrait)
            return
        elif theme == 'ranked':
            if self._stamp_fit(canvas, 'assets/ui/extracted/geogreymon_title.png', box):
                return
        elif theme in ('scan', 'evolution', 'party', 'auth'):
            pair = {'scan': ('lunamon_title.png', 'coronamon_title.png'),
                    'evolution': ('coronamon_title.png', 'geogreymon_title.png'),
                    'party': ('dawn_tamer_boy.png', 'gaogamon_title.png'),
                    'auth': ('dawn_tamer_boy.png', 'dawn_tamer_girl.png')}[theme]
            for index, filename in enumerate(pair):
                portrait = pygame.Rect(box.x+index*98, box.y+8, 94, box.height-8)
                self._stamp_fit(canvas, 'assets/ui/extracted/'+filename, portrait)
            return
        elif theme == 'maps':
            landscape = box.inflate(16, -24)
            draw.rect(canvas, p['line'], landscape.inflate(4, 4), 1, border_radius=3)
            self._stamp(canvas, 'df_bg00.png', landscape, (0, 0, 256, 192), 225)
            return
        elif theme in ('lab', 'dex', 'storage', 'skills', 'battle', 'settings'):
            portrait = {'lab': 'sunflowmon_title.png', 'dex': 'gaogamon_title.png',
                        'storage': 'dawn_tamer_girl.png', 'skills': 'coronamon_title.png',
                        'battle': 'geogreymon_title.png', 'settings': 'dusk_tamer_boy.png'}[theme]
            if self._stamp_fit(canvas, 'assets/ui/extracted/'+portrait, box):
                return
        self._stamp(canvas, p['character'], box, (0, 0, 256, 192), 245)

    def shell(self, rect, theme, title, subtitle='', eyebrow='', *, header_height=128):
        """Paint a destination; return its padded body rectangle.

        Caller-owned close/navigation buttons may go above/right of the body.
        The hero reserves its rightmost 290 logical pixels for supplied art.
        """
        self._check_display()
        rect = pygame.Rect(rect)
        p = colors(theme)
        native = self.screen.to_physical_rect(rect) if isinstance(self.screen, NativeCanvas) else rect
        key = 'shell', theme, rect.size, native.size, self.scale, header_height
        backdrop = self._get(key)
        if backdrop is None:
            backdrop = self._backdrop(rect.size, native.size, theme, header_height)
            self._remember(key, backdrop)
        if isinstance(self.screen, NativeCanvas):
            self.screen.blit_native(backdrop, rect.topleft)
        else:
            self.screen.blit(backdrop, rect.topleft)
        cyber = getattr(self.app, 'cyber', None)
        if cyber is not None:
            cyber.rain(rect, theme)
        usable = max(80, rect.width-340)
        text(self.screen, self.app.assets, eyebrow or 'VENOM NXT  /  TAMER NETWORK',
             (rect.x+28, rect.y+18), 10, p['accent'], True, usable)
        text(self.screen, self.app.assets, title, (rect.x+26, rect.y+37), 32, WHITE, True, usable)
        text(self.screen, self.app.assets, subtitle, (rect.x+28, rect.y+85), 12, p['muted'], False, usable)
        # Five changing native lines cost no full-screen alpha/texture work.
        phase = float(getattr(self.app, 'now', 0.))
        for index in range(5):
            length = 5 + int(5*(1+math.sin(phase*2.0-index*.8)))
            x = rect.x+29+index*6
            draw.line(self.screen, p['accent'], (x, rect.y+header_height-12),
                      (x, rect.y+header_height-12-length), 2)
        station = {'shop': 'SUPPLY SIGNAL', 'ranked': 'ARENA SIGNAL',
                   'rivals': 'TAMER FREQUENCY', 'activity': 'NETWORK FREQUENCY',
                   'lab': 'DIGILAB SIGNAL', 'scan': 'SCAN FREQUENCY', 'dex': 'ARCHIVE SIGNAL',
                   'party': 'PARTNER LINK', 'evolution': 'EVOLUTION SIGNAL', 'storage': 'STORAGE LINK',
                   'maps': 'WORLD FREQUENCY', 'skills': 'TACTICAL SIGNAL', 'battle': 'BATTLE LINK',
                   'auth': 'GATEWAY SIGNAL', 'settings': 'SYSTEM FREQUENCY', 'season': 'CAREER SIGNAL'}.get(theme, 'DIGITAL WORLD')
        text(self.screen, self.app.assets, station, (rect.x+67, rect.y+header_height-25),
             9, p['muted'], True, usable-40)
        return pygame.Rect(rect.x+22, rect.y+header_height+20, rect.width-44,
                           max(0, rect.height-header_height-42))

    def _backdrop(self, logical_size, native_size, theme, header_height):
        p = colors(theme)
        result = pygame.Surface(native_size).convert()
        w, h = logical_size
        # Physical scanlines keep the gradient native at any UI scale.
        for y in range(native_size[1]):
            fraction = y/max(1, native_size[1]-1)
            color = _mix(p['panel'], p['ink'], min(1., fraction*2.1))
            pygame.draw.line(result, color, (0, y), (native_size[0], y))
        c = NativeCanvas(result, self.scale)
        self._circuits(c, pygame.Rect(0, 0, w, h), _mix(p['ink'], p['line'], .15),
                       _mix(p['ink'], p['line'], .20))
        # Asymmetrical cinematic hero; the content area remains quiet/readable.
        draw.polygon(c, p['glow'], [(w*.43, 0), (w, 0), (w, header_height), (w*.57, header_height)])
        draw.polygon(c, _mix(p['glow'], p['ink'], .4), [(w*.68, 0), (w, 0), (w, header_height), (w*.54, header_height)])
        texture_crop = (0, 32, 256, 160) if p['grid'] == 'm_bg04.png' else (0, 0, 256, 192)
        self._stamp(c, p['grid'], (w-430, 0, 430, header_height), texture_crop, 25)
        for x in range(22, max(22, w-20), 28):
            draw.line(c, _mix(p['line'], p['ink'], .45), (x, h-11), (x+9, h-11), 1)
        # Cropped hero art contains characters only, with no old-game logos/text.
        if theme in ('activity', 'lab', 'scan', 'evolution'):
            draw.circle(c, p['line'], (w-195, 67), 57, 1)
            draw.circle(c, p['accent'], (w-195, 67), 48, 1)
            self._stamp(c, 'm_bg03.png', (w-266, 6, 144, 121), (19, 0, 225, 192), 60,
                        (90, 255, 188) if theme == 'activity' else p['accent'])
        self._header_art(c, w, header_height, theme)
        if theme in ('ranked', 'season'):
            self.icon(pygame.Rect(w-360, 34, 66, 66), 'crown', theme, screen=c)
        elif theme == 'shop':
            self.icon(pygame.Rect(w-360, 34, 66, 66), 'shop', theme, screen=c)
        elif theme == 'rivals':
            self.icon(pygame.Rect(w-360, 34, 66, 66), 'versus', theme, screen=c)
        elif theme not in ('activity', 'shop', 'ranked', 'rivals'):
            self.icon(pygame.Rect(w-360, 34, 66, 66), theme, theme, screen=c)
        draw.line(c, p['line'], (1, header_height), (w-2, header_height), 1)
        draw.line(c, p['accent'], (22, header_height), (145, header_height), 2)
        draw.line(c, p['secondary'], (149, header_height), (195, header_height), 2)
        draw.line(c, p['line'], (22, h-25), (w-22, h-25), 1)
        draw.rect(c, p['line'], (0, 0, w, h), 1, border_radius=15)
        draw.line(c, p['secondary'] if theme == 'shop' else p['accent'], (15, 1), (w-16, 1), 2)
        draw.lines(c, p['accent'], False, [(1, 24), (1, 14), (13, 1), (68, 1)], 2)
        draw.lines(c, p['secondary'], False, [(w-68, h-1), (w-13, h-1), (w-1, h-14), (w-1, h-24)], 2)
        return result

    def card(self, rect, theme='rivals', selected=False, accent=False):
        rect = pygame.Rect(rect)
        p = colors(theme)
        cut = min(12, rect.height//4)
        points = [(rect.x, rect.y), (rect.right-cut, rect.y), (rect.right, rect.y+cut),
                  (rect.right, rect.bottom), (rect.x+cut, rect.bottom), (rect.x, rect.bottom-cut)]
        draw.polygon(self.screen, _mix(p['panel'], p['glow'], .40) if selected else p['panel'], points)
        draw.polygon(self.screen, p['accent'] if selected else p['line'], points, 1)
        if selected or accent:
            draw.line(self.screen, p['accent'], (rect.x+1, rect.y+10), (rect.x+1, rect.bottom-cut-2), 3)
        draw.line(self.screen, _mix(p['line'], p['accent'], .18),
                  (rect.x+12, rect.y+1), (rect.x+min(48, rect.width-14), rect.y+1), 1)

    def metric(self, rect, label, value, detail='', theme='rivals'):
        rect = pygame.Rect(rect)
        p = colors(theme)
        self.card(rect, theme, accent=True)
        text(self.screen, self.app.assets, label.upper(), (rect.x+16, rect.y+11), 10,
             p['muted'], True, rect.width-32)
        text(self.screen, self.app.assets, value, (rect.x+15, rect.y+29),
             27 if rect.height >= 82 else 20, p['accent'], True, rect.width-30)
        if detail and rect.height >= 82:
            text(self.screen, self.app.assets, detail, (rect.x+16, rect.bottom-22), 10,
                 p['muted'], False, rect.width-32)

    def badge(self, rect, label, theme='rivals'):
        rect = pygame.Rect(rect)
        p = colors(theme)
        draw.rect(self.screen, _mix(p['accent'], p['ink'], .85), rect, border_radius=4)
        draw.rect(self.screen, _mix(p['accent'], p['ink'], .56), rect, 1, border_radius=4)
        text(self.screen, self.app.assets, label, rect.center, 10, p['accent'], True,
             rect.width-12, True)

    def art(self, rect, kind='rivals', alpha=255):
        """Optional clean hero-character art for secondary feature cards."""
        self._check_display()
        clean = {'shop': 'shopkeeper.png', 'ranked': 'geogreymon_title.png',
                 'rivals': 'lunamon_title.png', 'activity': 'dawn_tamer_girl.png',
                 'lab': 'sunflowmon_title.png', 'scan': 'lunamon_title.png',
                 'dex': 'gaogamon_title.png', 'party': 'dawn_tamer_boy.png',
                 'evolution': 'geogreymon_title.png', 'storage': 'dawn_tamer_girl.png',
                 'maps': 'lalamon_title.png', 'skills': 'coronamon_title.png',
                 'battle': 'geogreymon_title.png', 'auth': 'dawn_tamer_boy.png',
                 'settings': 'dusk_tamer_boy.png'}
        if self._stamp_fit(self.screen, 'assets/ui/extracted/'+clean.get(kind, 'lunamon_title.png'), rect, alpha):
            return
        rect = pygame.Rect(rect)
        w = min(rect.width, round(rect.height*256/192))
        h = min(rect.height, round(w*192/256))
        fitted = pygame.Rect(0, 0, w, h)
        fitted.center = rect.center
        self._stamp(self.screen, colors(kind)['character'], fitted, (0, 0, 256, 192), alpha)

    def icon(self, rect, kind='radar', theme='rivals', *, screen=None):
        """Sharp native line emblems, avoiding whole atlas sheets and old labels."""
        screen = screen if screen is not None else self.screen
        rect = pygame.Rect(rect)
        p = colors(theme)
        def point(x, y):
            return rect.x+rect.width*x, rect.y+rect.height*y
        stroke = max(1, round(min(rect.size)/28))
        if kind in ('ranked', 'crown'):
            draw.polygon(screen, p['glow'], [point(.1,.25),point(.30,.44),point(.5,.13),point(.70,.44),point(.9,.25),point(.79,.74),point(.21,.74)])
            draw.lines(screen, p['accent'], True, [point(.1,.25),point(.30,.44),point(.5,.13),point(.70,.44),point(.9,.25),point(.79,.74),point(.21,.74)], stroke)
            draw.line(screen, p['accent'], point(.21,.86), point(.79,.86), stroke)
            draw.circle(screen, p['secondary'], point(.5,.57), max(2,rect.width*.045))
        elif kind in ('shop', 'bag'):
            draw.lines(screen, p['accent'], True, [point(.20,.35),point(.80,.35),point(.86,.85),point(.14,.85)],stroke)
            draw.arc(screen, p['secondary'], (rect.x+rect.width*.34,rect.y+rect.height*.13,rect.width*.32,rect.height*.43), 0, math.pi, stroke)
            draw.line(screen, p['accent'],point(.5,.48),point(.5,.72),stroke)
            draw.line(screen, p['accent'],point(.38,.60),point(.62,.60),stroke)
        elif kind in ('rivals', 'versus'):
            draw.lines(screen, p['accent'], False, [point(.12,.17),point(.43,.48),point(.12,.81)],stroke)
            draw.lines(screen, p['secondary'], False,[point(.88,.17),point(.57,.48),point(.88,.81)],stroke)
            draw.line(screen,p['accent'],point(.63,.10),point(.37,.90),stroke)
        elif kind == 'lab':
            draw.lines(screen, p['accent'], False,
                       [point(.36,.13),point(.36,.42),point(.15,.78),point(.22,.88),
                        point(.78,.88),point(.85,.78),point(.64,.42),point(.64,.13)], stroke)
            draw.line(screen, p['accent'], point(.27,.12), point(.73,.12), stroke)
            draw.line(screen, p['secondary'], point(.25,.66), point(.75,.66), stroke)
            for x,y in ((.45,.52),(.57,.75),(.36,.79)):
                draw.circle(screen,p['secondary'],point(x,y),max(1,rect.width*.025))
        elif kind == 'scan':
            for sx,sy in ((1,1),(-1,1),(1,-1),(-1,-1)):
                draw.lines(screen,p['accent'],False,
                           [point(.5+sx*.22,.5+sy*.36),point(.5+sx*.36,.5+sy*.36),
                            point(.5+sx*.36,.5+sy*.22)],stroke)
            draw.circle(screen,p['secondary'],point(.5,.5),min(rect.size)*.20,stroke)
            draw.line(screen,p['accent'],point(.12,.51),point(.88,.51),stroke)
        elif kind == 'dex':
            draw.lines(screen,p['accent'],True,
                       [point(.10,.20),point(.30,.15),point(.5,.25),point(.70,.15),
                        point(.90,.20),point(.90,.80),point(.70,.75),point(.5,.85),
                        point(.30,.75),point(.10,.80)],stroke)
            draw.line(screen,p['accent'],point(.5,.25),point(.5,.85),stroke)
            for y in (.36,.51,.66):
                draw.line(screen,p['secondary'],point(.19,y),point(.39,y+.02),stroke)
                draw.line(screen,p['secondary'],point(.61,y+.02),point(.81,y),stroke)
        elif kind == 'party':
            for x,y,color in ((.65,.32,p['secondary']),(.35,.39,p['accent'])):
                draw.circle(screen,color,point(x,y),min(rect.size)*.13,stroke)
                body=(rect.x+rect.width*(x-.20),rect.y+rect.height*(y+.18),rect.width*.40,rect.height*.31)
                draw.arc(screen,color,body,0,math.pi,stroke)
                draw.line(screen,color,point(x-.2,y+.34),point(x+.2,y+.34),stroke)
        elif kind == 'evolution':
            draw.lines(screen,p['accent'],True,[point(.5,.12),point(.76,.43),point(.5,.77),point(.24,.43)],stroke)
            draw.lines(screen,p['secondary'],False,[point(.15,.69),point(.15,.90),point(.36,.90)],stroke)
            draw.lines(screen,p['secondary'],False,[point(.64,.06),point(.85,.06),point(.85,.27)],stroke)
            draw.line(screen,p['secondary'],point(.15,.9),point(.40,.65),stroke)
            draw.line(screen,p['secondary'],point(.85,.06),point(.62,.29),stroke)
        elif kind == 'storage':
            for y in (.13,.40,.67):
                box=(rect.x+rect.width*.16,rect.y+rect.height*y,rect.width*.68,rect.height*.20)
                draw.rect(screen,p['accent'],box,stroke,border_radius=2)
                draw.line(screen,p['secondary'],point(.42,y+.10),point(.58,y+.10),stroke)
        elif kind == 'maps':
            draw.lines(screen,p['accent'],True,
                       [point(.12,.24),point(.36,.12),point(.65,.24),point(.88,.12),
                        point(.88,.76),point(.65,.88),point(.36,.76),point(.12,.88)],stroke)
            draw.line(screen,p['secondary'],point(.36,.12),point(.36,.76),stroke)
            draw.line(screen,p['secondary'],point(.65,.24),point(.65,.88),stroke)
            draw.circle(screen,p['accent'],point(.65,.48),min(rect.size)*.10,stroke)
        elif kind in ('skills','battle'):
            draw.lines(screen,p['accent'],False,
                       [point(.14,.85),point(.33,.66),point(.24,.57),point(.81,.12),
                        point(.89,.20),point(.44,.77),point(.34,.68)],stroke)
            draw.line(screen,p['secondary'],point(.23,.44),point(.65,.86),stroke)
            if kind == 'battle':
                draw.lines(screen,p['secondary'],False,
                           [point(.86,.85),point(.67,.66),point(.76,.57),point(.19,.12),
                            point(.11,.20),point(.56,.77),point(.66,.68)],stroke)
                draw.line(screen,p['accent'],point(.77,.44),point(.35,.86),stroke)
            else:
                draw.lines(screen,p['secondary'],False,[point(.2,.08),point(.2,.31)],stroke)
                draw.line(screen,p['secondary'],point(.09,.2),point(.31,.2),stroke)
        elif kind == 'auth':
            draw.lines(screen,p['accent'],False,
                       [point(.42,.87),point(.19,.87),point(.19,.12),point(.81,.12),point(.81,.87),point(.58,.87)],stroke)
            draw.lines(screen,p['secondary'],False,[point(.39,.38),point(.57,.55),point(.39,.72)],stroke)
            draw.line(screen,p['secondary'],point(.08,.55),point(.57,.55),stroke)
        elif kind == 'settings':
            center=rect.center
            radius=min(rect.size)*.28
            draw.circle(screen,p['accent'],center,radius,stroke)
            draw.circle(screen,p['secondary'],center,radius*.40,stroke)
            for i in range(8):
                angle=i*math.pi/4
                draw.line(screen,p['accent'],
                          (center[0]+math.cos(angle)*radius,center[1]+math.sin(angle)*radius),
                          (center[0]+math.cos(angle)*radius*1.4,center[1]+math.sin(angle)*radius*1.4),stroke+1)
        else:
            center=rect.center
            radius=max(2,min(rect.size)*.40)
            draw.circle(screen,p['line'],center,radius,stroke)
            draw.circle(screen,p['accent'],center,radius*.62,stroke)
            draw.line(screen,p['secondary'],center,point(.77,.21),stroke)
            for x,y in ((.3,.35),(.69,.62),(.34,.75)):
                draw.circle(screen,p['accent'],point(x,y),max(2,rect.width*.025))

    def capsule(self, rect, resource='hp', quality=1, theme='shop'):
        """A crisp two-tone recovery capsule, composed once at the real DPI."""
        self._check_display()
        rect = pygame.Rect(rect)
        native = self.screen.to_physical_rect(rect) if isinstance(self.screen, NativeCanvas) else rect
        if min(native.size) < 4:
            return
        kind = str(resource).lower()
        color = (250, 152, 184) if 'hp' in kind or 'health' in kind else (83, 219, 239)
        if 'reviv' in kind:
            color = (249, 203, 115)
        count = max(1, min(3, int(quality or 1)))
        key = 'capsule', native.size, color, count, theme
        rendered = self._get(key)
        if rendered is None:
            rendered = pygame.Surface(native.size, pygame.SRCALPHA)
            w, h = native.size
            cx, cy = w//2, h//2
            p = colors(theme)
            pygame.draw.circle(rendered, (*p['glow'], 100), (cx, cy), max(2, min(w,h)//2-1))
            pygame.draw.ellipse(rendered, (3, 10, 22, 115), (cx-w*.23, h*.78, w*.53, h*.12))
            bw, bh = max(8, round(w*.32)), max(16, round(h*.76))
            stroke = max(1, round(self.scale))
            pill = pygame.Surface((bw+4*stroke, bh+4*stroke), pygame.SRCALPHA)
            body = pygame.Rect(2*stroke, 2*stroke, bw, bh)
            pygame.draw.rect(pill, (193, 216, 231), body, border_radius=bw//2)
            inside = body.inflate(-2*stroke, -2*stroke)
            pygame.draw.rect(pill, (218, 236, 244), inside, border_radius=bw//2)
            pill.set_clip((0, 0, pill.get_width(), body.centery))
            pygame.draw.rect(pill, color, inside, border_radius=bw//2)
            pill.set_clip(None)
            pygame.draw.line(pill, (168, 204, 220), (inside.left, body.centery),
                             (inside.right-1, body.centery), stroke)
            pygame.draw.line(pill, (251, 252, 255), (inside.left+2*stroke, inside.y+bw//3),
                             (inside.left+2*stroke, inside.bottom-bw//3), stroke)
            mx, my = body.centerx, body.y+round(bh*.73)
            cross = max(2, round(bw*.16))
            pygame.draw.line(pill, (55, 92, 117), (mx-cross, my), (mx+cross, my), 2*stroke)
            pygame.draw.line(pill, (55, 92, 117), (mx, my-cross), (mx, my+cross), 2*stroke)
            angled = pygame.transform.rotate(pill, -29)
            rendered.blit(angled, angled.get_rect(center=(cx, cy-2*stroke)))
            for index in range(count):
                pygame.draw.circle(rendered, color, (round(cx+(index-(count-1)/2)*7*self.scale),
                                                     h-3*stroke), max(1, stroke))
            self._remember(key, rendered)
        if isinstance(self.screen, NativeCanvas):
            self.screen.blit_native(rendered, rect.topleft)
        else:
            self.screen.blit(rendered, rect.topleft)
