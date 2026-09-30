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
    # A crowded map can cycle through hundreds of distinct animation frames.
    # Let the byte budgets govern art retention; low entry limits discarded
    # tiny sprites while nearly all of the allocated budget was still free.
    IMAGE_CACHE_ITEMS = 4096
    SCALED_CACHE_ITEMS = 4096

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
        self._remember(self.cache, path, result, 'cache_bytes', self.IMAGE_CACHE_BYTES, self.IMAGE_CACHE_ITEMS)
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
        if flip:
            # Labelled pose packs can supply a genuine opposite-facing step.
            # Other frames still mirror normally; never flip that supplied pose twice.
            mirrored = self.species.get(species_id, {}).get('mirrored_frames', {}).get(path)
            if mirrored:
                path, flip = mirrored, False
        key = (path, tuple(box), flip)
        # The fitted frame is self-contained. Avoid decoding the original PNG
        # again after its independent source cache has evicted it.
        cached = self.scaled.get(key)
        if cached is not None:
            self.scaled.move_to_end(key)
            return cached
        source = self.image(path)
        return self.fit(source, box, key=key, flip=flip) if source else None

    def sprite_anchor(self, species_id, surface, motion='idle', now=0., flip=False):
        """Locate the original partner's feet within an aura-padded frame.

        Artwork remains intact. Fixed UI portraits fit the complete supplied
        canvas; open-world companions can retain their ordinary body size.
        """
        if surface is None:
            return (0, 0)
        entry = self.species.get(species_id, {})
        path = self.sprite_path(species_id, motion, now)
        mirrored = entry.get('mirrored_frames', {}).get(path) if flip else None
        if mirrored:
            path, flip = mirrored, False
        geometry = entry.get('sprite_geometry', {}).get(path, {})
        size = geometry.get('source_size')
        output = geometry.get('output_size')
        if not size or not output or min(output) <= 0:
            return (surface.get_width()/2, surface.get_height())
        padding = geometry.get('padding', {})
        x = padding.get('left', 0)+size[0]/2
        y = padding.get('top', 0)+size[1]
        if flip:
            x = output[0]-x
        return (x*surface.get_width()/output[0], y*surface.get_height()/output[1])

    def world_sprite(self, species_id, box, motion='idle', now=0., flip=False):
        """Size the body like its normal form and leave room for its aura."""
        entry = self.species.get(species_id, {})
        path = self.sprite_path(species_id, motion, now)
        if flip:
            path = entry.get('mirrored_frames', {}).get(path, path)
        geometry = entry.get('sprite_geometry', {}).get(path, {})
        size = geometry.get('source_size')
        output = geometry.get('output_size')
        if size and output and min(size) > 0:
            factor = min(box[0]/size[0], box[1]/size[1])
            factor = max(1, int(factor)) if factor >= 1 else factor
            box = (max(1, round(output[0]*factor)), max(1, round(output[1]*factor)))
        return self.sprite(species_id, box, motion, now, flip)

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
        self._remember(self.scaled, key, surface, 'scaled_bytes', self.SCALED_CACHE_BYTES, self.SCALED_CACHE_ITEMS)
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
        scale = entry.get('display_scale', 2)
        key = ('tamer', path, tuple(box), scale)
        cached = self.scaled.get(key)
        if cached is not None:
            self.scaled.move_to_end(key)
            return cached
        source = self.image(path)
        if not source: return None
        native = (source.get_width()*scale, source.get_height()*scale)
        display_box = (min(box[0], native[0]), min(box[1], native[1]))
        return self.fit(source, display_box, key=key)

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
    """Stream one scene soundtrack; retain only short effects in memory.

    ``music`` also advances a short volume envelope. It is cheap to call every
    frame, and never waits for a fade or decodes a complete song into RAM.
    """
    FADE_OUT_SECONDS = .14
    FADE_IN_MS = 420
    CUE_INTERVAL_SECONDS = .065
    SUCCESS_CUES = frozenset(('scan_complete', 'evolution_complete', 'purchase', 'error', 'season_enter', 'season_results', 'story_enter', 'story_badge', 'story_victory'))

    def __init__(self, assets):
        self.assets, self.enabled = assets, False
        self.available = False
        self.music_volume, self.effects_volume = .35, .3
        self.sounds, self.track = {}, None
        info = self.assets.catalog.get('audio', {})
        self._tracks = info.get('music', [])
        self._tracks_by_id = {t.get('id'): t for t in self._tracks if isinstance(t, dict)}
        # Appending another region must not change Dawn's established rotation.
        self._world_tracks = [track for track in self._tracks
                              if not isinstance(track, dict) or
                              (track.get('region_id') not in ('world_ds', 'xros_wars') and
                               not str(track.get('id', '')).startswith(('ds_', 'xros_')))]
        self._world_ds_tracks, self._world_ds_scenes = {}, {}
        self._world_ds_result = None
        self._play_once_paths = set()
        try:
            region_audio = json.loads((self.assets.root/'data/world_ds_audio.json').read_text('utf-8'))
            self._world_ds_tracks = {track['id']: track for track in region_audio.get('music', [])
                                     if isinstance(track, dict) and track.get('id') and track.get('path')}
            self._world_ds_scenes = region_audio.get('scene_tracks', {})
            self._tracks_by_id.update(self._world_ds_tracks)
            self._play_once_paths = {track['path'] for track in self._world_ds_tracks.values()
                                     if not track.get('looped', True)}
        except (OSError, ValueError, TypeError):
            # Older/custom asset packs retain their existing score.
            pass
        self._xros_tracks, self._xros_scenes = {}, {}
        try:
            region_audio = json.loads((self.assets.root/'data/xros_audio.json').read_text('utf-8'))
            self._xros_tracks = {track['id']: track for track in region_audio.get('music', [])
                                 if isinstance(track, dict) and track.get('id') and track.get('path')}
            self._xros_scenes = region_audio.get('scene_tracks', {})
            self._tracks_by_id.update(self._xros_tracks)
            self._play_once_paths.update(track['path'] for track in self._xros_tracks.values()
                                         if not track.get('looped', True))
        except (OSError, ValueError, TypeError):
            pass
        self._tracks_by_path = {track['path']: track for track in self._tracks_by_id.values()
                                if isinstance(track, dict) and track.get('path')}
        self._scene_tracks = info.get('scene_tracks', {})
        self._map_indices = {map_id: index for index, map_id in enumerate(self.assets.maps)}
        self._music_context = None
        self._effects = info.get('effects', [])
        self._effects_by_id = {t.get('id'): t for t in self._effects if isinstance(t, dict)} if isinstance(self._effects, list) else {}
        self._event_sounds = info.get('event_sounds', {})
        self._effect_paths = {}
        self._screen_tracks, self._ui_cues = {}, {}
        interface = self.assets.root/'data'/'ui_audio.json'
        try:
            configuration = json.loads(interface.read_text('utf-8'))
            if isinstance(configuration, dict):
                self._screen_tracks = configuration.get('screen_tracks', {})
                self._ui_cues = configuration.get('cues', {})
        except (OSError, ValueError):
            # Old/custom asset packs can keep using catalog music and effects.
            pass
        self._pending_track = None
        self._fade_started = 0.
        self._fade_from = self._music_gain = 1.
        self._failed_tracks = set()
        self._last_cue = -100.
        self._last_success_cues = {}
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
            self._apply_music_volume()
            for sound in self.sounds.values():
                sound.set_volume(self.effects_volume if self.enabled else 0.)

    def _apply_music_volume(self):
        pygame.mixer.music.set_volume(self.music_volume*self._music_gain if self.enabled else 0.)

    def _start_track(self, path):
        self._pending_track = None
        self._music_gain = 1.
        try:
            recording = self._tracks_by_path.get(path, {})
            intro = recording.get('intro_path')
            pygame.mixer.music.load(str(self.assets.root/(intro or path)))
            self._apply_music_volume()
            once = path in self._play_once_paths
            pygame.mixer.music.play(0 if once or intro else -1,
                                    fade_ms=25 if once else self.FADE_IN_MS)
            if intro:
                # SDL streams the original intro once, then the exact embedded
                # repeating range indefinitely without frame-timed restarts.
                pygame.mixer.music.queue(str(self.assets.root/path), loops=-1)
            elif recording.get('continuation_id'):
                continuation = self._tracks_by_id.get(recording['continuation_id'])
                if continuation:
                    pygame.mixer.music.queue(str(self.assets.root/continuation['path']), loops=-1)
            self.track = path
        except (pygame.error, OSError):
            # Do not retry missing/corrupt optional art every rendered frame.
            self._failed_tracks.add(path)
            self._apply_music_volume()

    def _advance_transition(self, now):
        if self._pending_track is None:
            return
        elapsed = max(0., now-self._fade_started)
        if elapsed >= self.FADE_OUT_SECONDS or not self.enabled or self.music_volume <= 0:
            self._start_track(self._pending_track)
        else:
            self._music_gain = self._fade_from*(1.-elapsed/self.FADE_OUT_SECONDS)
            self._apply_music_volume()

    STORY_TRACKS = {'story': 'bgm30', 'story_results': 'bgm60',
                    'story_tamer': 'bgm40', 'story_warden': 'bgm50', 'story_champion': 'bgm51'}
    STORY_REGIONS = ('bgm10', 'bgm12', 'bgm14', 'bgm16', 'bgm18', 'bgm20', 'bgm30', 'bgm31', 'bgm33')

    def music(self, battle=False, map_id=None, in_lab=False, screen=None, now=None, in_farm=False,
              in_story=False, story_battle=None, story_region=None, in_season=False, replay=False,
              story_campaign=None):
        """Route visible screens, with live battles/replays taking priority.

        Call again with ``screen=None`` when an overlay closes to restore its
        world/DigiLab/DigiFarm soundtrack. ``now`` is elapsed seconds, matching App.now.
        Muted screen changes still update the stream at zero gain so unmuting
        cannot briefly reveal music from a screen which has already closed.
        """
        if not self.available:
            return
        now = pygame.time.get_ticks()/1000 if now is None else now
        screen = {'lab': 'digilab', 'digifarm': 'farm'}.get(screen, screen)
        role = (story_battle.get('story_role', story_battle.get('role', 'tamer'))
                if isinstance(story_battle, dict) else story_battle)
        story_combat = 'story_'+('champion' if role in ('champion', 'defense', 'reclaim', 'challenger')
                                else 'warden' if role in ('warden', 'leader') else 'tamer')
        map_entry = self.assets.maps.get(map_id, {})
        ds_story = in_story and story_campaign == 'world_ds_paradox'
        xros_story = in_story and story_campaign == 'xros_ghostline'
        world_ds = (map_entry.get('region_id') == 'world_ds' and
                    not (in_story or in_season or in_farm or in_lab or replay))
        xros_world = (map_entry.get('region_id') == 'xros_wars' and
                      not (in_story or in_season or in_farm or in_lab or replay))
        scene = ('world_ds_final' if battle and ds_story and role == 'final'
                 else 'world_ds_battle' if battle and ds_story
                 else 'xros_final' if battle and xros_story and role == 'final'
                 else 'xros_battle' if battle and xros_story
                 else story_combat if battle and story_battle
                 else 'world_ds_battle' if battle and world_ds
                 else 'xros_battle' if battle and xros_world else 'battle' if battle
                 else 'xros_world' if xros_story and screen in ('story','story_results') and not (in_lab or in_farm)
                 else screen if screen in self._screen_tracks or screen in self.STORY_TRACKS
                 else 'farm' if in_farm else 'digilab' if in_lab
                 else 'world_ds_world' if ds_story else 'xros_world' if xros_story else 'story_world' if in_story
                 else 'title' if map_id is None else 'world')
        if self._world_ds_result and (now >= self._world_ds_result['until'] or
                                      map_id != self._world_ds_result['map_id'] or battle or
                                      not world_ds or scene != 'world'):
            self._world_ds_result = None
        if scene == 'world' and world_ds:
            scene = 'world_ds_victory' if self._world_ds_result else 'world_ds_world'
        if scene == 'world' and xros_world:
            scene = 'xros_world'
        region = story_region if story_region is not None else map_id
        context = (scene, map_id if scene == 'world' or scene.startswith(('world_ds_', 'xros_'))
                   else region if scene == 'story_world' else None)
        if context == self._music_context:
            self._advance_transition(now)
            return
        self._music_context = context
        tracks = self._tracks
        track = self._screen_tracks.get(scene)
        if scene.startswith('xros_'):
            identifier = (self._xros_scenes.get('endgame_battle') if scene == 'xros_final'
                          else map_entry.get('battle_music_id' if battle else 'music_id'))
            fallback = self._xros_scenes.get('battle' if battle else 'world')
            track = self._xros_tracks.get(identifier) or self._xros_tracks.get(fallback)
            if not track:
                track = self._tracks_by_id.get(self._scene_tracks.get('battle' if battle else 'world'),
                                                self._world_tracks[0] if self._world_tracks else None)
        elif scene.startswith('world_ds_'):
            identifier = (map_entry.get('music_id') if scene == 'world_ds_world' else
                          map_entry.get('battle_music_id') if scene == 'world_ds_battle' else
                          self._world_ds_scenes.get('endgame_battle') if scene == 'world_ds_final' else
                          self._world_ds_scenes.get('victory'))
            fallback = self._world_ds_scenes.get(scene.removeprefix('world_ds_'))
            track = self._world_ds_tracks.get(identifier) or self._world_ds_tracks.get(fallback)
            if not track:
                fallback = 'battle' if battle else 'world'
                track = self._tracks_by_id.get(self._scene_tracks.get(fallback),
                                                self._world_tracks[0] if self._world_tracks else None)
        elif scene == 'story_world':
            region_index = region if isinstance(region, int) else sum(ord(c) for c in str(region))
            track = self._tracks_by_id.get(self.STORY_REGIONS[region_index % len(self.STORY_REGIONS)])
            if not track:
                track = self._tracks_by_id.get(self._scene_tracks.get('world'), tracks[0] if tracks else None)
        elif scene in self.STORY_TRACKS and not track:
            track = self._tracks_by_id.get(self.STORY_TRACKS[scene])
            if not track:
                fallback = 'battle' if scene.startswith('story_') and scene != 'story_results' else 'world'
                track = self._tracks_by_id.get(self._scene_tracks.get(fallback), tracks[0] if tracks else None)
        elif scene == 'world':
            map_index = self._map_indices.get(map_id, 0)
            track = self._world_tracks[map_index % len(self._world_tracks)] if self._world_tracks else None
        elif not track:
            track = self._tracks_by_id.get(self._scene_tracks.get(scene), tracks[0] if tracks else None)
        if isinstance(track, dict):
            track = track.get('path')
        if not track or track in self._failed_tracks or track == self.track:
            # A rapid close can cancel a fade before another stream was loaded.
            self._pending_track = None
            if self._music_gain != 1.:
                self._music_gain = 1.
                self._apply_music_volume()
            return
        if not self.track or not self.enabled or self.music_volume <= 0:
            self._start_track(track)
        else:
            # pygame.mixer.music.fadeout blocks; this frame-driven envelope
            # keeps gameplay, UI interactions and network polling responsive.
            self._pending_track = track
            self._fade_started, self._fade_from = now, self._music_gain

    def world_ds_victory(self, map_id, now=None):
        """Play the supplied fanfare after a confirmed shared-world victory.

        The caller filters private-mode battles. Save loads and other tamers'
        replays never call this method. A new battle, map change or leaving the
        field cancels the temporary result soundtrack.
        """
        if self.assets.maps.get(map_id, {}).get('region_id') != 'world_ds':
            return
        track = self._world_ds_tracks.get(self._world_ds_scenes.get('victory'))
        if not track:
            return
        now = pygame.time.get_ticks()/1000 if now is None else now
        self._world_ds_result = {'map_id': map_id,
                                 'until': now + float(track.get('duration', 4.4)) + self.FADE_OUT_SECONDS}

    def cue(self, name='confirm', now=None):
        """A short UI response, debounced across nested button callbacks.

        Success cues are called only after confirmed game operations. A fast
        server response must not lose its completion sound to the initiating
        button's generic confirmation, while duplicate completions are bounded.
        """
        if not self.enabled or self.effects_volume <= 0:
            return
        now = pygame.time.get_ticks()/1000 if now is None else now
        if name in self.SUCCESS_CUES:
            if now-self._last_success_cues.get(name, -100.) < self.CUE_INTERVAL_SECONDS:
                return
            self._last_success_cues[name] = now
        elif now-self._last_cue < self.CUE_INTERVAL_SECONDS:
            return
        self._last_cue = now
        fallback_cue = {'story_enter': 'open', 'story_badge': 'evolution_complete',
                        'story_victory': 'purchase'}.get(name, name)
        path = self._ui_cues.get(name) or self._ui_cues.get(fallback_cue)
        if path:
            self._play_effect(path)
        else:
            self.effect({'back': 'cancel', 'tab': 'click', 'open': 'confirm',
                         'purchase': 'confirm', 'error': 'cancel',
                         'scan_complete': 'scan', 'evolution_complete': 'evolve'}.get(fallback_cue, fallback_cue))

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
        self._play_effect(path)

    def _play_effect(self, path):
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
            self._apply_music_volume()
            if not self.enabled:
                # Muting includes effects already playing, not only future sounds.
                pygame.mixer.stop()
