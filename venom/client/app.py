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
from .community import CommunityPanel
from .presentation import Presentation
from .cyber import CyberBackdrop
from .shop import ShopScreen
from .laboratory import LaboratoryScreen, ScanScreen
from .partners import PartnerScreen
from .destinations import WorldScreen
from .combat_menu import CombatMenu
from .entry_screen import EntryScreen
from .hud import GameHUD
from .digifarm import DigiFarmScreen


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
        self.ui.on_activate = lambda: self.audio.cue('confirm', now=self.now)
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
        self.cyber = CyberBackdrop(self)
        self.presentation = Presentation(self)
        self.shop_screen = ShopScreen(self)
        self.community = CommunityPanel(self)
        self.laboratory_screen = LaboratoryScreen(self)
        self.scan_screen = ScanScreen(self)
        self.partner_screen = PartnerScreen(self)
        self.world_screen = WorldScreen(self)
        self.combat_menu = CombatMenu(self)
        self.entry_screen = EntryScreen(self)
        self.hud = GameHUD(self)
        self.farm_screen = DigiFarmScreen(self)
        self.presentation_notice = None
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
            if op == 'digifarm':
                if payload.get('action') == 'feed':
                    self.toast('Visual preview only — start the dedicated server to feed partners.')
                    return
                self.state['in_farm'] = payload.get('action') != 'return'
                self.state['in_lab'] = False
                self.menu = None
                if payload.get('forfeit'):
                    self.state['battle'] = None
                self.reset_scene_position()
            elif op == 'digilab':
                self.state['in_farm'] = False
                self.state['in_lab'] = payload.get('action') != 'return'
                if payload.get('action') == 'return':
                    self.menu = None
                else:
                    self.menu = 'lab'
                self.reset_scene_position()
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
        if op == 'move':
            payload.setdefault('space', 'farm' if self.state and self.state.get('in_farm') else 'field')
        rid = self.connection.send(op, **payload)
        self.requests[rid] = op
        if op == 'move':
            self._motion.track(rid, payload)
        elif op in ('travel', 'digilab', 'digifarm'):
            self._motion.transition_pending = rid
        # Movement does not require a pending state; authoritative updates arrive asynchronously.
        if op in ('login', 'register'):
            self.auth_pending = True
        elif op not in ('move', 'ping', 'community'):
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
                self.community.disconnected()
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
                elif request not in ('move', 'community'):
                    self.action_pending = False
                if not message.get('ok', False):
                    if request == 'community':
                        self.community.failed(rid, str(message.get('error', 'Request could not be completed.')))
                    self._motion.pending.pop(rid, None)
                    self.status = str(message.get('error', 'Request could not be completed.'))
                    self.toast(self.status, RED)
                    if request not in ('move', 'ping'):
                        self.audio.cue('error', now=self.now)
                    continue
                if message.get('community'):
                    self.community.receive(message['community'], rid)
                position = message.get('position')
                if position and self.state:
                    space = 'farm' if self.state.get('in_farm') else 'field'
                    if position.get('space', 'field') != space:
                        # A reply from the departed scene cannot relocate us or
                        # overwrite the saved coordinates of the other scene.
                        self._motion.pending.pop(rid, None)
                    else:
                        if space == 'farm':
                            self.state.setdefault('farm_position', {}).update(
                                {k: position[k] for k in ('x', 'y', 'direction') if k in position})
                        else:
                            self.state.update({k:position[k] for k in ('map_id','x','y') if k in position})
                        entry, mask = self.movement_context()
                        desired = (position.get('x', self.position.x), position.get('y', self.position.y))
                        corrected = self._motion.reconcile(rid, desired, entry, mask,
                            reset=bool(self.state.get('battle') or self.state.get('in_lab')))
                        self.position.update(corrected)
                state = message.get('state')
                if state:
                    previous_state = self.state
                    old_battle = self.state.get('battle') if self.state else None
                    old_map = self.state.get('map_id') if self.state else None
                    self.state = state
                    desired = pygame.Vector2(self.active_position(state))
                    scene_changed = bool((previous_state or {}).get('in_farm')) != bool(state.get('in_farm'))
                    teleport = request in ('register', 'login', 'travel', 'digilab') or scene_changed or old_map != state.get('map_id')
                    entry, mask = self.movement_context(state)
                    self.position.update(self._motion.reconcile(rid, desired, entry, mask,
                        reset=teleport or bool(state.get('battle') or state.get('in_lab'))))
                    if teleport:
                        self.reset_scene_position()
                    if request in ('login', 'register'):
                        self.ui.focus = None
                        self.ui.values['password'] = ''
                        self.menu = None
                        self.log('Connected. Home / F2 for DigiFarm • WASD to move • E for encounters • F1 for DigiLab.', CYAN)
                    if request != 'ping':
                        cue = {'materialize': 'scan_complete', 'evolve': 'evolution_complete',
                               'shop': 'purchase'}.get(request)
                        self.consume_events(state.get('events', []), cue=cue)
                        self.confirmed_partner_change(request, previous_state, state)
                    if old_battle and not state.get('battle'):
                        self.battle_old = old_battle
                        self.battle_until = self.now+max(1.2, len(self.animations)*.5)
                    if request == 'digilab':
                        self.menu = 'lab' if state.get('in_lab') else None
                    if request == 'digifarm':
                        if state.get('in_farm'):
                            self.menu = None
                            self.battle_old = None
                            self.animations.clear()
                            self.farm_screen.confirmed(previous_state, state)
                        else:
                            self.menu = None
                    if request == 'travel':
                        self.menu = None
                    if state.get('battle'):
                        self.menu = None
                        enemies = state['battle'].get('enemies', [])
                        if self.target >= len(enemies) or enemies[self.target].get('hp', 0) <= 0:
                            self.target = next((i for i, e in enumerate(enemies) if e.get('hp', 0) > 0), 0)

    def confirmed_partner_change(self, request, previous, state):
        if request not in ('materialize', 'evolve') or not previous:
            return
        old = {mon.get('uid'): mon for key in ('party', 'storage') for mon in previous.get(key, [])}
        for key in ('party', 'storage'):
            for mon in state.get(key, []):
                before = old.get(mon.get('uid'))
                if (request == 'materialize' and before is None or
                        request == 'evolve' and before and before.get('species_id') != mon.get('species_id')):
                    self.presentation_notice = {
                        'theme': 'evolution' if request == 'evolve' else 'scan',
                        'label': 'EVOLUTION COMPLETE' if request == 'evolve' else 'MATERIALIZATION COMPLETE',
                        'name': mon.get('name', 'Partner'), 'species_id': mon['species_id'], 'until': self.now+3.5}
                    return

    def consume_events(self, events, cue=None):
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
        if cue:
            self.audio.cue(cue, now=self.now)
        elif any(e.get('kind') == 'damage' for e in events):
            self.audio.effect('hit')
        elif events:
            kinds = [e.get('kind') for e in events]
            self.audio.effect('heal' if 'heal' in kinds else 'scan' if 'scan' in kinds else 'confirm')

    def set_menu(self, menu):
        if self.state and self.state.get('battle'):
            self.toast('Finish the current battle first.')
            return
        self.farm_screen.manager_open = False
        self.partner_screen.pending_exchange = None
        self.menu = None if self.menu == menu else menu
        self.scroll = 0
        self.detail_species = None
        self.ui.values['search'] = ''
        self.ui.focus = None
        self.ui.actions, self.ui.fields = [], []
        pygame.key.stop_text_input()
        self.audio.cue('open' if self.menu else 'back', now=self.now)

    def close_menu(self):
        self.partner_screen.pending_exchange = None
        self.menu = None
        self.ui.focus = None
        self.ui.actions, self.ui.fields = [], []
        pygame.key.stop_text_input()
        self.audio.cue('back', now=self.now)

    def open_battle_menu(self, menu):
        if not self.state or not self.state.get('battle') or self.action_pending or self.animations:
            return
        self.menu, self.scroll = menu, 0
        self.ui.focus = None
        self.ui.actions, self.ui.fields = [], []
        pygame.key.stop_text_input()
        self.audio.cue('open', now=self.now)

    def enter_lab(self):
        self.partner_screen.pending_exchange = None
        if self.state and self.state.get('battle'):
            self.toast('Finish or flee the battle before returning to the DigiLab.')
        else:
            self.send('digilab', action='enter')

    def enter_farm(self):
        if not self.state or self.action_pending:
            return
        if self.settings_open:
            self.toggle_settings()
        self.farm_screen.manager_open = False
        self.partner_screen.pending_exchange = None
        self.ui.focus = None
        self.ui.actions, self.ui.fields = [], []
        pygame.key.stop_text_input()
        if self.state.get('battle'):
            self.farm_screen.home_confirmation = True
        elif self.state.get('in_farm'):
            self.close_menu()
        else:
            self.send('digifarm', action='enter')

    def logout(self):
        self.state = None
        self.players.clear()
        self.menu = None
        self.presentation_notice = None
        self.community.reset()
        self.farm_screen.reset()
        self.partner_screen.pending_exchange = None
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
        self.community.update(dt)
        self.toasts = [t for t in self.toasts if t[2] > self.now]
        self.animations = [a for a in self.animations if a['start']+a['duration'] > self.now]
        if not self.state:
            scene = 'settings' if self.settings_open else 'authpicker' if self.auth_picker else 'auth'
            self.audio.music(screen=scene, now=self.now)
            return
        screen_scene = self.community.tab if self.menu == 'community' else self.menu
        if self.menu == 'party':
            screen_scene = {'roster': 'party', 'evolution': 'evolution', 'storage': 'storage'}.get(self.partner_screen.mode, 'party')
        if self.settings_open:
            screen_scene = 'settings' 
        self.audio.music(bool(self.state.get('battle') or self.community.visible and self.community.replay),
                         self.state.get('map_id'), self.state.get('in_lab', False),
                         screen=screen_scene, now=self.now, in_farm=self.state.get('in_farm', False))
        map_id = self.state.get('map_id')
        scene = ('farm' if self.state.get('in_farm') else 'field', map_id)
        entry, self.walk_mask = self.movement_context()
        if self.last_map != scene:
            self.last_map = scene
            self.reset_scene_position()
        keys = pygame.key.get_pressed()
        allowed = (not self.menu and not self.ui.focus and not getattr(self, 'settings_open', False)
                   and not self.state.get('battle') and not self.state.get('in_lab')
                   and not self.farm_screen.manager_open and not self.farm_screen.home_confirmation
                   and self.partner_screen.pending_exchange is None
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
            following = difference * (1-34/distance) * (1-math.exp(-12*dt))
            if self.state.get('in_farm'):
                from venom.common.farm import move_farm_position, farm_walkable
                length = following.length()
                if not farm_walkable(self.follower.x, self.follower.y):
                    self.follower.update(self.position)
                elif length:
                    self.follower.update(move_farm_position(self.follower, following.x/length, following.y/length,
                                                           .1, speed=min(1000., length*10)))
            else:
                self.follower += following
        if self.args.demo:
            if self.state.get('in_farm'):
                self.state['farm_position'] = {'x': self.position.x, 'y': self.position.y, 'direction': self.direction}
            elif not self.state.get('in_lab'):
                self.state.update(x=self.position.x, y=self.position.y)
        self.farm_screen.update(dt)
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
        if self.state and self.state.get('in_farm'):
            self.farm_screen.set_zoom(value)
            return
        self.world.set_zoom(value)
        self.display.settings['zoom'] = self.world.zoom
        self.display.save()

    def change_zoom(self, amount):
        current = self.farm_screen.zoom if self.state and self.state.get('in_farm') else self.world.zoom
        self.set_zoom(current + amount)

    def active_position(self, state=None):
        state = self.state if state is None else state
        if state and state.get('in_farm'):
            from venom.common.farm import FARM_SPAWN
            position = state.get('farm_position', {})
            return position.get('x', FARM_SPAWN[0]), position.get('y', FARM_SPAWN[1])
        return (state or {}).get('x', 0), (state or {}).get('y', 0)

    def movement_context(self, state=None):
        state = self.state if state is None else state
        if state and state.get('in_farm'):
            from venom.common.farm import FARM_ENTRY
            return FARM_ENTRY, None
        entry = self.assets.maps.get((state or {}).get('map_id'), {})
        return entry, self.assets.image(entry.get('walkable'))

    def reset_scene_position(self):
        from .motion import MovementPredictor
        if not hasattr(self, '_motion'):
            self._motion = MovementPredictor()
        self._motion.reset()
        self.position.update(self.active_position())
        self.moving = self.sent_moving = False
        self.follower.update(self.position+pygame.Vector2(-34, 26))
        if self.state and self.state.get('in_farm'):
            from venom.common.farm import farm_walkable
            if not farm_walkable(self.follower.x, self.follower.y):
                self.follower.update(self.position)
            self.direction = self.state.get('farm_position', {}).get('direction', 'down')
            self.farm_screen.camera.ready = False
        self.last_map = ('farm' if self.state and self.state.get('in_farm') else 'field',
                         (self.state or {}).get('map_id'))

    def farm_visible(self):
        return bool(self.state and self.state.get('in_farm') and not self.settings_open and not self.menu
                    and not self.state.get('battle') and not self.farm_screen.manager_open
                    and not self.farm_screen.home_confirmation and self.partner_screen.pending_exchange is None)

    def zoom_visible(self):
        return self.field_visible() or self.farm_visible()

    def field_visible(self):
        return bool(self.state and not self.settings_open and not self.menu and
                    not self.state.get('battle') and not self.state.get('in_lab') and not self.state.get('in_farm'))

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
            view = self.farm_screen.viewport if self.farm_visible() else getattr(self, 'viewport', pygame.Rect(0,0,0,0))
            if self.zoom_visible() and view.collidepoint(point):
                self.change_zoom(event.y*.5)
            else:
                self.scroll = max(0, self.scroll-event.y*(1 if self.menu in ('scan','dex','party','maps') else 2))
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11 or (event.key == pygame.K_RETURN and getattr(event, 'mod', 0)&pygame.KMOD_ALT):
                self.apply_display(fullscreen=not self.display.fullscreen)
                return
            if self.farm_screen.home_confirmation:
                if event.key == pygame.K_ESCAPE:
                    self.farm_screen.home_confirmation = False
                return
            if event.key == pygame.K_F2 and self.state:
                self.enter_farm()
                return
            if self.partner_screen.pending_exchange is not None:
                if event.key == pygame.K_ESCAPE:
                    self.partner_screen.pending_exchange = None
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
                elif self.ui.focus == 'farm_search':
                    self.ui.focus = None
                    pygame.key.stop_text_input()
                elif self.field_visible() or (self.state and self.state.get('battle') and not self.menu):
                    self.ui.focus = 'chat'
                return
            if event.key == pygame.K_ESCAPE:
                if self.farm_screen.home_confirmation:
                    self.farm_screen.home_confirmation = False
                elif self.farm_screen.manager_open:
                    self.farm_screen.close_manager()
                elif self.auth_picker:
                    self.auth_picker = None
                    self.ui.focus = None
                    self.ui.actions, self.ui.fields = [], []
                    self.audio.cue('back', now=self.now)
                elif self.menu:
                    self.close_menu()
                else:
                    self.toggle_settings()
                return
            if self.ui.focus or not self.state:
                return
            if event.key == pygame.K_F2: self.enter_farm()
            elif event.key == pygame.K_F1: self.enter_lab()
            elif event.key == pygame.K_b: self.set_menu('shop')
            elif event.key == pygame.K_m: self.set_menu('maps')
            elif event.key in (pygame.K_TAB, pygame.K_j): self.set_menu('dex')
            elif event.key == pygame.K_p: self.set_menu('party')
            elif event.key == pygame.K_r: self.community.open('ranked')
            elif event.key == pygame.K_v: self.community.open('rivals')
            elif event.key == pygame.K_o: self.community.open('activity')
            elif event.key == pygame.K_e and self.field_visible(): self.send('encounter')
            elif event.key == pygame.K_SPACE and self.state.get('battle'): self.battle_action('attack')
            elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS) and self.zoom_visible(): self.change_zoom(.5)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS) and self.zoom_visible(): self.change_zoom(-.5)
            elif event.key in (pygame.K_0, pygame.K_KP_0) and self.zoom_visible(): self.set_zoom(1)

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
        self.cyber.draw()

    def draw(self):
        self.ui.begin()
        self.draw_background()
        if not self.state:
            self.draw_auth()
        else:
            self.draw_game()
        if self.settings_open:
            self.settings_panel.draw()
            if self.state:
                self.ui.button((22, 18, 156, 37), 'Home · DigiFarm', self.enter_farm, small=True, accent=LIME, disabled=self.action_pending)
        elif self.farm_screen.home_confirmation:
            self.farm_screen.draw_home_confirmation()
        else:
            self.hud.result()
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
        self.entry_screen.draw()

    def open_picker(self, kind):
        self.auth_picker = kind
        self.ui.focus = None
        self.scroll = 0
        self.ui.values['search'] = ''

    def draw_picker(self):
        self.entry_screen.draw_picker()

    def draw_game(self):
        w, h = self.screen.get_size()
        self.hud.header()
        self.viewport = pygame.Rect(20, 94, w-352, h-262)
        full = pygame.Rect(20, 98, w-40, h-118)
        if self.menu == 'shop':
            self.shop_screen.draw(full)
            return
        if self.menu == 'community':
            self.community.draw(full)
            return
        if self.menu:
            self.draw_menu()
            return
        if self.state.get('battle') or self.battle_old and self.now < self.battle_until:
            self.draw_battle()
        elif self.state.get('in_farm'):
            self.farm_screen.draw(full)
            return
        elif self.state.get('in_lab'):
            self.laboratory_screen.draw(full)
            return
        else:
            self.draw_world()
        self.draw_party_sidebar(pygame.Rect(w-312, 94, 292, h-115))
        self.draw_log(pygame.Rect(20, h-152, w-352, 132))
        if self.args.demo:
            text(self.screen, self.assets, 'OFFLINE VISUAL PREVIEW — NOT CONNECTED', (self.viewport.centerx, h-163), 11, GOLD, center=True)
        elif not self.connection or not self.connection.connected:
            text(self.screen, self.assets, 'DISCONNECTED • Exit to reconnect', (self.viewport.centerx, h-163), 12, RED, center=True)

    def draw_world(self):
        self.world.draw(self.viewport)

    def draw_party_sidebar(self, rect):
        self.hud.party(rect)

    def draw_log(self, rect):
        self.hud.feed(rect)

    def draw_lab_world(self):
        w, h = self.screen.get_size()
        self.laboratory_screen.draw(pygame.Rect(20, 98, w-40, h-118))

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
        self.hud.battle_stage(view)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(view)
        text(self.screen, self.assets, 'WILD ENCOUNTER', (view.x+20, view.y+14), 23, WHITE, True)
        text(self.screen, self.assets, 'TACTICAL LINK  /  SELECT YOUR TARGET', (view.x+21, view.y+45), 9, CYAN, True)
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
                           (lambda: self.open_battle_menu('battle_items')) if action=='items' else (lambda: self.open_battle_menu('skills')) if action=='skill' else lambda a=action:self.battle_action(a),
                           primary=action=='attack', disabled=disabled, small=True, accent=self.presentation.colors('battle')['accent'])

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
        w, h = self.screen.get_size()
        rect = pygame.Rect(20, 98, w-40, h-118)
        if self.menu in ('dex', 'scan'):
            self.scan_screen.draw(rect)
        elif self.menu == 'party':
            self.partner_screen.draw(rect)
        elif self.menu == 'maps':
            self.world_screen.draw(rect)
        elif self.menu == 'lab':
            self.laboratory_screen.draw(rect)
        elif self.menu in ('skills', 'battle_items'):
            self.combat_menu.draw(rect, self.menu)

    def draw_lab_menu(self, rect):
        self.laboratory_screen.draw(rect)

    def draw_dex(self, rect):
        self.scan_screen.draw(rect)

    def draw_roster(self, rect):
        self.partner_screen.draw(rect)

    def shop_data(self):
        if self.state.get('shop'):
            return self.state['shop']
        from venom.common.game import SHOP
        return SHOP

    def draw_shop(self, rect, battle=False):
        if battle:
            self.combat_menu.draw(rect, 'battle_items')
        else:
            self.shop_screen.draw(rect)

    def draw_maps(self, rect):
        self.world_screen.draw(rect)

    def draw_skills(self, rect):
        self.combat_menu.draw(rect, 'skills')

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
