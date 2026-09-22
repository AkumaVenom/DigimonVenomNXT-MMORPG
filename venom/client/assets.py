"""Bounded asset cache. Source art is kept at integer scales with nearest filtering."""
from __future__ import annotations
from collections import OrderedDict
import json
import math
from pathlib import Path
import weakref
import pygame


class Assets:
    IMAGE_CACHE_BYTES = 128 * 1024 * 1024
    SCALED_CACHE_BYTES = 96 * 1024 * 1024

    def __init__(self, root: Path):
        self.root = root
        path = root / 'data' / 'catalog.json'
        self.catalog = json.loads(path.read_text('utf-8')) if path.exists() else {'species': [], 'tamers': [], 'maps': [], 'audio': {}}
        effects_path = root/'data'/'effects_catalog.json'
        if effects_path.exists() and not self.catalog.get('battle_effects'):
            self.catalog['battle_effects'] = json.loads(effects_path.read_text('utf-8')).get('effects', [])
        self.species = {entry['id']: entry for entry in self.catalog.get('species', [])}
        self.tamers = {entry['id']: entry for entry in self.catalog.get('tamers', [])}
        self.maps = {entry['id']: entry for entry in self.catalog.get('maps', [])}
        self.cache: OrderedDict = OrderedDict()
        self.scaled: OrderedDict = OrderedDict()
        self.cache_bytes = 0
        self.scaled_bytes = 0
        self.map_id = None
        self.map_surface = None
        self.errors = []
        self.fonts: OrderedDict = OrderedDict()
        candidates = [self.root/'assets'/'fonts'/'DejaVuSans.ttf', self.root/'assets'/'fonts'/'NotoSans-Regular.ttf']
        self.font_path = next((str(p) for p in candidates if p.exists()), None)

    def font(self, size=18, bold=False):
        size = max(1, min(4096, round(size)))
        key = (size, bold)
        if key not in self.fonts:
            font = pygame.font.Font(self.font_path, size) if self.font_path else pygame.font.SysFont('segoeui,dejavusans,arial', size)
            font.set_bold(bold)
            self.fonts[key] = font
            while len(self.fonts) > 128:
                self.fonts.popitem(last=False)
        self.fonts.move_to_end(key)
        return self.fonts[key]

    @staticmethod
    def surface_bytes(surface):
        """Include row padding, which can exceed width * bytes per pixel."""
        return surface.get_pitch() * surface.get_height() if surface is not None else 0

    def _remember(self, cache, key, surface, byte_attr, byte_limit, count_limit):
        size = self.surface_bytes(surface)
        # Oversized transient surfaces must not displace the entire useful cache.
        if size > byte_limit:
            return
        if key in cache:
            setattr(self, byte_attr, getattr(self, byte_attr) - self.surface_bytes(cache.pop(key)))
        cache[key] = surface
        setattr(self, byte_attr, getattr(self, byte_attr) + size)
        while len(cache) > count_limit or getattr(self, byte_attr) > byte_limit:
            _, removed = cache.popitem(last=False)
            setattr(self, byte_attr, getattr(self, byte_attr) - self.surface_bytes(removed))

    def clear_scaled(self):
        """Release old display-size variants after a display scale change."""
        self.scaled.clear()
        self.scaled_bytes = 0

    def image(self, path):
        if not path:
            return None
        if isinstance(path, list):
            path = path[0] if path else None
        if not path:
            return None
        if path in self.cache:
            self.cache.move_to_end(path)
            return self.cache[path]
        try:
            result = pygame.image.load(str(self.root / path)).convert_alpha()
        except (pygame.error, FileNotFoundError, TypeError) as exc:
            if len(self.errors) < 20:
                self.errors.append(f'{path}: {exc}')
            result = None
        self._remember(self.cache, path, result, 'cache_bytes', self.IMAGE_CACHE_BYTES, 250)
        return result

    def sprite_path(self, species_id, motion='idle', now=0.):
        entry = self.species.get(species_id, {})
        animations = entry.get('animations', {})
        animation = animations.get(motion) or animations.get('attack' if motion in ('attack1','attack2') else motion)
        if animation:
            return animation[int(now*8) % len(animation)]
        sprites = entry.get('sprites', {})
        path = sprites.get(motion) or sprites.get('idle') or sprites.get('front')
        if isinstance(path, list):
            return path[int(now*8) % len(path)] if path else None
        return path

    def sprite(self, species_id, box, motion='idle', now=0., flip=False):
        path = self.sprite_path(species_id, motion, now)
        source = self.image(path)
        return self.fit(source, box, key=(path, box, flip), flip=flip) if source else None

    def fit(self, source, box, key=None, flip=False):
        if source is None:
            return None
        # A weak identity avoids retaining full maps behind tiny minimaps, and
        # prevents a recycled object id from returning a different map's art.
        key = key or (weakref.ref(source), tuple(box), flip)
        if key in self.scaled:
            self.scaled.move_to_end(key)
            return self.scaled[key]
        # Never invent blended colors in pixel art, including small previews.
        factor = min(box[0] / source.get_width(), box[1] / source.get_height())
        factor = max(1, int(factor)) if factor >= 1 else factor
        size = (max(1, round(source.get_width()*factor)), max(1, round(source.get_height()*factor)))
        surface = pygame.transform.scale(source, size)
        if flip:
            surface = pygame.transform.flip(surface, True, False)
        self._remember(self.scaled, key, surface, 'scaled_bytes', self.SCALED_CACHE_BYTES, 500)
        return surface

    def tamer(self, tamer_id, direction='down', moving=False, now=0., box=(64, 80)):
        entry = self.tamers.get(tamer_id, {})
        frames = entry.get('frames', {}).get(direction) or entry.get('frames', {}).get('down') or []
        if isinstance(frames, str):
            frames = [frames]
        if not frames:
            return None
        timings = entry.get('frame_seconds', {}).get(direction, [.133333]*len(frames))
        phase = now % max(.01, sum(timings))
        index = 0
        if moving:
            for index, duration in enumerate(timings):
                phase -= duration
                if phase < 0: break
            index = min(index, len(frames)-1)
        path = frames[index]
        source = self.image(path)
        if not source: return None
        scale = entry.get('display_scale', 2)
        native = (source.get_width()*scale, source.get_height()*scale)
        display_box = (min(box[0], native[0]), min(box[1], native[1]))
        return self.fit(source, display_box, key=(path, display_box, False))

    def map(self, map_id):
        if self.map_id != map_id:
            self.map_id = map_id
            entry = self.maps.get(map_id, {})
            try:
                self.map_surface = pygame.image.load(str(self.root / entry['path'])).convert()
            except (KeyError, pygame.error, FileNotFoundError):
                self.map_surface = None
        return self.map_surface


class Audio:
    def __init__(self, assets):
        self.assets, self.enabled = assets, False
        self.available = False
        self.music_volume, self.effects_volume = .35, .3
        self.sounds, self.track = {}, None
        info = self.assets.catalog.get('audio', {})
        self._tracks = info.get('music', [])
        self._tracks_by_id = {t.get('id'): t for t in self._tracks if isinstance(t, dict)}
        self._scene_tracks = info.get('scene_tracks', {})
        self._map_indices = {map_id: index for index, map_id in enumerate(self.assets.maps)}
        self._music_context = None
        self._effects = info.get('effects', [])
        self._effects_by_id = {t.get('id'): t for t in self._effects if isinstance(t, dict)} if isinstance(self._effects, list) else {}
        self._event_sounds = info.get('event_sounds', {})
        self._effect_paths = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self.available = self.enabled = True
            pygame.mixer.music.set_volume(self.music_volume)
        except pygame.error:
            pass

    def set_volumes(self, music, effects):
        """Apply saved gain independently of mute without requiring an audio device."""
        def volume(value, previous):
            try:
                value = float(value)
            except (TypeError, ValueError):
                return previous
            return max(0., min(1., value)) if math.isfinite(value) else previous
        self.music_volume = volume(music, self.music_volume)
        self.effects_volume = volume(effects, self.effects_volume)
        if self.available and pygame.mixer.get_init():
            pygame.mixer.music.set_volume(self.music_volume if self.enabled else 0.)
            for sound in self.sounds.values():
                sound.set_volume(self.effects_volume if self.enabled else 0.)

    def music(self, battle=False, map_id=None, in_lab=False):
        tracks = self._tracks
        if not self.enabled or not tracks:
            return
        scene = 'battle' if battle else 'digilab' if in_lab else 'title' if map_id is None else 'world'
        context = (scene, map_id if scene == 'world' else None)
        if context == self._music_context:
            return
        self._music_context = context
        if scene == 'world':
            map_index = self._map_indices.get(map_id, 0)
            track = tracks[map_index % len(tracks)]
        else:
            track = self._tracks_by_id.get(self._scene_tracks.get(scene), tracks[0])
        if isinstance(track, dict):
            track = track.get('path')
        if track and track != self.track:
            try:
                pygame.mixer.music.load(str(self.assets.root/track))
                pygame.mixer.music.play(-1, fade_ms=700)
                self.track = track
            except (pygame.error, FileNotFoundError):
                pass

    def effect(self, name='hit'):
        if not self.enabled or self.effects_volume <= 0:
            return
        if name not in self._effect_paths:
            effects = self._effects
            if isinstance(effects, dict):
                path = effects.get(name) or next(iter(effects.values()), None)
            else:
                sound_id = self._event_sounds.get(name, name)
                path = self._effects_by_id.get(sound_id)
                if path is None:
                    path = next((p for p in effects if str(sound_id).lower() in str(p).lower()), effects[0] if effects else None)
            if isinstance(path, dict):
                path = path.get('path')
            self._effect_paths[name] = path
        path = self._effect_paths[name]
        if not path:
            return
        try:
            if path not in self.sounds:
                self.sounds[path] = pygame.mixer.Sound(str(self.assets.root/path))
            self.sounds[path].set_volume(self.effects_volume)
            self.sounds[path].play()
        except (pygame.error, FileNotFoundError):
            pass

    def toggle(self):
        if not self.available:
            return
        self.enabled = not self.enabled
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(self.music_volume if self.enabled else 0.)
            if not self.enabled:
                # Muting includes effects already playing, not only future sounds.
                pygame.mixer.stop()
