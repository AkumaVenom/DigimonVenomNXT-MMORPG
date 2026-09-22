"""Server-backed rivals, ranked competition and population activity views.

This module only presents authoritative data. A combat replay never writes to
the player's real party, currency, rating or persistent world state.
"""
from __future__ import annotations

import copy
import math
import time
from datetime import datetime, timezone

import pygame

from .render import draw
from .widgets import BG, PANEL, CARD, LINE, WHITE, MUTED, CYAN, LIME, RED, GOLD, panel, text, wrap, bar


def number(value):
    try:
        return f'{int(value):,}'
    except (TypeError, ValueError):
        return '0'


def duration(seconds):
    seconds = max(0, int(seconds or 0))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    return f'{days}d {hours:02}h {minutes:02}m' if days else f'{hours:02}h {minutes:02}m'


def actor_name(entry):
    return str(entry.get('name') or entry.get('username') or entry.get('rival_name') or 'Tamer')


def is_bot(entry):
    return entry.get('kind') == 'bot' or bool(entry.get('is_bot')) or str(entry.get('id', '')).startswith('bot:')


def timestamp(value):
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else datetime.fromtimestamp(float(value), timezone.utc)
        return moment.strftime('%H:%M:%S UTC')
    except (TypeError, ValueError, OverflowError):
        return ''


class CommunityPanel:
    POLL_SECONDS = 3.0
    QUERY_ACTIONS = {'ranked', 'ladder', 'seasons', 'rivals', 'profile', 'activity'}

    def __init__(self, app):
        self.app = app
        self.reset()

    def reset(self):
        self.tab = 'ranked'
        self.mode = 'overview'
        self.scope = 'current'
        self.season_id = None
        self.profile_id = None
        self.offset = 0
        self.data = {}
        self.pending = {}
        self.request_ids = {}
        self.received_at = {}
        self.last_query = -100.
        self.error = ''
        self.replay = None
        self.activity_filter = 'All'
        self.stats_page = 0

    @property
    def visible(self):
        return self.app.menu == 'community'

    @property
    def busy(self):
        return any(action not in self.QUERY_ACTIONS for action in self.pending)

    def disconnected(self):
        self.pending.clear()
        self.request_ids.clear()
        if self.visible:
            self.error = 'Disconnected. Exit to sign in again.'

    def failed(self, rid, message):
        action = self.request_ids.pop(rid, None)
        if action:
            self.pending.pop(action, None)
        self.error = str(message)

    def request(self, action, **payload):
        if action in self.pending:
            return
        if self.app.args.demo:
            self.error = 'Connect to your dedicated server to view the live tamer network.'
            return
        if not self.app.connection or not self.app.connection.connected:
            self.error = 'The dedicated server is disconnected.'
            return
        rid = self.app.send('community', action=action, **payload)
        if rid is not None:
            self.pending[action] = (rid, self.app.now)
            self.request_ids[rid] = action
            self.last_query = self.app.now
            self.error = ''

    def open(self, tab='ranked'):
        if not self.app.state:
            return
        if self.app.state.get('battle'):
            self.app.toast('Finish your wild battle before opening the tamer network.')
            return
        changed = tab != self.tab or not self.visible
        self.app.menu = 'community'
        self.app.ui.focus = None
        self.app.ui.actions, self.app.ui.fields = [], []
        if changed:
            self.tab = tab
            self.mode = 'overview' if tab == 'ranked' else 'invites' if tab == 'rivals' else 'feed'
            self.app.scroll = 0
            self.profile_id = None
        self.refresh()

    def open_profile(self, bot_id):
        self.open('rivals')
        if not self.visible:
            return
        self.profile_id = bot_id
        self.mode = 'profile'
        self.app.scroll = 0
        self.request('profile', bot_id=bot_id)

    def close(self):
        self.app.menu = None
        self.app.ui.focus = None
        self.app.ui.actions, self.app.ui.fields = [], []

    def set_mode(self, mode):
        self.mode = mode
        self.app.scroll = 0
        self.refresh()

    def ladder(self, scope, season_id=None):
        self.mode, self.scope, self.season_id = 'ladder', scope, season_id
        self.app.scroll = 0
        self.refresh()

    def refresh(self):
        if self.replay:
            return
        if self.tab == 'ranked':
            if self.mode == 'ladder':
                payload = {'scope': self.scope}
                if self.season_id is not None:
                    payload['season_id'] = self.season_id
                self.request('ladder', **payload)
            elif self.mode == 'seasons':
                self.request('seasons')
            else:
                self.request('ranked')
        elif self.tab == 'rivals':
            if self.mode == 'profile' and self.profile_id:
                self.request('profile', bot_id=self.profile_id)
            else:
                self.request('rivals', query=self.app.ui.values.get('rival_search', '').strip(), offset=self.offset, limit=50)
        else:
            self.request('activity')

    def update(self, dt):
        # Coalesce reads even on a high-refresh display. Never retry a match or
        # accepted challenge: a timed-out mutation may already be committed.
        for action, (rid, started) in tuple(self.pending.items()):
            if self.app.now-started > 30 and action in self.QUERY_ACTIONS:
                self.pending.pop(action, None)
                self.request_ids.pop(rid, None)
                self.error = 'The server is taking longer than expected. Refresh to retry.'
        if self.visible and not self.app.settings_open and not self.replay and self.app.now-self.last_query >= self.POLL_SECONDS:
            self.refresh()
        if self.replay and self.visible and not self.app.settings_open:
            self.replay.update(dt)

    def receive(self, packet, rid=None):
        action = packet.get('action') or self.request_ids.get(rid, '')
        self.request_ids.pop(rid, None)
        self.pending.pop(action, None)
        data = packet.get('data', {})
        self.data[action] = data
        self.received_at[action] = self.app.now
        self.error = ''
        if action in ('match', 'challenge', 'accept'):
            result = data.get('match', data.get('result', data)) if isinstance(data, dict) else {}
            if isinstance(result, dict) and result.get('replay'):
                self.replay = MatchReplay(self.app, result)
                self.app.menu = 'community'
                self.app.ui.focus = None
                self.app.ui.actions, self.app.ui.fields = [], []
            elif isinstance(data, dict):
                self.app.toast(data.get('message', 'Challenge updated.'), CYAN)
        elif action == 'decline':
            self.app.toast('Challenge declined.')
            self.request('rivals', query='', offset=0, limit=50)

    def finish_replay(self):
        self.replay = None
        self.last_query = -100.
        self.refresh()

    def draw(self, rect):
        app = self.app
        panel(app.screen, rect, PANEL, LINE, 16)
        heading = {'ranked': 'RANKED ARENA', 'rivals': 'RIVALS HUB', 'activity': 'TAMER ACTIVITY'}[self.tab]
        subtitle = {'ranked': 'Weekly seasons · NXT rules · Server-resolved battles',
                    'rivals': 'AI rivals, friendly challenges and your shared battle history',
                    'activity': 'Live population counters and the latest 100 recorded activities'}[self.tab]
        text(app.screen, app.assets, heading, (rect.x+24, rect.y+19), 26, WHITE, True)
        text(app.screen, app.assets, subtitle, (rect.x+25, rect.y+55), 13, MUTED, max_width=rect.width-250)
        app.ui.button((rect.right-220, rect.y+22, 94, 34), 'Refresh', self.refresh, small=True, disabled=bool(self.pending) or bool(self.replay))
        app.ui.button((rect.right-112, rect.y+22, 88, 34), 'Field  Esc', self.close, small=True)
        body = pygame.Rect(rect.x+22, rect.y+86, rect.width-44, rect.height-115)
        if self.replay:
            self.replay.draw(body, self.finish_replay)
        else:
            nav = ([('overview', 'My arena'), ('ladder', 'Top 100'), ('seasons', 'Season history')] if self.tab == 'ranked'
                   else [('invites', 'Challenges'), ('directory', 'Rival directory'), ('history', 'Battle history')] if self.tab == 'rivals'
                   else [('feed', 'Live activity'), ('maps', 'Map population')])
            for index, (key, label) in enumerate(nav):
                app.ui.button((body.x+index*159, body.y, 150, 32), label,
                              lambda mode=key: self.set_mode(mode), selected=self.mode == key, small=True)
            body.y += 46
            body.height -= 46
            if self.tab == 'ranked':
                if self.mode == 'ladder': self.draw_ladder(body)
                elif self.mode == 'seasons': self.draw_seasons(body)
                else: self.draw_ranked(body)
            elif self.tab == 'rivals':
                if self.mode == 'profile': self.draw_profile(body)
                else: self.draw_rivals(body)
            elif self.mode == 'maps': self.draw_maps(body)
            else: self.draw_activity(body)
        status = self.error or ('OFFLINE PREVIEW  ·  No online account progress' if app.args.demo else
                               'Updating from server…' if self.pending else 'SERVER VERIFIED  ·  Human players and AI rivals share one world')
        text(app.screen, app.assets, status, (rect.x+24, rect.bottom-21), 11, RED if self.error else GOLD if app.args.demo else CYAN, max_width=rect.width-48)

    def empty(self, rect, message='Waiting for the dedicated server…'):
        text(self.app.screen, self.app.assets, message, rect.center, 18, MUTED, max_width=rect.width-30, center=True)

    def metric(self, rect, label, value, color=WHITE, detail=None):
        app = self.app
        panel(app.screen, rect, CARD, LINE, 10)
        text(app.screen, app.assets, label.upper(), (rect.x+12, rect.y+10), 10, MUTED, True, rect.width-24)
        text(app.screen, app.assets, value, (rect.x+12, rect.y+29), 22 if rect.height>63 else 17, color, True, rect.width-24)
        if detail:
            text(app.screen, app.assets, detail, (rect.x+12, rect.bottom-20), 10, MUTED, max_width=rect.width-24)

    def rows(self, rect, entries, height=57):
        count = max(1, rect.height//height)
        self.app.scroll = min(max(0, self.app.scroll), max(0, len(entries)-count))
        return [(pygame.Rect(rect.x, rect.y+i*height, rect.width, height-5), entry, self.app.scroll+i)
                for i, entry in enumerate(entries[self.app.scroll:self.app.scroll+count])]

    def draw_ranked(self, rect):
        app, data = self.app, self.data.get('ranked', {})
        if not data:
            self.empty(rect)
            return
        season, own = data.get('season', {}), data.get('own', {})
        remaining = season.get('seconds_remaining', 0)-(app.now-self.received_at.get('ranked', app.now))
        text(app.screen, app.assets, season.get('label', 'Current season'), rect.topleft, 20, WHITE, True, rect.width-220)
        text(app.screen, app.assets, 'Ends in '+duration(remaining), (rect.right-216, rect.y+4), 14, GOLD, True)
        energy = own.get('energy', {})
        stats = [('Season rank', '#'+number(own['rank']) if own.get('rank') else 'Unranked', CYAN),
                 ('Points / grade', number(own.get('points'))+' / '+str(own.get('grade', 'D')), WHITE),
                 ('Season W / L', f"{number(own.get('wins'))} / {number(own.get('losses'))}", LIME),
                 ('Career W / L', f"{number(own.get('career_wins'))} / {number(own.get('career_losses'))}", WHITE),
                 ('DigiRubies', number(own.get('digirubies')), GOLD),
                 ('Arena energy', f"{energy.get('current', 0)} / {energy.get('capacity', 0)}", CYAN)]
        width = (rect.width-5*9)//6
        for index, (label, value, color) in enumerate(stats):
            self.metric(pygame.Rect(rect.x+index*(width+9), rect.y+37, width, 67), label, value, color)
        text(app.screen, app.assets, 'MATCHED OPPONENTS  ·  THREE ACTIVE + RESERVES', (rect.x, rect.y+120), 12, CYAN, True)
        app.ui.button((rect.right-175, rect.y+114, 175, 30), 'Find match', lambda:self.request('match'),
                      primary=True, small=True, disabled=self.busy or energy.get('current', 1)<=0 or bool(app.state.get('in_lab')))
        opponent_area = pygame.Rect(rect.x, rect.y+157, rect.width, max(1, rect.height-227))
        opponents = data.get('opponents', [])
        if not opponents:
            self.empty(opponent_area, 'Opponents appear as rivals join the arena.')
        for row, rival, _ in self.rows(opponent_area, opponents, 65):
            self.draw_tamer_row(row, rival)
            text(app.screen, app.assets, f"{number(rival.get('points'))} pts   ·   {number(rival.get('wins'))}W / {number(rival.get('losses'))}L",
                 (row.x+260, row.y+11), 13, GOLD, max_width=row.width-585)
            for i, mon in enumerate(rival.get('party', [])[:3]):
                sprite = app.assets.sprite(mon.get('species_id'), (43, 44), now=app.now)
                if sprite: app.screen.blit(sprite, sprite.get_rect(center=(row.right-245+i*47, row.centery)))
            app.ui.button((row.right-100, row.y+12, 88, 34), 'Battle', lambda ident=rival.get('id'):self.request('match', opponent_id=ident),
                          primary=True, disabled=self.busy or energy.get('current', 1)<=0 or bool(app.state.get('in_lab')), small=True)
        rewards = data.get('rewards', [])
        preview = '  ·  '.join(f"Top {item.get('rank_max', '?')}: {number(item.get('digirubies'))}" for item in rewards[:4])
        next_grade = own.get('next_grade') or {}
        promotion = ('Promotion ready: win your next attacking match' if own.get('promotion_pending') else
                     f"Next grade: {next_grade.get('name')} at {number(next_grade.get('points'))} points" if next_grade else 'Highest grade reached')
        refill = max(0, energy.get('next_in', 0)-(app.now-self.received_at.get('ranked', app.now)))
        if refill: promotion += f'  ·  Next energy in {math.ceil(refill/60)} min'
        text(app.screen, app.assets, promotion, (rect.x, rect.bottom-54), 11, CYAN, max_width=rect.width)
        text(app.screen, app.assets, 'SEASON DIGIRUBIES  '+preview+'  + grade bonus', (rect.x, rect.bottom-34), 11, GOLD, max_width=rect.width)
        text(app.screen, app.assets, 'Start at least one ranked battle each season to qualify. Eligible season rewards arrive automatically.',
             (rect.x, rect.bottom-15), 11, MUTED, max_width=rect.width)

    def draw_tamer_row(self, row, entry, badge=True):
        app = self.app
        panel(app.screen, row, CARD, LINE, 8)
        sprite = app.assets.tamer(entry.get('tamer'), moving=False, now=app.now, box=(37, 45))
        if sprite: app.screen.blit(sprite, sprite.get_rect(midbottom=(row.x+31, row.bottom-5)))
        text(app.screen, app.assets, actor_name(entry), (row.x+62, row.y+9), 15, WHITE, True, min(210, row.width-85))
        if badge:
            text(app.screen, app.assets, 'AI RIVAL' if is_bot(entry) else 'PLAYER', (row.x+63, row.y+32), 10, CYAN if is_bot(entry) else LIME, True)

    def draw_ladder(self, rect):
        app = self.app
        app.ui.button((rect.x, rect.y, 132, 31), 'Current season', lambda:self.ladder('current'), selected=self.scope=='current', small=True)
        app.ui.button((rect.x+141, rect.y, 132, 31), 'Overall career', lambda:self.ladder('career'), selected=self.scope=='career', small=True)
        app.ui.button((rect.x+282, rect.y, 132, 31), 'Past seasons', lambda:self.set_mode('seasons'), selected=self.scope=='history', small=True)
        data = self.data.get('ladder', {})
        own = self.data.get('ranked', {}).get('own', {})
        season = data.get('season') or {}
        subtitle = 'Overall career rating' if self.scope=='career' else season.get('label', 'Current season')
        text(app.screen, app.assets, subtitle, (rect.x, rect.y+45), 15, WHITE, True, rect.width-270)
        text(app.screen, app.assets, f"{number(data.get('total'))} competitors  ·  Top 100", (rect.right-254, rect.y+47), 12, CYAN)
        headings = [(12, 'RANK'), (95, 'COMPETITOR'), (rect.width-353, 'RATING' if self.scope=='career' else 'POINTS'),
                    (rect.width-235, 'WINS'), (rect.width-138, 'LOSSES')]
        for x, label in headings:
            text(app.screen, app.assets, label, (rect.x+x, rect.y+76), 10, MUTED, True)
        area = pygame.Rect(rect.x, rect.y+97, rect.width, max(1, rect.height-126))
        entries = data.get('entries', [])[:100]
        if not entries: self.empty(area, 'No standings yet. Complete a ranked battle to join the ladder.')
        for row, entry, index in self.rows(area, entries, 42):
            mine = entry.get('id') == own.get('id')
            panel(app.screen, row, (24, 49, 59) if mine else CARD, CYAN if mine else LINE, 6)
            text(app.screen, app.assets, '#'+number(entry.get('rank', index+1)), (row.x+12, row.y+10), 15, GOLD if entry.get('rank', index+1)<=3 else WHITE, True)
            text(app.screen, app.assets, actor_name(entry), (row.x+95, row.y+10), 14, LIME if mine else WHITE, True, row.width-490)
            text(app.screen, app.assets, 'AI' if is_bot(entry) else 'PLAYER', (row.right-425, row.y+13), 9, CYAN if is_bot(entry) else LIME, True)
            text(app.screen, app.assets, number(entry.get('career_rating') if self.scope=='career' else entry.get('points')), (row.right-353, row.y+10), 14, GOLD)
            text(app.screen, app.assets, number(entry.get('wins')), (row.right-235, row.y+10), 14, LIME)
            text(app.screen, app.assets, number(entry.get('losses')), (row.right-138, row.y+10), 14, RED)
            if is_bot(entry): app.ui.actions.append((row, lambda ident=entry['id']:self.open_profile(ident)))
        rank_text = '#'+number(own.get('rank')) if own.get('rank') else 'Unranked'
        text(app.screen, app.assets, f'Your current-season rank: {rank_text}  ·  Scroll to browse all 100 positions',
             (rect.x, rect.bottom-16), 12, CYAN, max_width=rect.width)

    def draw_seasons(self, rect):
        app = self.app
        data = self.data.get('seasons', [])
        entries = data.get('seasons', data.get('entries', [])) if isinstance(data, dict) else data
        text(app.screen, app.assets, 'Every completed season keeps its final standings.', rect.topleft, 15, MUTED)
        area = pygame.Rect(rect.x, rect.y+38, rect.width, rect.height-58)
        if not entries: self.empty(area, 'The first season is underway. Final standings will appear here.')
        for row, season, _ in self.rows(area, entries, 65):
            panel(app.screen, row, CARD, LINE, 8)
            text(app.screen, app.assets, season.get('label', str(season.get('id', 'Season'))), (row.x+16, row.y+10), 17, WHITE, True)
            text(app.screen, app.assets, f"{str(season.get('status', 'completed')).upper()}  ·  {number(season.get('competitors'))} competitors",
                 (row.x+16, row.y+35), 11, CYAN)
            app.ui.button((row.right-173, row.y+12, 160, 34), 'View final top 100', lambda ident=season.get('id'):self.ladder('history', ident), small=True)

    def rival_data(self):
        return self.data.get('rivals', {})

    def directory_page(self, direction):
        self.offset = max(0, self.offset+direction*50)
        self.app.scroll = 0
        self.refresh()

    def directory_search(self):
        self.offset = 0
        self.app.scroll = 0
        self.refresh()

    def draw_rivals(self, rect):
        app, data = self.app, self.rival_data()
        if self.mode == 'directory':
            app.ui.field((rect.x, rect.y, rect.width-127, 36), 'rival_search', 'Search 5,000 AI rivals by name…', size=15)
            app.ui.button((rect.right-115, rect.y, 115, 36), 'Find rival', self.directory_search, primary=True, small=True)
            directory = data.get('directory', {})
            entries = directory.get('entries', []) if isinstance(directory, dict) else directory
            total = directory.get('total', data.get('total', len(entries))) if isinstance(directory, dict) else data.get('total', len(entries))
            area = pygame.Rect(rect.x, rect.y+49, rect.width, rect.height-93)
            for row, entry, _ in self.rows(area, entries, 61):
                self.draw_tamer_row(row, {**entry, 'is_bot': True})
                text(app.screen, app.assets, entry.get('map_name', 'Digital World'), (row.x+305, row.y+10), 14, WHITE, max_width=row.width-530)
                text(app.screen, app.assets, str(entry.get('status', entry.get('activity', 'Exploring'))).replace('_', ' ').title(),
                     (row.x+305, row.y+34), 11, CYAN, max_width=row.width-530)
                app.ui.button((row.right-112, row.y+12, 99, 33), 'Profile', lambda ident=entry.get('id'):self.open_profile(ident), small=True)
            if not entries: self.empty(area, 'No rivals match this search.')
            text(app.screen, app.assets, f'{number(total)} AI rivals  ·  Showing {self.offset+1 if total else 0}–{min(self.offset+len(entries), total)}  ·  Scroll within this page',
                 (rect.x, rect.bottom-26), 11, MUTED, max_width=rect.width-210)
            app.ui.button((rect.right-190, rect.bottom-35, 88, 31), 'Previous', lambda:self.directory_page(-1), disabled=self.offset<=0, small=True)
            app.ui.button((rect.right-92, rect.bottom-35, 88, 31), 'Next', lambda:self.directory_page(1), disabled=self.offset+50>=total, small=True)
            return
        if self.mode == 'history':
            entries = data.get('history', [])
            text(app.screen, app.assets, 'Your head-to-head record against every rival you have battled.', rect.topleft, 14, MUTED)
            area = pygame.Rect(rect.x, rect.y+36, rect.width, rect.height-53)
            if not entries: self.empty(area, 'No rival battles yet. Meet an AI rival on the field to get started.')
            for row, entry, _ in self.rows(area, entries, 65):
                self.draw_tamer_row(row, entry)
                wins, losses = entry.get('wins', 0), entry.get('losses', 0)
                text(app.screen, app.assets, f'{number(wins)} W  /  {number(losses)} L', (row.x+305, row.y+13), 17, GOLD, True)
                text(app.screen, app.assets, 'Last battle  '+timestamp(entry.get('last_at', entry.get('last_battle_at'))),
                     (row.x+305, row.y+37), 10, MUTED, max_width=row.width-435)
                bot_id = entry.get('bot_id', entry.get('rival_id', entry.get('id')))
                if bot_id and is_bot(entry): app.ui.button((row.right-112, row.y+12, 99, 34), 'Profile', lambda ident=bot_id:self.open_profile(ident), small=True)
            return
        entries = data.get('challenges', data.get('pending', []))
        text(app.screen, app.assets, 'PENDING CHALLENGES', rect.topleft, 13, CYAN, True)
        area = pygame.Rect(rect.x, rect.y+30, rect.width, max(125, rect.height//2-24))
        if not entries: self.empty(area, 'No pending challenges. Click an AI rival on your map to challenge them.')
        for row, entry, _ in self.rows(area, entries, 65):
            rival = entry.get('rival', entry)
            self.draw_tamer_row(row, {**rival, 'is_bot': True})
            text(app.screen, app.assets, 'Friendly battle · No ranked energy', (row.x+305, row.y+23), 12, MUTED, max_width=row.width-555)
            ident = entry.get('challenge_id', entry.get('id'))
            app.ui.button((row.right-220, row.y+12, 98, 34), 'Accept', lambda cid=ident:self.request('accept', challenge_id=cid), primary=True, small=True, disabled=self.busy)
            app.ui.button((row.right-111, row.y+12, 98, 34), 'Decline', lambda cid=ident:self.request('decline', challenge_id=cid), small=True, disabled=self.busy)
        lower = pygame.Rect(rect.x, area.bottom+20, rect.width, max(1, rect.bottom-area.bottom-40))
        text(app.screen, app.assets, 'NEARBY AI RIVALS', lower.topleft, 13, CYAN, True)
        nearby = data.get('nearby', [])
        lower.y += 27
        lower.height -= 27
        if not nearby: self.empty(lower, 'Explore a world sector to meet roaming tamers.')
        for i, rival in enumerate(nearby[:max(1, min(6, lower.width//175))]):
            width = (lower.width-10*5)//6
            card = pygame.Rect(lower.x+i*(width+10), lower.y, width, min(107, lower.height))
            panel(app.screen, card, CARD, LINE, 8)
            sprite = app.assets.tamer(rival.get('tamer'), moving=True, now=app.now, box=(35, 44))
            if sprite: app.screen.blit(sprite, sprite.get_rect(center=(card.centerx, card.y+32)))
            text(app.screen, app.assets, actor_name(rival), (card.centerx, card.y+65), 12, WHITE, True, card.width-12, True)
            text(app.screen, app.assets, 'AI RIVAL · Profile', (card.centerx, card.y+85), 10, CYAN, center=True)
            app.ui.actions.append((card, lambda ident=rival.get('id'):self.open_profile(ident)))

    def draw_profile(self, rect):
        app, data = self.app, self.data.get('profile', {})
        profile = data.get('bot', data.get('profile', data))
        if not profile or profile.get('id') != self.profile_id:
            self.empty(rect)
            return
        sprite = app.assets.tamer(profile.get('tamer'), moving=True, now=app.now, box=(65, 85))
        if sprite: app.screen.blit(sprite, sprite.get_rect(midbottom=(rect.x+43, rect.y+83)))
        text(app.screen, app.assets, actor_name(profile), (rect.x+94, rect.y), 26, WHITE, True, rect.width-310)
        text(app.screen, app.assets, 'AI RIVAL  ·  '+str(profile.get('map_name', 'Digital World')), (rect.x+95, rect.y+38), 12, CYAN, True, rect.width-320)
        activity = str(profile.get('status', profile.get('activity', 'Exploring'))).replace('_', ' ').title()
        text(app.screen, app.assets, activity+'  ·  Next: '+str(profile.get('next_activity', 'Training')).replace('_', ' '), (rect.x+95, rect.y+60), 12, MUTED, max_width=rect.width-335)
        same_map = profile.get('map_id') == app.state.get('map_id') and not app.state.get('in_lab')
        status = str(profile.get('status', '')).lower()
        rival_busy = bool(profile.get('battle') or profile.get('in_lab') or 'battle' in status or 'lab' in status)
        app.ui.button((rect.right-205, rect.y+7, 205, 39), 'Challenge rival', lambda:self.request('challenge', bot_id=self.profile_id),
                      primary=True, small=True, disabled=self.busy or not same_map or rival_busy)
        text(app.screen, app.assets, 'Meet on the same map to battle' if not same_map else 'Rival is busy · Check back shortly' if rival_busy else 'Move nearby · No ranked energy',
             (rect.right-205, rect.y+57), 10, MUTED, max_width=205)
        party = profile.get('party', [])[:6]
        width = (rect.width-5*10)//6
        for i, mon in enumerate(party):
            card = pygame.Rect(rect.x+i*(width+10), rect.y+103, width, 132)
            panel(app.screen, card, CARD, CYAN if i<3 else LINE, 10)
            image = app.assets.sprite(mon.get('species_id'), (74, 61), now=app.now)
            if image: app.screen.blit(image, image.get_rect(midbottom=(card.centerx, card.y+70)))
            text(app.screen, app.assets, mon.get('name', 'Digimon'), (card.centerx, card.y+85), 12, WHITE, True, card.width-12, True)
            text(app.screen, app.assets, f"Lv.{mon.get('level', 1)}  ·  {'ACTIVE' if i<3 else 'RESERVE'}", (card.centerx, card.y+107), 10, LIME if i<3 else MUTED, center=True)
        stats = profile.get('stats', {})
        pairs = [('Wild wins / losses', f"{number(stats.get('wild_wins'))} / {number(stats.get('wild_losses'))}"),
                 ('Ranked wins / losses', f"{number(stats.get('ranked_wins'))} / {number(stats.get('ranked_losses'))}"),
                 ('Materialized', number(stats.get('materialized'))), ('Levels gained', number(stats.get('level_ups'))),
                 ('Scans / ready', number(stats.get('scans'))+' / '+number(profile.get('scan_ready'))),
                 ('Partner swaps', number(stats.get('party_swaps'))), ('Sector changes', number(stats.get('travels'))),
                 ('Heals / items', number(stats.get('heals'))+' / '+number(stats.get('items_used')))]
        stats_area = pygame.Rect(rect.x, rect.y+250, rect.width, max(1, rect.height-267))
        columns = 4
        metric_width = (rect.width-9*(columns-1))//columns
        metric_height = min(68, max(48, (stats_area.height-8)//2))
        for i, (label, value) in enumerate(pairs):
            self.metric(pygame.Rect(stats_area.x+(i%columns)*(metric_width+9), stats_area.y+(i//columns)*(metric_height+8), metric_width, metric_height), label, value, CYAN)

    COUNTERS = [('wild_wins', 'Wild wins'), ('wild_losses', 'Wild losses'), ('ranked_wins', 'Ranked wins'), ('ranked_losses', 'Ranked losses'),
                ('scans', 'Scan events'), ('materialized', 'Materialized'), ('paradox_materialized', 'Paradox created'), ('level_ups', 'Levels gained'),
                ('xp_earned', 'Battle XP'), ('party_swaps', 'Partner swaps'), ('travels', 'Sector changes'), ('heals', 'Healing visits'),
                ('items_used', 'Items used'), ('purchases', 'Shop purchases'), ('evolutions', 'Digivolutions'), ('devolutions', 'De-digivolutions'),
                ('rival_wins', 'Rival wins'), ('rival_losses', 'Rival losses'), ('scan_data', 'Scan data earned'), ('walking_distance', 'Distance walked')]

    def draw_activity(self, rect):
        app, data = self.app, self.data.get('activity', {})
        counters = data.get('counters', data.get('totals', {}))
        text(app.screen, app.assets, f"{number(data.get('population'))} AI RIVALS  /  {number(data.get('active'))} ACTIVE",
             rect.topleft, 19, WHITE, True, rect.width-270)
        text(app.screen, app.assets, f"{number(data.get('occupied_maps'))} / {number(data.get('total_maps'))} maps occupied",
             (rect.right-253, rect.y+4), 13, CYAN)
        keys = self.COUNTERS[self.stats_page*12:(self.stats_page+1)*12]
        width = (rect.width-5*8)//6
        for i, (key, label) in enumerate(keys):
            self.metric(pygame.Rect(rect.x+(i%6)*(width+8), rect.y+36+(i//6)*65, width, 58), label, number(counters.get(key)), GOLD if 'loss' in key else LIME if 'wins' in key else CYAN)
        app.ui.button((rect.right-161, rect.y+171, 161, 28), 'More counters' if self.stats_page==0 else 'Main counters',
                      lambda:setattr(self, 'stats_page', 1-self.stats_page), small=True)
        for i, label in enumerate(('All', 'Wild', 'Ranked', 'Progress', 'Travel')):
            app.ui.button((rect.x+i*92, rect.y+171, 84, 28), label,
                          lambda value=label:self.set_activity_filter(value), selected=self.activity_filter==label, small=True)
        events = data.get('events', [])[:100]
        if self.activity_filter != 'All':
            tokens = {'Wild': ('wild', 'scan'), 'Ranked': ('rank',), 'Progress': ('level', 'material', 'evol', 'swap', 'heal', 'item', 'purchase'), 'Travel': ('travel', 'relocat', 'map')}[self.activity_filter]
            events = [event for event in events if any(token in str(event.get('kind', '')).lower() for token in tokens)]
        area = pygame.Rect(rect.x, rect.y+213, rect.width, max(1, rect.height-235))
        if not events: self.empty(area, 'Activity will appear here as the server population plays.')
        for row, event, _ in self.rows(area, events, 44):
            panel(app.screen, row, CARD, LINE, 5)
            kind = str(event.get('kind', 'activity')).replace('_', ' ').upper()
            text(app.screen, app.assets, timestamp(event.get('at')), (row.x+10, row.y+8), 10, MUTED, max_width=95)
            text(app.screen, app.assets, actor_name(event), (row.x+118, row.y+7), 12, CYAN, True, 180)
            text(app.screen, app.assets, kind, (row.x+118, row.y+24), 8, GOLD, max_width=180)
            text(app.screen, app.assets, event.get('text', kind), (row.x+308, row.y+13), 12, WHITE, max_width=row.width-320)
            if event.get('bot_id'): app.ui.actions.append((row, lambda ident=event['bot_id']:self.open_profile(ident)))
        text(app.screen, app.assets, f"{len(events)} of the latest 100 events  ·  Click a record to inspect its rival  ·  Refreshes every 3 seconds",
             (rect.x, rect.bottom-16), 11, MUTED, max_width=rect.width)

    def set_activity_filter(self, value):
        self.activity_filter = value
        self.app.scroll = 0

    def draw_maps(self, rect):
        app, data = self.app, self.data.get('activity', {})
        entries = sorted(data.get('maps', []), key=lambda entry: (-entry.get('count', 0), entry.get('name', '')))
        text(app.screen, app.assets, 'Population shifts as rivals explore and retreat from difficult sectors.', rect.topleft, 15, MUTED)
        area = pygame.Rect(rect.x, rect.y+35, rect.width, rect.height-56)
        for row, entry, _ in self.rows(area, entries, 43):
            panel(app.screen, row, CARD, LINE, 6)
            text(app.screen, app.assets, entry.get('name', entry.get('id', 'Map')), (row.x+14, row.y+10), 14, WHITE, True, row.width-430)
            text(app.screen, app.assets, 'Level '+str(entry.get('level', '?')), (row.right-378, row.y+11), 12, MUTED, max_width=100)
            bar(app.screen, pygame.Rect(row.right-260, row.y+16, 145, 7), entry.get('count', 0), max(1, entries[0].get('count', 1)), CYAN)
            text(app.screen, app.assets, number(entry.get('count'))+' AI', (row.right-91, row.y+11), 12, LIME, True)
        if not entries: self.empty(area)
        text(app.screen, app.assets, f'{len(entries)} sectors  ·  Scroll to browse', (rect.x, rect.bottom-15), 11, MUTED)


class MatchReplay:
    """Read-only presentation of the exact event stream returned by the server."""

    def __init__(self, app, result):
        self.app, self.result = app, copy.deepcopy(result)
        replay = result.get('replay', {})
        self.teams = {'player': copy.deepcopy(replay.get('party', [])), 'enemy': copy.deepcopy(replay.get('enemies', []))}
        self.active = {'player': list(replay.get('active', [0, 1, 2])), 'enemy': list(replay.get('enemy_active', [0, 1, 2]))}
        for side in self.active:
            self.active[side] = [index for index in self.active[side] if index<len(self.teams[side])]
        self.events = copy.deepcopy(replay.get('events', []))
        self.index = 0
        self.age = 0.
        self.elapsed = 0.
        self.speed = 1.
        self.applied = False
        self.effect = None
        self.log = 'The server has resolved this battle. Watch the action unfold.'
        self.done = not self.events

    def apply_event(self, event):
        side, index = event.get('side', 'enemy'), event.get('index', 0)
        if event.get('kind') == 'reserve':
            active = self.active.get(side, [])
            retired = event.get('retired_index')
            if retired in active: active[active.index(retired)] = index
            elif index not in active and len(active)<3: active.append(index)
        elif side in self.teams and isinstance(index, int) and 0<=index<len(self.teams[side]):
            mon = self.teams[side][index]
            if event.get('kind') == 'damage':
                mon['hp'] = max(0, event.get('hp_after', event.get('target_hp', mon.get('hp', 0)-event.get('amount', 0))))
            elif event.get('kind') == 'heal':
                mon['hp'] = min(mon.get('max_hp', 1), event.get('hp_after', mon.get('hp', 0)+event.get('amount', 0)))
            if 'sp_after' in event:
                attacker = self.teams.get(event.get('attacker_side', ''), [])
                attacker_index = event.get('attacker_index', -1)
                if 0<=attacker_index<len(attacker): attacker[attacker_index]['sp'] = event['sp_after']

    def update(self, dt):
        if self.done:
            return
        self.age += dt*self.speed
        self.elapsed += dt*self.speed
        while self.index<len(self.events):
            event = self.events[self.index]
            if not self.applied and self.age >= .22:
                self.apply_event(event)
                self.applied = True
                self.log = event.get('text') or str(event.get('move', event.get('kind', 'Battle action'))).replace('_', ' ').title()
                if event.get('kind') in ('damage', 'heal'):
                    self.app.audio.effect('heal' if event['kind']=='heal' else 'hit')
            if self.age < (.82 if event.get('kind') in ('damage', 'heal') else .25):
                break
            self.age -= .82 if event.get('kind') in ('damage', 'heal') else .25
            self.index += 1
            self.applied = False
        self.done = self.index>=len(self.events)

    def skip(self):
        for index in range(self.index, len(self.events)):
            if index != self.index or not self.applied:
                self.apply_event(self.events[index])
        self.index = len(self.events)
        self.done = True

    def draw(self, rect, close):
        app = self.app
        panel(app.screen, rect, (12, 23, 40), CYAN, 12)
        ranked = self.result.get('ranked', True)
        text(app.screen, app.assets, 'RANKED BATTLE' if ranked else 'RIVAL CHALLENGE', (rect.x+18, rect.y+17), 15, CYAN, True)
        title = self.result.get('attacker_name', 'Your team')+'  vs  '+self.result.get('defender_name', 'Rival')
        text(app.screen, app.assets, title, (rect.centerx, rect.y+48), 18, WHITE, True, rect.width-45, True)
        arena = pygame.Rect(rect.x+15, rect.y+50, rect.width-30, max(190, rect.height-140))
        old_view, old_now = app.viewport, app.now
        app.viewport = arena
        event = self.events[self.index] if not self.done else None
        for y in range(arena.y+60, arena.bottom, 37):
            draw.line(app.screen, (22, 43, 62), (arena.x, y), (arena.right, y))
        try:
            for side, indices in self.active.items():
                for slot, index in enumerate(indices):
                    if not 0<=index<len(self.teams[side]): continue
                    mon = self.teams[side][index]
                    position = app.battle_positions(side, slot, len(indices))
                    attacking = bool(event and event.get('attacker_side')==side and event.get('attacker_index')==index and self.age<.42)
                    if attacking:
                        target_side = event.get('side', 'enemy')
                        target_indices = self.active.get(target_side, [])
                        target_index = event.get('index', 0)
                        target_slot = target_indices.index(target_index) if target_index in target_indices else 0
                        target = app.battle_positions(target_side, target_slot, len(target_indices))
                        position += (target-position)*math.sin(self.age/.42*math.pi)*.48
                    if event and event.get('side')==side and event.get('index')==index and .2<self.age<.48:
                        position.x += math.sin(self.age*90)*5
                    size = (98, 75) if arena.height<430 else (135, 108)
                    sprite = app.assets.sprite(mon.get('species_id'), size, 'attack' if attacking else 'idle', app.now)
                    draw.ellipse(app.screen, (22, 54, 62) if side=='player' else (54, 30, 55), (position.x-50, position.y-8, 100, 19))
                    if sprite:
                        if mon.get('hp', 0)<=0:
                            sprite = sprite.copy()
                            sprite.set_alpha(65)
                        app.screen.blit(sprite, sprite.get_rect(midbottom=(round(position.x), round(position.y))))
                    text(app.screen, app.assets, mon.get('name', 'Digimon'), (position.x, position.y-size[1]-23), 13, WHITE, True, 190, True)
                    text(app.screen, app.assets, f"Lv.{mon.get('level', 1)}", (position.x, position.y-size[1]-7), 10, MUTED, center=True)
                    bar(app.screen, pygame.Rect(position.x-61, position.y+12, 122, 7), mon.get('hp', 0), mon.get('max_hp', 1), LIME if side=='player' else RED)
                    text(app.screen, app.assets, f"{number(mon.get('hp'))} / {number(mon.get('max_hp'))}", (position.x, position.y+31), 10, MUTED, center=True)
            if event and event.get('kind') in ('damage', 'heal') and self.age>=.12:
                effect = dict(event, start=app.now-self.age, duration=1.05)
                effect.setdefault('effectiveness', effect.get('multiplier', 1))
                if effect.get('side')=='enemy':
                    indices = self.active['enemy']
                    effect['index'] = indices.index(effect.get('index')) if effect.get('index') in indices else 0
                app.draw_effect(effect, [self.teams['enemy'][i] for i in self.active['enemy']], self.active['player'])
        finally:
            app.viewport, app.now = old_view, old_now
        bar(app.screen, pygame.Rect(rect.x+18, rect.bottom-72, rect.width-36, 4), self.index, max(1, len(self.events)), CYAN)
        if self.done:
            win = self.result.get('attacker_won', self.result.get('winner_id')==self.result.get('attacker_id'))
            delta = self.result.get('points', {}).get('attacker', {}).get('delta', 0)
            label = ('VICTORY' if win else 'DEFEAT') + (f'  ·  {delta:+} arena points' if ranked else '  ·  Friendly battle complete')
            text(app.screen, app.assets, label, (rect.x+20, rect.bottom-49), 19, LIME if win else RED, True, rect.width-225)
            app.ui.button((rect.right-191, rect.bottom-56, 174, 37), 'Return to hub', close, primary=True, small=True)
        else:
            text(app.screen, app.assets, self.log, (rect.x+18, rect.bottom-51), 12, MUTED, max_width=rect.width-325)
            app.ui.button((rect.right-285, rect.bottom-56, 119, 36), f'{self.speed:g}× playback', lambda:setattr(self, 'speed', 2. if self.speed==1 else 1.), small=True)
            app.ui.button((rect.right-153, rect.bottom-56, 135, 36), 'Show result', self.skip, small=True)
