"""Native-resolution, nearest-neighbour world rendering and a bounded map camera.

The camera operates in the supplied x2 map's coordinates.  UI scale is deliberately
separate: changing Windows DPI must not change movement or collision coordinates.
Only the visible map crop is enlarged, including at the maximum 8x view zoom.
"""
from __future__ import annotations

from collections import OrderedDict
import math

import pygame

from .widgets import BG, CYAN, LINE, LIME, MUTED, WHITE, panel, text


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
        destination = self.camera.crop_destination(crop)
        key = (id(surface), tuple(crop), destination.size)
        cached = self._layers.get(slot)
        if cached is None or cached[0] != key:
            # A view-sized allocation, never a full-map x8 intermediate.
            source = surface.subsurface(crop)
            scaled = pygame.transform.scale(source, destination.size)
            self._layers[slot] = (key, scaled)
        self._surface.blit(self._layers[slot][1], destination)

    def _scale_sprite(self, source):
        size = (max(1, round(source.get_width() * self.camera.scale)),
                max(1, round(source.get_height() * self.camera.scale)))
        key = (id(source), size)
        if key in self._sprites:
            self._sprites.move_to_end(key)
            return self._sprites[key][1]
        scaled = pygame.transform.scale(source, size)
        size_bytes = scaled.get_pitch() * scaled.get_height()
        # Keep a source reference: pygame can otherwise reuse its id after eviction.
        if size_bytes <= self.SPRITE_CACHE_BYTES:
            self._sprites[key] = (source, scaled, size_bytes)
            self._sprite_bytes += size_bytes
            while self._sprite_bytes > self.SPRITE_CACHE_BYTES or len(self._sprites) > 256:
                _, old = self._sprites.popitem(last=False)
                self._sprite_bytes -= old[2]
        return scaled

    def _draw_actor(self, kind, world_pos, ident, moving, direction, label, bot_id=None):
        app, scale = self.app, self.camera.scale
        pos = self.camera.world_to_screen(world_pos)
        if not self.camera.viewport.inflate(round(180 * scale), round(180 * scale)).collidepoint(pos):
            return
        shadow = pygame.Rect(round(pos.x - 15 * scale), round(pos.y - 5 * scale),
                             max(2, round(30 * scale)), max(1, round(12 * scale)))
        pygame.draw.ellipse(self._surface, (22, 33, 40), shadow)
        source = (app.assets.tamer(ident, direction, moving, app.now, (64, 80)) if kind == 'tamer'
                  else app.assets.sprite(ident, (58, 64), 'walk' if moving else 'idle', app.now))
        top = pos.y - 64 * scale
        destination = pygame.Rect(round(pos.x-16*scale), round(top), max(8, round(32*scale)), max(8, round(64*scale)))
        if source:
            sprite = self._scale_sprite(source)
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
            width, height = app.assets.font(11, True).size(label)
            label_rect = pygame.Rect(0, 0, width + 12, height + 6)
            label_rect.midbottom = (round(label_position[0]), round(label_position[1] - 6))
            panel(app.screen, label_rect, BG, None, 4)
            text(app.screen, app.assets, label, label_rect.center, 11, CYAN if bot_id else WHITE, True, center=True)
            if bot_id is not None and hasattr(app, 'community'):
                app.ui.actions.append((label_rect.clip(app.screen.to_logical_rect(self.camera.viewport)),
                                       lambda ident=bot_id: app.community.open_profile(ident)))

    def _actors(self):
        app, actors = self.app, []
        self._facings = {name: direction for name, direction in self._facings.items() if name in app.players}
        party = app.state.get('party', [])
        if party:
            actors.append((app.follower.y, 'digimon', app.follower, party[0]['species_id'], app.moving, app.direction, '', None))
        actors.append((app.position.y, 'tamer', app.position, app.state.get('tamer', app.tamer),
                       app.moving, app.direction, app.state.get('username', ''), None))
        for name, player in app.players.items():
            if name == app.state.get('username') or player.get('map_id') != app.state.get('map_id'):
                continue
            pos = app.player_render.get(name, pygame.Vector2(player.get('x', 0), player.get('y', 0)))
            dx, dy = player.get('dx', 0), player.get('dy', 0)
            vertical = 'down' if dy > 0 else 'up' if dy < 0 else ''
            horizontal = 'right' if dx > 0 else 'left' if dx < 0 else ''
            direction = f'{vertical}_{horizontal}' if vertical and horizontal else vertical or horizontal
            supplied = player.get('direction')
            if not direction:
                direction = supplied if supplied in ('up', 'down', 'left', 'right', 'up_left', 'up_right', 'down_left', 'down_right') else self._facings.get(name, 'down')
            self._facings[name] = direction
            bot_id = player.get('id') if player.get('is_bot') else None
            label = ('AI RIVAL · ' if bot_id is not None else '')+str(player.get('name') or name)
            actors.append((pos.y, 'tamer', pos, player.get('tamer'), bool(dx or dy), direction, label, bot_id))
            if player.get('lead'):
                follower = pos + pygame.Vector2(-24, 28)
                actors.append((follower.y, 'digimon', follower, player['lead'], bool(dx or dy), direction, '', None))
        return sorted(actors, key=lambda actor: actor[0])

    def draw(self, view):
        app = self.app
        view = pygame.Rect(view)
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
                for _, kind, position, ident, moving, direction, label, bot_id in self._actors():
                    self._draw_actor(kind, position, ident, moving, direction, label, bot_id)
                foreground = app.assets.image(entry.get('foreground'))
                if foreground:
                    self._draw_layer(foreground, 'foreground')
            finally:
                self._surface.set_clip(old_clip)
        else:
            text(app.screen, app.assets, 'Map asset unavailable', view.center, 23, WHITE, center=True)
        self._draw_hud(entry, view)

    def _draw_hud(self, entry, view):
        app = self.app
        hud = pygame.Rect(view.x + 14, view.y + 14, min(390, view.width - 186), 70)
        panel(app.screen, hud, (9, 19, 31), LINE, 9)
        text(app.screen, app.assets, entry.get('name', 'Digital World'), (hud.x + 13, hud.y + 11),
             19, WHITE, True, hud.width - 26)
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
        app.ui.button((view.right - 187, view.bottom - 51, 172, 36), 'Search for Digimon  E',
                      lambda: app.send('encounter'), small=True, disabled=app.action_pending)

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
        position = (round(destination.x + self.app.position.x * factor),
                    round(destination.y + self.app.position.y * factor))
        ui_scale = getattr(self.app.screen, 'scale', 1)
        pygame.draw.circle(self._surface, BG, position, max(2, round(5 * ui_scale)))
        pygame.draw.circle(self._surface, LIME, position, max(1, round(3 * ui_scale)))
