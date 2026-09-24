"""Illustrated world atlas with native-resolution, bounded map thumbnails."""
from __future__ import annotations

from collections import OrderedDict
import pygame

from .render import NativeCanvas, draw
from .widgets import text, WHITE, CYAN, LIME, MUTED


class WorldScreen:
    THUMBNAIL_BYTES = 12 * 1024 * 1024
    THUMBNAIL_ITEMS = 72

    def __init__(self, app):
        self.app = app
        self._thumbnails = OrderedDict()
        self._thumbnail_bytes = 0
        self._query = ''
        self._display_key = None

    def page(self, offset):
        self.app.scroll = max(0, self.app.scroll + offset)
        self.app.audio.cue('tab', now=self.app.now)

    def transfer(self, map_id):
        app = self.app
        if (app.action_pending or app.state.get('in_lab') or app.state.get('battle')
                or (map_id == app.state.get('map_id') and not app.state.get('in_farm'))
                or map_id not in app.assets.maps):
            return
        app.send('travel', map_id=map_id)

    def thumbnail(self, entry, rect):
        """Fit the original map without cropping or changing its aspect ratio.

        Cache lookup precedes image retrieval, so a map evicted from the shared
        source cache is not decoded again while its thumbnail remains visible.
        """
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
        body = art.shell(rect, 'maps', 'Your next adventure starts here.',
                         'Explore the Dawn sectors. Find new partners, gather scan data and keep moving.',
                         'VENOM NXT  /  DAWN ATLAS', header_height=128)
        side_width = min(294, max(260, round(body.width*.235)))
        side = pygame.Rect(body.x, body.y, side_width, body.height)
        area = pygame.Rect(side.right+18, body.y, body.right-side.right-18, body.height)
        current = app.assets.maps.get(app.state.get('map_id'), {})
        self.current_sector(side, current)
        field_width = max(170, area.width-364)
        app.ui.field((area.x, area.y, field_width, 36), 'world_search', 'Search sectors…', size=14)
        query = app.ui.values.get('world_search', '').strip().lower()
        if query != self._query:
            app.scroll, self._query = 0, query
        entries = [entry for entry in app.assets.maps.values()
                   if query in entry.get('name', '').lower() or query in entry.get('id', '').lower()]
        grid = pygame.Rect(area.x, area.y+51, area.width, area.height-82)
        columns = 3 if area.width >= 750 else 2
        rows = max(1, min(2, grid.height//185))
        page_size = columns*rows
        app.scroll = min(max(0, app.scroll), max(0, len(entries)-page_size))
        for index, (label, offset) in enumerate((('Previous', -page_size), ('Next', page_size))):
            disabled = app.scroll == 0 if offset < 0 else app.scroll+page_size >= len(entries)
            app.ui.button((area.x+field_width+10+index*98, area.y, 90, 36), label,
                          lambda change=offset:self.page(change), disabled=disabled,
                          small=True, accent=palette['accent'])
        return_label = 'DigiFarm  Esc' if app.state.get('in_farm') else 'DigiLab  Esc' if app.state.get('in_lab') else 'Field  Esc'
        app.ui.button((area.right-147, area.y, 147, 36), return_label, app.close_menu,
                      small=True, accent=palette['accent'])
        gap = 12
        width = (grid.width-gap*(columns-1))//columns
        height = (grid.height-gap*(rows-1))//rows
        for index, entry in enumerate(entries[app.scroll:app.scroll+page_size]):
            card = pygame.Rect(grid.x+(index%columns)*(width+gap),
                               grid.y+(index//columns)*(height+gap), width, height)
            self.destination(card, entry)
        if not entries:
            art.card(grid, 'maps')
            text(screen, app.assets, 'No sectors match your search.', grid.center, 18,
                 palette['muted'], center=True, max_width=grid.width-36)
        shown = min(len(entries), app.scroll+page_size)
        text(screen, app.assets, f'{app.scroll+1 if entries else 0}–{shown} of {len(entries)} sectors',
             (area.x, area.bottom-19), 11, palette['muted'])
        text(screen, app.assets, 'Scroll or use Next to explore the atlas.',
             (area.right-277, area.bottom-19), 11, palette['muted'], max_width=277)
        message = ('Return from DigiLab before transferring to another sector.' if app.state.get('in_lab')
                   else 'Finish the current battle before transferring.' if app.state.get('battle')
                   else 'Transfer pending — waiting for the server.' if app.action_pending
                   else 'Depart DigiFarm to any sector, or return to your saved field position.' if app.state.get('in_farm')
                   else 'Select a destination to transfer. Your server confirms every arrival.')
        text(screen, app.assets, message, (rect.x+25, rect.bottom-18), 10,
             palette['muted'], max_width=rect.width-50)

    def destination(self, rect, entry):
        app, art = self.app, self.app.presentation
        p = art.colors('maps')
        current = entry.get('id') == app.state.get('map_id') and not app.state.get('in_farm')
        art.card(rect, 'maps', selected=current)
        image_height = max(65, rect.height-105)
        image = pygame.Rect(rect.x+10, rect.y+8, rect.width-20, image_height)
        draw.rect(app.screen, (5, 14, 24), image, border_radius=5)
        self.thumbnail(entry, image.inflate(-4, -4))
        text(app.screen, app.assets, entry.get('name', 'Unknown sector'),
             (rect.x+12, image.bottom+8), 15, WHITE, True, rect.width-24)
        text(app.screen, app.assets, f"WILD LEVEL {entry.get('level', 1)}  ·  {entry.get('layer', 'a').upper()} SECTOR",
             (rect.x+12, image.bottom+32), 10, p['muted'], max_width=rect.width-24)
        app.ui.button((rect.x+12, rect.bottom-40, rect.width-24, 30),
                      'Current sector' if current else 'Transfer',
                      lambda ident=entry['id']:self.transfer(ident),
                      primary=not current, selected=current,
                      disabled=bool(current or app.action_pending or app.state.get('in_lab') or app.state.get('battle')),
                      small=True, accent=p['accent'])

    def current_sector(self, rect, entry):
        app, art = self.app, self.app.presentation
        p = art.colors('maps')
        art.card(rect, 'maps', accent=True)
        in_farm = bool(app.state.get('in_farm'))
        text(app.screen, app.assets, 'YOUR RETURN SECTOR' if in_farm else 'YOUR CURRENT SECTOR',
             (rect.x+17, rect.y+16), 10, p['accent'], True)
        art.badge((rect.right-77, rect.y+12, 61, 23), 'SAVED' if in_farm else 'LINKED', 'maps')
        image = pygame.Rect(rect.x+15, rect.y+47, rect.width-30, min(185, rect.height//3))
        draw.rect(app.screen, (5, 14, 24), image, border_radius=7)
        self.thumbnail(entry, image.inflate(-8, -8))
        text(app.screen, app.assets, entry.get('name', 'Unknown sector'),
             (rect.x+17, image.bottom+15), 21, WHITE, True, rect.width-34)
        text(app.screen, app.assets, f"WILD LEVEL {entry.get('level', 1)}", (rect.x+18, image.bottom+47),
             11, p['accent'], True, rect.width-36)
        y = image.bottom+83
        draw.line(app.screen, p['line'], (rect.x+17, y), (rect.right-17, y))
        text(app.screen, app.assets, 'LOCAL SIGNATURES', (rect.x+18, y+14), 10, p['muted'], True)
        ids = entry.get('encounters', [])[:3]
        if ids:
            width = (rect.width-34)//len(ids)
            for index, species_id in enumerate(ids):
                entry_species = app.assets.species.get(species_id, {})
                x = rect.x+17+index*width
                art.sprite((x+5, y+38, width-10, 75), species_id, now=app.now)
                text(app.screen, app.assets, entry_species.get('name', species_id), (x+width//2, y+128),
                     10, WHITE, max_width=width-6, center=True)
        else:
            text(app.screen, app.assets, 'No encounter data available.', (rect.x+18, y+53),
                 11, p['muted'], max_width=rect.width-36)
        if in_farm:
            app.ui.button((rect.x+17, rect.bottom-46, rect.width-34, 32), 'Return to field position',
                          lambda:app.send('digifarm', action='return'), disabled=app.action_pending,
                          small=True, accent=p['accent'])
        elif app.state.get('in_lab'):
            app.ui.button((rect.x+17, rect.bottom-46, rect.width-34, 32), 'Return from DigiLab',
                          lambda:app.send('digilab', action='return'), disabled=app.action_pending,
                          small=True, accent=p['accent'])
        else:
            text(app.screen, app.assets, 'DAWN NETWORK  /  CONNECTION ESTABLISHED',
                 (rect.x+18, rect.bottom-26), 9, p['muted'], max_width=rect.width-36)
