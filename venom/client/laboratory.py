"""Native DigiLab, species library and scan reconstruction destinations.

The laboratory changes presentation only. Recovery and reconstruction are still
authoritative server operations, and no species is hidden by a new unlock rule.
"""
from __future__ import annotations

from collections import Counter
import math

import pygame

from venom.common.game import FARM_CAPACITY
from .render import draw
from .battle_layout import wrapped_lines
from .varieties import VARIETIES, VARIETY_NAMES, variety_of, name_color, scan_hint as variety_scan_hint, FIREWALL_ORANGE
from .widgets import text, bar, WHITE, MUTED, CYAN, LIME, GOLD


def _button(app, rect, label, callback, theme='lab', **options):
    return app.ui.button(rect, label, callback, small=True,
                         accent=app.presentation.colors(theme)['accent'], **options)


def _partner_mode(app, mode):
    app.partner_screen.open_mode(mode)


def _sprite(app, species_id, rect):
    """Trim transparent source padding through the shared native artwork cache."""
    app.presentation.sprite(rect, species_id, now=app.now)


class LaboratoryScreen:
    def __init__(self, app):
        self.app = app

    def draw(self, rect):
        app, art = self.app, self.app.presentation
        state = app.state or {}
        party = state.get('party', [])
        ready = sum(value >= 100 for value in state.get('scan', {}).values())
        body = art.shell(rect, 'lab', 'A moment to reconnect.',
                         'Recover your team. Reconstruct new partners. Discover their next evolution.',
                         'DIGILAB  /  PARTNER SANCTUARY', header_height=128)
        in_lab, busy = bool(state.get('in_lab')), app.action_pending
        nav_y = body.y
        _button(app, (body.x, nav_y, 164, 36), 'Heal all partners' if in_lab else 'Enter DigiLab',
                lambda: app.send('digilab', action='heal') if in_lab else app.enter_lab(),
                primary=True, disabled=busy)
        _button(app, (body.x+176, nav_y, 164, 36), 'Return to field',
                lambda: app.send('digilab', action='return'), disabled=busy or not in_lab)
        _button(app, (body.right-136, nav_y, 136, 36), 'DigiFarm',
                app.enter_farm, disabled=busy or bool(state.get('battle')))
        text(app.screen, app.assets, 'Recovery is free. Your field position is kept.',
             (body.x+358, nav_y+12), 11, MUTED, max_width=body.width-510)
        metric_y = nav_y+49
        gap, metric_w = 12, (body.width-36)//4
        restored = sum(mon.get('hp', 0) >= mon.get('max_hp', 1) and
                       mon.get('sp', 0) >= mon.get('max_sp', 1) for mon in party)
        metrics = [('PARTNER LINK', f'{len(party)} / 6', 'First three enter battle'),
                   ('RECOVERED', f'{restored} / {len(party)}', 'Full HP and SP'),
                   ('SCAN READY', str(ready), '100% data or more'),
                   ('DIGIFARM', f"{min(FARM_CAPACITY, len(state.get('storage', [])))} / {FARM_CAPACITY}",
                    f"{len(state.get('storage', []))-FARM_CAPACITY} legacy partners preserved"
                    if len(state.get('storage', [])) > FARM_CAPACITY else 'Stored partners at home')]
        for index, (label, value, detail) in enumerate(metrics):
            art.metric((body.x+index*(metric_w+gap), metric_y, metric_w, 83),
                       label, value, detail, 'lab')
        content_y = metric_y+101
        content_h = body.bottom-content_y-20
        side_w = min(318, max(272, int(body.width*.27)))
        left_w = body.width-side_w-18
        text(app.screen, app.assets, 'YOUR PARTNERS  /  RECOVERY BAY',
             (body.x, content_y), 10, CYAN, True)
        text(app.screen, app.assets, 'LAB SERVICES',
             (body.right-side_w, content_y), 10, CYAN, True)
        grid_y = content_y+24
        card_w, card_h = (left_w-20)//3, (content_h-34)//2
        for index in range(6):
            card = pygame.Rect(body.x+(index%3)*(card_w+10),
                               grid_y+(index//3)*(card_h+10), card_w, card_h)
            self.partner_card(card, party[index] if index < len(party) else None, index)
        services = [
            ('Scan & materialize', f'{ready} signatures ready to reconstruct', 'scan',
             lambda: app.set_menu('scan')),
            ('Digivolution', 'Review routes and their requirements', 'evolution',
             lambda: _partner_mode(app, 'evolution')),
            ('DigiBank', 'Organize your DigiFarm residents', 'storage',
             lambda: _partner_mode(app, 'storage')),
            ('Active team', 'Choose your leader and formation', 'party',
             lambda: _partner_mode(app, 'roster')),
            ('Supply shop', 'Recovery capsules and DigiMeat', 'shop',
             lambda: app.set_menu('shop')),
        ]
        service_h = (content_h-24-4*8)//5
        for index, (label, detail, theme, callback) in enumerate(services):
            service = pygame.Rect(body.right-side_w, grid_y+index*(service_h+8), side_w, service_h)
            art.card(service, theme)
            art.icon((service.x+9, service.y+8, 33, service.height-16), theme, theme)
            _button(app, (service.x+50, service.y+5, service.width-59, service.height-10),
                    label, callback, theme)
        text(app.screen, app.assets, 'DigiLab restores the whole party on arrival. Materialized partners join your party or DigiBank.',
             (body.x, body.bottom+1), 10, MUTED, max_width=body.width)

    def partner_card(self, rect, mon, index):
        app, art = self.app, self.app.presentation
        art.card(rect, 'lab', selected=bool(mon and index == app.selected_party))
        if mon is None:
            draw.circle(app.screen, (42, 65, 78), (rect.centerx, rect.centery-9), 21, 1)
            text(app.screen, app.assets, '+', (rect.centerx, rect.centery-10), 26, (67, 101, 115), center=True)
            text(app.screen, app.assets, f'{index+1:02}  /  OPEN PARTNER SLOT',
                 (rect.centerx, rect.bottom-24), 9, MUTED, center=True)
            return
        text(app.screen, app.assets, f'{index+1:02}  /  {"ACTIVE" if index < 3 else "RESERVE"}',
             (rect.x+12, rect.y+9), 9, CYAN, True, rect.width-74)
        text(app.screen, app.assets, f'Lv.{mon.get("level", 1)}',
             (rect.right-51, rect.y+9), 9, MUTED)
        portrait = pygame.Rect(rect.x+9, rect.y+29, max(42, rect.width//3), max(24, rect.height-42))
        _sprite(app, mon.get('species_id'), portrait)
        x, width = portrait.right+8, rect.right-portrait.right-19
        text(app.screen, app.assets, mon.get('name', 'Partner'), (x, rect.y+32), 14, name_color(mon, app.assets.species, WHITE), True, width)
        for offset, resource, color in ((0, 'hp', LIME), (34, 'sp', CYAN)):
            y = rect.bottom-66+offset
            current, maximum = mon.get(resource, 0), mon.get('max_'+resource, 0)
            text(app.screen, app.assets, f'{resource.upper()}  {current}/{maximum}', (x, y), 9, MUTED,
                 max_width=width)
            bar(app.screen, pygame.Rect(x, y+16, width, 5), current, maximum, color)
        # Selection works like the field partner list, without changing formation.
        app.ui.actions.append((rect, lambda i=index: setattr(app, 'selected_party', i)))


class ScanScreen:
    """A paged species gallery with one cached filter pass per actual change."""
    def __init__(self, app):
        self.app = app
        self.stage = 'all'
        self.variant = 'all'
        self.ready_only = False
        self._filter_key = None
        self._entries = []
        self._owned = Counter()
        self._stages = ['all']
        self._catalog = None
        self._scan_snapshot = {}

    def filter(self, name, value):
        setattr(self, name, value)
        self.app.scroll = 0

    def cycle_stage(self):
        index = self._stages.index(self.stage) if self.stage in self._stages else 0
        self.filter('stage', self._stages[(index+1) % len(self._stages)])

    def cycle_variant(self):
        options = VARIETIES
        self.filter('variant', options[(options.index(self.variant)+1) % len(options)])

    def entries(self):
        app, state = self.app, self.app.state or {}
        species = app.assets.species
        if self._catalog is not species:
            self._catalog = species
            order = ('fresh', 'baby', 'in_training', 'rookie', 'champion', 'armor', 'ultimate', 'mega', 'ultra')
            stages = {entry.get('stage', '') for entry in species.values()} - {''}
            self._stages = ['all'] + sorted(stages, key=lambda s: (order.index(s) if s in order else 99, s))
        scans = state.get('scan', {})
        query = app.ui.values.get('search', '').strip().lower()
        key = (id(state), id(species), query, self.stage, self.variant, self.ready_only)
        if key == self._filter_key and self._scan_snapshot == scans:
            return self._entries
        if self._filter_key is not None and key[2:] != self._filter_key[2:]:
            app.scroll = 0
        self._filter_key = key
        self._scan_snapshot = dict(scans)
        self._owned = Counter(mon.get('species_id') for group in ('party', 'storage') for mon in state.get(group, []))
        self._entries = [entry for entry in species.values()
                         if (not query or query in (entry['name']+' '+entry.get('stage', '')+' '+entry.get('type', '')+' '+entry.get('attribute', '')).lower())
                         and (self.stage == 'all' or self.stage == entry.get('stage'))
                         and (self.variant == 'all' or variety_of(entry) == self.variant)
                         and (not self.ready_only or scans.get(entry['id'], 0) >= 100)]
        self._entries.sort(key=lambda entry: (-scans.get(entry['id'], 0), entry['name']))
        return self._entries

    def draw(self, rect):
        app, art = self.app, self.app.presentation
        state = app.state or {}
        theme = 'scan' if app.menu == 'scan' else 'dex'
        title = 'Scan & materialize.' if theme == 'scan' else 'Every form. A new possibility.'
        body = art.shell(rect, theme, title,
                         'Normal, Paradox, Shiny and FireWall each have separate scans. Reconstruct a level 1 partner at 100%.',
                         'DIGILAB  /  RECONSTRUCTION' if theme == 'scan' else 'DIGIDEX  /  SPECIES LIBRARY',
                         header_height=128)
        for index, (label, menu) in enumerate((('Scan & materialize', 'scan'), ('DigiDex', 'dex'), ('DigiLab', 'lab'))):
            _button(app, (body.x+index*168, body.y, 156, 34), label,
                    lambda m=menu: app.set_menu(m) if app.menu != m else None,
                    theme, selected=app.menu == menu)
        return_label = 'DigiFarm  Esc' if state.get('in_farm') else 'DigiLab  Esc' if state.get('in_lab') else 'Field  Esc'
        _button(app, (body.right-134, body.y, 134, 34), return_label,
                lambda: app.set_menu(app.menu), theme)
        filters = pygame.Rect(body.x, body.y+46, body.width, 46)
        art.card(filters, theme)
        control_w = 157
        search_w = filters.width-control_w*3-44
        app.ui.field((filters.x+8, filters.y+6, search_w, 34), 'search', 'Search Digimon, type or attribute…', size=13)
        x = filters.x+search_w+18
        _button(app, (x, filters.y+6, control_w-7, 34),
                'All stages  ›' if self.stage == 'all' else self.stage.replace('_', ' ').title()+'  ›',
                self.cycle_stage, theme, selected=self.stage != 'all')
        _button(app, (x+control_w, filters.y+6, control_w-7, 34),
                'All variants  ›' if self.variant == 'all' else VARIETY_NAMES[self.variant]+'  ›',
                self.cycle_variant, theme, selected=self.variant != 'all')
        _button(app, (x+control_w*2, filters.y+6, control_w-7, 34), 'Ready 100%+',
                lambda: self.filter('ready_only', not self.ready_only), theme, selected=self.ready_only)
        entries = self.entries()
        gallery_y, gallery_bottom = filters.bottom+31, body.bottom-61
        gallery_h = gallery_bottom-gallery_y
        cols = min(6, max(3, (body.width+12)//207))
        rows = max(1, min(3, (gallery_h+12)//270))
        count = cols*rows
        pages = max(1, math.ceil(len(entries)/count))
        app.scroll = max(0, min(app.scroll, pages-1))
        page = app.scroll
        text(app.screen, app.assets, f'{len(entries):,} forms  /  Page {page+1} of {pages}',
             (body.x, filters.bottom+11), 10, MUTED)
        scan_hint = variety_scan_hint(self.variant, state)
        text(app.screen, app.assets, scan_hint,
             (body.right-344, filters.bottom+11), 10, art.colors(theme)['accent'], max_width=344)
        cw, ch = (body.width-(cols-1)*12)//cols, (gallery_h-(rows-1)*12)//rows
        for index, entry in enumerate(entries[page*count:(page+1)*count]):
            card = pygame.Rect(body.x+(index%cols)*(cw+12), gallery_y+(index//cols)*(ch+12), cw, ch)
            self.species_card(card, entry, theme)
        if not entries:
            art.card((body.x, gallery_y, body.width, gallery_h), theme)
            art.icon((body.centerx-31, gallery_y+max(18, gallery_h//4-20), 62, 62), 'scan', theme)
            text(app.screen, app.assets, 'No signatures match these filters.',
                 (body.centerx, gallery_y+gallery_h//2+28), 20, WHITE, True, center=True)
            text(app.screen, app.assets, 'Try another stage or variant, or clear the search.',
                 (body.centerx, gallery_y+gallery_h//2+58), 12, MUTED, center=True)
        y = body.bottom-46
        _button(app, (body.x, y, 112, 32), 'Previous', lambda: setattr(app, 'scroll', max(0, page-1)),
                theme, disabled=page == 0)
        _button(app, (body.x+122, y, 112, 32), 'Next', lambda: setattr(app, 'scroll', min(pages-1, page+1)),
                theme, disabled=page+1 >= pages)
        if not (state.get('in_lab') or state.get('in_farm')):
            _button(app, (body.right-167, y, 167, 32), 'Enter DigiLab', app.enter_lab, theme,
                    primary=True, disabled=app.action_pending or bool(state.get('battle')))
        text(app.screen, app.assets,
             f'Uses all stored scan data. Each extra 20% adds 1 ABI, up to 5. A full party sends new partners to DigiFarm (up to {FARM_CAPACITY} residents).',
             (body.x, body.bottom+1), 10, MUTED, max_width=body.width)

    def species_card(self, rect, entry, theme):
        app, art = self.app, self.app.presentation
        scans = (app.state or {}).get('scan', {})
        percentage = scans.get(entry['id'], 0)
        ready = percentage >= 100
        variety = variety_of(entry)
        accent = FIREWALL_ORANGE if variety == 'firewall' else GOLD if variety in ('paradox', 'shiny') else art.colors(theme)['accent']
        art.card(rect, theme, accent=ready)
        text(app.screen, app.assets, entry.get('stage', 'Unknown').replace('_', ' ').upper(),
             (rect.x+13, rect.y+12), 9, accent, True, rect.width-24)
        if variety != 'normal':
            art.badge((rect.right-88, rect.y+29, 75, 19), variety.upper(), theme, accent=accent)
        if variety in ('shiny', 'firewall'):
            draw.line(app.screen, accent, (rect.x+12, rect.y+1), (rect.right-13, rect.y+1), 2)
        image_bottom = rect.bottom-147
        image_top = rect.y+37
        art_h = max(30, image_bottom-image_top)
        draw.ellipse(app.screen, (10, 25, 38), (rect.x+22, image_bottom-16, rect.width-44, 18))
        draw.ellipse(app.screen, (40, 81, 94), (rect.x+22, image_bottom-16, rect.width-44, 18), 1)
        _sprite(app, entry['id'], pygame.Rect(rect.x+22, image_top, rect.width-44, art_h))
        # Wrap long source names at word/camel-case boundaries, including the
        # variety prefix, so related modes can be distinguished in the gallery.
        scale = getattr(app.screen, 'scale', 1.)
        font_size = 14
        lines = wrapped_lines(app.assets.font(max(1, round(font_size*scale)), True),
                              entry['name'], (rect.width-26)*scale)
        if len(lines)>2:
            font_size = 12
            lines = wrapped_lines(app.assets.font(max(1, round(font_size*scale)), True),
                                  entry['name'], (rect.width-26)*scale)
        for index, line in enumerate(lines):
            text(app.screen, app.assets, line,
                 (rect.x+13, rect.bottom-139+(2-len(lines))*8+index*17), font_size,
                 name_color(entry, app.assets.species, WHITE), True, rect.width-26)
        y = rect.bottom-120
        text(app.screen, app.assets, f'{entry.get("type", "?").title()}  /  {entry.get("attribute", "?").title()}',
             (rect.x+13, y+25), 10, MUTED, max_width=rect.width-26)
        bar(app.screen, pygame.Rect(rect.x+13, y+46, rect.width-26, 5), percentage, 200, accent)
        # The thin marker distinguishes the 100% requirement from the 200% cap.
        draw.line(app.screen, WHITE, (rect.centerx, y+44), (rect.centerx, y+53), 1)
        text(app.screen, app.assets, f'{percentage:g} / 200% DATA', (rect.x+13, y+60), 9,
             accent if ready else MUTED, True, rect.width-80)
        text(app.screen, app.assets, f'{self._owned[entry["id"]]} OWNED',
             (rect.right-67, y+60), 9, MUTED, max_width=57)
        full = len((app.state or {}).get('party', [])) >= 6 and len((app.state or {}).get('storage', [])) >= FARM_CAPACITY
        in_hub = bool((app.state or {}).get('in_lab') or (app.state or {}).get('in_farm'))
        label = 'Materialize' if ready else f'{max(0, 100-percentage):g}% more data'
        if full and ready:
            label = 'DigiBank full'
        _button(app, (rect.x+12, rect.bottom-39, rect.width-24, 28), label,
                lambda ident=entry['id']: app.send('materialize', species_id=ident), theme,
                primary=ready and in_hub,
                disabled=not ready or not in_hub or full or app.action_pending or bool(app.state.get('battle')))
