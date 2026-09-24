"""An illustrated supply terminal; all purchases remain server authoritative."""
from __future__ import annotations

import pygame

from .render import draw
from .widgets import text, wrap, bar, WHITE, CYAN, GOLD, LIME, MUTED


class ShopScreen:
    def __init__(self, app):
        self.app = app
        self.category = 'all'
        self.quantities = {}

    def filter(self, category):
        self.app.audio.cue('tab', now=self.app.now)
        self.category = category
        self.app.scroll = 0

    def change_quantity(self, key, change):
        owned = self.app.state.get('inventory', {}).get(key, 0)
        maximum = max(1, min(99, 999-owned))
        self.quantities[key] = max(1, min(maximum, self.quantities.get(key, 1)+change))

    def buy(self, key):
        self.app.send('shop', item=key, quantity=self.quantities.get(key, 1))

    def use(self, key):
        item = self.app.shop_data().get(key, {})
        if item.get('category') == 'digimeat':
            self.app.farm_screen.open_manager(item=key)
        else:
            self.app.send('item', item=key, party_index=self.app.selected_party)

    def page(self, change, page_size, total):
        self.app.scroll = max(0, min(max(0, total-page_size), self.app.scroll+change*page_size))
        self.app.audio.cue('tab', now=self.app.now)

    @staticmethod
    def matches(item, category):
        meat = item.get('category') == 'digimeat'
        return category == 'all' or (meat if category == 'digimeat' else
                                     not meat and item.get('resource') == category)

    def meat_icon(self, rect, item=None):
        app = self.app
        source = app.assets.image((item or {}).get('icon', 'assets/ui/digifarm/digimeat.png'))
        if source:
            image = app.assets.fit(source, rect.size)
            app.screen.blit(image, image.get_rect(center=rect.center))

    def draw(self, rect):
        app, rect = self.app, pygame.Rect(rect)
        theme = app.presentation
        palette = theme.colors('shop')
        body = theme.shell(rect, 'shop', 'A little care. A stronger bond.',
                           'Recovery for the road. Optional DigiMeat treats for your home companions.',
                           'VENOM NXT  /  SUPPLY TERMINAL', header_height=148)
        tabs = [('all', 'All supplies'), ('hp', 'HP recovery'), ('sp', 'SP recovery'),
                ('digimeat', 'DigiMeat')]
        for index, (key, label) in enumerate(tabs):
            app.ui.button((body.x+index*126, body.y, 116, 34), label,
                          lambda value=key: self.filter(value), selected=self.category == key,
                          small=True, accent=palette['accent'])
        balance = pygame.Rect(body.right-348, body.y, 214, 34)
        theme.card(balance, 'shop')
        text(app.screen, app.assets, 'YOUR CREDITS', (balance.x+12, balance.y+11), 9, palette['muted'], True)
        text(app.screen, app.assets, f"{app.state.get('credits', 0):,} ¥", (balance.right-61, balance.centery),
             16, GOLD, True, max_width=112, center=True)
        back_label = ('DigiFarm  Esc' if app.state.get('in_farm') else
                      'DigiLab  Esc' if app.state.get('in_lab') else 'Field  Esc')
        app.ui.button((body.right-121, body.y, 121, 34), back_label,
                      lambda: app.set_menu('shop'), small=True, accent=palette['accent'])
        top = body.y+49
        height = body.bottom-top-2
        side_width = min(275, max(236, int(body.width*.225)))
        side = pygame.Rect(body.right-side_width, top, side_width, height)
        grid = pygame.Rect(body.x, top, side.x-body.x-18, height-39)
        entries = [(key, item) for key, item in app.shop_data().items()
                   if self.matches(item, self.category)]
        columns, gap = (3 if grid.width >= 738 else 2), 12
        row_count = max(1, min(2, grid.height//195))
        page_size = columns*row_count
        app.scroll = min(max(0, app.scroll), max(0, len(entries)-page_size))
        width = (grid.width-gap*(columns-1))//columns
        card_height = min(270, (grid.height-gap*(row_count-1))//row_count)
        for index, (key, item) in enumerate(entries[app.scroll:app.scroll+page_size]):
            card = pygame.Rect(grid.x+(index%columns)*(width+gap),
                               grid.y+(index//columns)*(card_height+gap), width, card_height)
            self.product(card, key, item)
        if not entries:
            text(app.screen, app.assets, 'No supplies in this category.', grid.center, 18,
                 palette['muted'], center=True)
        paging = pygame.Rect(grid.x, grid.bottom+9, grid.width, 30)
        app.ui.button((paging.x, paging.y, 95, 28), 'Previous',
                      lambda: self.page(-1, page_size, len(entries)), disabled=app.scroll <= 0,
                      small=True, accent=palette['accent'])
        app.ui.button((paging.right-95, paging.y, 95, 28), 'Next',
                      lambda: self.page(1, page_size, len(entries)),
                      disabled=app.scroll+page_size >= len(entries), small=True, accent=palette['accent'])
        count = (f'{app.scroll+1}–{min(app.scroll+page_size, len(entries))} / {len(entries)} supplies'
                 if entries else '0 supplies')
        text(app.screen, app.assets, count, paging.center, 11, palette['muted'], center=True)
        if self.category == 'digimeat':
            self.farm_care(side)
        else:
            self.partner(side)
        if app.args.demo:
            status = 'OFFLINE PREVIEW  ·  Connect to your server to buy and use supplies.'
        elif app.state.get('in_lab') or app.state.get('in_farm'):
            status = 'HOME SUPPLIES  ·  Use capsules on your party. Feed DigiMeat to a stored companion at your DigiFarm.'
        else:
            status = 'FIELD INVENTORY  ·  Use owned capsules here. Shop at your DigiFarm or the DigiLab.'
        text(app.screen, app.assets, status, (rect.x+25, rect.bottom-18), 10,
             palette['muted'], max_width=rect.width-50)

    def product(self, rect, key, item):
        app, art = self.app, self.app.presentation
        palette = art.colors('shop')
        resource = item.get('resource', 'hp')
        meat = item.get('category') == 'digimeat'
        rarity = item.get('rarity', 'common')
        color = ((211, 170, 255) if rarity == 'rare' else LIME) if meat else (
            (247, 151, 185) if resource == 'hp' else (97, 220, 240))
        art.card(rect, 'shop')
        draw.line(app.screen, color, (rect.x+10, rect.y+1), (rect.right-11, rect.y+1), 2)
        owned = app.state.get('inventory', {}).get(key, 0)
        maximum = max(1, min(99, 999-owned))
        quantity = self.quantities[key] = min(maximum, self.quantities.get(key, 1))
        quality = {'s': 1, 'm': 2, 'l': 3}.get(key.rsplit('_', 1)[-1], 1)
        band = min(81, max(65, rect.height//3))
        if meat:
            self.meat_icon(pygame.Rect(rect.x+12, rect.y+12, 68, band-20), item)
            label = f"{resource.upper()} +{item.get('amount', 0)}"
        else:
            art.capsule(pygame.Rect(rect.x+12, rect.y+5, 70, band-4), resource, quality)
            label = f"{resource.upper()} · {key.rsplit('_', 1)[-1].upper()}"
        text(app.screen, app.assets, label, (rect.x+88, rect.y+12), 21, color, True, rect.width-100)
        detail = f'{rarity.upper()}  ·  OWNED {owned}' if meat else f'OWNED  {owned} / 999'
        text(app.screen, app.assets, detail, (rect.x+90, rect.y+42), 9,
             palette['muted'], True, rect.width-103)
        draw.line(app.screen, palette['line'], (rect.x+1, rect.y+band), (rect.right-2, rect.y+band))
        text(app.screen, app.assets, item.get('name', key), (rect.x+14, rect.y+band+10), 15,
             WHITE, True, rect.width-28)
        amount = item.get('amount', 0)
        effect = (f'Bond +{amount} CAM · Optional treat' if resource == 'cam' else
                  f'Permanent +{amount} {resource.upper()}') if meat else f'Restore {amount:,} {resource.upper()}'
        text(app.screen, app.assets, effect,
             (rect.x+14, rect.y+band+34), 11, color, max_width=rect.width-28)
        price = item.get('price', 0)
        total = price*quantity
        text(app.screen, app.assets, f'{total:,} ¥', (rect.x+14, rect.bottom-70), 17,
             GOLD, True, rect.width-120)
        text(app.screen, app.assets, f'{price:,} each', (rect.right-99, rect.bottom-65), 10,
             palette['muted'], max_width=86)
        y = rect.bottom-43
        app.ui.button((rect.x+12, y, 32, 30), '−', lambda: self.change_quantity(key, -1),
                      disabled=quantity <= 1 or app.action_pending, small=True, accent=color)
        text(app.screen, app.assets, str(quantity), (rect.x+60, y+15), 13, WHITE, True, center=True)
        app.ui.button((rect.x+76, y, 32, 30), '+', lambda: self.change_quantity(key, 1),
                      disabled=quantity >= maximum or app.action_pending, small=True, accent=color)
        can_buy = (bool(app.state.get('in_lab') or app.state.get('in_farm')) and not app.action_pending
                   and app.state.get('credits', 0) >= total and owned+quantity <= 999)
        use_width = 62 if meat else 47
        buy_width = max(55, rect.width-138-use_width)
        app.ui.button((rect.x+116, y, buy_width, 30), 'Buy', lambda: self.buy(key),
                      primary=True, disabled=not can_buy, small=True, accent=palette['accent'])
        has_recipient = bool(app.state.get('storage')) if meat else bool(app.state.get('party'))
        app.ui.button((rect.right-12-use_width, y, use_width, 30), 'Feed' if meat else 'Use', lambda: self.use(key),
                      disabled=owned <= 0 or not has_recipient or app.action_pending,
                      small=True, accent=color)

    def farm_care(self, rect):
        app, art = self.app, self.app.presentation
        palette = art.colors('shop')
        art.card(rect, 'shop', accent=True)
        text(app.screen, app.assets, 'GROW TOGETHER', (rect.x+17, rect.y+17),
             10, palette['accent'], True, rect.width-34)
        self.meat_icon(pygame.Rect(rect.centerx-57, rect.y+42, 114, 63))
        text(app.screen, app.assets, 'DigiFarm treats', (rect.centerx, rect.y+130),
             20, WHITE, True, rect.width-30, True)
        y = wrap(app.screen, app.assets, 'Choose a stored companion at home to feed it a treat.',
                 (rect.x+19, rect.y+157), rect.width-38, 11, palette['muted'], max_lines=3)
        y = wrap(app.screen, app.assets, 'CAM meat builds your bond. Stat meat adds a permanent bonus.',
                 (rect.x+19, y+13), rect.width-38, 11, LIME, max_lines=3)
        y = wrap(app.screen, app.assets, 'No hunger or upkeep. Feed only when you want to.',
                 (rect.x+19, y+13), rect.width-38, 11, palette['muted'], max_lines=3)
        if y+68 < rect.bottom-56:
            text(app.screen, app.assets, 'PERMANENT TRAINING LIMIT', (rect.x+19, y+17),
                 9, palette['accent'], True, rect.width-38)
            wrap(app.screen, app.assets, '+100 per stat · +300 total per Digimon',
                 (rect.x+19, y+36), rect.width-38, 11, palette['muted'], max_lines=2)
        residents = len(app.state.get('storage', []))
        text(app.screen, app.assets, f'{residents} companions at home', (rect.centerx, rect.bottom-70),
             11, palette['muted'], max_width=rect.width-30, center=True)
        app.ui.button((rect.x+16, rect.bottom-48, rect.width-32, 32), 'Visit your DigiFarm',
                      lambda: app.farm_screen.open_manager(), small=True,
                      accent=LIME, disabled=app.action_pending)

    def partner(self, rect):
        app, art = self.app, self.app.presentation
        palette = art.colors('shop')
        art.card(rect, 'shop', accent=True)
        text(app.screen, app.assets, 'CARE FOR YOUR PARTNER', (rect.x+17, rect.y+17),
             10, palette['accent'], True, rect.width-34)
        party = app.state.get('party', [])[:6]
        app.selected_party = max(0, min(app.selected_party, len(party)-1)) if party else 0
        if party:
            mon = party[app.selected_party]
            # Reserve both roster rows and the field-to-lab action before
            # fitting the portrait; six partners must stay selectable.
            roster_height = 51 + (57 if len(party) > 3 else 0)
            footer_height = 42 if not (app.state.get('in_lab') or app.state.get('in_farm')) else 0
            slots_y = rect.bottom-18-footer_height-roster_height
            portrait_bottom = rect.y+min(149, rect.height//3+9, slots_y-rect.y-147)
            draw.ellipse(app.screen, (32, 69, 81), (rect.centerx-66, portrait_bottom-16, 132, 27), 1)
            draw.ellipse(app.screen, (31, 57, 66), (rect.centerx-48, portrait_bottom-12, 96, 18))
            sprite = app.assets.sprite(mon.get('species_id'),
                                       (133, min(115, max(40, portrait_bottom-rect.y-39))), now=app.now)
            if sprite:
                app.screen.blit(sprite, sprite.get_rect(midbottom=(rect.centerx, portrait_bottom)))
            y = portrait_bottom+19
            text(app.screen, app.assets, mon.get('name', 'Partner'), (rect.centerx, y),
                 19, WHITE, True, rect.width-30, True)
            text(app.screen, app.assets, f"Lv.{mon.get('level', 1)}  ·  Selected for recovery",
                 (rect.centerx, y+26), 10, palette['muted'], center=True)
            for index, (resource, color) in enumerate((('hp', (247, 151, 185)), ('sp', CYAN))):
                row_y = y+49+index*28
                value, maximum = mon.get(resource, 0), mon.get('max_'+resource, 1)
                text(app.screen, app.assets, f'{resource.upper()}  {value} / {maximum}',
                     (rect.x+19, row_y), 10, palette['muted'])
                bar(app.screen, pygame.Rect(rect.x+19, row_y+16, rect.width-38, 5), value, maximum, color)
            text(app.screen, app.assets, 'SELECT RECIPIENT', (rect.x+17, slots_y-19), 9, palette['muted'], True)
            slot_w = (rect.width-38)//3
            for index, member in enumerate(party):
                cell = pygame.Rect(rect.x+13+(index%3)*(slot_w+6), slots_y+(index//3)*57, slot_w, 51)
                art.card(cell, 'shop', selected=index == app.selected_party)
                image = app.assets.sprite(member.get('species_id'), (42, 39), now=app.now)
                if image:
                    app.screen.blit(image, image.get_rect(center=cell.center))
                app.ui.actions.append((cell, lambda selected=index: setattr(app, 'selected_party', selected)))
        else:
            text(app.screen, app.assets, 'No party partner', rect.center, 17, MUTED, center=True)
        if not (app.state.get('in_lab') or app.state.get('in_farm')):
            button_y = rect.bottom-40
            app.ui.button((rect.x+16, button_y, rect.width-32, 30), 'Visit DigiLab to buy',
                          app.enter_lab, small=True, accent=palette['accent'], disabled=app.action_pending)
