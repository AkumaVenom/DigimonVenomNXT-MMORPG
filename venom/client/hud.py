"""Shared field chrome; native UI cards retain the original world renderer."""
from __future__ import annotations
import pygame
from .render import draw
from .widgets import text, bar, WHITE, MUTED, CYAN, LIME, GOLD


class GameHUD:
    def __init__(self, app):
        self.app = app

    def header(self):
        app, screen, art = self.app, self.app.screen, self.app.presentation
        w = screen.get_width()
        accent = art.colors('party')['accent']
        draw.rect(screen, (9, 20, 34), (0, 0, w, 92))
        draw.line(screen, (31, 61, 77), (0, 75), (w, 75))
        draw.line(screen, CYAN, (22, 75), (179, 75), 2)
        app.ui.button((22, 18, 156, 37), 'Home · DigiFarm', app.enter_farm,
                      selected=bool(app.state.get('in_farm')) and not app.menu,
                      small=True, accent=LIME, disabled=app.action_pending)
        text(screen, app.assets, 'VENOM NXT / v0.6.0', (25, 3), 9, MUTED, True)
        tabs = [('dex', 'DigiDex'), ('party', 'Partners'), ('shop', 'Shop'), ('maps', 'Worlds')]
        battle = bool(app.state.get('battle'))
        for i, (key, label) in enumerate(tabs):
            app.ui.button((210+i*101, 18, 96, 37), label, lambda k=key:app.set_menu(k),
                          selected=app.menu==key or key=='dex' and app.menu=='scan',
                          small=True, accent=CYAN, disabled=battle)
        app.ui.button((625, 18, 91, 37), 'Settings', app.toggle_settings,
                      selected=app.settings_open, small=True, accent=CYAN)
        app.ui.button((w-430, 16, 147, 41), 'DigiLab  F1', app.enter_lab,
                      primary=True, accent=LIME, disabled=battle or app.action_pending)
        text(screen, app.assets, f"{app.state.get('credits', 0):,} ¥", (w-263, 13), 19, GOLD, True, 131)
        text(screen, app.assets, app.state.get('username', ''), (w-263, 42), 11, MUTED, max_width=124)
        app.ui.button((w-128, 15, 42, 40), '♪' if app.audio.enabled else '♫', app.audio.toggle, accent=CYAN)
        app.ui.button((w-77, 15, 55, 40), 'Exit', app.logout, small=True, accent=CYAN)
        for i, (key, label) in enumerate((('ranked','Ranked Arena  R'),('rivals','Rivals Hub  V'),('activity','Bot Activity  O'))):
            app.ui.button((22+i*148, 65, 138, 23), label,
                          lambda value=key:app.community.open(value), small=True,
                          selected=app.menu=='community' and app.community.tab==key,
                          accent=art.colors(key)['accent'], disabled=battle)
        text(screen, app.assets, 'LINK  /  '+('DIGIFARM' if app.state.get('in_farm') else 'DIGILAB' if app.state.get('in_lab') else 'BATTLE' if battle else 'FIELD'),
             (w-223, 71), 9, accent, True)

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
                      lambda:app.set_menu('party'),small=True,accent=palette['accent'],disabled=bool(app.state.get('battle')))

    def feed(self, rect):
        app, rect = self.app, pygame.Rect(rect)
        app.presentation.card(rect, 'activity')
        text(app.screen,app.assets,'WORLD FREQUENCY',(rect.x+15,rect.y+9),10,CYAN,True)
        for i,(message,color) in enumerate(app.logs[-3:]):
            text(app.screen,app.assets,message,(rect.x+15,rect.y+30+i*20),12,color,max_width=rect.width-30)
        app.ui.field((rect.x+12,rect.bottom-35,rect.width-89,27),'chat','Enter to chat with your world…',size=13)
        def chat():
            message=app.ui.values.get('chat','').strip()
            if message:
                app.send('chat',text=message)
                app.ui.values['chat']=''
        app.ui.button((rect.right-68,rect.bottom-35,55,27),'Send',chat,small=True,accent=CYAN)

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
        """Retain a native arena plate without repainting perspective lines."""
        from .render import NativeCanvas
        app, rect = self.app, pygame.Rect(rect)
        native=app.screen.to_physical_rect(rect)
        key=(native.size,app.screen.scale)
        palette=app.presentation.colors('battle')
        def paint(canvas, area):
            draw.rect(canvas,palette['panel'],area,border_radius=12)
            old=canvas.get_clip();canvas.set_clip(area)
            for y in range(area.y+80,area.bottom-25,36):
                draw.line(canvas,(23,44,61),(area.x,y),(area.right,y))
            for x in range(area.x-300,area.right+300,85):
                draw.line(canvas,(23,44,61),(area.centerx+(x-area.centerx)*.25,area.y+80),(x,area.bottom))
            draw.line(canvas,palette['line'],(area.x+18,area.y+65),(area.right-18,area.y+65))
            draw.line(canvas,palette['accent'],(area.x+17,area.y+1),(area.x+220,area.y+1),2)
            draw.rect(canvas,palette['line'],area,1,border_radius=12)
            canvas.set_clip(old)
        if getattr(self,'_stage_key',None)!=key:
            self._stage_key=key;self._stage=None
            if native.width*native.height*4 <= 32*1024*1024:
                surface=pygame.Surface(native.size).convert()
                canvas=NativeCanvas(surface,app.screen.scale)
                paint(canvas,canvas.get_rect())
                self._stage=surface
        if self._stage is None:
            paint(app.screen,rect)
        else:
            app.screen.blit_native(self._stage,rect.topleft)
