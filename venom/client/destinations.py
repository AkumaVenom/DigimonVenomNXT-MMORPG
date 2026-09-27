"""Native world atlas: independent regional browsing and authoritative travel."""
from __future__ import annotations

from collections import OrderedDict
import pygame

from .render import NativeCanvas, draw
from .widgets import text, WHITE


class WorldScreen:
    THUMBNAIL_BYTES = 12 * 1024 * 1024
    THUMBNAIL_ITEMS = 72
    REGIONS = (('dawn', 'Digimon Dawn'), ('world_ds', 'Digimon World DS'))
    BANDS = ((None, 'All levels'), ((1, 25), 'Lv. 1–25'), ((26, 50), 'Lv. 26–50'),
             ((51, 75), 'Lv. 51–75'), ((76, 99), 'Lv. 76–99'))

    def __init__(self, app):
        self.app = app
        self._thumbnails = OrderedDict()
        self._thumbnail_bytes = 0
        self._display_key = None
        self.region = 'dawn'
        self._browsing = {key: {'query': '', 'offset': 0, 'band': None} for key, _ in self.REGIONS}
        self._query = ''
        self._page_size = 6
        self._open_map_id = None
        self._focus_id = None

    @staticmethod
    def region_id(entry):
        # Earlier Dawn catalogs do not carry regional metadata.
        return 'world_ds' if entry.get('region_id') == 'world_ds' else 'dawn'

    @staticmethod
    def levels(entry):
        """Show authored ranges, with the legacy capped ±2 fallback."""
        level = max(1, min(99, int(entry.get('level', 1))))
        low = max(1, min(99, int(entry.get('level_min', level-2))))
        high = max(low, min(99, int(entry.get('level_max', level+2))))
        return low, high

    @classmethod
    def level_label(cls, entry):
        low, high = cls.levels(entry)
        return f'WILD Lv. {low}' if low == high else f'WILD Lv. {low}–{high}'

    def available_regions(self):
        present = {self.region_id(entry) for entry in self.app.assets.maps.values()}
        return [(key, name) for key, name in self.REGIONS if key in present]

    def region_entries(self, region=None):
        region = region or self.region
        entries = [entry for entry in self.app.assets.maps.values() if self.region_id(entry) == region]
        # DS is a deliberate low-to-high journey; existing Dawn ordering stays intact.
        return sorted(entries, key=lambda entry: (entry.get('level', 1), entry['id'])) if region == 'world_ds' else entries

    def entries(self):
        query = self.app.ui.values.get('world_search', '').strip().casefold()
        band = self._browsing[self.region]['band']
        return [entry for entry in self.region_entries()
                if (not band or band[0] <= int(entry.get('level', 1)) <= band[1])
                and (not query or query in ' '.join(str(entry.get(key, '')) for key in
                                                   ('name', 'id', 'zone_name', 'region_name')).casefold())]

    def _remember(self):
        self._browsing[self.region].update(query=self.app.ui.values.get('world_search', ''),
                                          offset=self.app.scroll)

    def select_region(self, region, *, cue=True, remember=True):
        if region not in dict(self.available_regions()):
            return
        if remember:
            self._remember()
        self.region = region
        saved = self._browsing[region]
        self.app.ui.values['world_search'] = saved['query']
        self._query = saved['query'].strip().casefold()
        self.app.scroll = saved['offset']
        self._focus_id = None
        self.app.ui.focus = None
        pygame.key.stop_text_input()
        if cue:
            self.app.audio.cue('tab', now=self.app.now)

    def on_open(self):
        current = self.app.state.get('map_id')
        if current != self._open_map_id:
            self.show_current(cue=False, remember=False)
            self._open_map_id = current
        else:
            saved = self._browsing[self.region]
            self.app.scroll = saved['offset']
            self.app.ui.values['world_search'] = saved['query']
            self._query = saved['query'].strip().casefold()

    def show_current(self, *, cue=True, remember=True):
        entry = self.app.assets.maps.get(self.app.state.get('map_id'))
        if not entry:
            return
        self.select_region(self.region_id(entry), cue=cue, remember=remember)
        self.app.ui.values['world_search'] = self._query = ''
        self._browsing[self.region]['band'] = None
        self._focus_id = entry['id']
        self.app.scroll = 0

    def filter_levels(self, band):
        self._browsing[self.region]['band'] = band
        self.app.scroll = 0
        self._focus_id = None
        self.app.audio.cue('tab', now=self.app.now)

    def page(self, offset):
        last = max(0, (len(self.entries())-1)//self._page_size*self._page_size)
        self.app.scroll = max(0, min(last, self.app.scroll + offset))
        self._remember()
        self.app.audio.cue('tab', now=self.app.now)

    def wheel(self, direction):
        if direction:
            self.page((-1 if direction > 0 else 1)*self._page_size)

    def blocked(self):
        state = self.app.state
        return bool(self.app.action_pending or state.get('in_lab') or state.get('battle')
                    or state.get('in_story') or state.get('in_season') or state.get('admin_jail'))

    def transfer(self, map_id):
        app = self.app
        if (self.blocked() or (map_id == app.state.get('map_id') and not app.state.get('in_farm'))
                or map_id not in app.assets.maps):
            return
        app.send('travel', map_id=map_id)

    def thumbnail(self, entry, rect):
        """Fit original map art; bound the cache by native bytes and entry count."""
        app, rect = self.app, pygame.Rect(rect)
        screen = app.screen
        native = screen.to_physical_rect(rect) if isinstance(screen, NativeCanvas) else rect
        display_key = (screen.get_size(), getattr(screen, 'scale', 1.))
        if display_key != self._display_key:
            self._thumbnails.clear()
            self._thumbnail_bytes = 0
            self._display_key = display_key
        path = entry.get('path')
        key = path, native.size
        if min(native.size) <= 0 or not path:
            return
        thumb = self._thumbnails.get(key)
        if thumb is not None:
            self._thumbnails.move_to_end(key)
        else:
            source = app.assets.image(path)
            if source is None:
                return
            factor = min(native.width/source.get_width(), native.height/source.get_height())
            size = (max(1, round(source.get_width()*factor)), max(1, round(source.get_height()*factor)))
            thumb = pygame.transform.scale(source, size)
            cost = thumb.get_pitch()*thumb.get_height()
            if cost <= self.THUMBNAIL_BYTES:
                self._thumbnails[key] = thumb
                self._thumbnail_bytes += cost
                while (len(self._thumbnails) > self.THUMBNAIL_ITEMS
                       or self._thumbnail_bytes > self.THUMBNAIL_BYTES):
                    _, old = self._thumbnails.popitem(last=False)
                    self._thumbnail_bytes -= old.get_pitch()*old.get_height()
        position = native.centerx-thumb.get_width()//2, native.centery-thumb.get_height()//2
        target = screen.surface if isinstance(screen, NativeCanvas) else screen
        target.blit(thumb, position)

    def draw(self, rect):
        app, rect = self.app, pygame.Rect(rect)
        art, screen = app.presentation, app.screen
        palette = art.colors('maps')
        body = art.shell(rect, 'maps', 'Choose your next adventure.',
                         'Two worlds to explore. The same partners, scan data and shared tamer community.',
                         'VENOM NXT  /  WORLD ATLAS', header_height=128)
        regions = self.available_regions()
        if self.region not in dict(regions) and regions:
            self.select_region(regions[0][0], cue=False)
        for index, (region, name) in enumerate(regions):
            count = len(self.region_entries(region))
            app.ui.button((body.x+index*234, body.y, 224, 34), f'{name}  ·  {count}',
                          lambda value=region: self.select_region(value),
                          selected=self.region == region, small=True, accent=palette['accent'])
        selected = self.region_entries()
        if selected:
            low, high = min(self.levels(entry)[0] for entry in selected), max(self.levels(entry)[1] for entry in selected)
            text(screen, app.assets, f'{len(selected)} destinations  /  wild Lv. {low}–{high}',
                 (body.right-304, body.y+11), 11, palette['muted'], max_width=304)
        body.y += 47
        body.height -= 47
        side_width = min(286, max(260, round(body.width*.23)))
        side = pygame.Rect(body.x, body.y, side_width, body.height)
        area = pygame.Rect(side.right+18, body.y, body.right-side.right-18, body.height)
        current = app.assets.maps.get(app.state.get('map_id'), {})
        self.current_sector(side, current)
        field_width = area.width-157
        app.ui.field((area.x, area.y, field_width, 34), 'world_search', 'Search maps or areas…', size=14)
        return_label = 'DigiFarm  Esc' if app.state.get('in_farm') else 'DigiLab  Esc' if app.state.get('in_lab') else 'Field  Esc'
        app.ui.button((area.right-147, area.y, 147, 34), return_label, app.close_menu,
                      small=True, accent=palette['accent'])
        band_width = (area.width-24)//5
        for index, (band, label) in enumerate(self.BANDS):
            app.ui.button((area.x+index*(band_width+6), area.y+42, band_width, 26), label,
                          lambda value=band: self.filter_levels(value), selected=self._browsing[self.region]['band'] == band,
                          disabled=bool(band and not any(band[0] <= int(entry.get('level', 1)) <= band[1] for entry in selected)),
                          small=True, accent=palette['accent'])
        query = app.ui.values.get('world_search', '').strip().casefold()
        if query != self._query:
            app.scroll, self._query, self._focus_id = 0, query, None
        entries = self.entries()
        grid = pygame.Rect(area.x, area.y+78, area.width, area.height-126)
        columns = 3 if area.width >= 750 else 2
        rows = max(1, min(2, grid.height//150))
        page_size = self._page_size = columns*rows
        if self._focus_id:
            position = next((i for i, entry in enumerate(entries) if entry['id'] == self._focus_id), 0)
            app.scroll = position//page_size*page_size
            self._focus_id = None
        last = max(0, (len(entries)-1)//page_size*page_size)
        app.scroll = min(max(0, app.scroll), last)
        self._remember()
        gap = 10
        width = (grid.width-gap*(columns-1))//columns
        height = (grid.height-gap*(rows-1))//rows
        for index, entry in enumerate(entries[app.scroll:app.scroll+page_size]):
            card = pygame.Rect(grid.x+(index%columns)*(width+gap), grid.y+(index//columns)*(height+gap), width, height)
            self.destination(card, entry)
        if not entries:
            art.card(grid, 'maps')
            text(screen, app.assets, 'No maps match these filters.', (grid.centerx, grid.centery-13), 18,
                 palette['muted'], center=True, max_width=grid.width-36)
            text(screen, app.assets, 'Try another area name or choose All levels.', (grid.centerx, grid.centery+16), 12,
                 palette['muted'], center=True, max_width=grid.width-36)
        shown = min(len(entries), app.scroll+page_size)
        text(screen, app.assets, f'{app.scroll+1 if entries else 0}–{shown} of {len(entries)} maps',
             (area.x, area.bottom-29), 11, palette['muted'])
        page_count = max(1, (len(entries)+page_size-1)//page_size)
        text(screen, app.assets, f'Page {app.scroll//page_size+1} / {page_count}',
             (area.centerx, area.bottom-24), 11, palette['muted'], center=True)
        for index, (label, offset) in enumerate((('Previous', -page_size), ('Next', page_size))):
            disabled = app.scroll == 0 if offset < 0 else app.scroll+page_size >= len(entries)
            app.ui.button((area.right-188+index*98, area.bottom-38, 90, 30), label,
                          lambda change=offset: self.page(change), disabled=disabled,
                          small=True, accent=palette['accent'])
        message = ('Return from DigiLab before transferring to another map.' if app.state.get('in_lab')
                   else 'Finish the current battle before transferring.' if app.state.get('battle')
                   else 'Opening your destination…' if app.action_pending
                   else 'Depart DigiFarm to any map, or return to your saved field position.' if app.state.get('in_farm')
                   else 'Choose a map to transfer. Wild levels describe opponents, not an entry requirement.')
        text(screen, app.assets, message, (rect.x+25, rect.bottom-18), 10,
             palette['muted'], max_width=rect.width-50)

    def destination(self, rect, entry):
        app, art = self.app, self.app.presentation
        p = art.colors('maps')
        current = entry.get('id') == app.state.get('map_id') and not app.state.get('in_farm')
        art.card(rect, 'maps', selected=current)
        image_height = max(47, rect.height-102)
        image = pygame.Rect(rect.x+9, rect.y+7, rect.width-18, image_height)
        draw.rect(app.screen, (5, 14, 24), image, border_radius=5)
        self.thumbnail(entry, image.inflate(-4, -4))
        text(app.screen, app.assets, entry.get('name', 'Unknown map'),
             (rect.x+11, image.bottom+7), 14, WHITE, True, rect.width-22)
        level = int(entry.get('level', 1))
        color = (241, 182, 135) if level >= 76 else p['accent']
        text(app.screen, app.assets, self.level_label(entry),
             (rect.x+12, image.bottom+29), 10, color, True, rect.width-24)
        app.ui.button((rect.x+11, rect.bottom-39, rect.width-22, 29),
                      'Current sector' if current else 'Transfer',
                      lambda ident=entry['id']: self.transfer(ident),
                      primary=not current, selected=current, disabled=bool(current or self.blocked()),
                      small=True, accent=p['accent'])

    def current_sector(self, rect, entry):
        app, art = self.app, self.app.presentation
        p = art.colors('maps')
        art.card(rect, 'maps', accent=True)
        in_farm, in_lab = bool(app.state.get('in_farm')), bool(app.state.get('in_lab'))
        text(app.screen, app.assets, 'YOUR RETURN SECTOR' if in_farm or in_lab else 'YOUR CURRENT SECTOR',
             (rect.x+16, rect.y+15), 10, p['accent'], True)
        region_name = dict(self.REGIONS).get(self.region_id(entry), 'Digimon Dawn')
        text(app.screen, app.assets, region_name.upper(), (rect.x+16, rect.y+36), 10, p['muted'], True)
        image = pygame.Rect(rect.x+14, rect.y+58, rect.width-28, min(132, max(82, rect.height//4)))
        draw.rect(app.screen, (5, 14, 24), image, border_radius=7)
        self.thumbnail(entry, image.inflate(-6, -6))
        text(app.screen, app.assets, entry.get('name', 'Unknown map'),
             (rect.x+16, image.bottom+10), 18, WHITE, True, rect.width-32)
        text(app.screen, app.assets, self.level_label(entry), (rect.x+17, image.bottom+39),
             11, p['accent'], True, rect.width-34)
        y = image.bottom+65
        draw.line(app.screen, p['line'], (rect.x+16, y), (rect.right-16, y))
        text(app.screen, app.assets, 'LOCAL DIGIMON', (rect.x+17, y+12), 10, p['muted'], True)
        ids = entry.get('encounters', [])[:3]
        if ids:
            width = (rect.width-32)//len(ids)
            for index, species_id in enumerate(ids):
                species = app.assets.species.get(species_id, {})
                x = rect.x+16+index*width
                art.sprite((x+5, y+34, width-10, 60), species_id, now=app.now)
                text(app.screen, app.assets, species.get('name', species_id), (x+width//2, y+106),
                     10, WHITE, max_width=width-6, center=True)
        else:
            text(app.screen, app.assets, 'Explore to find new partners.', (rect.x+17, y+42),
                 11, p['muted'], max_width=rect.width-34)
        # The link returns the atlas to the physical field location without travel.
        app.ui.button((rect.x+16, rect.bottom-79, rect.width-32, 29), 'Show this map in atlas',
                      self.show_current, small=True, accent=p['accent'])
        if in_farm:
            app.ui.button((rect.x+16, rect.bottom-43, rect.width-32, 29), 'Return to field position',
                          lambda: app.send('digifarm', action='return'), disabled=app.action_pending,
                          small=True, accent=p['accent'])
        elif in_lab:
            app.ui.button((rect.x+16, rect.bottom-43, rect.width-32, 29), 'Return from DigiLab',
                          lambda: app.send('digilab', action='return'), disabled=app.action_pending,
                          small=True, accent=p['accent'])
        else:
            text(app.screen, app.assets, 'SHARED WORLD  /  TAMERS ONLINE',
                 (rect.x+17, rect.bottom-25), 9, p['muted'], max_width=rect.width-34)
