"""An illustrated supply terminal; all purchases remain server authoritative."""
from __future__ import annotations

import pygame
import uuid

from .render import draw
from .widgets import text, wrap, bar, WHITE, CYAN, GOLD, LIME, MUTED, RED


class ShopScreen:
    def __init__(self, app):
        self.app = app
        self.category = 'all'
        self.quantities = {}
        self.currency = 'credits'

    @property
    def ruby_enabled(self):
        features = getattr(self.app, 'server_features', None)
        return bool((self.app.state.get('economy') or {}).get('enabled')) and (features is None or 'digiruby_economy' in features)

    @property
    def busy(self):
        return self.app.action_pending or bool(getattr(getattr(self.app,'community',None),'busy',False))

    def select_currency(self, currency):
        if self.busy or currency not in ('credits','digirubies'):
            return
        if currency == 'digirubies' and not self.ruby_enabled:
            self.app.toast('DigiRuby purchases require an updated server with the ranked economy enabled.', GOLD)
            return
        self.currency = currency
        self.app.ui.actions, self.app.ui.fields = [], []
        self.app.audio.cue('tab', now=self.app.now)

    def unit_price(self, item):
        value = item.get('ruby_price') if self.currency == 'digirubies' else item.get('price')
        return value if isinstance(value,int) and not isinstance(value,bool) and value > 0 else None

    def can_buy(self, key, item, quantity):
        price = self.unit_price(item)
        owned = self.app.state.get('inventory',{}).get(key,0)
        return (not self.busy and bool(self.app.state.get('in_lab') or self.app.state.get('in_farm'))
                and (self.currency != 'digirubies' or self.ruby_enabled)
                and price is not None and 1 <= quantity <= min(99,999-owned)
                and self.app.state.get(self.currency,0) >= price*quantity)

    def filter(self, category):
        self.app.audio.cue('tab', now=self.app.now)
        self.category = category
        self.app.scroll = 0

    def abi_recipient(self, uid=None):
        party = self.app.state.get('party', [])
        if uid is not None:
            return next(((index, mon) for index, mon in enumerate(party) if mon.get('uid') == uid), (None, None))
        index = max(0, min(self.app.selected_party, len(party)-1)) if party else 0
        return (index, party[index]) if party else (None, None)

    def can_use_abi(self, uid=None):
        _, mon = self.abi_recipient(uid)
        return bool(mon and mon.get('uid') and not self.busy and not self.app.state.get('battle')
                    and (self.app.state.get('in_lab') or self.app.state.get('in_farm'))
                    and mon.get('abi', 0) < 200
                    and self.app.state.get('inventory', {}).get('digimeat_abi', 0) > 0)

    def change_quantity(self, key, change):
        if self.busy:
            return
        owned = self.app.state.get('inventory', {}).get(key, 0)
        maximum = max(1, min(99, 999-owned))
        self.quantities[key] = max(1, min(maximum, self.quantities.get(key, 1)+change))

    def buy(self, key):
        item, quantity = self.app.shop_data().get(key,{}), self.quantities.get(key,1)
        if not self.can_buy(key,item,quantity):
            return
        if self.currency == 'digirubies':
            self.app.send('shop',item=key,quantity=quantity,currency='digirubies',transaction_id=uuid.uuid4().hex)
        else:
            # Keep the existing credits protocol usable on older servers.
            self.app.send('shop',item=key,quantity=quantity)

    def use(self, key, uid=None):
        item = self.app.shop_data().get(key, {})
        if key == 'digimeat_abi':
            if self.can_use_abi(uid):
                index, mon = self.abi_recipient(uid)
                self.app.send('item', item=key, party_index=index, uid=mon['uid'], quantity=1)
        elif item.get('category') == 'digimeat':
            self.app.farm_screen.open_manager(item=key)
        else:
            self.app.send('item', item=key, party_index=self.app.selected_party)

    def page(self, change, page_size, total):
        self.app.scroll = max(0, min(max(0, total-page_size), self.app.scroll+change*page_size))
        self.app.audio.cue('tab', now=self.app.now)

    @staticmethod
    def matches(item, category):
        meat = item.get('category') == 'digimeat'
        return category == 'all' or (meat and item.get('resource') == 'abi' if category == 'abi' else
                                     meat if category == 'digimeat' else
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
                           'Recovery, permanent ABI growth and optional treats for your companions.',
                           'VENOM NXT  /  SUPPLY TERMINAL', header_height=148)
        tabs = [('all', 'All supplies'), ('hp', 'HP recovery'), ('sp', 'SP recovery'),
                ('digimeat', 'DigiMeat'), ('abi', 'ABI growth')]
        tab_pitch = min(116, (body.width-565)//len(tabs))
        for index, (key, label) in enumerate(tabs):
            app.ui.button((body.x+index*tab_pitch, body.y, tab_pitch-8, 34), label,
                          lambda value=key: self.filter(value), selected=self.category == key,
                          small=True, accent=palette['accent'])
        for index,(currency,label,color) in enumerate((('credits','Credits',GOLD),('digirubies','DigiRubies',(215,161,255)))):
            value = app.state.get(currency,0)
            suffix = ' ¥' if currency == 'credits' else ''
            app.ui.button((body.right-553+index*216,body.y,204,34),f'{label} · {value:,}{suffix}',
                          lambda c=currency:self.select_currency(c),selected=self.currency==currency,
                          disabled=self.busy or currency=='digirubies' and not self.ruby_enabled,
                          small=True,accent=color)
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
        if self.category == 'abi':
            self.abi_partner(side)
        elif self.category == 'digimeat':
            self.farm_care(side)
        else:
            self.partner(side)
        if self.busy:
            status = 'PROCESSING  ·  Waiting for the server to confirm. Your displayed balances update after approval.'
        elif self.currency == 'digirubies':
            status = ('PAYING WITH DIGIRUBIES  ·  Ranked rewards buy the same supplies. All prices shown are in DigiRubies.' if self.ruby_enabled else
                      'DIGIRUBIES UNAVAILABLE  ·  Connect to an updated server with the ranked economy enabled.')
        elif app.args.demo:
            status = 'OFFLINE PREVIEW  ·  Connect to your server to buy and use supplies.'
        elif app.state.get('in_lab') or app.state.get('in_farm'):
            status = 'HOME SUPPLIES  ·  ABI DigiMeat works on your party here or on residents at your DigiFarm. Other route requirements still apply.'
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
        price = self.unit_price(item)
        total = price*quantity if price is not None else None
        affordable = total is not None and app.state.get(self.currency,0) >= total
        denomination = ('DigiRuby' if total==1 else 'DigiRubies') if self.currency=='digirubies' else '¥'
        price_label = 'Unavailable' if total is None else f'{total:,} {denomination}'
        text(app.screen, app.assets, price_label, (rect.x+14, rect.bottom-70), 15 if self.currency=='digirubies' else 17,
             (215,161,255) if affordable and self.currency=='digirubies' else GOLD if affordable else RED, True, rect.width-112)
        text(app.screen, app.assets, f'{price:,} each' if price is not None else 'No quote', (rect.right-99, rect.bottom-65), 10,
             palette['muted'], max_width=86)
        y = rect.bottom-43
        app.ui.button((rect.x+12, y, 32, 30), '−', lambda: self.change_quantity(key, -1),
                      disabled=quantity <= 1 or self.busy, small=True, accent=color)
        text(app.screen, app.assets, str(quantity), (rect.x+60, y+15), 13, WHITE, True, center=True)
        app.ui.button((rect.x+76, y, 32, 30), '+', lambda: self.change_quantity(key, 1),
                      disabled=quantity >= maximum or self.busy, small=True, accent=color)
        can_buy = self.can_buy(key,item,quantity)
        abi = key == 'digimeat_abi'
        use_width = 62 if meat else 47
        buy_width = max(55, rect.width-138-use_width)
        app.ui.button((rect.x+116, y, buy_width, 30), 'Buy', lambda: self.buy(key),
                      primary=True, disabled=not can_buy, small=True, accent=palette['accent'])
        has_recipient = bool(app.state.get('storage')) if meat else bool(app.state.get('party'))
        _, recipient = self.abi_recipient()
        uid = recipient.get('uid') if recipient else None
        choose_abi = abi and self.category != 'abi'
        app.ui.button((rect.right-12-use_width, y, use_width, 30), 'Choose' if choose_abi else 'Use' if abi or not meat else 'Feed',
                      lambda: self.filter('abi') if abi and self.category != 'abi' else self.use(key, uid=uid),
                      disabled=self.busy if choose_abi else not self.can_use_abi(uid) if abi else owned <= 0 or not has_recipient or app.action_pending,
                      small=True, accent=color)

    def abi_partner(self, rect):
        """A visible party recipient, including an only partner that cannot be deposited."""
        app, art = self.app, self.app.presentation
        palette = art.colors('shop')
        art.card(rect, 'shop', accent=True)
        text(app.screen, app.assets, 'SELECTED ABI RECIPIENT', (rect.x+17, rect.y+17),
             10, palette['accent'], True)
        party = app.state.get('party', [])[:6]
        index, mon = self.abi_recipient()
        if mon:
            app.selected_party = index
            image = app.assets.sprite(mon.get('species_id'), (110, 70), now=app.now)
            if image:
                app.screen.blit(image, image.get_rect(midbottom=(rect.centerx, rect.y+111)))
            wrap(app.screen, app.assets, mon.get('name', 'Partner'),
                 (rect.x+18, rect.y+125), rect.width-36, 14, WHITE, 2)
            abi = mon.get('abi', 0)
            text(app.screen, app.assets, f'ABI {abi} → {min(200, abi+1)} / 200',
                 (rect.centerx, rect.y+175), 18, LIME, True, center=True)
            hint = ('ABI is at its permanent cap of 200.' if abi >= 200 else
                    'Visit DigiLab or DigiFarm to use ABI meat.' if not (app.state.get('in_lab') or app.state.get('in_farm')) else
                    'Use on this partner. No de-digivolution needed.')
            wrap(app.screen, app.assets, hint, (rect.x+18, rect.y+199), rect.width-36, 11, palette['muted'], 2)
            roster_height = 51+(57 if len(party) > 3 else 0)
            slots_y = rect.bottom-65-roster_height
            text(app.screen, app.assets, 'CHOOSE PARTY PARTNER', (rect.x+17, slots_y-19), 9, palette['muted'], True)
            slot_w = (rect.width-38)//3
            for slot, member in enumerate(party):
                cell = pygame.Rect(rect.x+13+(slot%3)*(slot_w+6), slots_y+(slot//3)*57, slot_w, 51)
                art.card(cell, 'shop', selected=slot == index)
                image = app.assets.sprite(member.get('species_id'), (42, 39), now=app.now)
                if image:
                    app.screen.blit(image, image.get_rect(center=cell.center))
                app.ui.actions.append((cell, lambda selected=slot: setattr(app, 'selected_party', selected)))
        else:
            wrap(app.screen, app.assets, 'Withdraw a partner from DigiBank, or feed a resident at your DigiFarm.',
                 (rect.x+18, rect.y+71), rect.width-36, 13, palette['muted'], 5)
        home = bool(app.state.get('in_lab') or app.state.get('in_farm'))
        app.ui.button((rect.x+16, rect.bottom-45, rect.width-32, 30),
                      'Feed a farm resident' if home else 'Visit DigiLab to use',
                      (lambda: app.farm_screen.open_manager(item='digimeat_abi')) if home else app.enter_lab,
                      small=True, accent=LIME, disabled=self.busy or bool(app.state.get('battle')))

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
        y = wrap(app.screen, app.assets, 'CAM builds your bond. Stat meat adds bonuses. ABI meat adds +1 permanent ABI.',
                 (rect.x+19, y+13), rect.width-38, 11, LIME, max_lines=3)
        y = wrap(app.screen, app.assets, 'Use the ABI growth tab for party partners. ABI has its own 200 cap.',
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
