"""Native Digimon Venom NXT client: world, account, collection and combat views."""
from __future__ import annotations
import json
import math
from pathlib import Path
import queue
import random
import time
import pygame
from .assets import Assets, Audio
from .network import Connection
from .widgets import *
from .render import NativeCanvas, draw
from .display import DisplayManager
from .world import WorldRenderer
from .settings_panel import SettingsPanel
from .icon import get_icon


class App:
    SPEED = 180

    def __init__(self, root: Path, args):
        pygame.init()
        pygame.display.set_caption('Digimon Venom NXT')
        self.root, self.args = root, args
        self.display = DisplayManager(root, args)
        pygame.display.set_icon(get_icon())
        self.screen = NativeCanvas(self.display.surface, self.display.ui_scale)
        self.clock = pygame.time.Clock()
        self.assets = Assets(root)
        self.audio = Audio(self.assets)
        self.audio.set_volumes(self.display.settings['music_volume'], self.display.settings['effects_volume'])
        self.ui = UI(self.screen, self.assets)
        self.settings_open = False
        self.settings_panel = SettingsPanel(self)
        self.running = True
        self.now = 0.
        self.state = None
        self.players = {}
        self.player_render = {}
        self.position = pygame.Vector2(0, 0)
        self.follower = pygame.Vector2(0, 0)
        self.last_map = None
        self.walk_mask = None
        self.direction = 'down'
        self.moving = False
        self.menu = None
        self.scroll = 0
        self.selected_party = 0
        self.target = 0
        self.auth_tab = 'login'
        self.auth_pending = False
        self.action_pending = False
        self.status = 'Install the player kit supplied by your server administrator.'
        self.logs = []
        self.toasts = []
        self.animations = []
        self.battle_old = None
        self.battle_until = 0.
        self.move_timer = 0.
        self.sent_moving = False
        self.requests = {}
        self.connection = None
        self.tamer = next(iter(self.assets.tamers), '')
        rookies = [s for s in self.assets.species.values() if s.get('stage') == 'rookie' and not s.get('paradox')]
        self.starter = next((s['id'] for s in rookies if s['name'].lower() == 'agumon'), rookies[0]['id'] if rookies else '')
        self.auth_picker = None
        self.detail_species = None
        self.camera = pygame.Vector2()
        self.last_snapshot = 0.
        self.world = WorldRenderer(self)
        if args.demo:
            self.make_demo()
        else:
            self.connect()

    def connect(self):
        if self.connection:
            self.connection.close()
        path = Path(self.args.config) if self.args.config else self.root/'config/client.json'
        try:
            config = json.loads(path.read_text('utf-8')) if path.exists() else {}
            if self.args.dev:
                config = {**config, 'host': 'localhost', 'port': config.get('port', 8765), 'tls': False}
            self.connection = Connection(config, self.root, self.args.dev)
            self.status = 'Connecting to your server…'
        except (OSError, ValueError) as exc:
            self.status = str(exc)

    def make_demo(self):
        species = list(self.assets.species.values())
        preferred = [self.assets.species[self.starter]] if self.starter else []
        preferred += [s for s in species if s.get('stage') == 'rookie' and not s.get('paradox') and s['id'] != self.starter][:2]
        def mon(entry, index):
            stats = entry.get('base_stats', {})
            return {'uid': f'preview-{index}', 'species_id': entry['id'], 'name': entry['name'], 'level': 12,
                    'hp': 260+index*45, 'max_hp': 310+index*45, 'sp': 30, 'max_sp': 42, 'xp': 80, 'abi': 8,
                    'cam': 32, 'atk': stats.get('atk', 36), 'def': stats.get('def', 25), 'int': stats.get('int', 30),
                    'spd': stats.get('spd', 25), 'type': entry.get('type', 'Unknown'), 'attribute': entry.get('attribute', 'Unknown')}
        map_entry = next(iter(self.assets.maps.values()), {'id': '', 'spawn': [600, 300]})
        self.state = {'username': 'TamerPreview', 'tamer': self.tamer, 'map_id': map_entry['id'],
                      'x': map_entry.get('spawn', [600, 300])[0], 'y': map_entry.get('spawn', [600, 300])[1],
                      'credits': 2400, 'party': [mon(s, i) for i, s in enumerate(preferred)], 'storage': [],
                      'scan': {s['id']: 120 if i == 0 else 35 for i, s in enumerate(preferred)},
                      'inventory': {'hp_s': 5, 'hp_m': 2, 'hp_l': 1, 'sp_s': 3, 'sp_m': 1, 'sp_l': 1},
                      'in_lab': False, 'battle': None, 'events': []}
        if self.args.demo_battle and preferred:
            self.state['battle'] = {'enemies': [mon(s, i+3) for i, s in enumerate(preferred)], 'active': list(range(len(preferred))), 'actor': 0, 'turn': 1}
        self.position.update(self.state['x'], self.state['y'])
        self.follower.update(self.position+pygame.Vector2(-34, 26))
        self.status = 'OFFLINE VISUAL PREVIEW • no account progress'
        self.log('Offline visual preview. Connect to a dedicated server to play.', CYAN)

    def send(self, op, **payload):
        if self.args.demo:
            if op == 'digilab':
                self.state['in_lab'] = payload.get('action') != 'return'
                if payload.get('action') == 'return':
                    self.menu = None
                else:
                    self.menu = 'lab'
            else:
                self.toast('Visual preview only — start the dedicated server to play.')
            return
        if not self.connection or not self.connection.connected:
            self.toast('Server is disconnected. Reconnect from the sign-in screen.', RED)
            return
        from .motion import MovementPredictor
        if not hasattr(self, '_motion'):
            self._motion = MovementPredictor()
        # Send the input already predicted this frame before a gameplay action.
        # This keeps the action's authoritative coordinates in request order.
        if op != 'move':
            for movement in self._motion.take_buffer():
                self.send('move', **movement.payload())
        rid = self.connection.send(op, **payload)
        self.requests[rid] = op
        if op == 'move':
            self._motion.track(rid, payload)
        elif op in ('travel', 'digilab'):
            self._motion.transition_pending = rid
        # Movement does not require a pending state; authoritative updates arrive asynchronously.
        if op in ('login', 'register'):
            self.auth_pending = True
        elif op != 'move' and op != 'ping':
            self.action_pending = True
        return rid

    def log(self, message, color=MUTED):
        if message:
            self.logs.append((str(message), color))
            self.logs = self.logs[-80:]

    def toast(self, message, color=CYAN):
        self.toasts.append((str(message), color, self.now+5.))
        self.toasts = self.toasts[-3:]

    def poll(self):
        if not self.connection:
            return
        from .motion import MovementPredictor, RemoteMotion
        if not hasattr(self, '_motion'):
            self._motion = MovementPredictor()
        if not hasattr(self, '_remote_motion'):
            self._remote_motion = RemoteMotion()
        while True:
            try:
                message = self.connection.incoming.get_nowait()
            except queue.Empty:
                break
            op = message.get('op')
            if op == 'connected':
                self.status = 'Server connected. Sign in or create your tamer.'
            elif op == 'error':
                self.status = message.get('error', 'Connection error')
                self.auth_pending = self.action_pending = False
                self._motion.reset()
                self.toast(self.status, RED)
            elif op == 'chat':
                self.log(f"{message.get('username', 'World')}: {message.get('text', '')}", CYAN)
            elif op == 'world':
                self.players = {p['username']: p for p in message.get('players', []) if 'username' in p}
                self._remote_motion.push(self.now, self.players)
                self.last_snapshot = self.now
            elif op == 'result':
                rid = message.get('rid')
                request = self.requests.pop(rid, None)
                if self._motion.transition_pending == rid:
                    self._motion.transition_pending = None
                if request in ('register', 'login'):
                    self.auth_pending = False
                elif request != 'move':
                    self.action_pending = False
                if not message.get('ok', False):
                    self._motion.pending.pop(rid, None)
                    self.status = str(message.get('error', 'Request could not be completed.'))
                    self.toast(self.status, RED)
                    continue
                position = message.get('position')
                if position and self.state:
                    self.state.update({k:position[k] for k in ('map_id','x','y') if k in position})
                    entry = self.assets.maps.get(self.state.get('map_id'), {})
                    mask = self.assets.image(entry.get('walkable'))
                    desired = (position.get('x', self.position.x), position.get('y', self.position.y))
                    corrected = self._motion.reconcile(rid, desired, entry, mask,
                        reset=bool(self.state.get('battle') or self.state.get('in_lab')))
                    self.position.update(corrected)
                state = message.get('state')
                if state:
                    old_battle = self.state.get('battle') if self.state else None
                    old_map = self.state.get('map_id') if self.state else None
                    self.state = state
                    desired = pygame.Vector2(state.get('x', 0), state.get('y', 0))
                    teleport = request in ('register', 'login', 'travel', 'digilab') or old_map != state.get('map_id')
                    entry = self.assets.maps.get(state.get('map_id'), {})
                    mask = self.assets.image(entry.get('walkable'))
                    self.position.update(self._motion.reconcile(rid, desired, entry, mask,
                        reset=teleport or bool(state.get('battle') or state.get('in_lab'))))
                    if teleport:
                        self.follower.update(desired+pygame.Vector2(-34, 26))
                    if request in ('login', 'register'):
                        self.ui.focus = None
                        self.ui.values['password'] = ''
                        self.menu = None
                        self.log('Connected. WASD to move • E to search for encounters • F1 for DigiLab.', CYAN)
                    if request != 'ping':
                        self.consume_events(state.get('events', []))
                    if old_battle and not state.get('battle'):
                        self.battle_old = old_battle
                        self.battle_until = self.now+max(1.2, len(self.animations)*.5)
                    if request == 'digilab':
                        self.menu = 'lab' if state.get('in_lab') else None
                    if request == 'travel':
                        self.menu = None
                    if state.get('battle'):
                        self.menu = None
                        enemies = state['battle'].get('enemies', [])
                        if self.target >= len(enemies) or enemies[self.target].get('hp', 0) <= 0:
                            self.target = next((i for i, e in enumerate(enemies) if e.get('hp', 0) > 0), 0)

    def consume_events(self, events):
        start = self.now
        for event in events:
            kind = event.get('kind')
            if event.get('text'):
                self.log(event['text'], LIME if kind in ('win', 'scan', 'heal') else RED if kind == 'lose' else MUTED)
            if kind in ('damage', 'heal'):
                self.animations.append({**event, 'start': start, 'duration': 1.05})
                start += .4
            elif kind in ('win', 'lose', 'flee'):
                self.toast(event.get('text', kind.title()), LIME if kind == 'win' else GOLD)
        if any(e.get('kind') == 'damage' for e in events):
            self.audio.effect('hit')
        elif events:
            kinds = [e.get('kind') for e in events]
            self.audio.effect('heal' if 'heal' in kinds else 'scan' if 'scan' in kinds else 'confirm')

    def set_menu(self, menu):
        if self.state and self.state.get('battle'):
            self.toast('Finish the current battle first.')
            return
        self.menu = None if self.menu == menu else menu
        self.scroll = 0
        self.detail_species = None
        self.ui.values['search'] = ''
        self.ui.focus = None

    def enter_lab(self):
        if self.state and self.state.get('battle'):
            self.toast('Finish or flee the battle before returning to the DigiLab.')
        else:
            self.send('digilab', action='enter')

    def logout(self):
        self.state = None
        self.players.clear()
        self.menu = None
        self.ui.values['password'] = ''
        self.connect()

    def auth(self):
        username, password = self.ui.values.get('username', '').strip(), self.ui.values.get('password', '')
        if len(username) < 3 or not all(c.isascii() and (c.isalnum() or c == '_') for c in username) or len(username)>24:
            self.status = 'Use 3–24 letters, numbers or underscores for your username.'
            return
        if len(password) < 8:
            self.status = 'Your password must have at least 8 characters.'
            return
        payload = {'username': username, 'password': password}
        if self.auth_tab == 'register':
            if not self.tamer or not self.starter:
                self.status = 'Import the supplied assets before creating an account.'
                return
            payload.update(tamer=self.tamer, starter=self.starter)
        self.send(self.auth_tab, **payload)

    def update(self, dt):
        from .motion import MovementPredictor
        if not hasattr(self, '_motion'):
            self._motion = MovementPredictor()
        self.now = pygame.time.get_ticks()/1000
        self.poll()
        self.toasts = [t for t in self.toasts if t[2] > self.now]
        self.animations = [a for a in self.animations if a['start']+a['duration'] > self.now]
        if not self.state:
            self.audio.music()
            return
        self.audio.music(bool(self.state.get('battle')), self.state.get('map_id'), self.state.get('in_lab', False))
        map_id = self.state.get('map_id')
        if self.last_map != map_id:
            self.last_map = map_id
            entry = self.assets.maps.get(map_id, {})
            self.walk_mask = self.assets.image(entry.get('walkable'))
            self._motion.reset()
        keys = pygame.key.get_pressed()
        allowed = (not self.menu and not self.ui.focus and not getattr(self, 'settings_open', False)
                   and not self.state.get('battle') and not self.state.get('in_lab')
                   and self._motion.transition_pending is None
                   and (self.args.demo or self.connection and self.connection.connected))
        dx = int(keys[pygame.K_d] or keys[pygame.K_RIGHT])-int(keys[pygame.K_a] or keys[pygame.K_LEFT]) if allowed else 0
        dy = int(keys[pygame.K_s] or keys[pygame.K_DOWN])-int(keys[pygame.K_w] or keys[pygame.K_UP]) if allowed else 0
        vector = pygame.Vector2(dx, dy)
        if vector.length_squared() > 1:
            vector.normalize_ip()
        self.moving = bool(vector.length_squared())
        if self.moving:
            self.direction = (('down' if dy > 0 else 'up') + ('_right' if dx>0 else '_left') if dx and dy else ('down' if dy > 0 else 'up') if dy else ('right' if dx > 0 else 'left'))
        direction = (vector.x, vector.y)
        changed = direction != self._motion.last_direction
        if self.moving or self.sent_moving or self._motion.buffer:
            entry = self.assets.maps.get(map_id, {})
            self.position.update(self._motion.advance(self.position, vector.x, vector.y, dt, entry, self.walk_mask))
        # Flush each direction separately: a released key must not replace the
        # entire previous movement interval with a zero-direction packet.
        if changed or self._motion.buffered_time >= .05:
            for movement in self._motion.take_buffer():
                if not self.args.demo:
                    self.send('move', **movement.payload())
        self.move_timer = self._motion.buffered_time
        self._motion.last_direction = direction
        self.sent_moving = self.moving
        distance = self.follower.distance_to(self.position)
        if distance > 34:
            difference = self.position-self.follower
            self.follower += difference * (1-34/distance) * (1-math.exp(-12*dt))
        if hasattr(self, '_remote_motion'):
            self.player_render = {name: pygame.Vector2(point)
                                  for name, point in self._remote_motion.positions(self.now).items()}

    def toggle_settings(self):
        self.settings_open = not self.settings_open
        self.ui.focus = None
        pygame.key.stop_text_input()
        self.ui.actions, self.ui.fields = [], []
        if not self.settings_open:
            self.display.save()

    def apply_display(self, **changes):
        self.display.apply(**changes)
        self.screen = NativeCanvas(self.display.surface, self.display.ui_scale)
        self.ui.screen = self.screen
        self.ui.actions, self.ui.fields = [], []
        self.audio.set_volumes(self.display.settings['music_volume'], self.display.settings['effects_volume'])
        self.display.save()

    def set_zoom(self, value):
        self.world.set_zoom(value)
        self.display.settings['zoom'] = self.world.zoom
        self.display.save()

    def change_zoom(self, amount):
        self.set_zoom(self.world.zoom + amount)

    def field_visible(self):
        return bool(self.state and not self.settings_open and not self.menu and
                    not self.state.get('battle') and not self.state.get('in_lab'))

    def key(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.VIDEORESIZE:
            self.display.resize((event.w, event.h))
            self.screen = NativeCanvas(self.display.surface, self.display.ui_scale)
            self.ui.screen = self.screen
        elif event.type == getattr(pygame, 'WINDOWDISPLAYCHANGED', -1):
            self.apply_display()
        elif event.type == pygame.MOUSEWHEEL:
            if self.settings_open:
                return
            point = self.screen.to_logical_point(pygame.mouse.get_pos())
            if self.field_visible() and getattr(self, 'viewport', pygame.Rect(0,0,0,0)).collidepoint(point):
                self.change_zoom(event.y*.5)
            else:
                self.scroll = max(0, self.scroll-event.y*2)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11 or (event.key == pygame.K_RETURN and getattr(event, 'mod', 0)&pygame.KMOD_ALT):
                self.apply_display(fullscreen=not self.display.fullscreen)
                return
            if event.key == pygame.K_F10:
                self.toggle_settings()
                return
            if self.settings_open:
                if event.key == pygame.K_ESCAPE:
                    self.toggle_settings()
                return
            if event.key == pygame.K_RETURN:
                if not self.state and self.ui.focus:
                    self.auth()
                elif self.ui.focus == 'chat':
                    message = self.ui.values.get('chat', '').strip()
                    if message:
                        self.send('chat', text=message)
                        self.ui.values['chat'] = ''
                    self.ui.focus = None
                elif self.state and not self.menu:
                    self.ui.focus = 'chat'
                return
            if event.key == pygame.K_ESCAPE:
                if self.auth_picker:
                    self.auth_picker = None
                elif self.menu:
                    self.menu = None
                else:
                    self.toggle_settings()
                return
            if self.ui.focus or not self.state:
                return
            if event.key == pygame.K_F1: self.enter_lab()
            elif event.key == pygame.K_b: self.set_menu('shop')
            elif event.key == pygame.K_m: self.set_menu('maps')
            elif event.key in (pygame.K_TAB, pygame.K_j): self.set_menu('dex')
            elif event.key == pygame.K_p: self.set_menu('party')
            elif event.key == pygame.K_e and not self.menu and not self.state.get('battle'): self.send('encounter')
            elif event.key == pygame.K_SPACE and self.state.get('battle'): self.battle_action('attack')
            elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS) and self.field_visible(): self.change_zoom(.5)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS) and self.field_visible(): self.change_zoom(-.5)
            elif event.key in (pygame.K_0, pygame.K_KP_0) and self.field_visible(): self.set_zoom(1)

    def battle_action(self, action, item=None):
        if self.action_pending or self.animations:
            return
        battle = self.state.get('battle') if self.state else None
        if not battle:
            return
        payload = {'action': action, 'target': self.target, 'party_index': battle.get('actor', 0)}
        if item:
            payload.update(item=item, party_index=self.selected_party)
        self.send('battle', **payload)

    def draw_background(self):
        self.screen.fill(BG)
        w, h = self.screen.get_size()
        for x in range(0, w, 52):
            draw.line(self.screen, (13, 23, 37), (x, 0), (x, h))
        for y in range(0, h, 52):
            draw.line(self.screen, (13, 23, 37), (0, y), (w, y))

    def draw(self):
        self.ui.begin()
        self.draw_background()
        if not self.state:
            self.draw_auth()
        else:
            self.draw_game()
        if self.settings_open:
            self.settings_panel.draw()
        if self.display.settings.get('show_fps'):
            text(self.screen, self.assets, f'{self.clock.get_fps():.0f} FPS',
                 (self.screen.get_width()-81, self.screen.get_height()-16), 11, CYAN, True)
        for i, (message, color, until) in enumerate(self.toasts):
            width = min(self.screen.get_width()-80, max(440, self.assets.font(16).size(message)[0]+32))
            rect = pygame.Rect((self.screen.get_width()-width)//2, self.screen.get_height()-55-i*48, width, 40)
            panel(self.screen, rect, (29, 46, 63), color, 9)
            text(self.screen, self.assets, message, rect.center, 15, color, max_width=rect.width-24, center=True)
        pygame.display.flip()

    def draw_auth(self):
        w, h = self.screen.get_size()
        left = pygame.Rect(50, 65, max(390, w-640), h-130)
        text(self.screen, self.assets, 'DIGITAL WORLD // ONLINE', (left.x, left.y+20), 16, CYAN, True)
        text(self.screen, self.assets, 'DIGIMON', (left.x, left.y+70), 58, WHITE, True)
        text(self.screen, self.assets, 'VENOM NXT', (left.x, left.y+135), 48, LIME, True)
        wrap(self.screen, self.assets, 'Build your bond. Discover the Digital World.', (left.x, left.y+215), left.width-20, 24, WHITE, 2)
        wrap(self.screen, self.assets, 'An online adventure with real-time exploration, a six-partner roster and tactical three-on-three battles.', (left.x, left.y+294), left.width-20, 18, MUTED, 3)
        entries = [s for s in self.assets.species.values() if s.get('stage')=='rookie' and not s.get('paradox')][:4]
        for i, entry in enumerate(entries):
            bx = left.x+55+i*min(112, (left.width-50)//4)
            by = left.bottom-110 + math.sin(self.now*1.5+i)*3
            draw.ellipse(self.screen, (20, 55, 64), (bx-40, by+38, 80, 18))
            surface = self.assets.sprite(entry['id'], (96, 105))
            if surface: self.screen.blit(surface, surface.get_rect(midbottom=(bx, by+48)))
        text(self.screen, self.assets, 'NATIVE WINDOWS CLIENT  /  ALPHA 0.1.1', (left.x, left.bottom-32), 13, MUTED)
        self.ui.button((left.x, left.bottom+5, 142, 34), 'Settings  F10', self.toggle_settings, small=True)
        text(self.screen, self.assets, 'F11  /  FULLSCREEN', (left.x+160, left.bottom+16), 11, CYAN)
        card = pygame.Rect(w-540, 58, 490, h-116)
        panel(self.screen, card, PANEL, LINE, 20)
        x, y = card.x+30, card.y+25
        text(self.screen, self.assets, 'YOUR NEXT ADVENTURE', (x, y), 14, CYAN, True)
        text(self.screen, self.assets, 'Welcome, Tamer', (x, y+29), 30, WHITE, True)
        for i, (key, label) in enumerate((('login', 'Sign in'), ('register', 'Create account'))):
            self.ui.button((x+i*218, y+85, 207, 42), label, lambda k=key: setattr(self, 'auth_tab', k), selected=self.auth_tab==key)
        text(self.screen, self.assets, 'USERNAME', (x, y+151), 12, MUTED, True)
        self.ui.field((x, y+176, 428, 46), 'username', 'Your tamer username')
        text(self.screen, self.assets, 'PASSWORD', (x, y+242), 12, MUTED, True)
        self.ui.field((x, y+267, 428, 46), 'password', 'At least 8 characters', password=True)
        next_y = y+337
        if self.auth_tab == 'register':
            for col, (kind, label, ident) in enumerate((('tamer', 'TAMER APPEARANCE', self.tamer), ('starter', 'ROOKIE PARTNER', self.starter))):
                rx = x+col*218
                text(self.screen, self.assets, label, (rx, next_y), 11, MUTED, True)
                entry = self.assets.tamers.get(ident, {}) if kind == 'tamer' else self.assets.species.get(ident, {})
                surface = self.assets.tamer(ident, moving=True, now=self.now, box=(60, 64)) if kind == 'tamer' else self.assets.sprite(ident, (65, 64))
                if surface: self.screen.blit(surface, surface.get_rect(center=(rx+33, next_y+57)))
                self.ui.button((rx+70, next_y+26, 138, 62), entry.get('name', 'Select'), lambda k=kind: self.open_picker(k), small=True)
            next_y += 105
        self.ui.button((x, next_y, 428, 48), 'Connecting…' if self.auth_pending else 'Enter the Digital World' if self.auth_tab=='login' else 'Begin your adventure', self.auth, primary=True, disabled=self.auth_pending or not (self.connection and self.connection.connected))
        wrap(self.screen, self.assets, self.status, (x, next_y+65), 428, 14, MUTED, 3)
        self.ui.button((x, card.bottom-50, 125, 30), 'Reconnect', self.connect, small=True)
        text(self.screen, self.assets, ('TLS VERIFIED' if self.connection and self.connection.connected else 'TLS REQUIRED') if not self.args.dev else 'LOCAL DEVELOPMENT', (x+145, card.bottom-43), 12, CYAN)
        if self.auth_picker:
            self.draw_picker()

    def open_picker(self, kind):
        self.auth_picker = kind
        self.ui.focus = None
        self.scroll = 0
        self.ui.values['search'] = ''

    def draw_picker(self):
        self.ui.actions = []
        self.ui.fields = []
        w, h = self.screen.get_size()
        if not hasattr(self, '_picker_overlay') or self._picker_overlay.get_size() != self.display.surface.get_size():
            self._picker_overlay = pygame.Surface(self.display.surface.get_size(), pygame.SRCALPHA)
            self._picker_overlay.fill((0, 0, 0, 195))
        self.screen.blit_native(self._picker_overlay, (0, 0))
        rect = pygame.Rect(80, 55, w-160, h-110)
        panel(self.screen, rect, PANEL, CYAN, 18)
        kind = self.auth_picker
        text(self.screen, self.assets, 'Choose your tamer' if kind=='tamer' else 'Choose your rookie partner', (rect.x+24, rect.y+22), 27, WHITE, True)
        self.ui.button((rect.right-90, rect.y+20, 64, 34), 'Close', lambda: setattr(self, 'auth_picker', None), small=True)
        self.ui.field((rect.x+24, rect.y+70, rect.width-48, 40), 'search', 'Search all available appearances…' if kind=='tamer' else 'Search rookie partners…')
        query = self.ui.values.get('search', '').lower()
        entries = list(self.assets.tamers.values()) if kind=='tamer' else [s for s in self.assets.species.values() if s.get('stage')=='rookie' and not s.get('paradox')]
        entries = [e for e in entries if query in e['name'].lower()]
        cols = max(4, (rect.width-48)//160)
        cellw = (rect.width-48)//cols
        rows = max(1, (rect.height-155)//142)
        self.scroll = min(self.scroll, max(0, math.ceil(len(entries)/cols)-rows))
        for n, entry in enumerate(entries[self.scroll*cols:(self.scroll+rows)*cols]):
            cell = pygame.Rect(rect.x+24+(n%cols)*cellw, rect.y+124+(n//cols)*142, cellw-10, 132)
            selected = entry['id'] == (self.tamer if kind=='tamer' else self.starter)
            panel(self.screen, cell, (28, 48, 62) if selected else CARD, LIME if selected else LINE, 10)
            surface = self.assets.tamer(entry['id'], moving=True, now=self.now, box=(80, 80)) if kind=='tamer' else self.assets.sprite(entry['id'], (96, 80))
            if surface: self.screen.blit(surface, surface.get_rect(center=(cell.centerx, cell.y+48)))
            text(self.screen, self.assets, entry['name'], (cell.centerx, cell.bottom-32), 13, WHITE, max_width=cell.width-10, center=True)
            def pick(ident=entry['id']):
                if kind=='tamer': self.tamer = ident
                else: self.starter = ident
                self.auth_picker = None
            self.ui.actions.append((cell, pick))
        text(self.screen, self.assets, f'{len(entries)} available • Mouse wheel to browse', (rect.x+24, rect.bottom-27), 13, MUTED)

    def draw_game(self):
        w, h = self.screen.get_size()
        draw.rect(self.screen, (13, 23, 38), (0, 0, w, 76))
        draw.line(self.screen, LINE, (0, 75), (w, 75))
        text(self.screen, self.assets, 'VENOM', (22, 11), 27, WHITE, True)
        text(self.screen, self.assets, 'NXT / DIGITAL WORLD', (24, 45), 11, CYAN, True)
        tabs = [('dex', 'Digidex', 'J'), ('party', 'Partners', 'P'), ('shop', 'Shop', 'B'), ('maps', 'Worlds', 'M')]
        for i, (key, label, shortcut) in enumerate(tabs):
            self.ui.button((210+i*100, 20, 91, 37), f'{label}  {shortcut}', lambda k=key: self.set_menu(k), selected=self.menu==key, small=True)
        self.ui.button((625, 20, 91, 37), 'Settings', self.toggle_settings, selected=self.settings_open, small=True)
        self.ui.button((w-430, 18, 147, 41), 'DigiLab  F1', self.enter_lab, primary=True, disabled=bool(self.state.get('battle')))
        text(self.screen, self.assets, f"{self.state.get('credits', 0):,} ¥", (w-263, 15), 19, GOLD, True)
        text(self.screen, self.assets, self.state.get('username', ''), (w-263, 43), 12, MUTED, max_width=120)
        self.ui.button((w-128, 17, 42, 40), '♪' if self.audio.enabled else '♫', self.audio.toggle)
        self.ui.button((w-77, 17, 55, 40), 'Exit', self.logout, small=True)
        self.viewport = pygame.Rect(20, 94, w-352, h-262)
        if self.state.get('battle') or self.battle_old and self.now < self.battle_until:
            self.draw_battle()
        elif self.state.get('in_lab'):
            self.draw_lab_world()
        else:
            self.draw_world()
        self.draw_party_sidebar(pygame.Rect(w-312, 94, 292, h-115))
        self.draw_log(pygame.Rect(20, h-152, w-352, 132))
        if self.menu:
            self.draw_menu()
        if self.args.demo:
            text(self.screen, self.assets, 'OFFLINE VISUAL PREVIEW — NOT CONNECTED', (self.viewport.centerx, h-163), 11, GOLD, center=True)
        elif not self.connection or not self.connection.connected:
            text(self.screen, self.assets, 'DISCONNECTED • Exit to reconnect', (self.viewport.centerx, h-163), 12, RED, center=True)

    def draw_world(self):
        self.world.draw(self.viewport)

    def draw_party_sidebar(self, rect):
        panel(self.screen, rect)
        text(self.screen, self.assets, 'YOUR PARTNERS', (rect.x+18, rect.y+17), 14, CYAN, True)
        party = self.state.get('party', [])
        text(self.screen, self.assets, f'{len(party)} / 6', (rect.right-58, rect.y+17), 13, MUTED)
        height = min(92, (rect.height-97)//6)
        self.selected_party = min(self.selected_party, max(0, len(party)-1))
        for i in range(6):
            card = pygame.Rect(rect.x+12, rect.y+50+i*(height+5), rect.width-24, height)
            selected = self.selected_party == i
            panel(self.screen, card, CARD if i<len(party) else (12, 22, 36), CYAN if selected and i<len(party) else LINE, 9)
            if i >= len(party):
                text(self.screen, self.assets, f'0{i+1}  /  Partner slot', card.center, 13, (73, 98, 121), center=True)
                continue
            mon = party[i]
            sprite = self.assets.sprite(mon['species_id'], (61, height-18), now=self.now)
            if sprite: self.screen.blit(sprite, sprite.get_rect(center=(card.x+39, card.centery)))
            x = card.x+77
            text(self.screen, self.assets, mon['name'], (x, card.y+8), 14, WHITE, True, card.width-83)
            text(self.screen, self.assets, f"Lv.{mon['level']}  {'LEAD' if i==0 else 'ACTIVE' if i<3 else 'RESERVE'}", (x, card.y+28), 10, LIME if i<3 else MUTED)
            bar(self.screen, pygame.Rect(x, card.y+47, card.width-91, 6), mon.get('hp', 0), mon.get('max_hp', 1), LIME)
            bar(self.screen, pygame.Rect(x, card.y+60, card.width-91, 4), mon.get('sp', 0), mon.get('max_sp', 1), CYAN)
            if height >= 85:
                text(self.screen, self.assets, f"HP {mon.get('hp', 0)}/{mon.get('max_hp', 0)}   SP {mon.get('sp', 0)}", (x, card.y+71), 10, MUTED)
            self.ui.actions.append((card, lambda index=i: setattr(self, 'selected_party', index)))
        y = rect.bottom-43
        self.ui.button((rect.x+13, y, rect.width-26, 30), 'Manage partners  P', lambda: self.set_menu('party'), small=True, disabled=bool(self.state.get('battle')))

    def draw_log(self, rect):
        panel(self.screen, rect)
        text(self.screen, self.assets, 'WORLD FEED', (rect.x+15, rect.y+10), 11, CYAN, True)
        for i, (message, color) in enumerate(self.logs[-3:]):
            text(self.screen, self.assets, message, (rect.x+15, rect.y+31+i*20), 13, color, max_width=rect.width-30)
        self.ui.field((rect.x+12, rect.bottom-35, rect.width-89, 27), 'chat', 'Enter to chat with your world…', size=13)
        def chat():
            message = self.ui.values.get('chat', '').strip()
            if message:
                self.send('chat', text=message)
                self.ui.values['chat'] = ''
        self.ui.button((rect.right-68, rect.bottom-35, 55, 27), 'Send', chat, small=True)

    def draw_lab_world(self):
        view = self.viewport
        panel(self.screen, view, (13, 34, 47), CYAN, 14)
        center = (view.centerx, view.centery+40)
        for radius in range(70, 260, 50):
            draw.ellipse(self.screen, (25, 62, 74), (center[0]-radius, center[1]-radius/2, radius*2, radius), 2)
        for n, mon in enumerate(self.state.get('party', [])[:3]):
            pos = (view.centerx+(n-1)*155, view.centery+55)
            sprite = self.assets.sprite(mon['species_id'], (120, 150), now=self.now)
            if sprite: self.screen.blit(sprite, sprite.get_rect(midbottom=pos))
        text(self.screen, self.assets, 'DIGILAB', (view.centerx, view.y+52), 38, WHITE, True, center=True)
        text(self.screen, self.assets, 'Restore. Materialize. Digivolve.', (view.centerx, view.y+102), 18, CYAN, center=True)
        self.ui.button((view.centerx-210, view.bottom-75, 200, 43), 'Heal all partners', lambda:self.send('digilab', action='heal'), primary=True)
        self.ui.button((view.centerx+10, view.bottom-75, 200, 43), 'Return to field', lambda:self.send('digilab', action='return'))

    def battle_positions(self, side, index, count):
        view = self.viewport
        slots = max(1, count)
        x = view.x+view.width*(index+1)/(slots+1)
        y = view.y+view.height*(.42 if side=='enemy' else .78)
        return pygame.Vector2(x, y)

    def draw_battle(self):
        view = self.viewport
        battle = self.state.get('battle') or self.battle_old
        enemies, party = battle.get('enemies', []), self.state.get('party', [])
        active = battle.get('active', list(range(min(3, len(party)))))
        panel(self.screen, view, (14, 24, 42), (62, 84, 105), 14)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(view)
        for y in range(view.y+80, view.bottom-25, 36):
            draw.line(self.screen, (22, 43, 62), (view.x, y), (view.right, y))
        for x in range(view.x-300, view.right+300, 85):
            draw.line(self.screen, (22, 43, 62), (view.centerx+(x-view.centerx)*.25, view.y+80), (x, view.bottom))
        text(self.screen, self.assets, 'ENCOUNTER  /  WILD DIGIMON', (view.x+20, view.y+18), 16, CYAN, True)
        text(self.screen, self.assets, f"TURN {battle.get('turn', 1):02}", (view.right-99, view.y+23), 16, GOLD, True)
        actor = battle.get('actor', 0)
        for side, mons in (('enemy', enemies), ('player', [party[i] for i in active if i < len(party)])):
            for index, mon in enumerate(mons):
                actual_index = index if side=='enemy' else active[index]
                pos = self.battle_positions(side, index, len(mons))
                attacking, hit = False, False
                for a in self.animations:
                    age = self.now-a['start']
                    if 0 <= age < .42 and a.get('attacker_side') == side and a.get('attacker_index') == actual_index:
                        attacking = True
                        dest_side = a.get('side', 'enemy')
                        dest_idx = a.get('index', 0)
                        dest = self.battle_positions(dest_side, dest_idx, len(enemies) if dest_side=='enemy' else len(active))
                        pos += (dest-pos)*math.sin(age/.42*math.pi)*.55
                    if .18 < age < .5 and a.get('side') == side and a.get('index') == actual_index:
                        hit = True
                        pos.x += math.sin(age*85)*5
                size = (112, 86) if view.height<500 else (135, 104)
                sprite = self.assets.sprite(mon['species_id'], size, 'attack' if attacking else 'idle', self.now)
                draw.ellipse(self.screen, (13, 53, 64) if side=='player' else (52, 29, 55), (int(pos.x)-62, int(pos.y)-7, 124, 24))
                if sprite:
                    copy = sprite.copy() if mon.get('hp', 0)<=0 else sprite
                    if mon.get('hp', 0)<=0: copy.set_alpha(75)
                    self.screen.blit(copy, copy.get_rect(midbottom=(int(pos.x), int(pos.y))))
                name_y = int(pos.y)-size[1]-31
                text(self.screen, self.assets, mon['name'], (pos.x, name_y), 15, RED if side=='enemy' else WHITE, True, 200, True)
                text(self.screen, self.assets, f"Lv.{mon.get('level', 1)} · {mon.get('type', '?')} / {mon.get('attribute', '?')}", (pos.x, name_y+22), 11, MUTED, max_width=220, center=True)
                bar(self.screen, pygame.Rect(int(pos.x)-65, int(pos.y)+20, 130, 7), mon.get('hp', 0), mon.get('max_hp', 1), RED if side=='enemy' else LIME)
                if side=='player':
                    bar(self.screen, pygame.Rect(int(pos.x)-65, int(pos.y)+32, 130, 4), mon.get('sp', 0), mon.get('max_sp', 1), CYAN)
                    if actor == actual_index and self.state.get('battle'):
                        text(self.screen, self.assets, 'YOUR TURN', (pos.x, int(pos.y)+49), 11, LIME, True, center=True)
                elif mon.get('hp', 0)>0:
                    target_rect = pygame.Rect(int(pos.x)-83, int(pos.y)-size[1]-50, 166, size[1]+93)
                    if index==self.target:
                        draw.rect(self.screen, GOLD, target_rect, 2, border_radius=13)
                        text(self.screen, self.assets, 'TARGET', (pos.x, target_rect.y+9), 9, GOLD, True, center=True)
                    self.ui.actions.append((target_rect, lambda i=index: setattr(self, 'target', i)))
        for animation in self.animations:
            self.draw_effect(animation, enemies, active)
        self.screen.set_clip(old_clip)
        disabled = bool(self.action_pending or self.animations or not self.state.get('battle'))
        actions = [('Attack', 'attack'), ('Skill · SP', 'skill'), ('Struggle · 0 SP', 'struggle'), ('Items', 'items'), ('Flee', 'flee')]
        width = (view.width-40-4*8)//5
        for i, (label, action) in enumerate(actions):
            self.ui.button((view.x+20+i*(width+8), view.bottom-48, width, 34), label,
                           (lambda: setattr(self, 'menu', 'battle_items')) if action=='items' else (lambda: setattr(self, 'menu', 'skills')) if action=='skill' else lambda a=action:self.battle_action(a),
                           primary=action=='attack', disabled=disabled, small=True)

    def draw_effect(self, effect, enemies, active):
        age = self.now-effect['start']
        if age<0: return
        side = effect.get('side', 'enemy')
        idx = effect.get('index', 0)
        if side=='player':
            idx = active.index(idx) if idx in active else 0
        pos = self.battle_positions(side, idx, len(enemies) if side=='enemy' else len(active))
        pos.y -= 65
        alpha = int(max(0, min(1, age/.09, (1.05-age)/.35))*255)
        color = LIME if effect.get('kind')=='heal' else GOLD if effect.get('effectiveness', 1)>1 else WHITE
        physical_size = self.screen.to_physical_rect(self.viewport).size
        if (not hasattr(self, '_effect_layer') or self._effect_layer.surface.get_size() != physical_size
                or self._effect_layer.scale != self.screen.scale):
            self._effect_layer = NativeCanvas(pygame.Surface(physical_size, pygame.SRCALPHA), self.screen.scale)
        layer = self._effect_layer
        layer.fill((0, 0, 0, 0))
        local = pos-pygame.Vector2(self.viewport.topleft)
        effect_catalog = self.assets.catalog.get('battle_effects', {})
        effects = effect_catalog.get('effects', []) if isinstance(effect_catalog, dict) else effect_catalog
        if effects:
            element = effect.get('attribute', 'neutral')
            effect_id = effect_catalog.get('attribute_effects', {}).get(element, 'dawn_023') if isinstance(effect_catalog, dict) else 'dawn_023'
            if effect.get('kind')=='heal':
                effect_id = effect_catalog.get('event_effects', {}).get('heal', 'dawn_155') if isinstance(effect_catalog, dict) else 'dawn_155'
            chosen = next((e for e in effects if e.get('id')==effect_id), effects[0])
            frames = chosen.get('frames', [])
            frame_index = int(age/max(.01, chosen.get('frame_seconds', .08)))
            if frame_index<len(frames):
                path = frames[frame_index]
                source = self.assets.image(path)
                frame = self.assets.fit(source, (190, 190), key=('effect', path)) if source else None
                if frame: layer.blit(frame, frame.get_rect(center=(int(local.x), int(local.y))))
        for i in range(16):
            angle = i*math.tau/16+.2
            radius = age*130
            particle = local+pygame.Vector2(math.cos(angle), math.sin(angle))*radius
            draw.circle(layer, (*color, max(0, alpha-70)), (int(particle.x), int(particle.y)), max(1, int(5*(1-age))))
        amount = int(effect.get('amount', 0))
        value = f'+{amount}' if effect.get('kind')=='heal' else str(amount)
        outlined_text(layer, self.assets, value, (local.x, local.y-age*50),
                      size=34, color=color, alpha=alpha, outline_width=2)
        multiplier = effect.get('effectiveness', 1)
        label = 'HEALED' if effect.get('kind')=='heal' else f'SUPER EFFECTIVE ×{multiplier:g}' if multiplier>1 else f'RESISTED ×{multiplier:g}' if multiplier<1 else 'NORMAL'
        outlined_text(layer, self.assets, label, (local.x, local.y-age*50+28),
                      size=11, color=color, alpha=alpha, outline_width=1)
        self.screen.blit_native(layer.surface, self.viewport.topleft)

    def draw_menu(self):
        view = self.viewport
        self.ui.actions = [(area, callback) for area, callback in self.ui.actions if not area.colliderect(view)]
        self.ui.fields = [(area, key) for area, key in self.ui.fields if not area.colliderect(view)]
        # Menu occupies the field viewport while keeping the live party and event feed visible.
        rect = view.inflate(-16, -16)
        panel(self.screen, rect, PANEL, CYAN, 13)
        titles = {'dex':'DIGIDEX / SCAN DATA', 'party':'PARTNERS / ROSTER', 'shop':'ITEM SHOP', 'maps':'WORLD TRANSFER', 'lab':'DIGILAB', 'battle_items':'BATTLE ITEMS', 'skills':'SELECT A SKILL'}
        text(self.screen, self.assets, titles.get(self.menu, 'MENU'), (rect.x+20, rect.y+17), 22, WHITE, True)
        self.ui.button((rect.right-82, rect.y+15, 63, 30), 'Close', lambda:setattr(self, 'menu', None), small=True)
        body = pygame.Rect(rect.x+20, rect.y+62, rect.width-40, rect.height-82)
        if self.menu == 'dex': self.draw_dex(body)
        elif self.menu == 'party': self.draw_roster(body)
        elif self.menu in ('shop', 'battle_items'): self.draw_shop(body, self.menu=='battle_items')
        elif self.menu == 'maps': self.draw_maps(body)
        elif self.menu == 'lab': self.draw_lab_menu(body)
        elif self.menu == 'skills': self.draw_skills(body)

    def draw_lab_menu(self, rect):
        text(self.screen, self.assets, 'A moment to reconnect.', (rect.x, rect.y+4), 28, CYAN, True)
        wrap(self.screen, self.assets, 'Your partners are fully restored when you enter. Return to the exact place you left whenever you are ready.', (rect.x, rect.y+49), rect.width, 17, MUTED, 3)
        buttons = [('Heal all partners', lambda:self.send('digilab', action='heal'), True), ('Return to field', lambda:self.send('digilab', action='return'), False), ('Materialize scan data', lambda:self.set_menu('dex'), False), ('Manage / digivolve', lambda:self.set_menu('party'), False)]
        bw = (rect.width-16)//2
        for i,(label,callback,primary) in enumerate(buttons):
            self.ui.button((rect.x+(i%2)*(bw+16), rect.y+122+(i//2)*63, bw, 48), label, callback, primary=primary, disabled=self.action_pending)
        for i,mon in enumerate(self.state.get('party', [])[:3]):
            sprite = self.assets.sprite(mon['species_id'], (115, 100), now=self.now)
            if sprite: self.screen.blit(sprite, sprite.get_rect(midbottom=(rect.x+rect.width*(i+1)/4, rect.bottom)))

    def draw_dex(self, rect):
        self.ui.field((rect.x, rect.y, rect.width, 37), 'search', 'Search all Digimon, including Paradox variants…', size=15)
        query = self.ui.values.get('search', '').lower()
        scans = self.state.get('scan', {})
        entries = [s for s in self.assets.species.values() if query in s['name'].lower() or query in s.get('stage', '').lower()]
        entries.sort(key=lambda s:(-scans.get(s['id'], 0), s['name']))
        rows = max(1, (rect.height-80)//72)
        self.scroll = min(self.scroll, max(0, len(entries)-rows))
        for i, entry in enumerate(entries[self.scroll:self.scroll+rows]):
            row = pygame.Rect(rect.x, rect.y+50+i*72, rect.width, 64)
            panel(self.screen, row, CARD, LINE, 8)
            sprite = self.assets.sprite(entry['id'], (52, 53), now=self.now)
            if sprite: self.screen.blit(sprite, sprite.get_rect(center=(row.x+35, row.centery)))
            percentage = scans.get(entry['id'], 0)
            text(self.screen, self.assets, entry['name'], (row.x+75, row.y+9), 16, GOLD if entry.get('paradox') else WHITE, True, row.width-315)
            text(self.screen, self.assets, f"{entry.get('stage', '?').replace('_', ' ').title()} · {entry.get('type', '?')} / {entry.get('attribute', '?')}", (row.x+75, row.y+36), 11, MUTED, max_width=row.width-310)
            bar(self.screen, pygame.Rect(row.right-240, row.y+34, 109, 7), percentage, 100, GOLD if entry.get('paradox') else CYAN)
            text(self.screen, self.assets, f'{percentage:g}% SCAN', (row.right-240, row.y+12), 11, GOLD if percentage>=100 else MUTED, True)
            self.ui.button((row.right-117, row.y+14, 106, 35), 'Materialize', lambda ident=entry['id']:self.send('materialize', species_id=ident), primary=percentage>=100, disabled=percentage<100 or self.action_pending, small=True)
        text(self.screen, self.assets, f'{len(entries)} Digimon · 100% scan + DigiLab to materialize · Scroll to browse', (rect.x, rect.bottom-15), 11, MUTED, max_width=rect.width)

    def draw_roster(self, rect):
        party = self.state.get('party', [])
        if not party:
            text(self.screen, self.assets, 'No partners in your party.', rect.topleft)
            return
        index = min(self.selected_party, len(party)-1)
        mon = party[index]
        sprite = self.assets.sprite(mon['species_id'], (130, 132), now=self.now)
        if sprite: self.screen.blit(sprite, sprite.get_rect(center=(rect.x+73, rect.y+63)))
        x = rect.x+156
        text(self.screen, self.assets, mon['name'], (x, rect.y), 25, WHITE, True, rect.width-160)
        text(self.screen, self.assets, f"Lv.{mon['level']}  •  {mon.get('type', '?')} / {mon.get('attribute', '?')}", (x, rect.y+38), 15, CYAN)
        text(self.screen, self.assets, f"ABI  {mon.get('abi', 0)}      CAM  {mon.get('cam', 0)}%      EXP  {mon.get('xp', 0)}", (x, rect.y+66), 14, GOLD)
        text(self.screen, self.assets, f"ATK {mon.get('atk', 0)}    DEF {mon.get('def', 0)}    INT {mon.get('int', 0)}    SPD {mon.get('spd', 0)}", (x, rect.y+94), 13, MUTED)
        self.ui.button((rect.x, rect.y+141, 156, 35), 'Make leader', lambda:self.send('party', action='lead', index=index), primary=True, disabled=index==0 or self.action_pending, small=True)
        self.ui.button((rect.x+166, rect.y+141, 156, 35), 'Move to storage', lambda:self.send('party', action='deposit', index=index), disabled=len(party)<2 or self.action_pending, small=True)
        text(self.screen, self.assets, 'Select any partner in the right panel.', (rect.x+334, rect.y+152), 11, MUTED, max_width=rect.width-334)
        # Evolution requirements come from the authoritative game state.
        options = self.state.get('evolution_options', [])
        options = options[index] if isinstance(options, list) and index<len(options) else options.get(str(index), []) if isinstance(options, dict) else []
        storage = self.state.get('storage', [])
        text(self.screen, self.assets, 'DIGIVOLUTION / DE-DIGIVOLUTION', (rect.x, rect.y+199), 12, CYAN, True)
        combined = [('evolve', route) for route in options] + [('storage', item) for item in storage]
        rows = max(1, (rect.height-237)//58)
        self.scroll = min(self.scroll, max(0, len(combined)-rows))
        for n,(kind,entry) in enumerate(combined[self.scroll:self.scroll+rows]):
            row = pygame.Rect(rect.x, rect.y+225+n*58, rect.width, 52)
            panel(self.screen, row, CARD, LINE, 7)
            if kind=='evolve':
                name = entry.get('name', entry.get('to', '?'))
                eligible = entry.get('eligible', False)
                text(self.screen, self.assets, name, (row.x+12, row.y+7), 14, WHITE, True, row.width-170)
                missing = entry.get('missing', [])
                if isinstance(missing, list): missing = ' · '.join(str(m) for m in missing)
                info = 'Ready to de-digivolve' if entry.get('devolve') and eligible else 'Requirements met' if eligible else str(missing or f"Lv.{entry.get('level', 1)} · ABI {entry.get('abi', 0)} · CAM {entry.get('cam', 0)}")
                text(self.screen, self.assets, info, (row.x+12, row.y+29), 11, LIME if eligible else MUTED, max_width=row.width-168)
                self.ui.button((row.right-127, row.y+9, 115, 33), 'De-digivolve' if entry.get('devolve') else 'Digivolve', lambda to=entry['to']:self.send('evolve', party_index=index, to=to), primary=eligible, disabled=not eligible or self.action_pending, small=True)
            else:
                storage_index = storage.index(entry)
                text(self.screen, self.assets, f"STORAGE  •  {entry['name']}  Lv.{entry['level']}", (row.x+12, row.y+16), 14, WHITE, max_width=row.width-170)
                self.ui.button((row.right-127, row.y+9, 115, 33), 'Withdraw', lambda i=storage_index:self.send('party', action='withdraw', index=i), disabled=len(party)>=6 or self.action_pending, small=True)
        if not combined:
            wrap(self.screen, self.assets, 'No routes or stored partners yet. Scan more Digimon in the wild to expand your roster.', (rect.x, rect.y+232), rect.width, 16, MUTED)
        text(self.screen, self.assets, 'Scroll for more routes and storage • First 3 partners form your active battle team', (rect.x, rect.bottom-13), 11, MUTED, max_width=rect.width)

    def shop_data(self):
        if self.state.get('shop'):
            return self.state['shop']
        return {key:{'name':label, 'price':price, 'resource':resource, 'amount':amount} for key,label,price,resource,amount in [('hp_s','HP Capsule S',100,'hp',100), ('hp_m','HP Capsule M',350,'hp',500), ('hp_l','HP Capsule L',800,'hp',1500), ('sp_s','SP Capsule S',200,'sp',30), ('sp_m','SP Capsule M',650,'sp',100), ('sp_l','SP Capsule L',1400,'sp',9999)]}

    def draw_shop(self, rect, battle=False):
        party = self.state.get('party', [])
        selected = party[self.selected_party] if party else None
        text(self.screen, self.assets, 'Restore health and skill points.', (rect.x, rect.y), 20, CYAN, True)
        text(self.screen, self.assets, f"Using items on: {selected['name'] if selected else 'no partner'} · select a partner on the right", (rect.x, rect.y+34), 13, MUTED, max_width=rect.width)
        shop, inventory = self.shop_data(), self.state.get('inventory', {})
        rows = max(1, (rect.height-74)//58)
        entries = list(shop.items())
        self.scroll = min(self.scroll, max(0, len(entries)-rows))
        for i,(key,item) in enumerate(entries[self.scroll:self.scroll+rows]):
            row = pygame.Rect(rect.x, rect.y+65+i*58, rect.width, 50)
            panel(self.screen, row, CARD, LINE, 7)
            color = CYAN if item.get('resource')=='sp' else LIME
            draw.circle(self.screen, color, (row.x+23, row.centery), 10, 2)
            text(self.screen, self.assets, '+' if item.get('resource')=='hp' else 'S', (row.x+23, row.centery), 13, color, True, center=True)
            text(self.screen, self.assets, item.get('name',key), (row.x+45, row.y+7), 14, WHITE, True, row.width-333)
            amount = item.get('amount', 0)
            text(self.screen, self.assets, f"Restore {amount} {item.get('resource','').upper()} · Owned {inventory.get(key, 0)}", (row.x+45, row.y+29), 11, MUTED, max_width=row.width-333)
            if not battle:
                text(self.screen, self.assets, f"¥ {item.get('price', 0):,}", (row.right-267, row.y+17), 13, GOLD)
                self.ui.button((row.right-183, row.y+8, 81, 33), 'Buy 1', lambda ident=key:self.send('shop', item=ident, quantity=1), disabled=self.action_pending, small=True)
            def use(ident=key):
                if battle:
                    self.menu = None
                    self.battle_action('item', ident)
                else:
                    self.send('item', item=ident, party_index=self.selected_party)
            self.ui.button((row.right-91, row.y+8, 80, 33), 'Use', use, primary=bool(inventory.get(key,0)), disabled=not inventory.get(key,0) or self.action_pending, small=True)
        text(self.screen, self.assets, 'Battle items use your current turn.' if battle else 'Buy and use items instantly. DigiLab healing is free.', (rect.x, rect.bottom-13), 12, MUTED)

    def draw_maps(self, rect):
        self.ui.field((rect.x, rect.y, rect.width, 37), 'search', 'Search world destinations…', size=15)
        query = self.ui.values.get('search', '').lower()
        entries = [entry for entry in self.assets.maps.values() if query in entry['name'].lower() or query in entry['id'].lower()]
        rows = max(1, (rect.height-78)//63)
        self.scroll = min(self.scroll, max(0, len(entries)-rows))
        for i,entry in enumerate(entries[self.scroll:self.scroll+rows]):
            row = pygame.Rect(rect.x, rect.y+51+i*63, rect.width, 55)
            panel(self.screen, row, CARD, LINE, 8)
            text(self.screen, self.assets, entry['name'], (row.x+14,row.y+7), 15, WHITE, True, row.width-158)
            text(self.screen, self.assets, f"Wild level {entry.get('level',1)} · Field destination", (row.x+14,row.y+32), 11, MUTED, max_width=row.width-158)
            current = self.state.get('map_id')==entry['id']
            self.ui.button((row.right-120,row.y+10,108,35), 'Current' if current else 'Transfer', lambda ident=entry['id']:self.send('travel',map_id=ident), selected=current, disabled=current or self.action_pending, small=True)
        text(self.screen, self.assets, f'{len(entries)} areas · Scroll to explore', (rect.x,rect.bottom-13), 12, MUTED)

    def draw_skills(self, rect):
        battle = self.state.get('battle')
        if not battle:
            self.menu = None
            return
        mon = self.state['party'][battle.get('actor',0)]
        text(self.screen, self.assets, f"{mon['name']}  •  SP {mon.get('sp',0)}/{mon.get('max_sp',0)}", (rect.x,rect.y+4), 21, CYAN, True)
        for i,skill in enumerate(mon.get('skills',[])[:5]):
            row = pygame.Rect(rect.x,rect.y+56+i*66,rect.width,57)
            panel(self.screen,row,CARD,LINE,8)
            cost = skill.get('sp',0)
            text(self.screen,self.assets,skill.get('name','Skill'),(row.x+14,row.y+8),16,WHITE,True)
            text(self.screen,self.assets,f"{skill.get('attribute','Neutral')} · {skill.get('kind','attack')} · {cost} SP",(row.x+14,row.y+33),12,MUTED)
            def cast(index=i):
                self.menu = None
                self.send('battle',action='skill',target=self.target,party_index=battle.get('actor',0),skill_index=index)
            self.ui.button((row.right-112,row.y+11,100,35),'Use skill',cast,primary=True,disabled=mon.get('sp',0)<cost or self.action_pending,small=True)
        text(self.screen,self.assets,'Attack and Struggle are always available without SP.',(rect.x,rect.bottom-18),14,MUTED)

    def run(self):
        frames = 0
        try:
            while self.running:
                dt = min(.05, self.clock.tick(self.display.settings['fps'])/1000)
                for event in pygame.event.get():
                    # Window shortcuts also work while typing in account/chat fields.
                    global_key = event.type == pygame.KEYDOWN and (event.key in (pygame.K_F10, pygame.K_F11) or
                        (event.key == pygame.K_RETURN and getattr(event, 'mod', 0)&pygame.KMOD_ALT))
                    if global_key:
                        self.key(event)
                        continue
                    consumed = self.ui.event(event)
                    if not consumed or event.type in (pygame.QUIT, pygame.VIDEORESIZE):
                        self.key(event)
                self.update(dt)
                self.world.update(dt)
                self.draw()
                frames += 1
                if self.args.frames and frames >= self.args.frames:
                    break
            if self.args.screenshot:
                path = Path(self.args.screenshot)
                path.parent.mkdir(parents=True, exist_ok=True)
                pygame.image.save(self.display.surface,str(path))
        finally:
            self.display.settings['zoom'] = self.world.zoom
            self.display.save()
            if self.connection: self.connection.close()
            pygame.quit()
