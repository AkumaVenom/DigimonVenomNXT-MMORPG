"""Native-pixel display ownership and nonsecret, per-user display preferences.

No pygame import occurs at module import time: ``configure_windows_dpi`` must run
before SDL creates any HWND when launching directly from Python. Frozen Windows
clients additionally carry the equivalent PerMonitorV2 executable manifest.
"""
from __future__ import annotations

import ctypes
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import warnings

MIN_LAYOUT = (1180, 800)
MIN_WINDOW = (960, 600)
FRAME_CAPS = (60, 120, 144, 165, 240)
DEFAULTS = {
    'version': 1,
    'window_size': [1280, 800],
    'fullscreen': False,
    'ui_scale': 'auto',
    'fps': 120,
    'show_fps': False,
    'zoom': 1.0,
    'music_volume': 0.35,
    'effects_volume': 0.30,
}


def configure_windows_dpi() -> None:
    """Prevent Windows bitmap virtualization before pygame/SDL is imported."""
    os.environ.setdefault('SDL_WINDOWS_DPI_AWARENESS', 'permonitorv2')
    os.environ.setdefault('SDL_WINDOWS_DPI_SCALING', '0')
    # All scene magnification is nearest-neighbour; no renderer blur is requested.
    os.environ.setdefault('SDL_RENDER_SCALE_QUALITY', '0')
    if sys.platform != 'win32':
        return
    try:
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        set_context = user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_int
        if set_context(ctypes.c_void_p(-4)):
            return
        # ERROR_ACCESS_DENIED means a manifest/host already established awareness.
        if ctypes.get_last_error() == 5:
            return
    except (AttributeError, OSError):
        pass
    try:
        shcore = ctypes.WinDLL('shcore', use_last_error=True)
        set_awareness = shcore.SetProcessDpiAwareness
        set_awareness.argtypes = [ctypes.c_int]
        set_awareness.restype = ctypes.c_long
        if set_awareness(2) in (0, -2147024891):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split('x', 1)
        result = int(width), int(height)
        if not (MIN_WINDOW[0] <= result[0] <= 16384 and MIN_WINDOW[1] <= result[1] <= 16384):
            raise ValueError
        return result
    except (ValueError, AttributeError):
        raise ValueError('Use WIDTHxHEIGHT, from 960x600 to 16384x16384.') from None


def parse_ui_scale(value) -> str | float:
    if value == 'auto':
        return 'auto'
    try:
        factor = float(value[:-1]) / 100 if isinstance(value, str) and value.endswith('%') else float(value)
        if not math.isfinite(factor) or not 0.75 <= factor <= 3:
            raise ValueError
        return factor
    except (ValueError, TypeError):
        raise ValueError('UI scale must be auto, a factor from 0.75 to 3, or 75% to 300%.') from None


def settings_path() -> Path:
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
        return base / 'DigimonVenomNXT' / 'display.json'
    base = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return base / 'DigimonVenomNXT' / 'display.json'


def validate_settings(value) -> dict:
    """Whitelist settings; malformed values cannot break startup or add secrets."""
    result = dict(DEFAULTS, window_size=list(DEFAULTS['window_size']))
    if not isinstance(value, dict):
        return result
    size = value.get('window_size')
    if isinstance(size, (list, tuple)) and len(size) == 2:
        try:
            if any(isinstance(x, bool) for x in size):
                raise ValueError
            result['window_size'] = list(parse_size(f'{int(size[0])}x{int(size[1])}'))
        except (ValueError, TypeError, OverflowError):
            pass
    for key in ('fullscreen', 'show_fps'):
        if isinstance(value.get(key), bool):
            result[key] = value[key]
    try:
        result['ui_scale'] = parse_ui_scale(value.get('ui_scale', 'auto'))
    except ValueError:
        pass
    fps = value.get('fps')
    if isinstance(fps, int) and not isinstance(fps, bool) and fps in FRAME_CAPS:
        result['fps'] = fps
    for key, lower, upper in (('zoom', 1.0, 8.0), ('music_volume', 0.0, 1.0), ('effects_volume', 0.0, 1.0)):
        try:
            number = float(value.get(key, result[key]))
            if math.isfinite(number):
                result[key] = max(lower, min(upper, number))
        except (ValueError, TypeError, OverflowError):
            pass
    return result



def windows_workarea(pygame):
    """Return current-monitor physical work area and resizable window borders.

    The process is PerMonitorV2 aware, so Win32 RECTs are physical pixels. Before
    the first window exists, MonitorFromWindow selects the primary monitor.
    """
    if sys.platform != 'win32':
        return None
    try:
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                        ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        try:
            hwnd = pygame.display.get_wm_info().get('window', 0)
        except pygame.error:
            hwnd = 0
        monitor_from_window = user32.MonitorFromWindow
        monitor_from_window.argtypes = [wintypes.HWND, wintypes.DWORD]
        monitor_from_window.restype = wintypes.HANDLE
        monitor = monitor_from_window(hwnd, 2 if hwnd else 1)
        info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
        get_info = user32.GetMonitorInfoW
        get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        get_info.restype = wintypes.BOOL
        if not monitor or not get_info(monitor, ctypes.byref(info)):
            return None
        work = info.rcWork
        borders = (48, 80)
        try:
            get_dpi = user32.GetDpiForWindow
            get_dpi.argtypes = [wintypes.HWND]
            get_dpi.restype = wintypes.UINT
            if hwnd:
                dpi = get_dpi(hwnd)
            else:
                get_system_dpi = user32.GetDpiForSystem
                get_system_dpi.argtypes = []
                get_system_dpi.restype = wintypes.UINT
                dpi = get_system_dpi()
            adjust = user32.AdjustWindowRectExForDpi
            adjust.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD,
                               wintypes.BOOL, wintypes.DWORD, wintypes.UINT]
            adjust.restype = wintypes.BOOL
            frame = wintypes.RECT(0, 0, 0, 0)
            if adjust(ctypes.byref(frame), 0x00CF0000, False, 0, dpi or 96):
                borders = frame.right - frame.left, frame.bottom - frame.top
        except (AttributeError, OSError):
            pass
        return ((work.left, work.top, work.right, work.bottom), borders)
    except (AttributeError, OSError, ValueError):
        return None


def effective_ui_scale(size, preference='auto') -> float:
    """Scale layout, never the final framebuffer; fit controls even on 720p."""
    width, height = size
    limit = min(width / MIN_LAYOUT[0], height / MIN_LAYOUT[1])
    if preference == 'auto':
        # 1080p=125%, 1440p=150%, 2160p=250%. Fonts render at native size.
        desired = max(1.0, math.floor(min(width / 1536, height / 864) * 4) / 4)
    else:
        desired = float(preference)
    return max(0.1, min(desired, limit))


class DisplayManager:
    """Own the actual desktop-pixel surface and restore windowed geometry.

    Methods that may change the drawable return the current ``surface``. The
    caller must update its drawing wrapper and UI after apply/resize/toggle.
    """
    def __init__(self, root: Path, args):
        import pygame
        self.pygame = pygame
        self.root = Path(root)
        explicit = getattr(args, 'settings', None)
        self.settings_path = Path(explicit).expanduser() if explicit else settings_path()
        self.save_enabled = bool(explicit) or not (getattr(args, 'demo', False) or getattr(args, 'frames', 0))
        self.warning = ''
        loaded = {}
        # Preview runs are reproducible and do not inherit a player's settings.
        if self.save_enabled:
            try:
                loaded = json.loads(self.settings_path.read_text(encoding='utf-8'))
            except FileNotFoundError:
                pass
            except (OSError, ValueError, UnicodeError):
                self.warning = 'Display settings could not be read; safe defaults were loaded.'
        self.settings = validate_settings(loaded)
        # On a first real launch, size the window for the current desktop. Preview
        # runs remain deterministic and explicit/saved dimensions take precedence.
        if (not isinstance(loaded, dict) or 'window_size' not in loaded) and not getattr(args, 'size', None):
            if not (getattr(args, 'demo', False) or getattr(args, 'frames', 0)) and pygame.display.get_driver() != 'dummy':
                desktop = pygame.display.get_desktop_sizes()[0]
                self.settings['window_size'] = [
                    max(MIN_WINDOW[0], min(desktop[0] - 48, round(desktop[0] * 0.8))),
                    max(MIN_WINDOW[1], min(desktop[1] - 80, round(desktop[1] * 0.8))),
                ]
        overrides = {}
        for name in ('ui_scale', 'zoom', 'fps'):
            value = getattr(args, name, None)
            if value is not None:
                overrides[name] = value
        size = getattr(args, 'size', None)
        if size:
            overrides['window_size'] = parse_size(size) if isinstance(size, str) else size
        if getattr(args, 'fullscreen', False):
            overrides['fullscreen'] = True
        self.settings = validate_settings({**self.settings, **overrides})
        if not size and pygame.display.get_driver() != 'dummy':
            self.settings['window_size'] = list(self._fit_window_size(self.window_size))
        self._window = None
        self._window_position = None
        self._fullscreen = False
        self.surface = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        pygame.display.set_caption('Digimon Venom NXT')
        self._bind_window()
        if self.settings['fullscreen']:
            self._set_fullscreen(True)

    def _bind_window(self):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', DeprecationWarning)
                self._window = self.pygame.Window.from_display_module()
            self._window.minimum_size = MIN_WINDOW
        except (AttributeError, self.pygame.error):
            self._window = None

    @property
    def fullscreen(self) -> bool:
        return self._fullscreen

    @property
    def window_size(self) -> tuple[int, int]:
        return tuple(self.settings['window_size'])

    @property
    def maximum_window_size(self) -> tuple[int, int]:
        native = windows_workarea(self.pygame)
        if native is not None:
            (left, top, right, bottom), (border_w, border_h) = native
            return max(MIN_WINDOW[0], right - left - border_w), max(MIN_WINDOW[1], bottom - top - border_h)
        desktop = self.pygame.display.get_desktop_sizes()[0]
        return max(MIN_WINDOW[0], desktop[0] - 48), max(MIN_WINDOW[1], desktop[1] - 80)

    def _fit_window_size(self, size):
        if self.pygame.display.get_driver() == 'dummy':
            return tuple(size)
        maximum = self.maximum_window_size
        return tuple(min(maximum[i], max(MIN_WINDOW[i], int(size[i]))) for i in range(2))

    def _keep_window_visible(self):
        # Increasing a centered window can otherwise leave its right/bottom edge
        # off-screen even when its new client dimensions fit the work area.
        if self._window is None or self._fullscreen or self.pygame.display.get_driver() == 'dummy':
            return
        native = windows_workarea(self.pygame)
        if native is not None:
            (left, top, right, bottom), (border_w, border_h) = native
        else:
            right, bottom = self.pygame.display.get_desktop_sizes()[0]
            left = top = 0
            border_w, border_h = 48, 80
        width, height = self.surface.get_size()
        x, y = self._window.position
        self._window.position = (max(left, min(x, right - width - border_w)),
                                 max(top, min(y, bottom - height - border_h)))

    @property
    def ui_scale(self) -> float:
        return effective_ui_scale(self.surface.get_size(), self.settings['ui_scale'])

    def _set_fullscreen(self, enabled: bool):
        if enabled == self._fullscreen:
            return self.surface
        previous_size = self.window_size
        try:
            if self._window is not None:
                if enabled:
                    self.settings['window_size'] = list(self.surface.get_size())
                    self._window_position = self._window.position
                    # SDL_FULLSCREEN_DESKTOP keeps the monitor's native mode.
                    self._window.set_fullscreen(desktop=True)
                else:
                    self._window.set_windowed()
                    self._window.size = self.window_size
                    if self._window_position is not None:
                        self._window.position = self._window_position
                self.surface = self.pygame.display.get_surface()
            else:
                if enabled:
                    self.settings['window_size'] = list(self.surface.get_size())
                    desktop = self.pygame.display.get_desktop_sizes()[0]
                    self.surface = self.pygame.display.set_mode(desktop, self.pygame.NOFRAME)
                else:
                    self.surface = self.pygame.display.set_mode(self.window_size, self.pygame.RESIZABLE)
                self._bind_window()
            self._fullscreen = enabled
            self.settings['fullscreen'] = enabled
        except self.pygame.error:
            self.settings['window_size'] = list(previous_size)
            self.settings['fullscreen'] = self._fullscreen
            self.warning = 'The requested display mode is unavailable on this monitor.'
        return self.surface

    def toggle_fullscreen(self):
        return self._set_fullscreen(not self._fullscreen)

    def resize(self, size):
        if self._fullscreen:
            self.surface = self.pygame.display.get_surface()
            return self.surface
        width = max(MIN_WINDOW[0], min(16384, int(size[0])))
        height = max(MIN_WINDOW[1], min(16384, int(size[1])))
        actual = width, height
        # SDL already updates ordinary resize events; avoid recreating its window.
        if self.pygame.display.get_surface().get_size() != actual:
            if self._window is not None:
                self._window.size = actual
                self.surface = self.pygame.display.get_surface()
            else:
                self.surface = self.pygame.display.set_mode(actual, self.pygame.RESIZABLE)
                self._bind_window()
        else:
            self.surface = self.pygame.display.get_surface()
        self.settings['window_size'] = list(actual)
        return self.surface

    def apply(self, **changes):
        previous_size = self.window_size
        checked = validate_settings({**self.settings, **changes})
        if 'window_size' in changes:
            checked['window_size'] = list(self._fit_window_size(checked['window_size']))
        requested_fullscreen = checked['fullscreen']
        self.settings = checked
        if requested_fullscreen != self._fullscreen:
            self._set_fullscreen(requested_fullscreen)
        elif not self._fullscreen and self.window_size != previous_size:
            self.resize(self.window_size)
        if 'window_size' in changes:
            self._keep_window_visible()
        return self.surface

    def save(self) -> bool:
        if not self.save_enabled:
            return False
        temporary = None
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic replace prevents partial writes if a client is interrupted.
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.settings_path.parent,
                                             prefix='.display-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(validate_settings(self.settings), stream, indent=2, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.settings_path)
            return True
        except (OSError, ValueError):
            self.warning = 'Display settings could not be saved; current settings remain active.'
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
