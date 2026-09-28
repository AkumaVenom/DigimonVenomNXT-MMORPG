"""Shared field chrome; native UI cards retain the original world renderer."""
from __future__ import annotations
import pygame
import math
import time
from .render import draw
from .widgets import text, bar, panel, WHITE, MUTED, CYAN, LIME, GOLD, RED
from .world import player_title
from venom.version import VERSION


class GameHUD:
    def __init__(self, app):
        self.app = app

    def header(self):
        app, screen, art = self.app, self.app.screen, self.app.presentation
        w = screen.get_width()
        accent = art.colors('party')['accent']
        season = bool(app.state.get('in_season'))
        story = bool(app.state.get('in_story'))
        jailed = bool(app.state.get('admin_jail'))
        draw.rect(screen, (9, 20, 34), (0, 0, w, 92))
        draw.line(screen, (31, 61, 77), (0, 75), (w, 75))
        draw.line(screen, CYAN, (22, 75), (179, 75), 2)
        app.ui.button((22, 18, 156, 37), 'Home · DigiFarm', app.enter_farm,
                      selected=bool(app.state.get('in_farm')) and not app.menu,
                      small=True, accent=LIME, disabled=app.action_pending or season or jailed or story and bool(app.state.get('battle')))
        text(screen, app.assets, f'VENOM NXT / v{VERSION}', (25, 3), 9, MUTED, True)
        tabs = [('dex', 'DigiDex'), ('party', 'Partners'), ('shop', 'Shop'), ('maps', 'Story atlas' if story else 'Worlds')]
        battle = bool(app.state.get('battle'))
        for i, (key, label) in enumerate(tabs):
            app.ui.button((210+i*101, 18, 96, 37), label, lambda k=key:app.set_menu(k),
                          selected=app.menu==key or key=='dex' and app.menu=='scan',
                          small=True, accent=CYAN, disabled=battle or season or jailed)
        app.ui.button((625, 18, 91, 37), 'Settings', app.toggle_settings,
                      selected=app.settings_open, small=True, accent=CYAN)
        app.ui.button((w-430, 16, 147, 41), 'DigiLab  F1', app.enter_lab,
                      primary=True, accent=LIME, disabled=battle or season or jailed or app.action_pending)
        text(screen, app.assets, f"{app.state.get('credits', 0):,} ¥", (w-263, 13), 19, GOLD, True, 131)
        text(screen, app.assets, app.state.get('username', ''), (w-263, 39), 11, MUTED, max_width=124)
        title = player_title(app.state.get('active_title'))
        if title:
            text(screen, app.assets, title, (w-263, 55), 9, GOLD, True, max_width=131)
        app.ui.button((w-128, 15, 42, 40), '♪' if app.audio.enabled else '♫', app.audio.toggle, accent=CYAN)
        app.ui.button((w-77, 15, 55, 40), 'Exit', app.logout, small=True, accent=CYAN)
        for i, (key, label) in enumerate((('ranked','Ranked Arena  R'),('rivals','Rivals Hub  V'),('activity','Bot Activity  O'))):
            app.ui.button((22+i*148, 65, 138, 23), label,
                          lambda value=key:app.community.open(value), small=True,
                          selected=app.menu=='community' and app.community.tab==key,
                          accent=art.colors(key)['accent'], disabled=battle or season or story or jailed)
        app.ui.button((466, 65, 187, 23), 'Return to World  F3' if season else 'Season Mode  F3',
                      app.season_screen.toggle, small=True, selected=season, accent=(105, 229, 255),
                      disabled=app.action_pending or battle or story or jailed)
        app.ui.button((665, 65, 187, 23), 'Return to MMO  F4' if story else 'Story Mode  F4',
                      app.story_screen.toggle, small=True, selected=story, accent=(115, 230, 224),
                      disabled=app.action_pending or battle or season or jailed)
        app.ui.button((864, 65, 151, 23), f'Server notices  {len(app.server_notices)}',
                      app.toggle_notices, small=True, accent=CYAN, selected=app.notice_history_open)
        status_x = max(1027, w-223)
        text(screen, app.assets, 'LINK  /  '+('DETAINED' if jailed else 'SOLO SEASON' if season else 'STORY MODE' if story else 'DIGIFARM' if app.state.get('in_farm') else 'DIGILAB' if app.state.get('in_lab') else 'BATTLE' if battle else 'FIELD'),
             (status_x, 71), 9, accent, True, max_width=max(0, w-22-status_x))

    def party(self, rect):
        app, art, rect = self.app, self.app.presentation, pygame.Rect(rect)
        palette = art.colors('party')
        art.card(rect, 'party')
        text(app.screen, app.assets, 'PARTNER LINK', (rect.x+18, rect.y+16), 12, palette['accent'], True)
        party = app.state.get('party', [])[:6]
        text(app.screen, app.assets, f'{len(party)} / 6', (rect.right-55, rect.y+16), 12, MUTED)
        draw.line(app.screen, palette['line'], (rect.x+15, rect.y+38), (rect.right-15, rect.y+38))
        height = min(92, (rect.height-100)//6)
        app.selected_party = max(0, min(app.selected_party, max(0,len(party)-1)))
        for index in range(6):
            cell=pygame.Rect(rect.x+12, rect.y+49+index*(height+5), rect.width-24, height)
            art.card(cell, 'party', selected=index==app.selected_party and index<len(party))
            if index>=len(party):
                text(app.screen, app.assets, f'0{index+1}  /  OPEN LINK', cell.center, 10, (82,107,127), center=True)
                continue
            mon=party[index]
            sprite=app.assets.sprite(mon['species_id'], (62,height-15), now=app.now)
            if sprite:app.screen.blit(sprite,sprite.get_rect(center=(cell.x+38,cell.centery)))
            x=cell.x+77
            text(app.screen,app.assets,mon['name'],(x,cell.y+8),14,WHITE,True,cell.width-85)
            role='LEAD' if index==0 else 'ACTIVE' if index<3 else 'RESERVE'
            text(app.screen,app.assets,f"Lv.{mon['level']}  /  {role}",(x,cell.y+28),9,palette['accent'] if index<3 else MUTED)
            bar(app.screen,pygame.Rect(x,cell.y+46,cell.width-91,5),mon.get('hp',0),mon.get('max_hp',1),LIME)
            bar(app.screen,pygame.Rect(x,cell.y+58,cell.width-91,4),mon.get('sp',0),mon.get('max_sp',1),CYAN)
            if height>=85:
                text(app.screen,app.assets,f"HP {mon.get('hp',0)}/{mon.get('max_hp',0)}  SP {mon.get('sp',0)}",(x,cell.y+70),9,MUTED)
            app.ui.actions.append((cell,lambda i=index:setattr(app,'selected_party',i)))
        app.ui.button((rect.x+13,rect.bottom-43,rect.width-26,30),'Manage partners  P',
                      lambda:app.set_menu('party'),small=True,accent=palette['accent'],disabled=bool(app.state.get('battle') or app.state.get('admin_jail')))

    def feed(self, rect):
        app, rect = self.app, pygame.Rect(rect)
        app.presentation.card(rect, 'activity')
        season = bool(app.state.get('in_season'))
        story = bool(app.state.get('in_story'))
        jailed = bool(app.state.get('admin_jail'))
        text(app.screen,app.assets,'PRIVATE CELL FREQUENCY' if jailed else 'STORY BATTLE LOG' if story else 'SEASON MATCH LOG' if season else 'WORLD FREQUENCY',(rect.x+15,rect.y+9),10,CYAN,True)
        for i,(message,color) in enumerate(app.logs[-3:]):
            text(app.screen,app.assets,message,(rect.x+15,rect.y+30+i*20),12,color,max_width=rect.width-30)
        if (season or story) and not jailed:
            text(app.screen, app.assets, 'Your commands are live. Exit safely saves this battle for later.',
                 (rect.x+15, rect.bottom-25), 11, MUTED, max_width=rect.width-30)
            return
        app.ui.field((rect.x+12,rect.bottom-35,rect.width-89,27),'chat','Message your private cell…' if jailed else 'Enter to chat with your world…',size=13)
        def chat():
            message=app.ui.values.get('chat','').strip()
            if message:
                app.send('chat',text=message)
                app.ui.values['chat']=''
        app.ui.button((rect.right-68,rect.bottom-35,55,27),'Send',chat,small=True,accent=CYAN)

    def _lines(self, value, width, size=14):
        """Wrap notices at rendered widths, including long unbroken words."""
        scale = getattr(self.app.screen, 'scale', 1)
        font = self.app.assets.font(max(1, round(size*scale)))
        limit = max(1, width*scale)
        lines, line = [], ''
        for word in str(value).split():
            candidate = f'{line} {word}'.strip()
            if font.size(candidate)[0] <= limit:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ''
            for char in word:
                if line and font.size(line+char)[0] > limit:
                    lines.append(line)
                    line = ''
                line += char
        if line:
            lines.append(line)
        return lines or ['']

    def _cover(self, rect):
        """A notice must not leave covered gameplay controls clickable."""
        app = self.app
        app.ui.actions = [(area, action) for area, action in app.ui.actions if not rect.colliderect(area)]
        hidden = {key for area, key in app.ui.fields if rect.colliderect(area)}
        app.ui.fields = [(area, key) for area, key in app.ui.fields if not rect.colliderect(area)]
        if app.ui.focus in hidden:
            app.ui.focus = None
            pygame.key.stop_text_input()

    def notices(self):
        app, screen = self.app, self.app.screen
        w, h = screen.get_size()
        if app.notice_history_open:
            # The log remains available after the transient banner expires, even
            # when battle or chat messages have filled the normal activity feed.
            app.ui.actions, app.ui.fields = [], []
            panel(screen, (0, 92, w, h-92), (6, 13, 23), None, 0)
            rect = pygame.Rect(35, 110, w-70, h-140)
            panel(screen, rect, (13, 26, 43), (48, 89, 112), 12)
            text(screen, app.assets, 'SERVER NOTICES', (rect.x+25, rect.y+22), 23, WHITE, True)
            text(screen, app.assets, 'Staff messages received during this session.',
                 (rect.x+25, rect.y+59), 12, MUTED)
            app.ui.button((rect.right-108, rect.y+20, 82, 32), 'Close', app.toggle_notices, small=True)
            entries = list(reversed(app.server_notices))
            app.notice_history_page = max(0, min(app.notice_history_page, max(0, len(entries)-1)))
            if entries:
                notice = entries[app.notice_history_page]
                text(screen, app.assets, notice['label'], (rect.x+25, rect.y+107), 12, notice['color'], True)
                for i, line in enumerate(self._lines(notice['text'], rect.width-55, 15)):
                    text(screen, app.assets, line, (rect.x+25, rect.y+137+i*23), 15, WHITE)
                text(screen, app.assets, f'{app.notice_history_page+1} / {len(entries)}  ·  Newest first',
                     (rect.x+25, rect.bottom-40), 12, MUTED)
                app.ui.button((rect.right-223, rect.bottom-51, 92, 32), 'Newer',
                              lambda: setattr(app, 'notice_history_page', app.notice_history_page-1),
                              disabled=app.notice_history_page == 0, small=True)
                app.ui.button((rect.right-120, rect.bottom-51, 92, 32), 'Older',
                              lambda: setattr(app, 'notice_history_page', app.notice_history_page+1),
                              disabled=app.notice_history_page >= len(entries)-1, small=True)
            else:
                text(screen, app.assets, 'No server notices received yet.', (rect.x+25, rect.y+127), 16, MUTED)
            return
        notice = app.server_notice
        if not notice or app.now >= notice['until']:
            return
        width = min(840, w-60)
        lines = self._lines(notice['text'], width-48, 14)
        rect = pygame.Rect((w-width)//2, 104, width, 78+min(3, len(lines))*21)
        self._cover(rect)
        panel(screen, rect, (13, 28, 44), notice['color'], 10)
        draw.rect(screen, notice['color'], (rect.x+1, rect.y+13, 4, rect.height-26), border_radius=2)
        text(screen, app.assets, notice['label'], (rect.x+22, rect.y+14), 11, notice['color'], True)
        for i, line in enumerate(lines[:3]):
            text(screen, app.assets, line, (rect.x+22, rect.y+37+i*21), 14, WHITE)
        app.ui.button((rect.right-174, rect.bottom-30, 149, 23),
                      'Read full notice' if len(lines)>3 else 'Open notices', app.toggle_notices,
                      small=True, accent=notice['color'])
        app.ui.button((rect.right-45, rect.y+9, 28, 22), '×',
                      lambda: setattr(app, 'server_notice', None), small=True, accent=notice['color'])

    def detainment(self, rect):
        app, rect = self.app, pygame.Rect(rect)
        jail = app.state.get('admin_jail') or {}
        cell = pygame.Rect(rect.x, rect.y, rect.width, rect.height-149)
        app.presentation.card(cell, 'party')
        draw.line(app.screen, GOLD, (cell.x+24, cell.y+2), (cell.x+230, cell.y+2), 3)
        text(app.screen, app.assets, 'PRIVATE DETENTION', (cell.x+28, cell.y+25), 11, GOLD, True)
        text(app.screen, app.assets, 'Your adventure is paused', (cell.x+28, cell.y+52), 27, WHITE, True)
        until = jail.get('until')
        if isinstance(until, (int, float)) and math.isfinite(until):
            remaining = max(0, math.ceil(until-time.time()))
            days, seconds = divmod(remaining, 86400)
            hours, seconds = divmod(seconds, 3600)
            minutes, seconds = divmod(seconds, 60)
            duration = (f'{days}d ' if days else '') + f'{hours:02}:{minutes:02}:{seconds:02}'
            release = f'Release in {duration}' if remaining else 'Awaiting release from the server'
        else:
            release = 'Release requires a server administrator'
        text(app.screen, app.assets, release, (cell.x+28, cell.y+101), 15, GOLD, True)
        text(app.screen, app.assets, 'REASON', (cell.x+28, cell.y+144), 10, MUTED, True)
        reason = ' '.join(str(jail.get('reason') or 'Please wait for a server administrator.').split())[:500]
        lines = self._lines(reason, cell.width-280, 15)
        for i, line in enumerate(lines[:5]):
            text(app.screen, app.assets, line, (cell.x+28, cell.y+169+i*22), 15, WHITE)
        if len(lines)>5:
            text(app.screen, app.assets, 'See the server notice for the full reason.',
                 (cell.x+28, cell.y+284), 12, MUTED)
        text(app.screen, app.assets, 'Your saved world and career resume when you are released.',
             (cell.x+28, cell.bottom-47), 12, CYAN, max_width=cell.width-56)
        text(app.screen, app.assets, 'This cell has private chat. Settings and Exit remain available.',
             (cell.x+28, cell.bottom-27), 11, MUTED, max_width=cell.width-56)
        emblem = pygame.Rect(cell.right-207, cell.y+102, 166, min(180, cell.height-188))
        if emblem.height > 50:
            panel(app.screen, emblem, (9, 20, 33), (52, 82, 99), 9)
            sprite = app.assets.tamer(app.state.get('tamer', app.tamer), 'down', False, app.now, (80, 110))
            if sprite:
                app.screen.blit(sprite, sprite.get_rect(center=(emblem.centerx, emblem.centery-10)))
            text(app.screen, app.assets, app.state.get('username', ''),
                 (emblem.centerx, emblem.bottom-20), 12, WHITE, True, emblem.width-12, center=True)
        self.feed(pygame.Rect(rect.x, rect.bottom-137, rect.width, 137))

    def result(self):
        app=self.app
        notice=getattr(app,'presentation_notice',None)
        if not notice or app.now>=notice['until']:
            return
        rect=pygame.Rect((app.screen.get_width()-450)//2,app.screen.get_height()-145,450,105)
        # Success art must never leave an obscured purchase/formation action live.
        app.ui.actions = [(area, action) for area, action in app.ui.actions
                          if not rect.colliderect(area)]
        hidden_fields = {key for area, key in app.ui.fields if rect.colliderect(area)}
        app.ui.fields = [(area, key) for area, key in app.ui.fields
                         if not rect.colliderect(area)]
        if app.ui.focus in hidden_fields:
            app.ui.focus = None
            pygame.key.stop_text_input()
        theme=notice['theme'];palette=app.presentation.colors(theme)
        app.presentation.card(rect,theme,accent=True)
        sprite=app.assets.sprite(notice['species_id'],(80,80),now=app.now)
        if sprite:app.screen.blit(sprite,sprite.get_rect(center=(rect.x+58,rect.centery)))
        text(app.screen,app.assets,notice['label'],(rect.x+115,rect.y+17),10,palette['accent'],True,rect.width-132)
        text(app.screen,app.assets,notice['name'],(rect.x+115,rect.y+40),21,WHITE,True,rect.width-132)
        text(app.screen,app.assets,'Partner data synchronized.',(rect.x+115,rect.y+75),11,MUTED,max_width=rect.width-132)

    def battle_stage(self, rect):
        """Reuse one crisp native arena, keeping memory and draw work bounded."""
        from .render import NativeCanvas
        from . import battle_arena
        app, rect = self.app, pygame.Rect(rect)
        native = app.screen.to_physical_rect(rect)
        if native.width <= 0 or native.height <= 0:
            return
        key = (native.size, app.screen.scale, rect.size)
        target = app.screen.surface
        old_clip = target.get_clip()
        target.set_clip(old_clip.clip(native))
        try:
            if getattr(self, '_stage_key', None) != key:
                # Release the old plate before allocating after a large resize.
                # Only publish a new key once a complete paint succeeds.
                self._stage = None
                self._stage_key = None
                if native.width*native.height*4 <= battle_arena.CACHE_BYTES:
                    surface = pygame.Surface(native.size).convert()
                    canvas = NativeCanvas(surface, app.screen.scale)
                    battle_arena.paint(canvas, pygame.Rect((0, 0), rect.size))
                    self._stage = surface
                self._stage_key = key
            if self._stage is None:
                battle_arena.paint(app.screen, rect)
            else:
                app.screen.blit_native(self._stage, rect.topleft)
        finally:
            target.set_clip(old_clip)
