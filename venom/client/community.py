"""Server-backed rivals, ranked competition and population activity views.

This module only presents authoritative data. A combat replay never writes to
the player's real party, currency, rating or persistent world state.
"""
from __future__ import annotations

import copy
from collections import OrderedDict
import math
import time
import uuid
from datetime import datetime, timezone

import pygame

from .render import draw
from .presentation import Presentation
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
        self.presentation = getattr(app, 'presentation', None) or Presentation(app)
        self._portraits = OrderedDict()
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
        self.exchange_review = None
        self.exchange_receipt = None

    @property
    def visible(self):
        return self.app.menu == 'community'

    @property
    def busy(self):
        return any(action not in self.QUERY_ACTIONS for action in self.pending)

    @property
    def exchange_modal(self):
        return self.visible and self.tab == 'ranked' and self.mode == 'exchange' and self.exchange_review is not None

    @property
    def economy_enabled(self):
        features = getattr(self.app,'server_features',None)
        return bool((self.app.state.get('economy') or {}).get('enabled')) and (features is None or 'digiruby_economy' in features)

    def exchange_terms(self):
        economy = self.app.state.get('economy') or {}
        rate, maximum = economy.get('credits_per_ruby'), economy.get('max_exchange_rubies')
        if not all(isinstance(value,int) and not isinstance(value,bool) and value>0 for value in (rate,maximum)):
            return None,None
        return rate,maximum

    def exchange_amount(self):
        value = self.app.ui.values.get('ruby_exchange_amount','1').strip()
        return int(value) if value.isascii() and value.isdecimal() and len(value)<=9 else None

    def exchange_problem(self, amount=None):
        rate,maximum = self.exchange_terms()
        if not self.economy_enabled or rate is None:
            return 'DigiRuby exchange requires an updated server with the ranked economy enabled.'
        if any(self.app.state.get(key) for key in ('battle','in_story','in_season')):
            return 'Return to the shared world before exchanging DigiRubies.'
        amount = self.exchange_amount() if amount is None else amount
        if amount is None or not 1 <= amount <= maximum:
            return f'Enter a whole number from 1 to {number(maximum)}.'
        balance = self.app.state.get('digirubies',0)
        if amount > balance:
            return f'You need {number(amount-balance)} more DigiRubies for this exchange.'
        from venom.common.economy import MAX_CREDITS
        ceiling = (self.app.state.get('economy') or {}).get('max_credits',MAX_CREDITS)
        if self.app.state.get('credits',0)+amount*rate > ceiling:
            return 'Your credits are near their limit. Spend credits or choose a smaller amount.'
        return ''

    def exchange_maximum(self):
        from venom.common.economy import MAX_CREDITS
        rate,maximum = self.exchange_terms()
        if not rate or not maximum:
            return 0
        ceiling = (self.app.state.get('economy') or {}).get('max_credits',MAX_CREDITS)
        capacity = max(0,(ceiling-self.app.state.get('credits',0))//rate)
        return min(maximum,self.app.state.get('digirubies',0),capacity)

    def set_exchange_amount(self, amount):
        if self.busy or self.app.action_pending or self.exchange_review is not None:
            return
        self.app.ui.values['ruby_exchange_amount'] = str(max(1,int(amount)))
        self.exchange_receipt = None
        self.error = ''

    def review_exchange(self):
        if self.busy or self.app.action_pending or self.exchange_review is not None:
            return
        problem = self.exchange_problem()
        if problem:
            self.error = problem
            return
        amount = self.exchange_amount()
        rate,_ = self.exchange_terms()
        self.exchange_review = {'amount':amount,'rate':rate,'credits':amount*rate,'transaction_id':uuid.uuid4().hex}
        self.exchange_receipt = None
        self.error = ''
        self.app.ui.focus = None
        self.app.ui.actions,self.app.ui.fields = [],[]
        pygame.key.stop_text_input()

    def cancel_exchange_review(self):
        if self.busy:
            return
        self.exchange_review = None
        self.app.ui.actions,self.app.ui.fields = [],[]
        self.cue('back')

    def confirm_exchange(self):
        review = self.exchange_review
        if not review or self.busy or self.app.action_pending:
            return
        problem = self.exchange_problem(review['amount'])
        if self.exchange_terms()[0] != review['rate']:
            problem = 'The exchange rate changed. Go back and review the current offer.'
        if problem:
            self.error = problem
            return
        self.request('exchange',amount=review['amount'],transaction_id=review['transaction_id'])

    def cue(self, name):
        audio = getattr(self.app, 'audio', None)
        if audio is not None:
            audio.cue(name, now=self.app.now)

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
        if action not in self.QUERY_ACTIONS and (self.busy or self.app.action_pending):
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
        return rid

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
            self.cue('open')
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
        self.cue('back')
        self.app.menu = None
        self.app.ui.focus = None
        self.app.ui.actions, self.app.ui.fields = [], []

    def set_mode(self, mode):
        self.cue('tab')
        self.mode = mode
        self.app.scroll = 0
        self.refresh()

    def ladder(self, scope, season_id=None):
        self.cue('tab')
        self.mode, self.scope, self.season_id = 'ladder', scope, season_id
        self.app.scroll = 0
        self.refresh()

    def refresh(self):
        if self.replay or self.exchange_review is not None:
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
        if action == 'exchange' and self.request_ids.get(rid) != 'exchange':
            return
        self.request_ids.pop(rid, None)
        self.pending.pop(action, None)
        data = packet.get('data', {})
        self.data[action] = data
        self.received_at[action] = self.app.now
        if self.exchange_review is None or action == 'exchange':
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
        elif action == 'exchange':
            self.exchange_review = None
            self.exchange_receipt = copy.deepcopy(data)
            message = ('Exchange already confirmed' if data.get('duplicate') else 'Exchange complete')
            message += f" · {number(data.get('rubies_spent'))} DigiRubies → {number(data.get('credits_gained'))} credits"
            self.app.toast(message,LIME)
            self.app.ui.actions,self.app.ui.fields = [],[]
            self.last_query = self.app.now

    def finish_replay(self):
        self.replay = None
        self.last_query = -100.
        self.refresh()

    def portrait(self, tamer_id, box=(44, 62), moving=False):
        """Fit visible portrait pixels, without changing overworld sprite sizing."""
        source = self.app.assets.tamer(tamer_id, moving=moving, now=self.app.now, box=(128, 160))
        if source is None:
            return None
        key = source, tuple(box)
        if key in self._portraits:
            self._portraits.move_to_end(key)
            return self._portraits[key]
        bounds = source.get_bounding_rect(min_alpha=8)
        if not bounds.width or not bounds.height:
            return None
        factor = min(box[0]/bounds.width, box[1]/bounds.height)
        size = max(1, round(bounds.width*factor)), max(1, round(bounds.height*factor))
        image = pygame.transform.scale(source.subsurface(bounds), size)
        self._portraits[key] = image
        while len(self._portraits)>96:
            self._portraits.popitem(last=False)
        return image

    def button(self, rect, label, callback, *, primary=False, selected=False, disabled=False, small=True):
        """Theme-aware controls retain the shared UI's hit testing and sound hook."""
        app, rect = self.app, pygame.Rect(rect)
        colors = self.presentation.colors(self.tab)
        hover = rect.collidepoint(app.ui.mouse) and not disabled
        fill = colors['accent'] if primary and not disabled else colors['panel']
        edge = colors['accent'] if selected or hover else colors['line']
        panel(app.screen, rect, fill, edge, 7)
        if selected:
            draw.rect(app.screen, colors['accent'], (rect.x+12, rect.bottom-3, rect.width-24, 2))
        text(app.screen, app.assets, label, rect.center, 12 if small else 15,
             colors['ink'] if primary and not disabled else MUTED if disabled else WHITE,
             primary or selected, rect.width-16, True)
        if not disabled:
            app.ui.actions.append((rect, callback))

    def draw(self, rect):
        app = self.app
        headings = {'ranked': ('RANKED ARENA', 'Enter the circuit. Build your legacy.', 'NXT COMPETITIVE CIRCUIT'),
                    'rivals': ('RIVALS HUB', 'A world of rivals. Your next great battle.', 'TAMER NETWORK'),
                    'activity': ('BOT ACTIVITY', 'Every battle, every discovery, every journey.', 'WORLD OBSERVATORY')}
        title, subtitle, eyebrow = headings[self.tab]
        self.presentation.shell(rect, self.tab, title, subtitle, eyebrow)
        body = pygame.Rect(rect.x+24, rect.y+148, rect.width-48, rect.height-180)
        if self.replay:
            self.replay.draw(body, self.finish_replay)
        else:
            nav = ([('overview', 'My arena'), ('ladder', 'Top 100'), ('seasons', 'Season archive'), ('exchange','DigiRuby exchange')] if self.tab == 'ranked'
                   else [('invites', 'Challenges'), ('directory', 'Rival directory'), ('history', 'Battle history')] if self.tab == 'rivals'
                   else [('feed', 'Live activity'), ('maps', 'Map population')])
            for index, (key, label) in enumerate(nav):
                self.button((body.x+index*153, body.y, 180 if key=='exchange' else 143, 34), label,
                            lambda mode=key: self.set_mode(mode), selected=self.mode == key)
            if self.mode == 'profile' and self.tab == 'rivals':
                self.presentation.badge(pygame.Rect(body.x+466, body.y+5, 118, 24), 'RIVAL DOSSIER', 'rivals')
            self.button((body.right-210, body.y, 98, 34), 'Refresh', self.refresh, disabled=bool(self.pending))
            self.button((body.right-102, body.y, 102, 34), ('DigiLab  Esc' if app.state.get('in_lab') else 'DigiFarm  Esc' if app.state.get('in_farm') else 'Field  Esc'), self.close)
            body.y += 48
            body.height -= 48
            if self.tab == 'ranked':
                if self.mode == 'ladder': self.draw_ladder(body)
                elif self.mode == 'seasons': self.draw_seasons(body)
                elif self.mode == 'exchange': self.draw_exchange(body)
                else: self.draw_ranked(body)
            elif self.tab == 'rivals':
                if self.mode == 'profile': self.draw_profile(body)
                else: self.draw_rivals(body)
            elif self.mode == 'maps': self.draw_maps(body)
            else: self.draw_activity(body)
        status = self.error or ('OFFLINE PREVIEW  /  Connect to access the live tamer network' if app.args.demo else
                               'SYNCING  /  Updating from the dedicated server…' if self.pending else
                               'SERVER VERIFIED  /  Human players and AI rivals share one world')
        color = RED if self.error else GOLD if app.args.demo else self.presentation.colors(self.tab)['accent']
        draw.circle(app.screen, color, (rect.x+28, rect.bottom-17), 3)
        text(app.screen, app.assets, status, (rect.x+39, rect.bottom-24), 10, color, max_width=rect.width-70)
        if self.exchange_modal:
            self.draw_exchange_review(rect)

    def empty(self, rect, message='Waiting for the dedicated server…'):
        app = self.app
        self.presentation.card(rect, self.tab)
        color = self.presentation.colors(self.tab)['accent']
        cx, cy = rect.centerx, rect.centery-17
        draw.circle(app.screen, color, (cx, cy), 15, 1)
        draw.line(app.screen, color, (cx-7, cy), (cx+7, cy), 2)
        draw.line(app.screen, color, (cx, cy-7), (cx, cy+7), 2)
        text(app.screen, app.assets, message, (cx, cy+39), 13, MUTED, max_width=rect.width-28, center=True)

    def metric(self, rect, label, value, color=WHITE, detail=None):
        self.presentation.metric(rect, label, value, detail or '', self.tab)

    def rows(self, rect, entries, height=57):
        count = max(1, rect.height//height)
        self.app.scroll = min(max(0, self.app.scroll), max(0, len(entries)-count))
        return [(pygame.Rect(rect.x, rect.y+i*height, rect.width, height-7), entry, self.app.scroll+i)
                for i, entry in enumerate(entries[self.app.scroll:self.app.scroll+count])]

    def grid(self, rect, entries, height=100, columns=2):
        count = max(1, rect.height//height)*columns
        self.app.scroll = min(max(0, self.app.scroll), max(0, len(entries)-count))
        width = (rect.width-(columns-1)*12)//columns
        return [(pygame.Rect(rect.x+(i%columns)*(width+12), rect.y+(i//columns)*height, width, height-10), entry, self.app.scroll+i)
                for i, entry in enumerate(entries[self.app.scroll:self.app.scroll+count])]

    def draw_ranked(self, rect):
        app, data = self.app, self.data.get('ranked', {})
        if not data:
            self.empty(rect, 'Connect to your dedicated server to enter the arena.' if app.args.demo else 'Loading the current season…')
            return
        season, own = data.get('season', {}), data.get('own', {})
        remaining = season.get('seconds_remaining', 0)-(app.now-self.received_at.get('ranked', app.now))
        energy = own.get('energy', {})
        side = pygame.Rect(rect.x, rect.y, min(306, rect.width//3), rect.height)
        self.presentation.card(side, 'ranked', accent=True)
        text(app.screen, app.assets, 'YOUR SEASON', (side.x+20, side.y+18), 10, GOLD, True)
        text(app.screen, app.assets, season.get('label', 'Current season'), (side.x+20, side.y+39), 19, WHITE, True, side.width-40)
        text(app.screen, app.assets, 'Closes in '+duration(remaining), (side.x+20, side.y+67), 11, MUTED)
        grade = str(own.get('grade', 'D'))
        badge = pygame.Rect(side.x+20, side.y+102, 72, 76)
        draw.polygon(app.screen, (67, 46, 34), [(badge.x, badge.y), (badge.right, badge.y), (badge.right-8, badge.bottom-17), (badge.centerx, badge.bottom), (badge.x+8, badge.bottom-17)])
        draw.polygon(app.screen, GOLD, [(badge.x, badge.y), (badge.right, badge.y), (badge.right-8, badge.bottom-17), (badge.centerx, badge.bottom), (badge.x+8, badge.bottom-17)], 1)
        text(app.screen, app.assets, grade, badge.center, 37, GOLD, True, 63, True)
        text(app.screen, app.assets, '#'+number(own['rank']) if own.get('rank') else 'Unranked', (side.x+108, side.y+104), 27, WHITE, True, side.width-128)
        text(app.screen, app.assets, number(own.get('points'))+' SEASON POINTS', (side.x+109, side.y+143), 10, GOLD, True, side.width-127)
        draw.line(app.screen, (89, 65, 46), (side.x+20, side.y+195), (side.right-20, side.y+195))
        pairs = [('Season record', f"{number(own.get('wins'))} W  /  {number(own.get('losses'))} L"),
                 ('Career record', f"{number(own.get('career_wins'))} W  /  {number(own.get('career_losses'))} L"),
                 ('DigiRubies', number(app.state.get('digirubies',own.get('digirubies'))))]
        for i, (label, value) in enumerate(pairs):
            y = side.y+211+i*31
            text(app.screen, app.assets, label, (side.x+20, y), 11, MUTED)
            text(app.screen, app.assets, value, (side.right-82, y+7), 12, GOLD if i==2 else WHITE, True, side.width//2, True)
        energy_y = side.y+317
        text(app.screen, app.assets, 'ARENA ENERGY', (side.x+20, energy_y), 10, GOLD, True)
        text(app.screen, app.assets, f"{energy.get('current', 0)} / {energy.get('capacity', 0)}", (side.right-76, energy_y-2), 13, WHITE, True)
        bar(app.screen, pygame.Rect(side.x+20, energy_y+24, side.width-40, 6), energy.get('current', 0), energy.get('capacity', 1), GOLD)
        refill = max(0, energy.get('next_in', 0)-(app.now-self.received_at.get('ranked', app.now)))
        text(app.screen, app.assets, f'Next charge in {math.ceil(refill/60)} min' if refill else 'Ready for the circuit', (side.x+20, energy_y+40), 10, MUTED, max_width=side.width-40)
        disabled = self.busy or energy.get('current', 1)<=0 or bool(app.state.get('in_lab'))
        self.button((side.x+20, side.bottom-53, side.width-40, 35), 'Find ranked match', lambda:self.request('match'), primary=True, disabled=disabled)
        main = pygame.Rect(side.right+18, rect.y, rect.width-side.width-18, rect.height)
        text(app.screen, app.assets, 'CHOOSE YOUR CHALLENGER', main.topleft, 13, GOLD, True)
        text(app.screen, app.assets, 'Three active partners + reserves', (main.x, main.y+23), 11, MUTED)
        opponent_area = pygame.Rect(main.x, main.y+53, main.width, max(1, main.height-168))
        opponents = data.get('opponents', [])
        if not opponents:
            self.empty(opponent_area, 'Opponents appear as rivals join the arena.')
        for row, rival, _ in self.rows(opponent_area, opponents, 86):
            self.draw_tamer_row(row, rival)
            text(app.screen, app.assets, f"{number(rival.get('points'))} pts  /  {number(rival.get('wins'))}W · {number(rival.get('losses'))}L",
                 (row.x+70, row.y+56), 11, GOLD, max_width=row.width-332)
            for i, mon in enumerate(rival.get('party', [])[:3]):
                sprite = app.assets.sprite(mon.get('species_id'), (48, 52), now=app.now)
                if sprite: app.screen.blit(sprite, sprite.get_rect(midbottom=(row.right-242+i*51, row.bottom-10)))
            self.button((row.right-99, row.y+23, 86, 34), 'Battle', lambda ident=rival.get('id'):self.request('match', opponent_id=ident), primary=True, disabled=disabled)
        reward = pygame.Rect(main.x, main.bottom-106, main.width, 106)
        self.presentation.card(reward, 'ranked')
        text(app.screen, app.assets, 'SEASON REWARDS', (reward.x+16, reward.y+12), 10, GOLD, True)
        preview = '  ·  '.join(f"Top {item.get('rank_max', '?')}: {number(item.get('digirubies'))}" for item in data.get('rewards', [])[:4])
        text(app.screen, app.assets, preview+'  + grade bonus' if preview else 'Season rewards are issued automatically.', (reward.x+16, reward.y+33), 12, WHITE, max_width=reward.width-32)
        next_grade = own.get('next_grade') or {}
        promotion = ('Promotion ready · Win your next attacking match' if own.get('promotion_pending') else
                     f"Next grade: {next_grade.get('name')} at {number(next_grade.get('points'))} points" if next_grade else 'Highest grade reached')
        text(app.screen, app.assets, promotion, (reward.x+16, reward.y+57), 11, GOLD, max_width=reward.width-32)
        text(app.screen, app.assets, 'Play one ranked battle this season to qualify. Scroll opponents to browse.', (reward.x+16, reward.y+81), 10, MUTED, max_width=reward.width-32)

    def draw_exchange(self, rect):
        app = self.app
        rate,maximum = self.exchange_terms()
        amount = self.exchange_amount()
        problem = self.exchange_problem()
        pending = self.busy or app.action_pending
        rubies,credits = app.state.get('digirubies',0),app.state.get('credits',0)
        valid = not problem and amount is not None and rate is not None
        gain = amount*rate if valid else None
        left = pygame.Rect(rect.x,rect.y,int(rect.width*.59),rect.height)
        right = pygame.Rect(left.right+16,rect.y,rect.width-left.width-16,rect.height)
        self.presentation.card(left,'ranked',accent=True)
        self.presentation.card(right,'ranked')
        text(app.screen,app.assets,'YOUR RANKED REWARDS  /  YOUR CHOICE',(left.x+23,left.y+20),10,GOLD,True,left.width-46)
        text(app.screen,app.assets,'Turn DigiRubies into credits',(left.x+23,left.y+43),25,WHITE,True,left.width-46)
        rate_label = f'1 DigiRuby → {number(rate)} credits' if rate else 'Waiting for the server’s exchange rate'
        text(app.screen,app.assets,rate_label,(left.x+23,left.y+84),14,GOLD,True,left.width-46)
        text(app.screen,app.assets,'DIGIRUBIES TO CONVERT',(left.x+23,left.y+117),10,MUTED,True)
        field = pygame.Rect(left.x+23,left.y+139,left.width-46,44)
        app.ui.values.setdefault('ruby_exchange_amount','1')
        if pending:
            panel(app.screen,field,BG,LINE,8)
            text(app.screen,app.assets,app.ui.values['ruby_exchange_amount'],(field.x+12,field.y+10),19,MUTED,max_width=field.width-24)
        else:
            app.ui.field(field,'ruby_exchange_amount','Enter a whole number',size=19)
        preset_width = (left.width-76)//4
        max_amount = self.exchange_maximum()
        for i,(label,value) in enumerate((('1',1),('10',10),('100',100),('Max',max_amount))):
            self.button((left.x+23+i*(preset_width+10),left.y+195,preset_width,31),label,
                        lambda n=value:self.set_exchange_amount(n),disabled=pending or not self.economy_enabled or value<1)
        quote = pygame.Rect(left.x+23,left.y+245,left.width-46,91)
        panel(app.screen,quote,(26,31,42),(81,65,49),8)
        text(app.screen,app.assets,'YOU SPEND',(quote.x+17,quote.y+15),10,MUTED,True)
        text(app.screen,app.assets,f'{number(amount)} DigiRubies' if amount is not None else '—',
             (quote.x+17,quote.y+40),20,WHITE,True,quote.width//2-25)
        text(app.screen,app.assets,'YOU RECEIVE',(quote.centerx+13,quote.y+15),10,GOLD,True)
        text(app.screen,app.assets,f'{number(gain)} credits' if gain is not None else '—',
             (quote.centerx+13,quote.y+40),20,GOLD,True,quote.width//2-28)
        if self.exchange_receipt:
            receipt = self.exchange_receipt
            message = f"Confirmed: {number(receipt.get('rubies_spent'))} DigiRubies exchanged for {number(receipt.get('credits_gained'))} credits."
            color = LIME
        else:
            message = problem or f'Up to {number(maximum)} DigiRubies per exchange. Review before confirming.'
            color = RED if problem else MUTED
        wrap(app.screen,app.assets,message,(left.x+23,left.y+350),left.width-46,12,color,max_lines=2)
        self.button((left.x+23,left.bottom-56,left.width-46,37),'Review exchange',self.review_exchange,
                    primary=True,disabled=pending or not valid or app.args.demo)
        text(app.screen,app.assets,'YOUR WALLET',(right.x+23,right.y+20),10,GOLD,True)
        text(app.screen,app.assets,number(rubies),(right.x+23,right.y+49),31,(215,161,255),True,right.width-46)
        text(app.screen,app.assets,'DIGIRUBIES',(right.x+24,right.y+91),10,MUTED,True)
        text(app.screen,app.assets,number(credits)+' ¥',(right.x+23,right.y+123),27,GOLD,True,right.width-46)
        text(app.screen,app.assets,'CREDITS',(right.x+24,right.y+158),10,MUTED,True)
        draw.line(app.screen,(81,65,49),(right.x+23,right.y+194),(right.right-23,right.y+194))
        text(app.screen,app.assets,'AFTER THIS EXCHANGE',(right.x+23,right.y+214),10,GOLD,True)
        for i,(label,value) in enumerate((('DigiRubies',rubies-amount if valid else None),('Credits',credits+gain if valid else None))):
            y = right.y+246+i*32
            text(app.screen,app.assets,label,(right.x+23,y),12,MUTED)
            # A separate bounded value column keeps large wallets inside.
            value_rect = pygame.Rect(right.x+130,y,right.width-153,22)
            text(app.screen,app.assets,number(value) if value is not None else '—',
                 value_rect.center,12,WHITE,True,value_rect.width,True)
        wrap(app.screen,app.assets,'DigiRubies can also buy supplies directly in the shop. Compare both prices before choosing. Credits work with your usual items and systems.',
             (right.x+23,right.y+326),right.width-46,12,MUTED,max_lines=4)
        text(app.screen,app.assets,'Balances change only after server confirmation.',
             (right.x+23,right.bottom-27),10,GOLD,max_width=right.width-46)

    def draw_exchange_review(self, bounds):
        app,review = self.app,self.exchange_review
        rect = pygame.Rect(0,0,min(680,bounds.width-48),390)
        rect.center = bounds.center
        app.ui.actions,app.ui.fields = [],[]
        panel(app.screen,rect,(10,23,37),GOLD,12)
        text(app.screen,app.assets,'REVIEW YOUR EXCHANGE',(rect.x+28,rect.y+23),11,GOLD,True)
        text(app.screen,app.assets,'Confirm this amount?',(rect.x+27,rect.y+50),27,WHITE,True,rect.width-54)
        text(app.screen,app.assets,f"{number(review['amount'])} DigiRubies → {number(review['credits'])} credits",
             (rect.x+28,rect.y+109),24,GOLD,True,rect.width-56)
        text(app.screen,app.assets,f"Rate: 1 DigiRuby = {number(review['rate'])} credits",
             (rect.x+28,rect.y+153),13,MUTED,max_width=rect.width-56)
        remaining = app.state.get('digirubies',0)-review['amount']
        text(app.screen,app.assets,f'DigiRubies remaining: {number(max(0,remaining))}',
             (rect.x+28,rect.y+191),14,WHITE,max_width=rect.width-56)
        pending = 'exchange' in self.pending
        message = ('Waiting for the server to confirm this exchange…' if pending else self.error or
                   'Confirming spends the selected DigiRubies. Your credits become available as soon as the server confirms.')
        wrap(app.screen,app.assets,message,(rect.x+28,rect.y+236),rect.width-56,13,
             GOLD if pending else RED if self.error else MUTED,max_lines=3)
        width = (rect.width-68)//2
        self.button((rect.x+28,rect.bottom-65,width,39),'Back',self.cancel_exchange_review,disabled=pending)
        self.button((rect.x+40+width,rect.bottom-65,width,39),'Confirm exchange',self.confirm_exchange,
                    primary=True,disabled=pending or app.action_pending or bool(self.exchange_problem(review['amount'])))

    def draw_tamer_row(self, row, entry, badge=True):
        app = self.app
        self.presentation.card(row, self.tab)
        colors = self.presentation.colors(self.tab)
        draw.rect(app.screen, colors['accent'], (row.x, row.y+13, 3, row.height-26), border_radius=2)
        draw.circle(app.screen, colors['ink'], (row.x+34, row.centery), min(28, row.height//2-5))
        sprite = self.portrait(entry.get('tamer'), (43, min(62, row.height-12)))
        if sprite: app.screen.blit(sprite, sprite.get_rect(midbottom=(row.x+34, row.bottom-8)))
        text(app.screen, app.assets, actor_name(entry), (row.x+70, row.y+13), 15, WHITE, True, min(230, row.width-88))
        if badge:
            text(app.screen, app.assets, 'AI RIVAL' if is_bot(entry) else 'PLAYER', (row.x+71, row.y+36), 9, colors['accent'], True)

    def draw_ladder(self, rect):
        app = self.app
        self.button((rect.x, rect.y, 132, 31), 'Current season', lambda:self.ladder('current'), selected=self.scope=='current', small=True)
        self.button((rect.x+141, rect.y, 132, 31), 'Overall career', lambda:self.ladder('career'), selected=self.scope=='career', small=True)
        self.button((rect.x+282, rect.y, 132, 31), 'Past seasons', lambda:self.set_mode('seasons'), selected=self.scope=='history', small=True)
        data = self.data.get('ladder', {})
        own = self.data.get('ranked', {}).get('own', {})
        season = data.get('season') or {}
        subtitle = 'Overall career rating' if self.scope=='career' else season.get('label', 'Current season')
        text(app.screen, app.assets, subtitle, (rect.x, rect.y+45), 15, WHITE, True, rect.width-270)
        text(app.screen, app.assets, f"{number(data.get('total'))} competitors  ·  Top 100", (rect.right-254, rect.y+47), 12, CYAN)
        headings = [(12, 'RANK'), (117, 'COMPETITOR'), (rect.width-353, 'RATING' if self.scope=='career' else 'POINTS'),
                    (rect.width-235, 'WINS'), (rect.width-138, 'LOSSES')]
        for x, label in headings:
            text(app.screen, app.assets, label, (rect.x+x, rect.y+76), 10, MUTED, True)
        area = pygame.Rect(rect.x, rect.y+97, rect.width, max(1, rect.height-126))
        entries = data.get('entries', [])[:100]
        if not entries: self.empty(area, 'No standings yet. Complete a ranked battle to join the ladder.')
        for row, entry, index in self.rows(area, entries, 53):
            mine = entry.get('id') == own.get('id')
            self.presentation.card(row, 'ranked', selected=mine)
            rank = entry.get('rank', index+1)
            if rank<=3:
                draw.circle(app.screen, (64, 48, 36), (row.x+29, row.centery), 17)
            text(app.screen, app.assets, '#'+number(rank), (row.x+12, row.y+13), 15, GOLD if rank<=3 else WHITE, True)
            portrait = self.portrait(entry.get('tamer'), (27, 35))
            if portrait: app.screen.blit(portrait, portrait.get_rect(midbottom=(row.x+84, row.bottom-4)))
            text(app.screen, app.assets, actor_name(entry), (row.x+117, row.y+13), 14, LIME if mine else WHITE, True, row.width-512)
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
        text(app.screen, app.assets, 'THE HALL OF SEASONS', rect.topleft, 12, GOLD, True)
        text(app.screen, app.assets, 'Every completed season preserves its final standings.', (rect.x, rect.y+25), 12, MUTED)
        area = pygame.Rect(rect.x, rect.y+55, rect.width, rect.height-72)
        if not entries: self.empty(area, 'The first season is underway. Final standings will appear here.')
        for row, season, _ in self.grid(area, entries, 122):
            self.presentation.card(row, 'ranked')
            self.presentation.icon(pygame.Rect(row.x+15, row.y+17, 43, 43), 'crown', 'ranked')
            text(app.screen, app.assets, season.get('label', str(season.get('id', 'Season'))), (row.x+73, row.y+15), 17, WHITE, True, row.width-87)
            text(app.screen, app.assets, f"{str(season.get('status', 'completed')).upper()}  /  {number(season.get('competitors'))} competitors",
                 (row.x+74, row.y+43), 10, GOLD, max_width=row.width-90)
            self.button((row.x+74, row.bottom-40, row.width-90, 28), 'View final top 100', lambda ident=season.get('id'):self.ladder('history', ident))

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
        accent = self.presentation.colors('rivals')['accent']
        if self.mode == 'directory':
            app.ui.field((rect.x, rect.y, rect.width-135, 39), 'rival_search', 'Search AI rivals by name…', size=14)
            self.button((rect.right-123, rect.y, 123, 39), 'Find rival', self.directory_search, primary=True)
            directory = data.get('directory', {})
            entries = directory.get('entries', []) if isinstance(directory, dict) else directory
            total = directory.get('total', data.get('total', len(entries))) if isinstance(directory, dict) else data.get('total', len(entries))
            area = pygame.Rect(rect.x, rect.y+55, rect.width, rect.height-101)
            for card, entry, _ in self.grid(area, entries, 102):
                self.draw_tamer_row(card, {**entry, 'is_bot': True})
                status = str(entry.get('status', entry.get('activity', 'Exploring'))).replace('_', ' ').title()
                text(app.screen, app.assets, entry.get('map_name', 'Digital World'), (card.x+71, card.y+55), 12, WHITE, max_width=card.width-205)
                text(app.screen, app.assets, status, (card.x+71, card.y+75), 10, MUTED, max_width=card.width-205)
                self.button((card.right-113, card.y+39, 98, 34), 'Profile', lambda ident=entry.get('id'):self.open_profile(ident))
            if not entries: self.empty(area, 'No rivals match this search.' if data else 'Connect to browse the live rival directory.')
            text(app.screen, app.assets, f'{number(total)} AI rivals  /  {self.offset+1 if total else 0}–{min(self.offset+len(entries), total)}  /  Scroll this page',
                 (rect.x, rect.bottom-25), 11, MUTED, max_width=rect.width-216)
            self.button((rect.right-198, rect.bottom-36, 94, 33), 'Previous', lambda:self.directory_page(-1), disabled=self.offset<=0)
            self.button((rect.right-94, rect.bottom-36, 94, 33), 'Next', lambda:self.directory_page(1), disabled=self.offset+50>=total)
            return
        if self.mode == 'history':
            entries = data.get('history', [])
            text(app.screen, app.assets, 'HEAD-TO-HEAD ARCHIVE', rect.topleft, 12, accent, True)
            text(app.screen, app.assets, 'Every shared battle adds to your rivalry.', (rect.x, rect.y+24), 12, MUTED)
            area = pygame.Rect(rect.x, rect.y+53, rect.width, rect.height-66)
            if not entries: self.empty(area, 'No rival battles yet. Meet an AI rival on the field to get started.')
            for card, entry, _ in self.grid(area, entries, 102):
                self.draw_tamer_row(card, entry)
                wins, losses = entry.get('wins', 0), entry.get('losses', 0)
                text(app.screen, app.assets, f'{number(wins)} W  /  {number(losses)} L', (card.x+71, card.y+56), 15, GOLD, True)
                text(app.screen, app.assets, 'Last battle  '+timestamp(entry.get('last_at', entry.get('last_battle_at'))),
                     (card.x+71, card.y+78), 9, MUTED, max_width=card.width-200)
                bot_id = entry.get('bot_id', entry.get('rival_id', entry.get('id')))
                if bot_id and is_bot(entry): self.button((card.right-111, card.y+39, 96, 34), 'Profile', lambda ident=bot_id:self.open_profile(ident))
            return
        entries = data.get('challenges', data.get('pending', []))
        left = pygame.Rect(rect.x, rect.y, int(rect.width*.56)-8, rect.height)
        right = pygame.Rect(left.right+18, rect.y, rect.right-left.right-18, rect.height)
        text(app.screen, app.assets, 'CHALLENGE INBOX', left.topleft, 12, accent, True)
        text(app.screen, app.assets, f'{number(len(entries))} pending  /  Friendly battles use no ranked energy', (left.x, left.y+25), 11, MUTED, max_width=left.width)
        area = pygame.Rect(left.x, left.y+53, left.width, left.height-64)
        if not entries: self.empty(area, 'No challenges yet. Meet a rival on your map.')
        for row, entry, _ in self.rows(area, entries, 119):
            rival = entry.get('rival', entry)
            self.draw_tamer_row(row, {**rival, 'is_bot': True})
            ident = entry.get('challenge_id', entry.get('id'))
            text(app.screen, app.assets, 'INVITES YOU TO BATTLE', (row.x+71, row.y+57), 9, MUTED, True)
            self.button((row.right-211, row.bottom-42, 96, 30), 'Accept', lambda cid=ident:self.request('accept', challenge_id=cid), primary=True, disabled=self.busy)
            self.button((row.right-105, row.bottom-42, 92, 30), 'Decline', lambda cid=ident:self.request('decline', challenge_id=cid), disabled=self.busy)
        text(app.screen, app.assets, 'NEARBY TAMERS', right.topleft, 12, accent, True)
        text(app.screen, app.assets, 'Your next rivalry begins in the field.', (right.x, right.y+25), 11, MUTED, max_width=right.width)
        nearby = data.get('nearby', [])
        lower = pygame.Rect(right.x, right.y+53, right.width, right.height-64)
        if not nearby: self.empty(lower, 'Explore a sector to meet roaming tamers.')
        columns = 2
        width = (lower.width-12)//columns
        h = min(124, max(99, lower.height//3))
        for i, rival in enumerate(nearby[:6]):
            card = pygame.Rect(lower.x+(i%columns)*(width+12), lower.y+(i//columns)*h, width, h-10)
            self.presentation.card(card, 'rivals')
            sprite = self.portrait(rival.get('tamer'), (44, 57), moving=True)
            if sprite: app.screen.blit(sprite, sprite.get_rect(midbottom=(card.x+35, card.bottom-17)))
            text(app.screen, app.assets, actor_name(rival), (card.x+67, card.y+23), 12, WHITE, True, card.width-80)
            text(app.screen, app.assets, 'AI RIVAL', (card.x+67, card.y+46), 9, accent, True)
            text(app.screen, app.assets, 'View profile →', (card.x+67, card.y+67), 10, MUTED, max_width=card.width-80)
            app.ui.actions.append((card, lambda ident=rival.get('id'):self.open_profile(ident)))

    def draw_profile(self, rect):
        app, data = self.app, self.data.get('profile', {})
        profile = data.get('bot', data.get('profile', data))
        if not profile or profile.get('id') != self.profile_id:
            self.empty(rect, 'Loading this rival’s dossier…')
            return
        accent = self.presentation.colors('rivals')['accent']
        header = pygame.Rect(rect.x, rect.y, rect.width, 100)
        self.presentation.card(header, 'rivals', accent=True)
        draw.circle(app.screen, (13, 29, 44), (rect.x+52, rect.y+51), 39)
        sprite = self.portrait(profile.get('tamer'), (61, 80), moving=True)
        if sprite: app.screen.blit(sprite, sprite.get_rect(midbottom=(rect.x+52, rect.y+87)))
        text(app.screen, app.assets, actor_name(profile), (rect.x+107, rect.y+13), 23, WHITE, True, rect.width-349)
        text(app.screen, app.assets, 'AI RIVAL  /  '+str(profile.get('map_name', 'Digital World')), (rect.x+108, rect.y+45), 11, accent, True, rect.width-350)
        activity = str(profile.get('status', profile.get('activity', 'Exploring'))).replace('_', ' ').title()
        text(app.screen, app.assets, activity+'  ·  Next: '+str(profile.get('next_activity', 'Training')).replace('_', ' '), (rect.x+108, rect.y+65), 11, MUTED, max_width=rect.width-350)
        if profile.get('training_round'):
            training = (f"Training team {number(profile['training_round'])}  ·  {number(profile.get('training_partners'))} partners  ·  Goal Lv.{number(profile.get('training_goal'))}")
            if profile.get('coverage_duty'): training += '  ·  Veteran visit'
            text(app.screen, app.assets, training, (rect.x+108, rect.y+82), 9, GOLD, max_width=rect.width-350)
        same_map = profile.get('map_id') == app.state.get('map_id') and not app.state.get('in_lab')
        status = str(profile.get('status', '')).lower()
        rival_busy = bool(profile.get('battle') or profile.get('in_lab') or 'battle' in status or 'lab' in status)
        self.button((rect.right-221, rect.y+17, 204, 36), 'Challenge rival', lambda:self.request('challenge', bot_id=self.profile_id), primary=True, disabled=self.busy or not same_map or rival_busy)
        text(app.screen, app.assets, 'Meet on the same map to battle' if not same_map else 'Rival is busy · Check back shortly' if rival_busy else 'Move nearby · No ranked energy',
             (rect.right-221, rect.y+65), 10, MUTED, max_width=204)
        party = profile.get('party', [])[:6]
        width = (rect.width-5*10)//6
        text(app.screen, app.assets, 'PARTNER ROSTER', (rect.x, rect.y+113), 10, accent, True)
        for i, mon in enumerate(party):
            card = pygame.Rect(rect.x+i*(width+10), rect.y+136, width, 117)
            self.presentation.card(card, 'rivals', selected=i<3)
            draw.ellipse(app.screen, (18, 39, 53), (card.centerx-33, card.y+56, 66, 12))
            image = app.assets.sprite(mon.get('species_id'), (79, 64), now=app.now)
            if image: app.screen.blit(image, image.get_rect(midbottom=(card.centerx, card.y+67)))
            text(app.screen, app.assets, mon.get('name', 'Digimon'), (card.centerx, card.y+83), 12, WHITE, True, card.width-12, True)
            text(app.screen, app.assets, f"Lv.{mon.get('level', 1)}  /  {'ACTIVE' if i<3 else 'RESERVE'}", (card.centerx, card.y+104), 9, accent if i<3 else MUTED, center=True)
        stats = profile.get('stats', {})
        pairs = [('Wild wins / losses', f"{number(stats.get('wild_wins'))} / {number(stats.get('wild_losses'))}"),
                 ('Ranked wins / losses', f"{number(stats.get('ranked_wins'))} / {number(stats.get('ranked_losses'))}"),
                 ('Materialized', number(stats.get('materialized'))), ('Levels gained', number(stats.get('level_ups'))),
                 ('Scans / ready', number(stats.get('scans'))+' / '+number(profile.get('scan_ready'))),
                 ('Partner swaps', number(stats.get('party_swaps'))), ('Sector changes', number(stats.get('travels'))),
                 ('Heals / items', number(stats.get('heals'))+' / '+number(stats.get('items_used'))),
                 ('Team changes', number(stats.get('training_rotations'))), ('Teams trained', number(stats.get('teams_trained'))),
                 ('Veteran visits', number(stats.get('coverage_visits'))), ('Banked partners', number(profile.get('storage_count')))]
        stats_area = pygame.Rect(rect.x, rect.y+270, rect.width, max(1, rect.height-270))
        columns, gap = 4, 8
        metric_width = (rect.width-gap*(columns-1))//columns
        metric_height = min(70, max(46, (stats_area.height-2*gap)//3))
        for i, (label, value) in enumerate(pairs):
            self.metric(pygame.Rect(stats_area.x+(i%columns)*(metric_width+gap), stats_area.y+(i//columns)*(metric_height+gap), metric_width, metric_height), label, value, accent)

    COUNTERS = [('wild_wins', 'Wild wins'), ('wild_losses', 'Wild losses'), ('ranked_wins', 'Ranked wins'), ('ranked_losses', 'Ranked losses'),
                ('scans', 'Scan events'), ('materialized', 'Materialized'), ('paradox_materialized', 'Paradox created'), ('level_ups', 'Levels gained'),
                ('xp_earned', 'Battle XP'), ('party_swaps', 'Partner swaps'), ('travels', 'Sector changes'), ('heals', 'Healing visits'),
                ('items_used', 'Items used'), ('purchases', 'Shop purchases'), ('evolutions', 'Digivolutions'), ('devolutions', 'De-digivolutions'),
                ('rival_wins', 'Rival wins'), ('rival_losses', 'Rival losses'), ('scan_data', 'Scan data earned'), ('walking_distance', 'Distance walked'),
                ('training_rotations', 'Team changes'), ('teams_trained', 'Teams trained'), ('coverage_visits', 'Veteran visits')]

    def draw_activity(self, rect):
        app, data = self.app, self.data.get('activity', {})
        if not data:
            self.empty(rect, 'Connect to your dedicated server to see the world in motion.' if app.args.demo else 'Loading the world activity feed…')
            return
        counters = data.get('counters', data.get('totals', {}))
        accent = self.presentation.colors('activity')['accent']
        summary = [('AI population', number(data.get('population'))), ('Active tamers', number(data.get('active'))),
                   ('Sectors occupied', f"{number(data.get('occupied_maps'))} / {number(data.get('total_maps'))}"),
                   ('Recorded events', number(len(data.get('events', [])[:100])))]
        width = (rect.width-36)//4
        for i, (label, value) in enumerate(summary):
            self.metric(pygame.Rect(rect.x+i*(width+12), rect.y, width, 65), label, value)
        left = pygame.Rect(rect.x, rect.y+82, min(330, rect.width//3), rect.height-82)
        self.presentation.card(left, 'activity')
        text(app.screen, app.assets, 'WORLD TOTALS', (left.x+14, left.y+14), 10, accent, True)
        keys = self.COUNTERS[self.stats_page*12:(self.stats_page+1)*12]
        metric_h = min(69, max(44, (left.height-78)//6))
        metric_w = (left.width-34)//2
        for i, (key, label) in enumerate(keys):
            cell = pygame.Rect(left.x+12+(i%2)*(metric_w+10), left.y+39+(i//2)*metric_h, metric_w, metric_h-4)
            text(app.screen, app.assets, label.upper(), (cell.x+2, cell.y+3), 8, MUTED, True, cell.width-4)
            text(app.screen, app.assets, number(counters.get(key)), (cell.x+2, cell.y+18), 20 if metric_h>46 else 18,
                 GOLD if 'loss' in key else accent, True, cell.width-4)
            if i<10: draw.line(app.screen, (30, 54, 62), (cell.x, cell.bottom), (cell.right, cell.bottom))
        self.button((left.x+12, left.bottom-35, left.width-24, 25), 'More counters' if self.stats_page==0 else 'Main counters',
                    lambda:setattr(self, 'stats_page', 1-self.stats_page))
        main = pygame.Rect(left.right+18, left.y, rect.right-left.right-18, left.height)
        text(app.screen, app.assets, 'ON THE NETWORK', main.topleft, 12, accent, True)
        text(app.screen, app.assets, 'RECORDED ADVENTURES', (main.right-155, main.y+3), 9, MUTED, True)
        filter_width = min(91, (main.width-32)//5)
        for i, label in enumerate(('All', 'Wild', 'Ranked', 'Progress', 'Travel')):
            self.button((main.x+i*(filter_width+8), main.y+28, filter_width, 29), label,
                        lambda value=label:self.set_activity_filter(value), selected=self.activity_filter==label)
        events = data.get('events', [])[:100]
        if self.activity_filter != 'All':
            tokens = {'Wild': ('wild', 'scan'), 'Ranked': ('rank',), 'Progress': ('level', 'material', 'evol', 'swap', 'heal', 'item', 'purchase', 'training'), 'Travel': ('travel', 'relocat', 'map', 'coverage')}[self.activity_filter]
            events = [event for event in events if any(token in str(event.get('kind', '')).lower() for token in tokens)]
        area = pygame.Rect(main.x, main.y+71, main.width, max(1, main.height-94))
        if not events: self.empty(area, 'Activity appears here as the server population plays.')
        for row, event, _ in self.rows(area, events, 76):
            self.presentation.card(row, 'activity')
            kind = str(event.get('kind', 'activity')).replace('_', ' ').upper()
            event_color = GOLD if 'LOSS' in kind else accent
            draw.circle(app.screen, (19, 57, 55), (row.x+23, row.centery), 12)
            draw.circle(app.screen, event_color, (row.x+23, row.centery), 4)
            text(app.screen, app.assets, actor_name(event), (row.x+47, row.y+11), 12, WHITE, True, max(80, row.width-175))
            text(app.screen, app.assets, timestamp(event.get('at')), (row.right-112, row.y+13), 9, MUTED, max_width=101)
            text(app.screen, app.assets, kind, (row.x+47, row.y+30), 8, event_color, True, row.width-62)
            text(app.screen, app.assets, event.get('text', kind), (row.x+47, row.y+47), 11, WHITE, max_width=row.width-62)
            if event.get('bot_id'): app.ui.actions.append((row, lambda ident=event['bot_id']:self.open_profile(ident)))
        text(app.screen, app.assets, f'{len(events)} / 100 latest records  ·  Click a rival to inspect  ·  Scroll to browse',
             (main.x, main.bottom-14), 10, MUTED, max_width=main.width)

    def set_activity_filter(self, value):
        self.cue('tab')
        self.activity_filter = value
        self.app.scroll = 0

    def draw_maps(self, rect):
        app, data = self.app, self.data.get('activity', {})
        if not data:
            self.empty(rect, 'Loading sector population…' if not app.args.demo else 'Connect to view occupied sectors.')
            return
        entries = sorted(data.get('maps', []), key=lambda entry: (-entry.get('count', 0), entry.get('name', '')))
        accent = self.presentation.colors('activity')['accent']
        text(app.screen, app.assets, 'THE LIVING DIGITAL WORLD', rect.topleft, 12, accent, True)
        text(app.screen, app.assets, 'Rivals explore, train and retreat across the world. Occupancy is relative to the busiest sector.', (rect.x, rect.y+25), 12, MUTED, max_width=rect.width)
        area = pygame.Rect(rect.x, rect.y+59, rect.width, rect.height-85)
        peak = max(1, entries[0].get('count', 1)) if entries else 1
        for row, entry, _ in self.grid(area, entries, 91):
            self.presentation.card(row, 'activity')
            draw.rect(app.screen, (24, 54, 61), (row.x+16, row.y+18, 40, 42), border_radius=7)
            draw.polygon(app.screen, accent, [(row.x+24, row.y+32), (row.x+35, row.y+26), (row.x+47, row.y+32), (row.x+47, row.y+46), (row.x+35, row.y+52), (row.x+24, row.y+46)], 1)
            draw.line(app.screen, accent, (row.x+35, row.y+39), (row.x+35, row.y+52))
            draw.line(app.screen, accent, (row.x+24, row.y+32), (row.x+35, row.y+39))
            draw.line(app.screen, accent, (row.x+47, row.y+32), (row.x+35, row.y+39))
            text(app.screen, app.assets, entry.get('name', entry.get('id', 'Map')), (row.x+72, row.y+13), 15, WHITE, True, row.width-169)
            text(app.screen, app.assets, 'SECTOR LEVEL '+str(entry.get('level', '?')), (row.x+73, row.y+38), 9, MUTED, True)
            text(app.screen, app.assets, number(entry.get('count'))+' AI', (row.right-85, row.y+18), 15, accent, True, 72)
            bar(app.screen, pygame.Rect(row.x+73, row.y+62, row.width-92, 5), entry.get('count', 0), peak, accent)
        if not entries: self.empty(area, 'Sector data will appear when the world population is ready.')
        text(app.screen, app.assets, f"{len(entries)} sectors  /  {number(data.get('occupied_maps'))} occupied  ·  Scroll to explore all sectors", (rect.x, rect.bottom-14), 11, MUTED, max_width=rect.width)


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
        ranked = self.result.get('ranked', True)
        presentation = app.community.presentation
        theme = 'ranked' if ranked else 'rivals'
        presentation.card(rect, theme, accent=True)
        text(app.screen, app.assets, 'RANKED BATTLE' if ranked else 'RIVAL CHALLENGE', (rect.x+18, rect.y+17), 15, CYAN, True)
        title = self.result.get('attacker_name', 'Your team')+'  vs  '+self.result.get('defender_name', 'Rival')
        text(app.screen, app.assets, title, (rect.centerx, rect.y+48), 18, WHITE, True, rect.width-45, True)
        arena = pygame.Rect(rect.x+15, rect.y+50, rect.width-30, max(190, rect.height-120))
        old_view, old_now = app.viewport, app.now
        app.viewport = arena
        event = self.events[self.index] if not self.done else None
        draw.polygon(app.screen, (20, 38, 54), [(arena.x, arena.y+90), (arena.centerx-42, arena.y+110), (arena.centerx-12, arena.bottom-8), (arena.x, arena.bottom-8)])
        draw.polygon(app.screen, (38, 29, 50), [(arena.right, arena.y+90), (arena.centerx+42, arena.y+110), (arena.centerx+12, arena.bottom-8), (arena.right, arena.bottom-8)])
        draw.line(app.screen, (67, 82, 101), (arena.centerx, arena.y+115), (arena.centerx, arena.bottom-8), 1)
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
                    text(app.screen, app.assets, mon.get('name', 'Digimon'), (position.x, position.y-size[1]-20), 13, WHITE, True, 190, True)
                    text(app.screen, app.assets, f"Lv.{mon.get('level', 1)}", (position.x, position.y-size[1]-5), 10, MUTED, center=True)
                    bar(app.screen, pygame.Rect(position.x-61, position.y+12, 122, 7), mon.get('hp', 0), mon.get('max_hp', 1), LIME if side=='player' else RED)
                    text(app.screen, app.assets, f"{number(mon.get('hp'))} / {number(mon.get('max_hp'))}", (position.x, position.y+27), 10, MUTED, center=True)
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
