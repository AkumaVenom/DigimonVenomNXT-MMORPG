"""Native-resolution, nearest-neighbour world rendering and a bounded map camera.

The camera operates in the supplied x2 map's coordinates.  UI scale is deliberately
separate: changing Windows DPI must not change movement or collision coordinates.
Only the visible map crop and a small scrolling margin are enlarged, including
at the maximum 8x view zoom. The final display always stays at native resolution.
"""
from __future__ import annotations

from collections import OrderedDict
import math

import pygame

from .widgets import BG, CYAN, GOLD, LINE, LIME, MUTED, WHITE, panel, text, wrap


def player_title(value):
    """Bound a server-owned display label without changing the account identity."""
    if not isinstance(value, str):
        return ''
    return ' '.join(''.join(c if c.isprintable() else ' ' for c in value).split())[:32]


def _zoom(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(1.0, min(8.0, value)) if math.isfinite(value) else 1.0


class MapCamera:
    """Fit-relative camera with screen/world transforms and a smooth follow target."""

    def __init__(self, zoom=1.0):
        self.zoom = _zoom(zoom)
        self.map_size = (1, 1)
        self.viewport = pygame.Rect(0, 0, 1, 1)
        self.center = pygame.Vector2(.5, .5)
        self.ready = False

    @property
    def scale(self):
        return min(self.viewport.width / self.map_size[0],
                   self.viewport.height / self.map_size[1]) * self.zoom

    @property
    def origin(self):
        # Snap the camera translation to physical pixels, never fractional blits.
        return pygame.Vector2(round(self.viewport.centerx - self.center.x * self.scale),
                              round(self.viewport.centery - self.center.y * self.scale))

    def configure(self, map_size, viewport, target, *, snap=False):
        map_size = tuple(max(1, int(n)) for n in map_size)
        changed = map_size != self.map_size
        self.map_size = map_size
        self.viewport = pygame.Rect(viewport)
        self.viewport.width = max(1, self.viewport.width)
        self.viewport.height = max(1, self.viewport.height)
        if snap or changed or not self.ready:
            self.center.update(target)
        self.ready = True
        self._clamp()

    def _clamp(self):
        for axis, span in enumerate(self.map_size):
            half = self.viewport.size[axis] / (2 * self.scale)
            self.center[axis] = span / 2 if 2 * half >= span else min(span - half, max(half, self.center[axis]))

    def update(self, dt, target):
        if not self.ready:
            return
        target = pygame.Vector2(target)
        for axis, span in enumerate(self.map_size):
            half = self.viewport.size[axis] / (2 * self.scale)
            target[axis] = span / 2 if 2 * half >= span else min(span - half, max(half, target[axis]))
        self.center += (target - self.center) * (1 - math.exp(-12 * max(0, dt)))
        self._clamp()

    def world_to_screen(self, position):
        return self.origin + pygame.Vector2(position) * self.scale

    def screen_to_world(self, position):
        return (pygame.Vector2(position) - self.origin) / self.scale

    def source_crop(self):
        """Return the intersecting source pixels, with at most one-pixel overscan."""
        origin, scale = self.origin, self.scale
        left = math.floor((self.viewport.left - origin.x) / scale)
        top = math.floor((self.viewport.top - origin.y) / scale)
        right = math.ceil((self.viewport.right - origin.x) / scale)
        bottom = math.ceil((self.viewport.bottom - origin.y) / scale)
        return pygame.Rect(left, top, right - left, bottom - top).clip(pygame.Rect((0, 0), self.map_size))

    def crop_destination(self, crop):
        origin, scale = self.origin, self.scale
        left = round(origin.x + crop.left * scale)
        top = round(origin.y + crop.top * scale)
        right = round(origin.x + crop.right * scale)
        bottom = round(origin.y + crop.bottom * scale)
        return pygame.Rect(left, top, max(1, right - left), max(1, bottom - top))


class WorldRenderer:
    """World view plus readable, DPI-scaled map controls."""

    SPRITE_CACHE_BYTES = 24 * 1024 * 1024
    SPRITE_CACHE_ITEMS = 4096
    LAYER_SCROLL_MARGIN = 128  # Physical pixels, independent of map zoom/DPI.

    def __init__(self, app):
        self.app = app
        settings = getattr(getattr(app, 'display', None), 'settings', {})
        self.camera = MapCamera(settings.get('zoom', 1.0))
        self.map_id = None
        self._layers = {}
        self._sprites = OrderedDict()
        self._sprite_bytes = 0
        self._mini_key = None
        self._mini_surface = None
        self._facings = {}
        self._label_sizes = OrderedDict()
        self._story_label_rects = []

    @property
    def zoom(self):
        return self.camera.zoom

    @property
    def focus(self):
        # Authoritative positions are foot anchors. Aim at the character's body
        # so close-up views do not put the head above the top of the viewport.
        return pygame.Vector2(self.app.position) - pygame.Vector2(0, 20)

    def set_zoom(self, value):
        self.camera.zoom = _zoom(value)
        if self.camera.ready:
            # A zoom command focuses the player immediately, even after a wide
            # fit view put the map centre far away from their current location.
            self.camera.center.update(self.focus)
            self.camera._clamp()
        settings = getattr(getattr(self.app, 'display', None), 'settings', None)
        if settings is not None:
            settings['zoom'] = self.zoom
        return self.zoom

    def change_zoom(self, delta):
        return self.set_zoom(self.zoom + delta)

    def reset_zoom(self):
        return self.set_zoom(1.0)

    def update(self, dt):
        self.camera.update(dt, self.focus)

    @property
    def _surface(self):
        return getattr(self.app.screen, 'surface', self.app.screen)

    def _physical_rect(self, rect):
        transform = getattr(self.app.screen, 'to_physical_rect', None)
        return transform(rect) if transform else pygame.Rect(rect)

    def _logical_point(self, point):
        transform = getattr(self.app.screen, 'to_logical_point', None)
        return transform(point) if transform else point

    def _draw_layer(self, surface, slot):
        crop = self.camera.source_crop().clip(surface.get_rect())
        if not crop.width or not crop.height:
            return
        scale = self.camera.scale
        # Keep a modest margin around the view. Walking normally translates this
        # cached patch; it must not resample a multi-megapixel map every frame.
        # Retaining the source also prevents id reuse after a map-cache eviction.
        key = (surface, scale, self.camera.viewport.size)
        cached = self._layers.get(slot)
        if cached is None or cached[0] != key or not cached[1].contains(crop):
            margin = math.ceil(self.LAYER_SCROLL_MARGIN / scale)
            patch = crop.inflate(2 * margin, 2 * margin).clip(surface.get_rect())
            destination = self.camera.crop_destination(patch)
            # Bounded by the physical viewport plus the scrolling margin, never
            # by the size of a full map enlarged to the maximum zoom.
            source = surface.subsurface(patch)
            scaled = pygame.transform.scale(source, destination.size)
            cached = self._layers[slot] = (key, patch, scaled)
        destination = self.camera.crop_destination(cached[1])
        self._surface.blit(cached[2], destination)

    def _scale_sprite(self, source, scale=None):
        scale = self.camera.scale if scale is None else scale
        size = (max(1, round(source.get_width() * scale)),
                max(1, round(source.get_height() * scale)))
        if size == source.get_size():
            return source
        key = (id(source), size)
        if key in self._sprites:
            self._sprites.move_to_end(key)
            return self._sprites[key][1]
        scaled = pygame.transform.scale(source, size)
        size_bytes = (scaled.get_pitch() * scaled.get_height()
                      + source.get_pitch() * source.get_height())
        # Keep a source reference: pygame can otherwise reuse its id after eviction.
        if size_bytes <= self.SPRITE_CACHE_BYTES:
            self._sprites[key] = (source, scaled, size_bytes)
            self._sprite_bytes += size_bytes
            while self._sprite_bytes > self.SPRITE_CACHE_BYTES or len(self._sprites) > self.SPRITE_CACHE_ITEMS:
                _, old = self._sprites.popitem(last=False)
                self._sprite_bytes -= old[2]
        return scaled

    def _draw_actor(self, kind, world_pos, ident, moving, direction, label, bot_id=None, *, title='', frame=None, story_npc=None):
        app = self.app
        if frame is None:
            scale, origin = self.camera.scale, self.camera.origin
            visible = self.camera.viewport.inflate(round(180 * scale), round(180 * scale))
        else:
            scale, origin, visible = frame
        position = world_pos if isinstance(world_pos, pygame.Vector2) else pygame.Vector2(world_pos)
        pos = origin + position * scale
        if not visible.collidepoint(pos):
            return
        shadow = pygame.Rect(round(pos.x - 15 * scale), round(pos.y - 5 * scale),
                             max(2, round(30 * scale)), max(1, round(12 * scale)))
        pygame.draw.ellipse(self._surface, (22, 33, 40), shadow)
        # Only explicitly directional pose packs opt in; existing imported
        # sheet animations retain their established presentation.
        facing_left = (kind != 'tamer' and str(direction).endswith('left')
                       and bool(app.assets.species.get(ident, {}).get('mirrored_frames')))
        source = (app.assets.tamer(ident, direction, moving, app.now, (64, 80)) if kind == 'tamer'
                  else app.assets.sprite(ident, (58, 64), 'walk' if moving else 'idle', app.now,
                                         flip=facing_left))
        top = pos.y - 64 * scale
        destination = pygame.Rect(round(pos.x-16*scale), round(top), max(8, round(32*scale)), max(8, round(64*scale)))
        if source:
            sprite = self._scale_sprite(source, scale)
            appearance = app.assets.tamers.get(ident, {}) if kind == 'tamer' else {}
            anchor = appearance.get('anchors', {}).get(direction)
            if anchor:
                native = appearance.get('native_size', [16, 32])
                # X and Y are rounded independently after final native-pixel scaling.
                anchor_x = anchor[0] * sprite.get_width() / max(1, native[0])
                anchor_y = anchor[1] * sprite.get_height() / max(1, native[1])
                destination = sprite.get_rect(topleft=(round(pos.x - anchor_x), round(pos.y - anchor_y)))
            else:
                destination = sprite.get_rect(midbottom=(round(pos.x), round(pos.y)))
            self._surface.blit(sprite, destination)
            top = destination.top
        if story_npc is not None:
            # Authored story tamers never route to the shared rival profile.
            self._story_target(destination, story_npc)
            title = self._story_role(story_npc)
        if bot_id is not None and hasattr(app, 'community'):
            # Hit areas use the same interpolated foot anchor and camera transform
            # as the rendered sprite, including at fractional DPI and map zoom.
            target = app.screen.to_logical_rect(destination).inflate(10, 8)
            target = target.clip(app.screen.to_logical_rect(self.camera.viewport))
            if target.width and target.height:
                app.ui.actions.append((target, lambda ident=bot_id: app.community.open_profile(ident)))
            hover = target.collidepoint(app.ui.mouse)
            if self.zoom < 2 and not hover:
                # At full-map zoom dozens of always-on nameplates hide the map.
                # A small cyan AI marker remains visible; hover reveals the name.
                logical = self._logical_point((pos.x, top-3))
                text(app.screen, app.assets, 'AI', logical, 9, CYAN, True, center=True)
                label = ''
        if label:
            # Names are UI text: crisp and readable independently of map magnification.
            label_position = self._logical_point((pos.x, top))
            font = app.assets.font(11, True)
            key = (font, label)
            dimensions = self._label_sizes.get(key)
            if dimensions is None:
                dimensions = self._label_sizes[key] = font.size(label)
                if len(self._label_sizes) > 1024:
                    self._label_sizes.popitem(last=False)
            else:
                self._label_sizes.move_to_end(key)
            width, height = dimensions
            title = self._story_role(story_npc) if story_npc is not None else player_title(title) if kind == 'tamer' and bot_id is None else ''
            title_height = app.assets.font(10, True).get_height() + 3 if title else 0
            title_width = app.assets.font(10, True).size(title)[0] if title else 0
            label_rect = pygame.Rect(0, 0, max(width, title_width) + 12, height + 6 + title_height)
            label_rect.midbottom = (round(label_position[0]), round(label_position[1] - 6))
            # Both lines stay inside the map, including at its edges and at any DPI.
            corner = self._logical_point(self.camera.viewport.topleft)
            opposite = self._logical_point(self.camera.viewport.bottomright)
            label_view = pygame.Rect(corner, (opposite[0]-corner[0], opposite[1]-corner[1])).inflate(-4, -4)
            label_rect.width = min(label_rect.width, label_view.width)
            label_rect.clamp_ip(label_view)
            if self._story_view() is not None:
                label_rect = self._place_story_label(label_rect)
                self._story_leader(label_rect, (pos.x, top-2), self._story_color(story_npc) if story_npc else MUTED)
            panel(app.screen, label_rect, BG, self._story_color(story_npc) if story_npc else None, 4)
            if title:
                text(app.screen, app.assets, title,
                     (label_rect.centerx, label_rect.y+3+title_height//2), 10, GOLD, True,
                     max_width=label_rect.width-12, center=True)
            # The title is a separate line: it never changes or shortens a username.
            name_center = (label_rect.centerx, label_rect.y+3+title_height+height//2)
            text(app.screen, app.assets, label, name_center, 11,
                 CYAN if bot_id else WHITE, True, center=True)
            if story_npc is not None:
                self._story_target(self._physical_rect(label_rect), story_npc)
            if bot_id is not None and hasattr(app, 'community'):
                app.ui.actions.append((label_rect.clip(app.screen.to_logical_rect(self.camera.viewport)),
                                       lambda ident=bot_id: app.community.open_profile(ident)))

    def _story_view(self):
        state = self.app.state
        if (not state.get('in_story') or state.get('in_lab') or state.get('in_farm')
                or state.get('admin_jail') or state.get('in_jail')):
            return None
        return (state.get('story') or {}).get('view') or {}

    def _story_entries(self, key):
        view = self._story_view()
        if view is None:
            return []
        return [row for row in view.get(key, []) if isinstance(row, dict)
                and row.get('id') and row.get('map_id', self.app.state.get('map_id')) == self.app.state.get('map_id')]

    def _story_npcs(self):
        return self._story_entries('npcs')

    def _story_exits(self):
        return self._story_entries('exits')

    @staticmethod
    def _story_color(npc):
        status, role = npc.get('status', ''), npc.get('role', '')
        return (MUTED if status in ('locked', 'unavailable') else LIME if status in ('complete', 'defeated', 'cleared')
                else GOLD if role in ('warden', 'champion', 'challenger', 'final') else CYAN)

    @staticmethod
    def _story_role(npc):
        status, role = npc.get('status', ''), npc.get('role', 'tamer')
        label = {'trainer': 'STORY TAMER', 'tamer': 'STORY TAMER', 'warden': 'DIGIBADGE WARDEN',
                 'champion': 'STORY CHAMPION', 'healer': 'PARTNER RECOVERY', 'guide': 'STORY GUIDE',
                 'mentor': 'STORY MENTOR', 'shop': 'SUPPLIES', 'quest': 'STORY QUEST',
                 'final': 'FINAL CONVERGENCE', 'lab': 'DIGILAB', 'farm': 'DIGIFARM'}.get(role, role.replace('_', ' ').upper())
        if npc.get('display_species') and role == 'warden':
            label = 'PARADOX GUARDIAN'
        if npc.get('level') and role in ('trainer','warden','final'):
            label += f" · Lv.{npc['level']}"
        marker = 'CLEARED' if status in ('complete', 'defeated', 'cleared') else 'LOCKED' if status in ('locked', 'unavailable') else 'REPORT' if status=='turn_in' else '!'
        return f'{marker}  ·  {label}'

    def nearest_story_interaction(self):
        """One proximity rule for the E shortcut and the native map prompt."""
        view = self._story_view()
        if view is None:
            return None
        choices = [(pygame.Vector2(row.get('x', 0), row.get('y', 0)).distance_to(self.app.position), kind, row)
                   for kind, rows in (('npc', self._story_npcs()), ('exit', self._story_exits())) for row in rows]
        choices.sort(key=lambda item: item[0])
        return choices[0][1:] if choices and choices[0][0] <= view.get('talk_radius', 128) else None

    def _nearby_story_npc(self):
        nearby = self.nearest_story_interaction()
        return nearby[1] if nearby and nearby[0] == 'npc' else None

    def _story_target(self, destination, row, *, kind='npc'):
        app = self.app
        if not hasattr(app, 'story_screen'):
            return
        logical_rect = getattr(app.screen, 'to_logical_rect', pygame.Rect)
        target = logical_rect(destination).inflate(10, 8).clip(logical_rect(self.camera.viewport))
        if target.width and target.height:
            callback = app.story_screen.exit if kind == 'exit' else app.story_screen.talk
            app.ui.actions.append((target, lambda ident=row['id'], invoke=callback: invoke(ident)))

    def _story_exit_requirement(self, gate):
        if gate.get('unlocked'):
            return 'OPEN PATH  ·  E NEARBY'
        badge_id = gate.get('requires_badge')
        badges = (self._story_view() or {}).get('badges', [])
        badge = next((row.get('name', 'DigiBadge') for row in badges if row.get('id') == badge_id), 'Next DigiBadge')
        return f'LOCKED  ·  {badge}'

    def _reset_story_labels(self, view):
        self._story_label_rects = []
        if self._story_view() is not None:
            # Keep world names away from opaque HUD panels as well as each other.
            self._story_label_rects = [
                pygame.Rect(view.x+14, view.y+14, min(430, view.width-186), 116),
                pygame.Rect(view.right-153, view.y+15, 136, 88),
                pygame.Rect(view.x+14, view.bottom-57, 266, 43),
                pygame.Rect(view.right-203, view.bottom-51, 188, 36)]

    def _place_story_label(self, preferred):
        logical = getattr(self.app.screen, 'to_logical_rect', pygame.Rect)
        bounds = logical(self.camera.viewport).inflate(-8, -8)
        preferred = pygame.Rect(preferred)
        preferred.clamp_ip(bounds)
        candidates = []
        for row in (0, -1, 1, -2, 2, -3, 3, -4, 4):
            for column in (0, -1, 1, -2, 2):
                dx, dy = column*(preferred.width+10), row*(preferred.height+9)
                rect = preferred.move(dx, dy)
                if bounds.contains(rect):
                    candidates.append((dx*dx+dy*dy, rect))
        candidates.sort(key=lambda item: item[0])
        chosen = preferred
        for _, rect in candidates:
            if not any(rect.colliderect(other.inflate(8, 6)) for other in self._story_label_rects):
                chosen = rect
                break
        self._story_label_rects.append(chosen)
        return chosen

    def _story_leader(self, label, anchor, color):
        physical = self._physical_rect(label)
        x = min(physical.right-5, max(physical.left+5, round(anchor[0])))
        y = physical.bottom if anchor[1] >= physical.centery else physical.top
        if pygame.Vector2(x, y).distance_to(anchor) > 16:
            pygame.draw.line(self._surface, tuple(round(value*.6) for value in color),
                             (x, y), (round(anchor[0]), round(anchor[1])),
                             max(1, round(getattr(self.app.screen, 'scale', 1))))

    def _draw_story_exits(self):
        app, scale = self.app, self.camera.scale
        for gate in self._story_exits():
            point = self.camera.world_to_screen((gate.get('x', 0), gate.get('y', 0)))
            if not self.camera.viewport.inflate(round(140*scale), round(140*scale)).collidepoint(point):
                continue
            color = CYAN if gate.get('unlocked') else MUTED
            radius = max(8, round(24*scale))
            ring = pygame.Rect(0, 0, radius*2, max(6, round(radius*.7)))
            ring.center = (round(point.x), round(point.y))
            pygame.draw.ellipse(self._surface, BG, ring)
            pygame.draw.ellipse(self._surface, color, ring, max(1, round(scale)))
            for step in (-1, 1):
                y = point.y+step*5*scale
                pygame.draw.lines(self._surface, color, False,
                                  [(round(point.x-8*scale), round(y+3*scale)), (round(point.x), round(y-2*scale)),
                                   (round(point.x+8*scale), round(y+3*scale))], max(1, round(2*scale)))
            logical = self._logical_point((point.x, point.y-radius-8))
            viewport = getattr(app.screen, 'to_logical_rect', pygame.Rect)(self.camera.viewport).inflate(-8, -8)
            label = pygame.Rect(0, 0, min(202, viewport.width), 40)
            label.midbottom = (round(logical[0]), round(logical[1]))
            label.clamp_ip(viewport)
            label = self._place_story_label(label)
            self._story_leader(label, point, color)
            panel(app.screen, label, BG, color, 5)
            text(app.screen, app.assets, gate.get('name', 'Story path'), (label.centerx, label.y+12),
                 11, WHITE, True, label.width-12, center=True)
            text(app.screen, app.assets, self._story_exit_requirement(gate), (label.centerx, label.y+28),
                 9, color, True, label.width-12, center=True)
            self._story_target(ring.inflate(10, 10), gate, kind='exit')
            self._story_target(self._physical_rect(label), gate, kind='exit')

    def _actors(self):
        app, actors = self.app, []
        self._facings = {name: direction for name, direction in self._facings.items() if name in app.players}
        party = app.state.get('party', [])
        if party:
            actors.append((app.follower.y, 'digimon', app.follower, party[0]['species_id'], app.moving, app.direction, '', '', None))
        actors.append((app.position.y, 'tamer', app.position, app.state.get('tamer', app.tamer),
                       app.moving, app.direction, app.state.get('username', ''), player_title(app.state.get('active_title')), None))
        if app.state.get('in_story'):
            for npc in self._story_npcs():
                pos = pygame.Vector2(npc.get('x', 0), npc.get('y', 0))
                actors.append((pos.y, 'story_npc', pos, npc.get('display_species') or npc.get('tamer_id', npc.get('tamer')),
                               False, npc.get('direction', 'down'), npc.get('name', 'Story tamer'), '', npc))
            return sorted(actors, key=lambda actor: actor[0])
        for name, player in app.players.items():
            if name == app.state.get('username') or player.get('map_id') != app.state.get('map_id'):
                continue
            pos = app.player_render.get(name)
            if pos is None:
                pos = pygame.Vector2(player.get('x', 0), player.get('y', 0))
            dx, dy = player.get('dx', 0), player.get('dy', 0)
            vertical = 'down' if dy > 0 else 'up' if dy < 0 else ''
            horizontal = 'right' if dx > 0 else 'left' if dx < 0 else ''
            direction = f'{vertical}_{horizontal}' if vertical and horizontal else vertical or horizontal
            supplied = player.get('direction')
            if not direction:
                direction = supplied if supplied in ('up', 'down', 'left', 'right', 'up_left', 'up_right', 'down_left', 'down_right') else self._facings.get(name, 'down')
            self._facings[name] = direction
            bot_id = player.get('id') if player.get('is_bot') else None
            label = ('AI RIVAL · '+str(player.get('name') or name) if bot_id is not None
                     else str(player.get('username') or name))
            title = player_title(player.get('active_title')) if bot_id is None else ''
            actors.append((pos.y, 'tamer', pos, player.get('tamer'), bool(dx or dy), direction, label, title, bot_id))
            if player.get('lead'):
                follower = pos + pygame.Vector2(-24, 28)
                actors.append((follower.y, 'digimon', follower, player['lead'], bool(dx or dy), direction, '', '', None))
        return sorted(actors, key=lambda actor: actor[0])

    def draw(self, view):
        app = self.app
        view = pygame.Rect(view)
        self._reset_story_labels(view)
        panel(app.screen, view, (12, 23, 31), LINE, 12)
        map_id = app.state.get('map_id')
        entry = app.assets.maps.get(map_id, {})
        surface = app.assets.map(map_id)
        if surface:
            changed = map_id != self.map_id
            if changed:
                self._layers.clear()
            self.map_id = map_id
            physical_view = self._physical_rect(view.inflate(-2, -2))
            self.camera.configure(surface.get_size(), physical_view, self.focus, snap=changed)
            old_clip = self._surface.get_clip()
            self._surface.set_clip(physical_view.clip(old_clip))
            try:
                self._draw_layer(surface, 'background')
                scale = self.camera.scale
                frame = (scale, self.camera.origin,
                         self.camera.viewport.inflate(round(180 * scale), round(180 * scale)))
                for _, kind, position, ident, moving, direction, label, title, bot_id in self._actors():
                    npc = bot_id if kind == 'story_npc' else None
                    self._draw_actor(('digimon' if npc.get('display_species') else 'tamer') if npc else kind, position, ident, moving, direction, label,
                                     None if npc else bot_id, title=title, frame=frame, story_npc=npc)
                foreground = app.assets.image(entry.get('foreground'))
                if foreground:
                    self._draw_layer(foreground, 'foreground')
                self._draw_story_exits()
            finally:
                self._surface.set_clip(old_clip)
        else:
            text(app.screen, app.assets, 'Map asset unavailable', view.center, 23, WHITE, center=True)
        self._draw_hud(entry, view)

    def _draw_hud(self, entry, view):
        app = self.app
        story = self._story_view()
        hud = pygame.Rect(view.x + 14, view.y + 14, min(430 if story is not None else 390, view.width - 186),
                          116 if story is not None else 70)
        panel(app.screen, hud, (9, 19, 31), LINE, 9)
        text(app.screen, app.assets, (story.get('map_name') if story is not None else None) or entry.get('name', 'Digital World'),
             (hud.x + 13, hud.y + 11), 19, WHITE, True, hud.width - 26)
        if story is not None:
            subtitle = (f"WORLD DS  ·  {story.get('badge_count',0)} / {story.get('badge_total',17)} PARADOX CRESTS"
                        if story.get('campaign_id') == 'world_ds_paradox' else story.get('chapter_name', 'STORY MODE'))
            text(app.screen, app.assets, subtitle, (hud.x+13, hud.y+39),
                 11, GOLD, True, hud.width-26)
            # Preparation guidance remains in the full journal/feed. Keep this
            # compact map overlay focused on the actionable quest objective.
            objective = story.get('objective', 'Speak with the tamers in this area.').split(' Field training and free recovery',1)[0]
            wrap(app.screen, app.assets, objective,
                 (hud.x+13, hud.y+60), hud.width-26, 12, WHITE, max_lines=2)
            text(app.screen, app.assets, 'WASD / arrows to explore  ·  E to interact', (hud.x+13, hud.bottom-17),
                 10, CYAN, max_width=hud.width-26)
        else:
            text(app.screen, app.assets, 'WASD / arrows  ·  Mouse wheel to zoom', (hud.x + 13, hud.y + 42),
                 12, CYAN, max_width=hud.width - 26)
        self._draw_minimap(entry, pygame.Rect(view.right - 153, view.y + 15, 136, 88))
        controls = pygame.Rect(view.x + 14, view.bottom - 57, 266, 43)
        panel(app.screen, controls, (9, 19, 31), LINE, 9)
        change_zoom = getattr(app, 'change_zoom', self.change_zoom)
        set_zoom = getattr(app, 'set_zoom', self.set_zoom)
        app.ui.button((controls.x + 5, controls.y + 5, 33, 33), '−', lambda: change_zoom(-.5), disabled=self.zoom <= 1)
        label = f'{self.zoom:g}×' + ('  FIT' if self.zoom <= 1 else '')
        text(app.screen, app.assets, label, (controls.x + 86, controls.centery), 15, WHITE, True, center=True)
        app.ui.button((controls.x + 133, controls.y + 5, 33, 33), '+', lambda: change_zoom(.5), disabled=self.zoom >= 8)
        app.ui.button((controls.x + 177, controls.y + 5, 83, 33), 'Fit level', lambda: set_zoom(1), small=True, selected=self.zoom <= 1)
        if story is not None:
            nearby = self.nearest_story_interaction()
            label = ('Take path  E' if nearby[1].get('unlocked') else 'Locked path  E') if nearby and nearby[0] == 'exit' else 'Talk nearby  E' if nearby else 'Approach a marker'
            def interact():
                if nearby:
                    callback = app.story_screen.exit if nearby[0] == 'exit' else app.story_screen.talk
                    callback(nearby[1]['id'])
            app.ui.button((view.right-203, view.bottom-51, 188, 36), label, interact,
                          small=True, disabled=app.action_pending or nearby is None, accent=GOLD)
        else:
            app.ui.button((view.right - 187, view.bottom - 51, 172, 36), 'Search for Digimon  E',
                          lambda: app.send('encounter'), small=True, disabled=app.action_pending or bool(app.state.get('admin_jail')))

    def _draw_minimap(self, entry, rect):
        surface = self.app.assets.map(self.app.state.get('map_id'))
        if surface is None:
            return
        panel(self.app.screen, rect, BG, CYAN, 6)
        inner = self._physical_rect(rect.inflate(-8, -8))
        factor = min(inner.width / surface.get_width(), inner.height / surface.get_height())
        size = (max(1, round(surface.get_width() * factor)), max(1, round(surface.get_height() * factor)))
        key = (entry.get('id'), id(surface), size)
        if key != self._mini_key:
            self._mini_surface = pygame.transform.scale(surface, size)
            self._mini_key = key
        destination = self._mini_surface.get_rect(center=inner.center)
        self._surface.blit(self._mini_surface, destination)
        if self.zoom > 1:
            crop = self.camera.source_crop()
            visible = pygame.Rect(round(destination.x + crop.x * factor), round(destination.y + crop.y * factor),
                                  max(1, round(crop.width * factor)), max(1, round(crop.height * factor)))
            pygame.draw.rect(self._surface, CYAN, visible, max(1, round(getattr(self.app.screen, 'scale', 1))))
        for npc in self._story_npcs():
            marker = (round(destination.x+npc.get('x', 0)*factor), round(destination.y+npc.get('y', 0)*factor))
            radius = max(2, round(3*getattr(self.app.screen, 'scale', 1)))
            pygame.draw.circle(self._surface, BG, marker, radius+1)
            pygame.draw.circle(self._surface, self._story_color(npc), marker, radius)
        for gate in self._story_exits():
            marker = pygame.Rect(0, 0, max(4, round(6*getattr(self.app.screen, 'scale', 1))), max(4, round(6*getattr(self.app.screen, 'scale', 1))))
            marker.center = (round(destination.x+gate.get('x', 0)*factor), round(destination.y+gate.get('y', 0)*factor))
            pygame.draw.rect(self._surface, BG, marker.inflate(2, 2))
            pygame.draw.rect(self._surface, CYAN if gate.get('unlocked') else MUTED, marker, 1 if not gate.get('unlocked') else 0)
        position = (round(destination.x + self.app.position.x * factor),
                    round(destination.y + self.app.position.y * factor))
        ui_scale = getattr(self.app.screen, 'scale', 1)
        pygame.draw.circle(self._surface, BG, position, max(2, round(5 * ui_scale)))
        pygame.draw.circle(self._surface, LIME, position, max(1, round(3 * ui_scale)))
