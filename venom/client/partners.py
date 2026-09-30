"""Partner dossiers, authoritative evolution routes and a searchable DigiBank."""
from __future__ import annotations

import math
import pygame

from venom.common.game import FARM_CAPACITY
from .varieties import variety_of, name_color, VARIETY_NAMES
from .render import draw
from .widgets import text, bar, wrap, WHITE, CYAN, LIME, GOLD, RED


class PartnerScreen:
    MODES = ('roster', 'evolution', 'storage')

    def __init__(self, app):
        self.app = app
        self.mode = 'roster'
        self.route_filter = 'all'
        self._storage_query = ''
        self.pending_exchange = None

    def open_mode(self, mode):
        if mode not in self.MODES:
            return
        app = self.app
        self.mode = mode
        self.pending_exchange = None
        app.scroll = 0
        app.ui.focus = None
        pygame.key.stop_text_input()
        if app.menu != 'party':
            app.set_menu('party')
        else:
            app.ui.actions, app.ui.fields = [], []
            app.audio.cue('tab', now=app.now)

    @property
    def theme(self):
        return 'party' if self.mode == 'roster' else self.mode

    def select(self, index):
        self.app.selected_party = index
        self.app.scroll = 0

    def _button(self, rect, label, callback, **kwargs):
        self.app.ui.button(rect, label, callback, small=True,
                           accent=self.app.presentation.colors(self.theme)['accent'], **kwargs)

    def _portrait(self, species_id, rect):
        self.app.presentation.sprite(pygame.Rect(rect), species_id, now=self.app.now)

    def _selected(self):
        party = self.app.state.get('party', [])
        self.app.selected_party = max(0, min(self.app.selected_party, len(party)-1)) if party else 0
        return party[self.app.selected_party] if party else None

    def _peace(self):
        return not self.app.action_pending and not self.app.state.get('battle')

    def _lab_ready(self):
        return self._peace() and bool(self.app.state.get('in_lab') or self.app.state.get('in_farm'))

    def manage_stored(self, uid):
        """Open the resident's farm dossier; ownership stays server authoritative."""
        if not self._peace() or not uid:
            return
        self.app.enter_farm()
        self.app.farm_screen.select(uid)

    def choose_exchange_slot(self):
        party = self.app.state.get('party', [])
        if party:
            self.app.selected_party = (self.app.selected_party+1) % len(party)

    def request_exchange(self, uid):
        if not self._lab_ready():
            return
        mon = self._selected()
        if mon:
            self.pending_exchange = (mon.get('uid'), uid)

    def confirm_exchange(self):
        if not self.pending_exchange or not self._lab_ready():
            return
        party_uid, stored_uid = self.pending_exchange
        index = next((i for i, mon in enumerate(self.app.state.get('party', []))
                      if mon.get('uid') == party_uid), None)
        stored = any(mon.get('uid') == stored_uid for mon in self.app.state.get('storage', []))
        self.pending_exchange = None
        if index is not None and stored:
            self.app.send('party', action='exchange', party_index=index, uid=stored_uid)

    def routes(self):
        """Read the exact selected party's server routes, without inventing any."""
        self._selected()
        options = self.app.state.get('evolution_options', [])
        index = self.app.selected_party
        if isinstance(options, list):
            return options[index] if index < len(options) and isinstance(options[index], list) else []
        return options.get(str(index), []) if isinstance(options, dict) else []

    def draw(self, rect):
        app, rect = self.app, pygame.Rect(rect)
        if self.mode not in self.MODES:
            self.mode = 'roster'
        theme = self.theme
        p = app.presentation.colors(theme)
        heading = {'roster': ('Your partners. Your next adventure.', 'Choose your lead partner, review your team and prepare for the field.', 'PARTNER LINK'),
                   'evolution': ('Discover your next evolution.', 'Explore each route. Train the requirements. Shape your partner’s future.', 'DIGILAB  /  EVOLUTION CHAMBER'),
                   'storage': ('A home for every partner.', 'Your stored partners live in DigiFarm. Organize your team here, or visit them to feed and train.', 'DIGIFARM  /  PARTNER ARCHIVE')}[self.mode]
        body = app.presentation.shell(rect, theme, heading[0], heading[1], heading[2])
        for index, (mode, label) in enumerate((('roster', 'Active party'), ('evolution', 'Digivolution'), ('storage', 'DigiBank'))):
            self._button((body.x+index*142, body.y, 132, 34), label,
                         lambda m=mode: self.open_mode(m), selected=self.mode == mode)
        party = app.state.get('party', [])
        self._button((body.right-368, body.y, 105, 34), 'DigiFarm', app.enter_farm,
                     disabled=not self._peace())
        self._button((body.right-253, body.y, 107, 34), 'DigiLab', app.enter_lab,
                     disabled=not self._peace())
        return_label = 'DigiFarm  Esc' if app.state.get('in_farm') else 'DigiLab  Esc' if app.state.get('in_lab') else 'Field  Esc'
        self._button((body.right-136, body.y, 136, 34), return_label, lambda: app.set_menu('party'))
        content = pygame.Rect(body.x, body.y+48, body.width, body.height-48)
        {'roster': self.draw_roster, 'evolution': self.draw_evolution, 'storage': self.draw_storage}[self.mode](content)
        if self.mode == 'roster':
            footer = 'FORMATION  ·  The first three partners fight. Slots four to six stay in reserve.'
        elif not (app.state.get('in_lab') or app.state.get('in_farm')):
            footer = 'FIELD PREVIEW  ·  Enter DigiFarm or DigiLab to digivolve, deposit or withdraw partners.'
        elif self.mode == 'evolution':
            footer = 'EVOLUTION  ·  Level resets to 1. CAM is retained. ABI increases, up to 200.'
        else:
            count = len(app.state.get('storage', []))
            footer = (f'LEGACY STORAGE  ·  Every partner is preserved. Withdraw below {FARM_CAPACITY} residents before adding more.'
                      if count > FARM_CAPACITY else f'DIGIFARM  ·  {FARM_CAPACITY} resident capacity. Withdrawn partners return with full HP and SP. Feeding is optional.')
        text(app.screen, app.assets, footer, (rect.x+25, rect.bottom-18), 10, p['muted'], max_width=rect.width-50)
        if self.pending_exchange:
            self.draw_exchange_confirmation(rect)

    def draw_roster(self, rect):
        app, art = self.app, self.app.presentation
        p = art.colors(self.theme)
        mon = self._selected()
        width = max(315, int(rect.width*.355))
        dossier = pygame.Rect(rect.x, rect.y, width, rect.height)
        art.card(dossier, self.theme, accent=True)
        if mon:
            self.dossier(dossier, mon)
        else:
            wrap(app.screen, app.assets, 'Your next partnership starts here.', (dossier.x+24, dossier.y+38),
                 dossier.width-48, 27, WHITE, 3)
            wrap(app.screen, app.assets, 'Visit Scan & Materialize, or withdraw a partner from DigiBank.',
                 (dossier.x+24, dossier.y+156), dossier.width-48, 15, p['muted'], 4)
            self._button((dossier.x+23, dossier.bottom-100, dossier.width-46, 35), 'Open DigiBank',
                         lambda: self.open_mode('storage'), primary=True)
            self._button((dossier.x+23, dossier.bottom-55, dossier.width-46, 35), 'Scan & Materialize',
                         lambda: app.set_menu('scan'))
        grid = pygame.Rect(dossier.right+16, rect.y, rect.right-dossier.right-16, rect.height)
        text(app.screen, app.assets, 'YOUR FORMATION', (grid.x, grid.y+2), 11, p['accent'], True)
        text(app.screen, app.assets, 'Select a partner to inspect', (grid.right-164, grid.y+3), 10, p['muted'])
        gap = 12
        card_w = (grid.width-2*gap)//3
        card_h = (grid.height-32-gap)//2
        party = app.state.get('party', [])
        for index in range(6):
            card = pygame.Rect(grid.x+(index%3)*(card_w+gap), grid.y+32+(index//3)*(card_h+gap), card_w, card_h)
            art.card(card, self.theme, selected=bool(mon) and index == app.selected_party)
            if index >= len(party):
                draw.circle(app.screen, p['line'], (card.centerx, card.centery-14), 28, 1)
                text(app.screen, app.assets, '+', (card.centerx, card.centery-15), 32, p['muted'], center=True)
                text(app.screen, app.assets, f'{index+1:02d}  /  OPEN SLOT', (card.centerx, card.bottom-45),
                     10, p['muted'], True, card.width-20, True)
                continue
            member = party[index]
            role = 'LEAD PARTNER' if index == 0 else 'ACTIVE TEAM' if index < 3 else 'RESERVE'
            text(app.screen, app.assets, f'{index+1:02d}  /  {role}', (card.x+12, card.y+12), 9,
                 p['accent'] if index < 3 else p['muted'], True, card.width-24)
            image_height = max(42, min(104, card.height-99))
            self._portrait(member.get('species_id'), (card.x+18, card.y+34, card.width-36, image_height))
            text(app.screen, app.assets, member.get('name', 'Partner'), (card.centerx, card.bottom-49), 16,
                 name_color(member, app.assets.species, WHITE), True, card.width-22, True)
            text(app.screen, app.assets, f"Lv.{member.get('level', 1)}  ·  {member.get('hp', 0)}/{member.get('max_hp', 0)} HP",
                 (card.centerx, card.bottom-25), 10, p['muted'], False, card.width-20, True)
            app.ui.actions.append((card, lambda i=index: self.select(i)))

    def dossier(self, rect, mon):
        app, art = self.app, self.app.presentation
        p = art.colors(self.theme)
        index = app.selected_party
        text(app.screen, app.assets, VARIETY_NAMES[variety_of(mon, app.assets.species)].upper()+' PARTNER' if variety_of(mon, app.assets.species) != 'normal' else 'PARTNER DOSSIER', (rect.x+20, rect.y+17), 10, name_color(mon, app.assets.species, p['accent']), True)
        text(app.screen, app.assets, f"Lv.{mon.get('level', 1):02d}", (rect.right-78, rect.y+13), 24, WHITE, True)
        bottom = rect.y+min(170, max(122, rect.height-277))
        draw.ellipse(app.screen, p['line'], (rect.centerx-92, bottom-19, 184, 29), 1)
        draw.ellipse(app.screen, p['glow'], (rect.centerx-72, bottom-15, 144, 21))
        self._portrait(mon.get('species_id'), (rect.x+40, rect.y+42, rect.width-80, bottom-rect.y-42))
        text(app.screen, app.assets, mon.get('name', 'Partner'), (rect.centerx, bottom+22), 27,
             name_color(mon, app.assets.species, WHITE), True, rect.width-35, True)
        species = app.assets.species.get(mon.get('species_id'), {})
        info = f"{species.get('stage', '').replace('_', ' ').title()}  ·  {mon.get('type', species.get('type', '?')).title()}  /  {mon.get('attribute', species.get('attribute', '?')).title()}"
        text(app.screen, app.assets, info, (rect.centerx, bottom+49), 11, p['muted'], max_width=rect.width-35, center=True)
        y = bottom+72
        half = (rect.width-52)//2
        for n, (resource, color) in enumerate((('hp', LIME), ('sp', CYAN))):
            value, maximum = mon.get(resource, 0), mon.get('max_'+resource, 1)
            x = rect.x+20+n*(half+12)
            text(app.screen, app.assets, f'{resource.upper()}  {value}/{maximum}', (x, y), 10, p['muted'], max_width=half)
            bar(app.screen, pygame.Rect(x, y+17, half, 5), value, maximum, color)
        y += 34
        text(app.screen, app.assets, f"ABI {mon.get('abi', 0)} / 200     CAM {mon.get('cam', 0)}%",
             (rect.x+20, y), 12, p['accent'], True, rect.width-40)
        y += 26
        for n, key in enumerate(('atk', 'def', 'int', 'spd')):
            x = rect.x+20+n*(rect.width-40)//4
            text(app.screen, app.assets, key.upper(), (x, y), 9, p['muted'], True)
            text(app.screen, app.assets, str(mon.get(key, 0)), (x, y+16), 20, WHITE, True)
        xp = f"EXP {mon.get('xp', 0):,}"
        if mon.get('next_xp'):
            xp += f"  /  {mon['next_xp']:,}"
        text(app.screen, app.assets, xp,
             (rect.x+20, rect.bottom-68), 10, p['muted'], max_width=rect.width-40)
        button_width = (rect.width-50)//2
        self._button((rect.x+20, rect.bottom-47, button_width, 32), 'Make leader',
                     lambda: app.send('party', action='lead', index=index), primary=True,
                     disabled=index == 0 or not self._peace())
        self._button((rect.x+30+button_width, rect.bottom-47, button_width, 32), 'Move to storage',
                     lambda: app.send('party', action='deposit', index=index),
                     disabled=not self._lab_ready() or len(app.state.get('party', [])) < 2
                     or len(app.state.get('storage', [])) >= FARM_CAPACITY)

    def partner_strip(self, rect, mon):
        app, art = self.app, self.app.presentation
        p = art.colors(self.theme)
        art.card(rect, self.theme)
        if not mon:
            text(app.screen, app.assets, 'No active partner — withdraw one from DigiBank to view routes.',
                 (rect.x+20, rect.centery-8), 15, p['muted'], max_width=rect.width-40)
            return
        self._portrait(mon.get('species_id'), (rect.x+15, rect.y+10, 69, rect.height-19))
        party = app.state.get('party', [])
        width = min(86, (rect.width-385)//6)
        start = rect.right-14-len(party)*(width+7)
        text(app.screen, app.assets, mon.get('name', 'Partner'), (rect.x+100, rect.y+17), 21,
             name_color(mon, app.assets.species, WHITE), True, max(150, start-rect.x-115))
        text(app.screen, app.assets, f"Lv.{mon.get('level', 1)}  ·  ABI {mon.get('abi', 0)}  ·  CAM {mon.get('cam', 0)}%",
             (rect.x+101, rect.y+49), 11, p['muted'], max_width=260)
        for index, member in enumerate(party):
            card = pygame.Rect(start+index*(width+7), rect.y+12, width, rect.height-24)
            art.card(card, self.theme, selected=index == app.selected_party)
            self._portrait(member.get('species_id'), (card.x+7, card.y+5, card.width-14, card.height-10))
            app.ui.actions.append((card, lambda i=index: self.select(i)))

    def set_route_filter(self, value):
        self.route_filter = value
        self.app.scroll = 0
        self.app.audio.cue('tab', now=self.app.now)

    def open_abi_shop(self):
        self.app.shop_screen.filter('abi')
        self.app.set_menu('shop')

    def abi_help(self, rect, mon):
        app = self.app
        p = app.presentation.colors(self.theme)
        app.presentation.card(rect, self.theme)
        text(app.screen, app.assets, 'Need ABI? ABI DigiMeat adds +1 permanently (cap 200).',
             (rect.x+13, rect.y+10), 12, p['accent'], True)
        text(app.screen, app.assets, 'No de-digivolution needed. Other route requirements still apply.',
             (rect.x+13, rect.y+31), 10, p['muted'])
        owned = app.state.get('inventory', {}).get('digimeat_abi', 0)
        uid = mon.get('uid') if mon else None
        abi = mon.get('abi', 0) if mon else 0
        self._button((rect.right-317, rect.y+10, 154, 34), 'ABI DigiMeat shop', self.open_abi_shop)
        label = 'Use +1 ABI' if owned else 'No ABI meat'
        self._button((rect.right-153, rect.y+10, 140, 34), label,
                     lambda: app.shop_screen.use('digimeat_abi', uid=uid),
                     primary=True, disabled=not app.shop_screen.can_use_abi(uid))

    def draw_evolution(self, rect):
        app = self.app
        p = app.presentation.colors(self.theme)
        mon = self._selected()
        self.partner_strip(pygame.Rect(rect.x, rect.y, rect.width, 82), mon)
        self.abi_help(pygame.Rect(rect.x, rect.y+91, rect.width, 55), mon)
        routes = [r for r in self.routes() if self.route_filter == 'all'
                  or (bool(r.get('devolve')) == (self.route_filter == 'down'))]
        for index, (key, label) in enumerate((('all', 'All routes'), ('up', 'Digivolve'), ('down', 'De-digivolve'))):
            self._button((rect.x+index*123, rect.y+157, 113, 28), label,
                         lambda k=key: self.set_route_filter(k), selected=self.route_filter == key)
        text(app.screen, app.assets, f'{len(routes)} ROUTES', (rect.right-113, rect.y+166), 10, p['muted'], True)
        top = rect.y+197
        page_size = 3
        offset = min(max(0, app.scroll), max(0, len(routes)-page_size))
        app.scroll = offset
        gap = 14
        width = (rect.width-gap*2)//3
        height = rect.bottom-top-40
        for index, route in enumerate(routes[offset:offset+page_size]):
            self.route_card(pygame.Rect(rect.x+index*(width+gap), top, width, height), mon, route)
        if mon and 0 < len(routes[offset:offset+page_size]) < page_size:
            index = len(routes[offset:offset+page_size])
            self.evolution_protocol(pygame.Rect(rect.x+index*(width+gap), top, width, height), mon)
        if not routes:
            text(app.screen, app.assets, 'No routes are available for this selection.',
                 (rect.centerx, top+height//2), 20, p['muted'], max_width=rect.width-50, center=True)
        self.pagination(pygame.Rect(rect.x, rect.bottom-30, rect.width, 30), len(routes), page_size, 'routes')

    @staticmethod
    def requirements(mon, route):
        result = []
        for key in ('level', 'abi', 'cam'):
            required = int(route.get(key, 0))
            if required > 0:
                result.append((key.upper(), mon.get(key, 0), required))
        for key, required in route.get('stats', {}).items():
            result.append((key.upper(), mon.get('max_'+key, mon.get(key, 0)), required))
        return result

    def route_card(self, rect, mon, route):
        app, art = self.app, self.app.presentation
        p = art.colors(self.theme)
        eligible = bool(route.get('eligible'))
        down = bool(route.get('devolve'))
        art.card(rect, self.theme, accent=eligible)
        color = p['accent'] if down else p['secondary']
        draw.line(app.screen, color, (rect.x+10, rect.y+1), (rect.right-11, rect.y+1), 2)
        text(app.screen, app.assets, 'DE-DIGIVOLUTION' if down else 'DIGIVOLUTION',
             (rect.x+16, rect.y+14), 9, color, True)
        requirements = self.requirements(mon, route)
        requirement_rows = max(1, math.ceil(len(requirements)/2))
        req_height = requirement_rows*24
        req_y = rect.bottom-55-req_height
        name_y = req_y-50
        art_space = max(26, name_y-rect.y-43)
        image_height = min(172, art_space)
        image_y = rect.y+31+(art_space-image_height)//2
        draw.ellipse(app.screen, p['line'], (rect.centerx-67, image_y+image_height-7, 134, 15), 1)
        self._portrait(route.get('to'), (rect.x+45, image_y, rect.width-90, image_height))
        text(app.screen, app.assets, route.get('name', route.get('to', '?')), (rect.x+16, name_y),
             21, name_color({'species_id': route.get('to')}, app.assets.species, WHITE), True, rect.width-32)
        gain = (5+mon.get('level', 1)//5) if down else (2+mon.get('level', 1)//10)
        abi = min(200, mon.get('abi', 0)+gain)
        species = app.assets.species.get(route.get('to'), {})
        text(app.screen, app.assets, f"{species.get('stage', '').replace('_', ' ').title()} · Lv.1 · ABI {abi}",
             (rect.x+16, name_y+28), 10, p['muted'], max_width=rect.width-32)
        cell_w = (rect.width-40)//2
        for index, (label, actual, required) in enumerate(requirements):
            box = pygame.Rect(rect.x+16+(index%2)*(cell_w+8), req_y+(index//2)*24, cell_w, 20)
            passed = actual >= required
            draw.rect(app.screen, (22, 57, 52) if passed else (62, 35, 52), box, border_radius=3)
            text(app.screen, app.assets, f'{label}  {actual} / {required}', (box.x+7, box.y+4), 9,
                 LIME if passed else (245, 161, 176), max_width=box.width-14)
        if not requirements:
            missing = route.get('missing', [])
            label = 'Requirements met' if eligible else ' · '.join(map(str, missing)) or 'Requirements not met'
            text(app.screen, app.assets, label, (rect.x+16, req_y+4), 10,
                 LIME if eligible else RED, max_width=rect.width-32)
        index = app.selected_party
        label = 'De-digivolve' if down else 'Digivolve'
        self._button((rect.x+16, rect.bottom-43, rect.width-32, 30), label,
                     lambda target=route.get('to'), selected=index: app.send('evolve', party_index=selected, to=target),
                     primary=eligible, disabled=not eligible or not self._lab_ready())

    def evolution_protocol(self, rect, mon):
        app, art = self.app, self.app.presentation
        p = art.colors(self.theme)
        art.card(rect, self.theme)
        text(app.screen, app.assets, 'BEFORE YOU EVOLVE', (rect.x+20, rect.y+19), 10, p['accent'], True)
        compact = rect.height < 320
        wrap(app.screen, app.assets, 'A new form. The same partner.', (rect.x+20, rect.y+47),
             rect.width-40, 16 if compact else 24, WHITE, 2)
        facts = [('01', 'Level resets to 1', VARIETY_NAMES[variety_of(mon, app.assets.species)]+' variety stays through evolution.' if variety_of(mon, app.assets.species) != 'normal' else 'Train your new form from the beginning.'),
                 ('02', 'CAM is retained', f"Your bond stays at {mon.get('cam', 0)}%."),
                 ('03', 'ABI grows with you', 'ABI DigiMeat also adds +1 permanently.')]
        top = rect.y+(82 if compact else 115)
        footer_space = 50 if not (app.state.get('in_lab') or app.state.get('in_farm')) else 0
        step = min(67, max(31, (rect.bottom-top-footer_space-15)//3))
        for index, (number, title, detail) in enumerate(facts):
            y = top+index*step
            text(app.screen, app.assets, number, (rect.x+20, y+2), 10, p['accent'], True)
            text(app.screen, app.assets, title, (rect.x+49, y), 12 if compact else 14, WHITE, True, rect.width-66)
            text(app.screen, app.assets, detail, (rect.x+49, y+(19 if compact else 23)), 10, p['muted'], max_width=rect.width-66)
        if not (app.state.get('in_lab') or app.state.get('in_farm')):
            self._button((rect.x+20, rect.bottom-43, rect.width-40, 30), 'Enter DigiLab to evolve',
                         app.enter_lab, disabled=not self._peace(), primary=True)

    def storage_entries(self):
        query = self.app.ui.values.get('bank_search', '').strip().casefold()
        if query != self._storage_query:
            self.app.scroll = 0
            self._storage_query = query
        # Enumerate BEFORE filtering: equal dictionaries may occupy different
        # server slots, and must never be resolved with storage.index(record).
        return [(index, mon) for index, mon in enumerate(self.app.state.get('storage', []))
                if query in mon.get('name', '').casefold() or query in mon.get('species_id', '').casefold()]

    def draw_storage(self, rect):
        app, art = self.app, self.app.presentation
        p = art.colors(self.theme)
        app.ui.field((rect.x, rect.y, rect.width-258, 36), 'bank_search', 'Search your stored partners…', size=14)
        count = len(app.state.get('storage', []))
        capacity = f'{count:,} / {FARM_CAPACITY} RESIDENTS' if count <= FARM_CAPACITY else f'{count:,} STORED · LEGACY OVERFLOW'
        text(app.screen, app.assets, capacity,
             (rect.right-240, rect.y+12), 10, GOLD if count >= FARM_CAPACITY else p['accent'], True, 240)
        full_party = len(app.state.get('party', [])) >= 6
        toolbar_height = 0
        if full_party:
            toolbar_height = 39
            selected = self._selected()
            text(app.screen, app.assets, 'SWAP INTO PARTY', (rect.x, rect.y+57), 10, p['accent'], True)
            self._button((rect.x+140, rect.y+46, 306, 31),
                         f"Slot {app.selected_party+1}: {selected.get('name', 'Partner')}  ›",
                         self.choose_exchange_slot, disabled=not self._peace())
            text(app.screen, app.assets, 'Party full · Choose a slot, then a stored partner to swap.',
                 (rect.x+459, rect.y+57), 10, p['muted'], max_width=rect.width-459)
        entries = self.storage_entries()
        columns = 4 if rect.width >= 1250 else 3
        rows, gap = 2, 12
        page_size = columns*rows
        app.scroll = min(max(0, app.scroll), max(0, len(entries)-page_size))
        grid = pygame.Rect(rect.x, rect.y+50+toolbar_height, rect.width, rect.height-90-toolbar_height)
        width, height = (grid.width-(columns-1)*gap)//columns, (grid.height-gap)//rows
        for n, (index, mon) in enumerate(entries[app.scroll:app.scroll+page_size]):
            card = pygame.Rect(grid.x+(n%columns)*(width+gap), grid.y+(n//columns)*(height+gap), width, height)
            art.card(card, self.theme)
            text(app.screen, app.assets, f'BANK  /  {index+1:04d}', (card.x+14, card.y+12), 9, p['accent'], True)
            text(app.screen, app.assets, f"Lv.{mon.get('level', 1)}", (card.right-57, card.y+12), 12, WHITE, True)
            image_height = max(35, card.height-93)
            self._portrait(mon.get('species_id'), (card.x+14, card.y+30, min(95, card.width//3), image_height))
            x = card.x+min(118, card.width//3+23)
            text(app.screen, app.assets, mon.get('name', 'Partner'), (x, card.y+41), 18, name_color(mon, app.assets.species, WHITE), True, card.right-x-14)
            text(app.screen, app.assets, f"ABI {mon.get('abi', 0)}  ·  CAM {mon.get('cam', 0)}%", (x, card.y+69),
                 10, p['muted'], max_width=card.right-x-14)
            button_width = (card.width-36)//2
            if full_party:
                self._button((card.x+14, card.bottom-42, button_width, 29), f'Swap into slot {app.selected_party+1}',
                             lambda uid=mon.get('uid'): self.request_exchange(uid),
                             disabled=not self._lab_ready() or not mon.get('uid'), primary=True)
            else:
                self._button((card.x+14, card.bottom-42, button_width, 29), 'Withdraw',
                             lambda selected=index: app.send('party', action='withdraw', index=selected),
                             disabled=not self._lab_ready(), primary=True)
            self._button((card.x+22+button_width, card.bottom-42, button_width, 29),
                         'Manage & feed' if index < FARM_CAPACITY else 'Legacy archive',
                         lambda uid=mon.get('uid'): self.manage_stored(uid),
                         disabled=not self._peace() or not mon.get('uid') or index >= FARM_CAPACITY)
        if not entries:
            message = 'No partners match your search.' if self._storage_query else 'Your DigiFarm is ready for its first resident.'
            text(app.screen, app.assets, message, (grid.centerx, grid.centery-18), 23, WHITE,
                 True, grid.width-60, True)
            text(app.screen, app.assets, 'Move a party partner into storage from the Active party screen.',
                 (grid.centerx, grid.centery+18), 13, p['muted'], max_width=grid.width-60, center=True)
        self.pagination(pygame.Rect(rect.x, rect.bottom-30, rect.width, 30), len(entries), page_size, 'partners')

    def draw_exchange_confirmation(self, rect):
        app = self.app
        party_uid, stored_uid = self.pending_exchange
        outgoing = next((mon for mon in app.state.get('party', []) if mon.get('uid') == party_uid), None)
        incoming = next((mon for mon in app.state.get('storage', []) if mon.get('uid') == stored_uid), None)
        if outgoing is None or incoming is None:
            self.pending_exchange = None
            return
        # Preserve the shared Home/navigation row while blocking the roster.
        # Only the confirmed pair can be sent, even if the selected slot changes.
        app.ui.actions = [(area, action) for area, action in app.ui.actions if area.bottom <= 92]
        app.ui.fields = []
        app.ui.focus = None
        pygame.key.stop_text_input()
        size = (round(rect.width*app.screen.scale), round(rect.height*app.screen.scale))
        if getattr(self, '_exchange_dim_size', None) != size:
            self._exchange_dim_size = size
            self._exchange_dim = pygame.Surface(size, pygame.SRCALPHA)
            self._exchange_dim.fill((3, 10, 20, 200))
        app.screen.blit_native(self._exchange_dim, rect.topleft)
        box = pygame.Rect(0, 0, min(604, rect.width-50), 251)
        box.center = rect.center
        app.presentation.card(box, self.theme, accent=True)
        p = app.presentation.colors(self.theme)
        text(app.screen, app.assets, 'Swap these partners?', (box.x+24, box.y+24), 25, WHITE, True)
        text(app.screen, app.assets, f"To your party: {incoming.get('name', 'Partner')}",
             (box.x+24, box.y+80), 17, WHITE, True, box.width-48)
        text(app.screen, app.assets, f"To storage: {outgoing.get('name', 'Partner')}",
             (box.x+24, box.y+112), 15, p['muted'], max_width=box.width-48)
        text(app.screen, app.assets, 'Both partners keep their progress. Resident count stays the same.',
             (box.x+24, box.y+148), 11, p['muted'], max_width=box.width-48)
        width = (box.width-60)//2
        self._button((box.x+24, box.bottom-62, width, 38), 'Cancel',
                     lambda: setattr(self, 'pending_exchange', None))
        self._button((box.x+36+width, box.bottom-62, width, 38), 'Confirm swap',
                     self.confirm_exchange, primary=True, disabled=not self._lab_ready())

    def pagination(self, rect, total, page_size, noun):
        app = self.app
        offset = app.scroll
        p = app.presentation.colors(self.theme)
        text(app.screen, app.assets, f'{offset+1 if total else 0}–{min(total, offset+page_size)} of {total} {noun}  ·  Scroll to browse',
             (rect.x, rect.y+9), 10, p['muted'], max_width=rect.width-250)
        self._button((rect.right-228, rect.y, 108, 29), 'Previous',
                     lambda: setattr(app, 'scroll', max(0, app.scroll-page_size)), disabled=offset <= 0)
        self._button((rect.right-108, rect.y, 108, 29), 'Next',
                     lambda: setattr(app, 'scroll', min(max(0, total-page_size), app.scroll+page_size)),
                     disabled=offset+page_size >= total)
