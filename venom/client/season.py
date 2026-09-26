"""Private, server-owned Season Mode. This view never simulates a fixture.

The live battle remains App's ordinary interactive combat view. Only the world
server may advance a booking or resolve the rest of its match card.
"""
from __future__ import annotations

import pygame

from .render import draw
from .widgets import text, wrap, bar, WHITE, MUTED, CYAN, LIME, GOLD


class SeasonScreen:
    TABS = (('card', 'This week'), ('roster', 'Roster & rankings'),
            ('rivalries', 'Rivalries'), ('titles', 'Championship'), ('archive', 'Career archive'))

    def __init__(self, app):
        self.app = app
        self.reset()

    def reset(self):
        self.tab = 'card'
        self.page = 0
        self.history = None
        self.history_pending = None
        self.history_error = ''
        self.archive_selection = None

    @property
    def data(self):
        return (self.app.state or {}).get('season') or {}

    @property
    def active(self):
        return bool((self.app.state or {}).get('in_season'))

    @property
    def battling(self):
        battle = (self.app.state or {}).get('battle') or {}
        return bool(battle.get('season') or battle.get('kind') == 'season')

    @property
    def visible(self):
        return self.active and not self.app.menu and not self.app.state.get('battle')

    def toggle(self):
        app = self.app
        if app.action_pending:
            return
        if self.battling:
            app.toast('Finish your match to return to the world. Exit saves your battle for later.', GOLD)
            return
        if self.active:
            self.return_world()
        elif app.state and app.state.get('battle'):
            app.toast('Finish the current battle before entering Season Mode.')
        else:
            self.command('enter')

    def command(self, action):
        if self.app.action_pending:
            return
        payload = {'action': action}
        if action in ('start', 'next'):
            token = self.data.get('card', {}).get('token')
            if not token:
                return
            payload['token'] = token
        self.app.send('season', **payload)

    def return_world(self):
        if self.battling:
            self.app.toast('Complete this match first. Exit pauses and saves the exact battle.', GOLD)
            return
        self.command('return')

    def select_tab(self, key):
        self.tab, self.page = key, 0
        self.app.scroll = 0
        self.app.ui.actions, self.app.ui.fields = [], []
        self.app.audio.cue('tab', now=self.app.now)
        if key == 'archive':
            self.request_history(0)

    def request_history(self, page):
        if self.app.action_pending or self.history_pending is not None:
            return
        self.history_error = ''
        self.archive_selection = None
        self.history_pending = self.app.send('season', action='history', page=max(0, page), page_size=8)

    def receive_history(self, data, rid):
        if self.history_pending is not None and rid != self.history_pending:
            return
        self.history = data
        self.history_pending = None
        self.history_error = ''
        self.page = data.get('page', 0)

    def failed(self, rid, message):
        if rid == self.history_pending:
            self.history_pending = None
            self.history_error = message

    def confirmed(self, previous, state):
        app = self.app
        previous = previous or {}
        if not previous.get('in_season') and state.get('in_season'):
            self.reset()
            app.menu = None
            app.ui.focus = None
            app.farm_screen.manager_open = False
            app.farm_screen.home_confirmation = False
            app.partner_screen.pending_exchange = None
            app.audio.cue('season_enter', now=app.now)
        old, new = previous.get('season') or {}, state.get('season') or {}
        if old.get('phase') != 'results' and new.get('phase') == 'results':
            self.tab, self.page = 'card', 0
            app.audio.cue('season_results', now=app.now)
        if old.get('week') != new.get('week'):
            self.tab, self.page = 'card', 0
            self.history = None
        if previous.get('in_season') and not state.get('in_season'):
            app.menu = None
            app.battle_old = None
            app.audio.cue('back', now=app.now)

    def write(self, value, position, size=13, color=WHITE, bold=False, width=None, center=False):
        return text(self.app.screen, self.app.assets, value, position, size, color, bold,
                    max_width=width, center=center)

    def card(self, rect, selected=False, accent=False):
        self.app.presentation.card(rect, 'season', selected=selected, accent=accent)

    def button(self, rect, label, callback, **options):
        self.app.ui.button(rect, label, callback, small=True,
                           accent=self.app.presentation.colors('season')['accent'], **options)

    def draw(self, rect):
        app, data, rect = self.app, self.data, pygame.Rect(rect)
        date = data.get('calendar', {}).get('label', 'Monday, 1 January, Year 1')
        week = data.get('week', 1)
        body = app.presentation.shell(rect, 'season', 'YOUR TAMER CAREER',
            f'{date}    /    Booking week {week:,}',
            'VENOM NXT  /  PRIVATE SOLO LEAGUE', header_height=128)
        self.button((rect.right-272, rect.y+74, 246, 32), 'Save & Return to World',
                    self.return_world, disabled=app.action_pending)
        for index, (key, label) in enumerate(self.TABS):
            width = min(190, (body.width-4*8)//5)
            self.button((body.x+index*(width+8), body.y, width, 33), label,
                        lambda k=key:self.select_tab(k), selected=self.tab == key)
        content = pygame.Rect(body.x, body.y+47, body.width, body.height-47)
        if not data:
            self.card(content)
            self.write('Synchronizing your private league…', content.center, 19, center=True)
        elif self.tab == 'card':
            self.draw_week(content)
        elif self.tab == 'roster':
            self.draw_roster(content)
        elif self.tab == 'rivalries':
            self.draw_rivalries(content)
        elif self.tab == 'titles':
            self.draw_titles(content)
        else:
            self.draw_archive(content)
        save_label = 'SAVING / Waiting for the server…' if app.action_pending else 'AUTO-SAVED  /  Your fictional calendar advances only when you play. Your league pauses when you leave.'
        self.write(save_label,
                   (rect.x+25, rect.bottom-19), 10, MUTED, width=rect.width-50)

    def draw_week(self, rect):
        data = self.data
        side_width = min(304, max(264, rect.width*.27))
        main = pygame.Rect(rect.x, rect.y, rect.width-side_width-15, rect.height)
        side = pygame.Rect(main.right+15, rect.y, side_width, rect.height)
        hero = pygame.Rect(main.x, main.y, main.width, 172)
        self.draw_player_match(hero)
        matches = pygame.Rect(main.x, hero.bottom+12, main.width, main.bottom-hero.bottom-12)
        self.draw_matches(matches, data.get('card', {}))
        champion = pygame.Rect(side.x, side.y, side.width, 151)
        self.draw_champion(champion)
        stats = pygame.Rect(side.x, champion.bottom+12, side.width, 100)
        self.card(stats)
        career = data.get('career', {})
        self.write('YOUR CAREER', (stats.x+16, stats.y+12), 10, CYAN, True)
        rank = next((i+1 for i, value in enumerate(data.get('standings', [])) if value == 'player'), '—')
        values = ((f"{career.get('wins', 0)}–{career.get('losses', 0)}", 'WINS / LOSSES'),
                  (f'#{rank}', 'LEAGUE RANK'), (str(career.get('titles', 0)), 'TITLES'))
        width = (stats.width-28)/3
        for index, (value, caption) in enumerate(values):
            center = stats.x+14+width*(index+.5)
            self.write(value, (center, stats.y+49), 23, WHITE, True, width-6, True)
            self.write(caption, (center, stats.y+79), 8, MUTED, width=width-4, center=True)
        news = pygame.Rect(side.x, stats.bottom+12, side.width, side.bottom-stats.bottom-12)
        self.card(news)
        self.write('LEAGUE FREQUENCY', (news.x+16, news.y+13), 10, CYAN, True)
        items = data.get('recent_news') or ['Your career begins here. Every booking writes the next chapter.']
        y = news.y+38
        for line in items[:3]:
            if y+31 > news.bottom-12:
                break
            draw.circle(self.app.screen, CYAN, (news.x+18, y+7), 2)
            y = wrap(self.app.screen, self.app.assets, line, (news.x+29, y),
                     news.width-44, 11, MUTED, max_lines=2)+10

    def draw_player_match(self, rect):
        app, data = self.app, self.data
        card = data.get('card', {})
        match = next((m for m in card.get('matches', []) if m.get('is_player')), {})
        resolved = data.get('phase') == 'results'
        self.card(rect, selected=True, accent=True)
        label = 'WEEK COMPLETE' if resolved else 'YOUR SCHEDULED MATCH'
        if match.get('title_match'):
            label += '  /  WORLD CHAMPIONSHIP'
        self.write(label, (rect.x+17, rect.y+12), 10, GOLD if match.get('title_match') else CYAN, True,
                   rect.width-35)
        self.write(card.get('title', 'Venom Circuit'), (rect.x+17, rect.y+35), 21, WHITE, True, rect.width-260)
        self.write(match.get('date_label') or f"{match.get('weekday', 'Tuesday')} · Booking week {data.get('week', 1)}",
                   (rect.x+18, rect.y+64), 11, MUTED, width=rect.width-260)
        for index, side in enumerate(('home', 'away')):
            x = rect.x+17+index*(rect.width-36)//2
            self.app.presentation.sprite((x, rect.y+93, 58, 65), match.get(f'{side}_species_id'), now=app.now)
            name = match.get(f'{side}_name', 'Tamer')
            you = match.get(f'{side}_id') == 'player'
            self.write(name, (x+68, rect.y+105), 15, CYAN if you else WHITE, True, (rect.width-60)//2-74)
            self.write('YOU' if you else 'AI OPPONENT', (x+69, rect.y+130), 9, MUTED)
        self.write('VS', (rect.centerx, rect.y+125), 11, GOLD, True, center=True)
        if resolved:
            winner = match.get('home_name') if match.get('winner_id') == match.get('home_id') else match.get('away_name')
            self.write('VICTORY' if match.get('winner_id') == 'player' else f'{winner} wins',
                       (rect.right-230, rect.y+37), 12, LIME if match.get('winner_id') == 'player' else GOLD,
                       True, 211)
            label, action = 'Next Week  →', 'next'
        else:
            label, action = 'Continue Season  ·  Fight', 'start'
        self.button((rect.right-247, rect.y+62, 229, 31), label,
                    lambda:self.command(action), primary=True, disabled=app.action_pending)

    def draw_matches(self, rect, card, *, archive=False):
        self.card(rect)
        self.write('MATCH CARD' if not archive else f"BOOKING WEEK {card.get('week', '?')}",
                   (rect.x+15, rect.y+12), 10, CYAN, True, rect.width-220)
        fixtures = card.get('matches', [])
        resolved = all(m.get('status') in ('complete', 'completed', 'resolved') or m.get('winner_id') for m in fixtures)
        self.write('RESULTS CONFIRMED' if resolved and fixtures else 'OTHER RESULTS AFTER YOUR MATCH',
                   (rect.right-239, rect.y+13), 8, LIME if resolved else MUTED, width=223)
        row_height = min(35, max(25, (rect.height-45)//max(1, len(fixtures))))
        name_width = max(76, int((rect.width-176)*.45))
        for index, match in enumerate(fixtures):
            y = rect.y+36+index*row_height
            if y+row_height > rect.bottom-5:
                break
            if match.get('is_player'):
                draw.rect(self.app.screen, (21, 58, 72), (rect.x+9,y-1,rect.width-18,row_height-2), border_radius=4)
            else:
                draw.line(self.app.screen, (31,49,67), (rect.x+13,y+row_height-2), (rect.right-13,y+row_height-2))
            self.write(str(match.get('weekday', ''))[:3].upper(), (rect.x+17,y+4), 9, MUTED)
            self.write(match.get('home_name', 'Tamer') + (' · WIN' if match.get('winner_id') == match.get('home_id') else ''), (rect.x+55,y+3), 11,
                       LIME if match.get('winner_id') == match.get('home_id') else CYAN if match.get('home_id') == 'player' else WHITE, match.get('winner_id') == match.get('home_id'), name_width)
            self.write('vs', (rect.x+62+name_width,y+5), 9, MUTED)
            self.write(match.get('away_name', 'Tamer') + (' · WIN' if match.get('winner_id') == match.get('away_id') else ''), (rect.x+85+name_width,y+3), 11,
                       LIME if match.get('winner_id') == match.get('away_id') else CYAN if match.get('away_id') == 'player' else WHITE, match.get('winner_id') == match.get('away_id'), name_width)
            status = 'TITLE' if match.get('title_match') else 'FINAL' if match.get('winner_id') else 'BOOKED'
            self.write(status, (rect.right-77,y+5), 8, GOLD if match.get('title_match') else LIME if match.get('winner_id') else MUTED,
                       True, 65)

    def draw_champion(self, rect):
        app, data = self.app, self.data
        champion = data.get('champion', {})
        holder = next((r for r in data.get('roster', []) if r.get('id') == champion.get('holder_id')), {})
        self.card(rect, accent=True)
        app.presentation.icon((rect.x+13, rect.y+13, 26, 26), 'crown', 'ranked')
        self.write('SOLO SEASON', (rect.x+49, rect.y+13), 9, GOLD, True)
        self.write('WORLD CHAMPION', (rect.x+49, rect.y+30), 11, GOLD, True, rect.width-60)
        app.presentation.sprite((rect.x+14, rect.y+60, 70, 70), holder.get('species_id'), now=app.now)
        self.write(champion.get('holder_name', 'Vacant'), (rect.x+95, rect.y+66), 16, WHITE, True, rect.width-110)
        self.write(f"Reign {champion.get('reign', 1)}  ·  {champion.get('defenses', 0)} defenses",
                   (rect.x+95, rect.y+94), 10, MUTED, width=rect.width-110)
        self.write(f"Since week {champion.get('since_week', 1)}", (rect.x+95, rect.y+116), 10, MUTED, width=rect.width-110)
        if rect.width > 650:
            for x, value, caption in ((rect.right-420, champion.get('reign', 1), 'REIGN NUMBER'),
                                      (rect.right-187, champion.get('defenses', 0), 'SUCCESSFUL DEFENSES')):
                self.write(value, (x, rect.y+75), 37, GOLD, True, 185, True)
                self.write(caption, (x, rect.y+113), 10, MUTED, width=185, center=True)

    def pager(self, rect, total, size):
        count = max(1, (total+size-1)//size)
        self.page = max(0, min(self.page, count-1))
        self.write(f'Page {self.page+1} / {count}', (rect.x+4, rect.bottom-23), 11, MUTED)
        self.button((rect.right-181, rect.bottom-34, 86, 29), 'Previous', lambda:setattr(self,'page',self.page-1), disabled=self.page == 0)
        self.button((rect.right-86, rect.bottom-34, 86, 29), 'Next', lambda:setattr(self,'page',self.page+1), disabled=self.page+1 >= count)

    def draw_roster(self, rect):
        data = self.data
        by_id = {r['id']: r for r in data.get('roster', [])}
        entries = [by_id[i] for i in data.get('standings', []) if i in by_id]
        size = max(1, min(8, (rect.height-74)//47))
        self.pager(rect, len(entries), size)
        self.write('THE COMPETING ROSTER', (rect.x+13, rect.y+4), 12, CYAN, True)
        self.write('Records and rankings belong to your private league.', (rect.x+13,rect.y+26), 11, MUTED)
        for pos, entry in enumerate(entries[self.page*size:(self.page+1)*size]):
            row = pygame.Rect(rect.x,rect.y+53+pos*47,rect.width,42)
            self.card(row, selected=entry.get('is_player', False))
            self.write(f'{self.page*size+pos+1:02}', (row.x+14,row.y+10), 17, GOLD if entry['id'] == data.get('champion',{}).get('holder_id') else MUTED, True)
            tamer = self.app.assets.tamer(entry.get('tamer'), now=self.app.now, box=(30,34))
            if tamer:
                self.app.screen.blit(tamer,tamer.get_rect(center=(row.x+65,row.centery)))
            self.app.presentation.sprite((row.x+85,row.y+3,42,35),entry.get('species_id'),now=self.app.now)
            self.write(entry.get('name','Tamer')+('  ·  YOU' if entry.get('is_player') else ''), (row.x+142,row.y+10), 14,
                       CYAN if entry.get('is_player') else WHITE, True, row.width-650)
            x = row.right-483
            for value, width in ((f"Lv.{entry.get('level',1)}",85), (f"{entry.get('rating',1000):,} RP",110),
                                 (f"{entry.get('wins',0)}W / {entry.get('losses',0)}L",126),
                                 (f"{entry.get('titles',0)} titles",83), (f"{entry.get('streak',0):+} run",76)):
                self.write(value,(x,row.y+13),10,MUTED,width=width-8)
                x += width

    def draw_rivalries(self, rect):
        entries = sorted(self.data.get('rivalries', []), key=lambda r:r.get('heat',0), reverse=True)
        self.write('RIVALRY SIGNALS', (rect.x+13,rect.y+4),12,CYAN,True)
        self.write('Repeated clashes build a history. Rivalries carry across weeks and years.',(rect.x+13,rect.y+27),11,MUTED)
        size = 6
        self.pager(rect, len(entries), size)
        if not entries:
            self.write('Your first rival is waiting on the match card.',rect.center,20,WHITE,True,rect.width-30,True)
        width, height = (rect.width-14)//2,(rect.height-107)//3
        for pos, entry in enumerate(entries[self.page*size:(self.page+1)*size]):
            cell = pygame.Rect(rect.x+(pos%2)*(width+14),rect.y+53+(pos//2)*(height+9),width,height)
            self.card(cell, selected=entry.get('a') == 'player' or entry.get('b') == 'player')
            self.write(f"{entry.get('a_name','Tamer')}  vs  {entry.get('b_name','Tamer')}",
                       (cell.x+17,cell.y+13),15,WHITE,True,cell.width-34)
            self.write(f"{entry.get('matches',0)} meetings  /  last clash week {entry.get('last_week',1)}",
                       (cell.x+17,cell.y+41),10,MUTED,width=cell.width-34)
            heat = entry.get('heat',0)
            self.write('INTENSE' if heat >= 65 else 'BUILDING' if heat >= 25 else 'NEW RIVALRY',
                       (cell.x+17,cell.bottom-28),9,GOLD if heat >= 65 else CYAN,True)
            bar(self.app.screen,pygame.Rect(cell.x+141,cell.bottom-24,cell.width-158,5),heat,100,GOLD if heat>=65 else CYAN)

    def draw_titles(self, rect):
        self.draw_champion(pygame.Rect(rect.x,rect.y,rect.width,151))
        area = pygame.Rect(rect.x,rect.y+168,rect.width,rect.height-168)
        self.card(area)
        self.write('CHAMPIONSHIP CONTINUITY', (area.x+17,area.y+14),12,GOLD,True)
        self.write('Recent reigns in your solo league. Older title changes remain in the Career archive.',
                   (area.x+17,area.y+40),11,MUTED,width=area.width-34)
        entries = self.data.get('recent_reigns', [])
        if not entries:
            self.write('The current champion writes the opening reign.',(area.x+17,area.y+83),15,WHITE,True)
            self.write('Completed cards and title changes stay in your Career archive.',(area.x+17,area.y+115),12,MUTED,width=area.width-34)
            return
        size = max(1, (area.height-121)//35)
        self.pager(area.inflate(-30,-10), len(entries), size)
        for index, reign in enumerate(list(reversed(entries))[self.page*size:(self.page+1)*size]):
            y = area.y+77+index*35
            self.write(reign.get('holder_name',reign.get('name','Champion')),(area.x+20,y),14,WHITE,True,area.width//2)
            span = f"Week {reign.get('start_week',1)} – {reign.get('end_week') or 'present'}"
            self.write(span,(area.x+area.width*.49,y+2),11,MUTED,width=area.width*.3)
            self.write(f"{reign.get('defenses',0)} defenses",(area.right-139,y+2),11,GOLD,width=120)

    def draw_archive(self, rect):
        self.write('YOUR CAREER ARCHIVE',(rect.x+13,rect.y+4),12,CYAN,True)
        if self.archive_selection is None:
            self.write('Every completed week remains available. Browse the full match cards below.',(rect.x+13,rect.y+26),11,MUTED)
        if self.history_error:
            self.write(self.history_error,(rect.x+13,rect.y+71),13,GOLD,width=rect.width-30)
            self.button((rect.x+13,rect.y+110,120,32),'Retry',lambda:self.request_history(self.page))
            return
        if self.history_pending is not None:
            self.write('Loading saved weeks…',rect.center,18,MUTED,center=True)
            return
        history = self.history or {}
        entries = history.get('items', [])
        if self.archive_selection is not None:
            item = next((x for x in entries if x.get('week') == self.archive_selection),None)
            self.button((rect.right-152,rect.y,152,32),'Back to archive',lambda:setattr(self,'archive_selection',None))
            if item:
                card = item.get('card',item)
                self.write(item.get('start_date', {}).get('label', 'Saved booking') + '  →  ' + item.get('end_date', {}).get('label', ''),
                           (rect.x+13, rect.y+27), 11, MUTED, width=rect.width-30)
                self.draw_matches(pygame.Rect(rect.x,rect.y+56,rect.width,rect.height-56),card,archive=True)
                champion = item.get('champion', {})
                self.write('WORLD CHAMPION AFTER THIS CARD  /  ' + champion.get('holder_name', 'Unknown'),
                           (rect.x+18, rect.bottom-67), 11, GOLD, True, rect.width-36)
                events = item.get('title_events', [])
                outcome = '  ·  '.join(('NEW CHAMPION: ' if event.get('kind') == 'title_change' else 'TITLE DEFENDED: ')
                                      + event.get('holder_name','Tamer') for event in events)
                self.write(outcome or 'No championship change on this card.', (rect.x+18,rect.bottom-40),11,MUTED,width=rect.width-36)
            return
        if not entries:
            self.write('Your first chapter is still in play.',(rect.centerx,rect.centery-16),21,WHITE,True,center=True)
            self.write('Complete a match and select Next Week to archive its card.',(rect.centerx,rect.centery+20),13,MUTED,center=True)
        else:
            row_height = min(48,(rect.height-102)//len(entries))
            for index, item in enumerate(entries):
                row = pygame.Rect(rect.x,rect.y+55+index*row_height,rect.width,row_height-5)
                self.card(row)
                card = item.get('card',item)
                self.write(f"WEEK {item.get('week',card.get('week','?'))}",(row.x+15,row.y+10),12,CYAN,True,150)
                self.write(card.get('title',item.get('title','Venom Circuit')),(row.x+177,row.y+10),13,WHITE,True,row.width*.56-190)
                self.write(item.get('start_date',{}).get('label',''),(row.x+row.width*.56,row.y+12),10,MUTED,width=row.width*.44-177)
                self.button((row.right-158,row.y+5,146,row.height-10),'View match card',lambda w=item.get('week'):setattr(self,'archive_selection',w))
        self.write(f"Archive page {history.get('page',0)+1}",(rect.x+12,rect.bottom-23),11,MUTED)
        self.button((rect.right-181,rect.bottom-34,86,29),'Newer',lambda:self.request_history(self.page-1),disabled=self.page==0)
        self.button((rect.right-86,rect.bottom-34,86,29),'Older',lambda:self.request_history(self.page+1),disabled=not history.get('has_more',False))
