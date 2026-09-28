"""Private DigiFarm: bounded ambient residents and server-confirmed care.

Only the authenticated character and their partners are rendered. Resident
roaming is cosmetic; player movement and care remain server authoritative.
"""
from __future__ import annotations

import hashlib
import math
import pygame

from .render import draw
from .world import MapCamera, WorldRenderer, _zoom, player_title
from .widgets import text, bar, wrap, panel, WHITE, MUTED, CYAN, LIME, GOLD, RED


ACCENT = (166, 237, 140)
STAT_NAMES = {'hp': 'HP', 'sp': 'SP', 'atk': 'ATK', 'def': 'DEF', 'int': 'INT', 'spd': 'SPD', 'cam': 'CAM', 'abi': 'ABI'}


class DigiFarmScreen(WorldRenderer):
    CAPACITY = 100
    COMPANION_SCALE = 1.5

    def __init__(self, app):
        super().__init__(app)
        # The home has its own camera. Changing its zoom never changes the
        # player's saved field-map preference.
        settings = getattr(getattr(app, 'display', None), 'settings', {})
        self.camera = MapCamera(settings.get('farm_zoom', 1.))
        self.viewport = pygame.Rect(0, 0, 0, 0)
        self.player_rect = self.follower_rect = None
        self.selected_uid = None
        self.manager_open = False
        self.request_manager = False
        self.item = 'digimeat_cam'
        self.food_page = 0
        self.page = 0
        self.query = ''
        self.home_confirmation = False
        self.paused = False
        self.age = 0.
        self._seeds = {}
        self.resident_rects = {}
        self.last_feedback = ''
        self.feedback_until = 0.

    def reset(self):
        self.selected_uid = None
        self.manager_open = self.request_manager = self.home_confirmation = False
        self.page = self.food_page = 0
        self._seeds.clear()
        self._layers.clear()
        settings = getattr(getattr(self.app, 'display', None), 'settings', {})
        self.camera = MapCamera(settings.get('farm_zoom', 1.))
        self.viewport = pygame.Rect(0, 0, 0, 0)
        self.player_rect = self.follower_rect = None
        self.last_feedback = ''
        self.app.ui.values['farm_search'] = ''

    def residents(self):
        return self.app.state.get('storage', [])[:self.CAPACITY] if self.app.state else []

    def selected(self):
        return next((m for m in self.residents() if m.get('uid') == self.selected_uid), None)

    @property
    def focus(self):
        # Keep the selected tamer readable at fit and their entire body in the
        # viewport even at 8x on the minimum supported display.
        return pygame.Vector2(self.app.position) - pygame.Vector2(0, 42)

    def set_zoom(self, value):
        self.camera.zoom = _zoom(value)
        if self.camera.ready:
            self.camera.center.update(self.focus)
            self.camera._clamp()
        display = getattr(self.app, 'display', None)
        if display is not None:
            display.settings['farm_zoom'] = self.zoom
            display.save()
        return self.zoom

    def update(self, dt):
        if self.app.state and self.app.state.get('in_farm'):
            self.camera.update(dt, self.focus)
        if not self.paused and not self.manager_open and not self.app.settings_open:
            self.age += min(.1, max(0., dt))
        if self.request_manager and self.app.state and self.app.state.get('in_farm'):
            self.request_manager = False
            self.open_manager(item=self.item)
        if self.manager_open and self.selected() is None:
            self.manager_open = False

    def select(self, uid):
        self.selected_uid = uid
        self.manager_open = True
        self.food_page = 0
        self.app.ui.focus = None
        self.app.ui.actions, self.app.ui.fields = [], []
        pygame.key.stop_text_input()

    def open_manager(self, item=None):
        if item:
            self.item = item
            keys = [key for key, value in self.app.shop_data().items() if value.get('category') == 'digimeat']
            self.food_page = keys.index(item)//6 if item in keys else 0
        if not self.app.state.get('in_farm'):
            self.request_manager = True
            self.app.enter_farm()
            return
        self.app.close_menu()
        if not self.selected() and self.residents():
            self.selected_uid = self.residents()[0]['uid']
        if self.selected():
            self.manager_open = True
        else:
            self.app.toast('Your DigiFarm is ready. Deposit a spare partner from DigiBank to begin.', ACCENT)

    def close_manager(self):
        self.manager_open = False
        self.app.ui.actions, self.app.ui.fields = [], []

    def open_shop(self):
        self.manager_open = False
        self.app.shop_screen.filter('digimeat')
        self.app.set_menu('shop')

    def transfer(self):
        self.manager_open = False
        self.app.partner_screen.open_mode('storage')

    def feed(self):
        mon = self.selected()
        item = self.app.shop_data().get(self.item, {})
        available = self.allowance(mon, item) if mon else 0
        fits = available > 0 if item.get('resource') == 'cam' else available >= item.get('amount', 1)
        if (mon and not self.app.action_pending and not self.app.state.get('battle')
                and self.app.state.get('in_farm') and fits
                and self.app.state.get('inventory', {}).get(self.item, 0) > 0):
            self.app.send('digifarm', action='feed', uid=mon['uid'], item=self.item, quantity=1)

    @staticmethod
    def allowance(mon, item):
        resource = item.get('resource')
        if resource == 'cam':
            return max(0, 100-mon.get('cam', 0))
        if resource == 'abi':
            return max(0, 200-mon.get('abi', 0))
        bonuses = mon.get('farm_bonuses', {})
        # The server publishes and enforces the same limits. The display never
        # modifies the monster, even while a care request is pending.
        return max(0, min(100-bonuses.get(resource, 0), 300-sum(bonuses.values())))

    def confirmed(self, previous, state):
        before = {m['uid']: m for m in (previous or {}).get('storage', [])}
        for mon in state.get('storage', []):
            old = before.get(mon.get('uid'))
            if not old:
                continue
            changes = []
            delta = mon.get('cam', 0)-old.get('cam', 0)
            if delta:
                changes.append(f'CAM +{delta}')
            abi_delta = mon.get('abi', 0)-old.get('abi', 0)
            if abi_delta:
                changes.append(f'ABI +{abi_delta} permanently')
            for stat, amount in mon.get('farm_bonuses', {}).items():
                gained = amount-old.get('farm_bonuses', {}).get(stat, 0)
                if gained:
                    changes.append(f'{STAT_NAMES.get(stat, stat)} +{gained} permanently')
            if changes:
                self.last_feedback = mon.get('name', 'Partner')+'  ·  '+', '.join(changes)
                self.feedback_until = self.app.now+5.
                self.app.toast(self.last_feedback, ACCENT)
                return

    def seed(self, uid):
        if uid not in self._seeds:
            self._seeds[uid] = int.from_bytes(hashlib.blake2s(str(uid).encode(), digest_size=4).digest(), 'big')
        return self._seeds[uid]

    def resident_position(self, uid, index, count, age=None):
        """Stable slots keep 100 residents legible and inside the grassy inset.

        Each Digimon takes a 3.4-second stroll then rests for 10–18 seconds.
        Paths stay inside a conservative rectangle wholly within the island.
        """
        count = max(1, count)
        columns = max(4, math.ceil(math.sqrt(count*2.25)))
        rows = max(3, math.ceil(count/columns))
        row, col = divmod(index, columns)
        seed = self.seed(uid)
        period = 14.+seed % 8
        phase = ((self.age if age is None else age)+(seed % 1300)/100.) % period
        cycle = int(((self.age if age is None else age)+(seed % 1300)/100.)//period)
        t = min(1., phase/3.4)
        blend = t*t*(3-2*t)
        def offset(n):
            return (math.sin(seed*.017+n*2.1)*.26, math.cos(seed*.013+n*1.7)*.25)
        a, b = offset(cycle), offset(cycle+1)
        ox, oy = (a[k]+(b[k]-a[k])*blend for k in (0, 1))
        x = .16+((col+.5+ox)/columns)*.68
        y = .23+((row+.5+oy)/rows)*.43
        return x, y, phase < 3.4 and not self.paused, b[0] < a[0]

    def _button(self, rect, label, action, **kwargs):
        self.app.ui.button(rect, label, action, small=True, accent=ACCENT, **kwargs)

    def draw(self, rect):
        app, rect = self.app, pygame.Rect(rect)
        art = app.presentation
        art.card(rect, 'farm', accent=True)
        text(app.screen, app.assets, 'YOUR PRIVATE HOME  /  DIGIFARM', (rect.x+22, rect.y+17), 10, ACCENT, True)
        text(app.screen, app.assets, 'A place to come home to.', (rect.x+21, rect.y+37), 28, WHITE, True, rect.width-460)
        count = len(self.residents())
        text(app.screen, app.assets, f'{count:02} / 100', (rect.right-324, rect.y+21), 27, ACCENT, True)
        text(app.screen, app.assets, 'RESIDENT DIGIMON', (rect.right-321, rect.y+58), 9, MUTED, True)
        self._button((rect.right-147, rect.y+27, 126, 34), 'Explore worlds', lambda: app.set_menu('maps'))
        side_width = 272
        stage = pygame.Rect(rect.x+14, rect.y+91, rect.width-side_width-42, rect.height-151)
        side = pygame.Rect(stage.right+13, stage.y, side_width, stage.height)
        self.draw_island(stage)
        self.draw_residents(side)
        y = rect.bottom-46
        self._button((rect.x+17, y, 127, 31), 'DigiBank', self.transfer)
        self._button((rect.x+153, y, 132, 31), 'DigiMeat shop', self.open_shop)
        self._button((rect.x+294, y, 143, 31), 'Resume roaming' if self.paused else 'Pause roaming',
                     lambda: setattr(self, 'paused', not self.paused))
        self._button((rect.right-184, y, 165, 31), 'Return to field',
                     lambda: app.send('digifarm', action='return'), disabled=app.action_pending)
        text(app.screen, app.assets, 'No hunger. No timers. Just your partners.',
             (rect.x+454, y+10), 10, MUTED, max_width=rect.width-660)
        if self.manager_open:
            self.draw_manager()

    def draw_island(self, rect):
        app = self.app
        self.viewport = pygame.Rect(rect)
        draw.rect(app.screen, (23, 109, 174), rect, border_radius=8)
        self.resident_rects.clear()
        self.player_rect = self.follower_rect = None
        source = app.assets.image('assets/ui/digifarm/level.png')
        if not source:
            return
        self.camera.configure(source.get_size(), self._physical_rect(rect), self.focus)
        old_clip = self._surface.get_clip()
        self._surface.set_clip(self.camera.viewport.clip(old_clip))
        try:
            # Share the field renderer's crop cache: at 8x only a viewport and
            # scrolling margin are scaled, never a giant version of the island.
            self._draw_layer(source, 'farm')
            residents = self.residents()
            actors = []
            for index, mon in enumerate(residents):
                x, y, moving, flip = self.resident_position(mon['uid'], index, len(residents))
                point = pygame.Vector2(x*source.get_width(), y*source.get_height())
                actors.append((point.y, 'resident', point, mon, moving, flip))
            party = app.state.get('party', [])
            if party:
                actors.append((app.follower.y, 'follower', app.follower, party[0], app.moving,
                               'left' in app.direction))
            actors.append((app.position.y, 'tamer', app.position, None, app.moving, False))
            logical_fit = min(rect.width/source.get_width(), rect.height/source.get_height())
            resident_size = 44 if len(residents) > 65 else 52 if len(residents) > 32 else 65
            resident_size = min(resident_size, max(32, round(source.get_width()*logical_fit*.085)))
            # Compute camera state only once, especially with 100 residents.
            frame = (self.camera.scale, self.camera.origin, resident_size/logical_fit)
            for _, kind, position, mon, moving, flip in sorted(actors, key=lambda row: row[0]):
                self._draw_farm_actor(kind, position, mon, moving, flip, frame)
        finally:
            self._surface.set_clip(old_clip)
        self._draw_farm_controls(rect)

    def _draw_farm_actor(self, kind, position, mon, moving, flip, frame):
        app = self.app
        scale, origin, resident_size = frame
        point = origin + pygame.Vector2(position)*scale
        if not self.camera.viewport.inflate(round(320*scale), round(320*scale)).collidepoint(point):
            return
        selected = kind == 'resident' and mon.get('uid') == self.selected_uid
        shadow_width = (resident_size*.55 if kind == 'resident' else 60)*scale
        shadow = pygame.Rect(round(point.x-shadow_width/2), round(point.y-5*scale),
                             max(2, round(shadow_width)), max(2, round(14*scale)))
        pygame.draw.ellipse(self._surface, (61, 120, 65), shadow)
        if selected or kind == 'tamer':
            ring = (249, 244, 168) if selected else CYAN
            pygame.draw.ellipse(self._surface, ring, shadow.inflate(round(8*scale), round(5*scale)),
                                max(1, round(2*getattr(app.screen, 'scale', 1))))
        if kind == 'tamer':
            ident = app.state.get('tamer', app.tamer)
            source = app.assets.tamer(ident, app.direction, moving, app.now, (64, 80))
            actor_scale = scale*self.COMPANION_SCALE
        else:
            ident = mon['species_id']
            species = app.assets.species.get(ident, {})
            motion = 'walk' if moving and 'walk' in species.get('animations', {}) else 'idle'
            size = (round(resident_size), round(resident_size)) if kind == 'resident' else (58, 64)
            source = app.assets.sprite(ident, size, motion=motion,
                                      now=self.age if kind == 'resident' else app.now, flip=flip)
            actor_scale = scale if kind == 'resident' else scale*self.COMPANION_SCALE
        destination = pygame.Rect(round(point.x-20*scale), round(point.y-100*scale),
                                  max(1, round(40*scale)), max(1, round(100*scale)))
        if source:
            sprite = self._scale_sprite(source, actor_scale)
            appearance = app.assets.tamers.get(ident, {}) if kind == 'tamer' else {}
            anchor = appearance.get('anchors', {}).get(app.direction)
            if anchor:
                native = appearance.get('native_size', [16, 32])
                destination = sprite.get_rect(topleft=(
                    round(point.x-anchor[0]*sprite.get_width()/max(1, native[0])),
                    round(point.y-anchor[1]*sprite.get_height()/max(1, native[1]))))
            else:
                destination = sprite.get_rect(midbottom=(round(point.x), round(point.y)))
            self._surface.blit(sprite, destination)
        logical = app.screen.to_logical_rect(destination)
        visible = logical.clip(self.viewport)
        if kind == 'resident':
            # Never leave an invisible, off-camera care button over the sidebar.
            hit = logical.inflate(8, 9).clip(self.viewport)
            if hit.width and hit.height:
                self.resident_rects[mon['uid']] = hit
                app.ui.actions.append((hit, lambda uid=mon['uid']: self.select(uid)))
                if selected or hit.collidepoint(app.ui.mouse):
                    label_point = self._logical_point((point.x, point.y))
                    text(app.screen, app.assets, mon.get('name', 'Partner'),
                         (label_point[0], label_point[1]+12), 11, WHITE, True,
                         170, True, outline=(10, 38, 38), outline_width=2)
        elif kind == 'tamer':
            self.player_rect = visible if visible.width and visible.height else None
            if self.player_rect:
                label = 'YOU · '+str(app.state.get('username') or 'Tamer')
                title = player_title(app.state.get('active_title'))
                title_width = app.assets.font(10, True).size(title)[0] if title else 0
                width = max(app.assets.font(11, True).size(label)[0], title_width)+16
                nameplate = pygame.Rect(0, 0, width, 38 if title else 23)
                nameplate.midbottom = (logical.centerx, logical.top-5)
                nameplate.clamp_ip(self.viewport.inflate(-8, -8))
                panel(app.screen, nameplate, (9, 29, 38), CYAN, 5)
                if title:
                    text(app.screen, app.assets, title, (nameplate.centerx, nameplate.y+11),
                         10, GOLD, True, width-10, True)
                text(app.screen, app.assets, label, (nameplate.centerx, nameplate.bottom-12),
                     11, WHITE, True, center=True)
        else:
            self.follower_rect = visible if visible.width and visible.height else None

    def _draw_farm_controls(self, rect):
        app = self.app
        instruction = pygame.Rect(rect.x+12, rect.y+12, min(440, rect.width-24), 28)
        panel(app.screen, instruction, (9, 29, 38), None, 6)
        app.ui.actions.append((instruction, lambda: None))
        text(app.screen, app.assets, 'WASD / arrows to walk  ·  Click a resident to care',
             (instruction.x+10, instruction.y+8), 10, WHITE, max_width=instruction.width-20)
        controls = pygame.Rect(rect.x+12, rect.bottom-55, 266, 43)
        panel(app.screen, controls, (9, 29, 38), None, 9)
        app.ui.actions.append((controls, lambda: None))
        self._button((controls.x+5, controls.y+5, 33, 33), '−',
                     lambda: self.change_zoom(-.5), disabled=self.zoom <= 1)
        label = f'{self.zoom:g}×'+('  FIT' if self.zoom <= 1 else '')
        text(app.screen, app.assets, label, (controls.x+86, controls.centery),
             14, WHITE, True, center=True)
        self._button((controls.x+133, controls.y+5, 33, 33), '+',
                     lambda: self.change_zoom(.5), disabled=self.zoom >= 8)
        self._button((controls.x+177, controls.y+5, 83, 33), 'Fit island',
                     self.reset_zoom, selected=self.zoom <= 1)
        # Keep the hint clear of the fit controls even on the minimum layout.
        text(app.screen, app.assets, 'Wheel / + − to zoom  ·  0 to fit',
             (controls.right+15, controls.y+17), 9, WHITE,
             max_width=max(1, rect.right-controls.right-28), outline=(22, 87, 137))

    def draw_residents(self, rect):
        app = self.app
        app.presentation.card(rect, 'farm')
        text(app.screen, app.assets, 'FARM RESIDENTS', (rect.x+15, rect.y+14), 11, ACCENT, True)
        app.ui.field((rect.x+12, rect.y+38, rect.width-24, 32), 'farm_search', 'Find a Digimon…', size=12)
        query = app.ui.values.get('farm_search', '').strip().casefold()
        if query != self.query:
            self.query, self.page = query, 0
        entries = [m for m in self.residents() if query in m.get('name', '').casefold()]
        size = max(1, (rect.height-127)//50)
        pages = max(1, math.ceil(len(entries)/size))
        self.page = min(self.page, pages-1)
        for i, mon in enumerate(entries[self.page*size:(self.page+1)*size]):
            row = pygame.Rect(rect.x+10, rect.y+80+i*50, rect.width-20, 44)
            app.presentation.card(row, 'farm', selected=mon.get('uid') == self.selected_uid)
            image = app.assets.sprite(mon.get('species_id'), (38, 37), now=app.now)
            if image:
                app.screen.blit(image, image.get_rect(center=(row.x+26, row.centery)))
            text(app.screen, app.assets, mon.get('name', 'Partner'), (row.x+51, row.y+6), 12, WHITE, True, row.width-61)
            text(app.screen, app.assets, f"Lv.{mon.get('level',1)}  ·  ABI {mon.get('abi',0)}  ·  CAM {mon.get('cam',0)}%", (row.x+51, row.y+25), 9, MUTED)
            app.ui.actions.append((row, lambda uid=mon['uid']: self.select(uid)))
        if not entries:
            wrap(app.screen, app.assets, 'No matching residents.' if query else 'Walk around with your lead partner. Deposit spare partners from DigiBank to welcome your first residents.',
                 (rect.x+20, rect.y+100), rect.width-40, 14, MUTED, 6)
        y = rect.bottom-36
        self._button((rect.x+12, y, 53, 26), 'Prev', lambda: setattr(self, 'page', self.page-1), disabled=self.page <= 0)
        text(app.screen, app.assets, f'{self.page+1} / {pages}', (rect.centerx, y+13), 11, MUTED, center=True)
        self._button((rect.right-65, y, 53, 26), 'Next', lambda: setattr(self, 'page', self.page+1), disabled=self.page >= pages-1)

    def draw_manager(self):
        app = self.app
        mon = self.selected()
        if not mon:
            self.manager_open = False
            return
        # Care is a modal: underlying resident, navigation, and search actions
        # cannot fire through it. Home remains visible and usable above it.
        app.ui.actions = [(r, fn) for r, fn in app.ui.actions if r.bottom <= 92]
        app.ui.fields = []
        w, h = app.screen.get_size()
        self.dim_background()
        rect = pygame.Rect((w-min(1000,w-70))//2, 110, min(1000,w-70), h-137)
        app.presentation.card(rect, 'farm', accent=True)
        text(app.screen, app.assets, 'PARTNER CARE  /  OPTIONAL DIGIMEAT TREATS', (rect.x+23, rect.y+18), 10, ACCENT, True)
        self._button((rect.right-104, rect.y+13, 85, 28), 'Close  Esc', self.close_manager)
        left = pygame.Rect(rect.x+19, rect.y+57, 306, rect.height-76)
        right = pygame.Rect(left.right+18, left.y, rect.right-left.right-37, left.height)
        app.presentation.card(left, 'farm')
        image = app.assets.sprite(mon.get('species_id'), (142, 116), now=app.now)
        if image:
            app.screen.blit(image, image.get_rect(midbottom=(left.centerx, left.y+130)))
        text(app.screen, app.assets, mon.get('name', 'Partner'), (left.centerx, left.y+150), 20, WHITE, True, left.width-30, True)
        text(app.screen, app.assets, f"Lv.{mon.get('level',1)}  /  Farm resident", (left.centerx, left.y+178), 11, MUTED, center=True)
        for column, (resource, maximum, color) in enumerate((('cam', 100, ACCENT), ('abi', 200, GOLD))):
            x = left.x+20+column*140
            text(app.screen, app.assets, f"{resource.upper()}  {mon.get(resource,0)} / {maximum}",
                 (x, left.y+207), 11, color, True)
            bar(app.screen, pygame.Rect(x, left.y+229, 126, 6), mon.get(resource,0), maximum, color)
        bonuses = mon.get('farm_bonuses', {})
        for i, stat in enumerate(STAT_NAMES):
            if stat in ('cam', 'abi'):
                continue
            x = left.x+20+(i%2)*136
            y = left.y+254+(i//2)*39
            value = mon.get('max_'+stat if stat in ('hp', 'sp') else stat, 0)
            text(app.screen, app.assets, f'{STAT_NAMES[stat]}  {value}', (x, y), 13, WHITE, True)
            text(app.screen, app.assets, f"+{bonuses.get(stat,0)} from care", (x, y+18), 9, ACCENT)
        wrap(app.screen, app.assets, 'ABI DigiMeat raises ABI permanently, even without a de-digivolution route. ABI uses its own 200 cap.',
             (left.x+20, left.y+377), left.width-40, 11, MUTED, 3)
        text(app.screen, app.assets, f'Stat care: {sum(bonuses.values())} / 300 total',
             (left.x+20, left.bottom-41), 11, ACCENT, True)
        text(app.screen, app.assets, 'Up to +100 in each stat. Kept on evolution.',
             (left.x+20, left.bottom-23), 9, MUTED)
        text(app.screen, app.assets, 'CHOOSE A TREAT', right.topleft, 12, ACCENT, True)
        self._button((right.right-132, right.y-6, 132, 29), 'DigiMeat shop', self.open_shop)
        items = [(key, value) for key, value in app.shop_data().items() if value.get('category') == 'digimeat']
        page_size = 6
        pages = max(1, math.ceil(len(items)/page_size))
        self.food_page = min(self.food_page, pages-1)
        row_h = min(53, max(42, (right.height-175)//6))
        for i, (key, item) in enumerate(items[self.food_page*page_size:(self.food_page+1)*page_size]):
            row = pygame.Rect(right.x, right.y+34+i*row_h, right.width, row_h-5)
            app.presentation.card(row, 'farm', selected=key == self.item)
            icon = app.assets.fit(app.assets.image('assets/ui/digifarm/digimeat.png'), (49, 29))
            if icon:
                app.screen.blit(icon, icon.get_rect(center=(row.x+33,row.centery)))
            owned = app.state.get('inventory', {}).get(key, 0)
            color = GOLD if item.get('rarity') == 'rare' else ACCENT
            text(app.screen, app.assets, item.get('name', key), (row.x+68, row.y+5), 12, WHITE if owned else MUTED, True, row.width-158)
            effect = f"{STAT_NAMES.get(item.get('resource'), '?')} +{item.get('amount',0)}"
            effect += '  ·  permanent' if item.get('resource') != 'cam' else '  ·  friendship'
            text(app.screen, app.assets, effect, (row.x+68, row.y+24), 9, color, max_width=row.width-157)
            text(app.screen, app.assets, f'×{owned}', (row.right-39,row.centery), 13, color if owned else MUTED, True, center=True)
            app.ui.actions.append((row, lambda value=key: setattr(self, 'item', value)))
        paging_y = right.y+36+6*row_h
        self._button((right.x, paging_y, 61, 25), 'Prev', lambda: setattr(self, 'food_page', self.food_page-1), disabled=self.food_page <= 0)
        text(app.screen, app.assets, f'Treats {self.food_page+1} / {pages}', (right.centerx,paging_y+13), 10, MUTED, center=True)
        self._button((right.right-61, paging_y, 61, 25), 'Next', lambda: setattr(self, 'food_page', self.food_page+1), disabled=self.food_page >= pages-1)
        item = app.shop_data().get(self.item, {})
        allowance = self.allowance(mon, item)
        amount = min(item.get('amount',0), allowance)
        owned = app.state.get('inventory',{}).get(self.item,0)
        fits = allowance > 0 if item.get('resource') == 'cam' else allowance >= item.get('amount', 1)
        ready = bool(item and owned and fits and not app.action_pending and not app.state.get('battle') and app.state.get('in_farm'))
        explanation = ('Waiting for the server…' if app.action_pending else
                       'ABI is at its permanent cap of 200.' if item.get('resource') == 'abi' and allowance <= 0 else
                       'This care bonus is at its limit.' if allowance <= 0 else
                       'This bonus will not fit. Choose a +1 treat instead.' if not fits else
                       'Buy this treat in the shop to feed it.' if not owned else
                       f"Use 1 {item.get('name','treat')} → {STAT_NAMES.get(item.get('resource'),'?')} +{amount}")
        text(app.screen, app.assets, explanation, (right.x,right.bottom-91), 11, GOLD if amount < item.get('amount',0) else MUTED,
             max_width=right.width)
        if item.get('resource') == 'abi' and allowance:
            text(app.screen, app.assets, f"ABI {mon.get('abi', 0)} → {mon.get('abi', 0)+amount} / 200 · Separate from stat care limits",
                 (right.x, right.bottom-70), 10, GOLD, max_width=right.width)
        if item.get('resource') != 'cam' and amount < item.get('amount',0) and allowance:
            text(app.screen, app.assets, 'No treat is consumed when its stat bonus exceeds the limit.', (right.x,right.bottom-70), 10, GOLD, max_width=right.width)
        self._button((right.x, right.bottom-43, right.width, 40), 'Feeding…' if app.action_pending else 'Feed one treat', self.feed, primary=True, disabled=not ready)

    def dim_background(self):
        app = self.app
        size = app.screen.surface.get_size()
        if getattr(self, '_dim_size', None) != size:
            self._dim_size = size
            self._dim = pygame.Surface((size[0], size[1]-round(94*app.screen.scale)), pygame.SRCALPHA)
            self._dim.fill((3, 10, 20, 180))
        app.screen.blit_native(self._dim, (0, 94))

    def draw_home_confirmation(self):
        app = self.app
        app.ui.actions, app.ui.fields = [], []
        self.dim_background()
        w, h = app.screen.get_size()
        rect = pygame.Rect((w-510)//2, (h-234)//2, 510, 234)
        app.presentation.card(rect, 'farm', accent=True)
        text(app.screen, app.assets, 'Return home?', (rect.x+26,rect.y+24), 27, WHITE, True)
        wrap(app.screen, app.assets, 'Leaving now forfeits this wild encounter. No victory rewards are earned. Your DigiFarm will be waiting.',
             (rect.x+26,rect.y+72), rect.width-52, 16, MUTED, 3)
        self._button((rect.x+26,rect.bottom-61,210,38), 'Stay in battle', lambda: setattr(self,'home_confirmation',False))
        def confirm():
            self.home_confirmation = False
            app.send('digifarm', action='enter', forfeit=True)
        self._button((rect.right-238,rect.bottom-61,212,38), 'Forfeit & return home', confirm, primary=True, disabled=app.action_pending)
