"""Native account gateway and partner selection in the shared in-game style."""
from __future__ import annotations
import math
import pygame
from .render import draw
from .widgets import GOLD, LIME, WHITE, text, wrap


class EntryScreen:
    def __init__(self, app):
        self.app = app
        self._overlay = None

    def _button(self, rect, label, callback, **kwargs):
        self.app.ui.button(rect, label, callback,
                           accent=self.app.presentation.colors('auth')['accent'], **kwargs)

    def _close_picker(self):
        app = self.app
        app.auth_picker = None
        app.ui.focus = None
        app.ui.actions, app.ui.fields = [], []
        pygame.key.stop_text_input()

    def _tab(self, value):
        self.app.auth_tab = value
        self.app.ui.actions, self.app.ui.fields = [], []

    def _tamer(self, rect, ident):
        """Enlarge the actual selected frame; field-scale caps do not suit cards."""
        entry = self.app.assets.tamers.get(ident, {})
        frames = entry.get('frames', {}).get('down', [])
        if isinstance(frames, str):
            frames = [frames]
        if not frames:
            return
        durations = entry.get('frame_seconds', {}).get('down', [.133333]*len(frames))
        phase = self.app.now % max(.01, sum(durations))
        index = 0
        for index, duration in enumerate(durations):
            phase -= duration
            if phase < 0:
                break
        self.app.presentation.image(rect, frames[min(index, len(frames)-1)])

    def draw(self):
        app, screen, assets, art = self.app, self.app.screen, self.app.assets, self.app.presentation
        w, h = screen.get_size()
        p = art.colors('auth')
        hero = pygame.Rect(36, 42, w-578, h-84)
        account = pygame.Rect(hero.right+20, hero.y, 486, hero.height)
        art.card(hero, 'auth', accent=True)
        art.card(account, 'auth', accent=True)
        cyber = getattr(app, 'cyber', None)
        if cyber:
            cyber.rain(hero, 'auth')
        old_clip = screen.get_clip()
        screen.set_clip(hero.clip(old_clip))
        self._hero(hero)
        screen.set_clip(old_clip)
        x, y, width = account.x+28, account.y+24, account.width-56
        text(screen, assets, 'TAMER GATEWAY  /  VENOM NXT', (x, y), 10, p['accent'], True)
        text(screen, assets, 'Welcome, Tamer.', (x, y+24), 30, WHITE, True)
        text(screen, assets, 'Your next adventure is waiting.', (x, y+64), 13, p['muted'])
        for index, (key, label) in enumerate((('login', 'Sign in'), ('register', 'Create account'))):
            self._button((x+index*(width+10)//2, y+99, (width-10)//2, 40), label,
                         lambda value=key: self._tab(value), selected=app.auth_tab == key,
                         disabled=app.auth_pending)
        text(screen, assets, 'USERNAME', (x, y+161), 10, p['muted'], True)
        app.ui.field((x, y+180, width, 44), 'username', 'Your tamer username', size=17)
        text(screen, assets, 'PASSWORD', (x, y+241), 10, p['muted'], True)
        app.ui.field((x, y+260, width, 44), 'password', 'At least 8 characters', password=True, size=17)
        next_y = y+327
        if app.auth_tab == 'register':
            for index, (kind, label, ident) in enumerate((('tamer', 'TAMER APPEARANCE', app.tamer),
                                                        ('starter', 'ROOKIE PARTNER', app.starter))):
                choice = pygame.Rect(x+index*(width+10)//2, next_y, (width-10)//2, 101)
                art.card(choice, 'auth')
                text(screen, assets, label, (choice.x+11, choice.y+10), 9, p['muted'], True)
                entry = assets.tamers.get(ident, {}) if kind == 'tamer' else assets.species.get(ident, {})
                portrait = pygame.Rect(choice.x+12, choice.y+31, 53, 61)
                if kind == 'tamer':
                    self._tamer(portrait, ident)
                else:
                    art.sprite(portrait, ident, now=app.now)
                self._button((choice.x+70, choice.y+35, choice.width-80, 53),
                             entry.get('name', 'Select'), lambda value=kind: app.open_picker(value),
                             small=True, disabled=app.auth_pending)
            next_y += 117
        self._button((x, next_y, width, 45),
                     'Connecting…' if app.auth_pending else 'Enter the Digital World' if app.auth_tab == 'login' else 'Begin your adventure',
                     app.auth, primary=True,
                     disabled=app.auth_pending or not (app.connection and app.connection.connected))
        wrap(screen, assets, app.status, (x, next_y+57), width, 12, p['muted'], 3)
        bottom = account.bottom-55
        draw.line(screen, p['line'], (x, bottom-16), (x+width, bottom-16))
        self._button((x, bottom, 122, 30), 'Reconnect', app.connect, small=True, disabled=app.auth_pending)
        connected = bool(app.connection and app.connection.connected)
        status = 'LOCAL DEVELOPMENT' if app.args.dev else 'TLS VERIFIED' if connected else 'TLS REQUIRED'
        draw.circle(screen, LIME if connected else GOLD, (x+145, bottom+15), 3)
        text(screen, assets, status, (x+158, bottom+9), 10, p['accent'], True, width-158)
        if app.auth_picker:
            self.draw_picker()

    def _hero(self, rect):
        app, screen, assets, art = self.app, self.app.screen, self.app.assets, self.app.presentation
        p = art.colors('auth')
        x, y = rect.x+28, rect.y+28
        width = rect.width-56
        text(screen, assets, 'THE DIGITAL WORLD IS CALLING', (x, y), 10, p['accent'], True, width)
        text(screen, assets, 'DIGIMON', (x-3, y+31), 52, WHITE, True, width)
        text(screen, assets, 'VENOM NXT', (x-2, y+91), 46, LIME, True, width)
        text(screen, assets, 'Make the connection.', (x, y+158), 24, WHITE, True, width)
        text(screen, assets, 'Find your next evolution.', (x, y+191), 19, p['muted'], True, width)
        wrap(screen, assets, 'Your partner. Your crew. Explore a living Digital World and build a team worth believing in.',
             (x, y+235), width, 14, p['muted'], 3)
        floor = rect.bottom-157
        center = (rect.centerx+int(rect.width*.12), floor-62)
        radius = min(150, max(69, int(rect.width*.18)), int((rect.height-370)*.43))
        for factor, color in ((1.0, p['line']), (.85, p['accent']), (.68, p['line'])):
            draw.circle(screen, color, center, radius*factor, 1)
        for index in range(24):
            angle = index*math.tau/24
            a = (center[0]+math.cos(angle)*radius, center[1]+math.sin(angle)*radius)
            b = (center[0]+math.cos(angle)*(radius-7), center[1]+math.sin(angle)*(radius-7))
            draw.line(screen, p['line'] if index % 3 else p['accent'], a, b, 2)
        for index in range(6):
            fy = floor-11+index*12
            draw.line(screen, (26, 58, 70), (x, fy), (rect.right-28, fy))
        for index in range(-4, 5):
            draw.line(screen, (26, 58, 70), (center[0]+index*17, floor-11),
                      (center[0]+index*62, floor+49))
        entries = [ident for ident in (app.starter, 'patamon', 'gabumon') if ident in assets.species]
        if len(entries) < 3:
            entries += [s['id'] for s in assets.species.values()
                        if s.get('stage') == 'rookie' and not s.get('paradox') and s['id'] not in entries][:3-len(entries)]
        partner_width = min(220, max(148, int(rect.width*.25)))
        companion_width = min(102, max(78, int(rect.width*.115)))
        positions = ((rect.centerx-52, floor+26, (partner_width, round(partner_width*1.09))),
                     (rect.right-99, floor-23, (companion_width, round(companion_width*1.1))),
                     (rect.x+80, floor-11, (companion_width, round(companion_width*1.1))))
        for index, (ident, (px, py, box)) in enumerate(zip(entries, positions)):
            py += math.sin(app.now*1.35+index)*3
            draw.ellipse(screen, (6, 18, 27), (px-box[0]*.30, py-5, box[0]*.60, 15))
            sprite = assets.sprite(ident, box, now=app.now)
            if sprite:
                screen.blit(sprite, sprite.get_rect(midbottom=(px, py)))
        info = pygame.Rect(x, rect.bottom-96, width, 42)
        draw.line(screen, p['line'], info.topleft, info.topright)
        gap = width//3
        for index, (value, label) in enumerate((('06', 'PARTNER SLOTS'), ('3 vs 3', 'TEAM BATTLES'), ('NXT', 'DIGITAL WORLD'))):
            fx = x+index*gap
            text(screen, assets, value, (fx, info.y+11), 17, LIME if index == 0 else WHITE, True)
            text(screen, assets, label, (fx, info.y+35), 8, p['muted'], True, gap-10)
        self._button((x, rect.bottom-36, 131, 25), 'Settings  F10', app.toggle_settings, small=True)
        text(screen, assets, 'F11 / FULLSCREEN', (x+148, rect.bottom-29), 9, p['muted'], True, width-148)

    def draw_picker(self):
        app, screen, assets, art = self.app, self.app.screen, self.app.assets, self.app.presentation
        app.ui.actions, app.ui.fields = [], []
        if self._overlay is None or self._overlay.get_size() != screen.surface.get_size():
            self._overlay = pygame.Surface(screen.surface.get_size(), pygame.SRCALPHA)
            self._overlay.fill((3, 8, 17, 238))
        screen.blit_native(self._overlay, (0, 0))
        w, h = screen.get_size()
        rect = pygame.Rect(48, 35, w-96, h-70)
        kind = app.auth_picker
        p = art.colors('auth')
        body = art.shell(rect, 'auth', 'Choose your tamer' if kind == 'tamer' else 'Choose your rookie partner',
                         'Choose the appearance that feels like you.' if kind == 'tamer' else 'Every adventure starts with a partner. Make your first connection.',
                         'NEW TAMER  /  IDENTITY' if kind == 'tamer' else 'NEW TAMER  /  PARTNER LINK', header_height=128)
        self._button((body.right-82, body.y, 82, 36), 'Close', self._close_picker, small=True)
        app.ui.field((body.x, body.y, body.width-96, 36), 'search',
                     'Search all available appearances…' if kind == 'tamer' else 'Search rookie partners…', size=15)
        query = app.ui.values.get('search', '').lower()
        entries = list(assets.tamers.values()) if kind == 'tamer' else [s for s in assets.species.values() if s.get('stage') == 'rookie' and not s.get('paradox')]
        entries = [entry for entry in entries if query in entry['name'].lower()]
        grid = pygame.Rect(body.x, body.y+55, body.width, body.height-98)
        columns = max(4, min(7, (grid.width+12)//172))
        rows = max(1, grid.height//178)
        width = (grid.width-12*(columns-1))//columns
        height = min(206, (grid.height-12*(rows-1))//rows)
        app.scroll = max(0, min(app.scroll, max(0, math.ceil(len(entries)/columns)-rows)))
        for index, entry in enumerate(entries[app.scroll*columns:(app.scroll+rows)*columns]):
            cell = pygame.Rect(grid.x+index%columns*(width+12), grid.y+index//columns*(height+12), width, height)
            selected = entry['id'] == (app.tamer if kind == 'tamer' else app.starter)
            art.card(cell, 'auth', selected=selected)
            text(screen, assets, 'SELECTED' if selected else 'TAMER' if kind == 'tamer' else 'ROOKIE',
                 (cell.x+12, cell.y+11), 8, p['accent'] if selected else p['muted'], True)
            portrait_h = cell.height-71
            draw.ellipse(screen, (6, 17, 27), (cell.centerx-32, cell.bottom-60, 64, 14))
            portrait = pygame.Rect(cell.x+18, cell.y+24, cell.width-36, portrait_h)
            if kind == 'tamer':
                self._tamer(portrait, entry['id'])
                wrap(screen, assets, entry['name'], (cell.x+12, cell.bottom-42), cell.width-24,
                     12, WHITE, 2)
            else:
                art.sprite(portrait, entry['id'], now=app.now)
                text(screen, assets, entry['name'], (cell.centerx, cell.bottom-31), 14, WHITE, True, cell.width-18, True)
                text(screen, assets, str(entry.get('type', 'Rookie')).upper(), (cell.centerx, cell.bottom-12), 8, p['muted'], False, cell.width-18, True)
            def pick(ident=entry['id']):
                if kind == 'tamer':
                    app.tamer = ident
                else:
                    app.starter = ident
                self._close_picker()
            app.ui.actions.append((cell, pick))
        if not entries:
            text(screen, assets, 'No matching appearances.' if kind == 'tamer' else 'No matching rookie partners.', grid.center, 20, WHITE, True, center=True)
            text(screen, assets, 'Try a different name.', (grid.centerx, grid.centery+34), 13, p['muted'], center=True)
        footer_y = body.bottom-25
        text(screen, assets, f'{len(entries)} available · Mouse wheel to browse', (body.x, footer_y+7), 11, p['muted'])
        self._button((body.right-184, footer_y, 87, 29), 'Previous',
                     lambda: setattr(app, 'scroll', max(0, app.scroll-rows)), small=True, disabled=app.scroll == 0)
        self._button((body.right-87, footer_y, 87, 29), 'Next',
                     lambda: setattr(app, 'scroll', app.scroll+rows), small=True,
                     disabled=(app.scroll+rows)*columns >= len(entries))
