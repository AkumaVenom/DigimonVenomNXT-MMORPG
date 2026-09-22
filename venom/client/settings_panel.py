"""In-game display preferences; all controls share the native-resolution UI."""
import pygame
from .widgets import BG, PANEL, LINE, WHITE, MUTED, CYAN, LIME, GOLD, panel, text, bar


class SettingsPanel:
    def __init__(self, app):
        self.app = app
        self._overlay = None

    def change(self, **values):
        app = self.app
        app.apply_display(**values)

    def volume(self, kind, delta):
        current = self.app.display.settings[kind]
        self.change(**{kind: round(max(0., min(1., current+delta)), 2)})

    def draw(self):
        app, ui, assets = self.app, self.app.ui, self.app.assets
        screen = app.screen
        # This modal owns all pointer targets. Gameplay keeps receiving server updates.
        ui.actions, ui.fields = [], []
        if self._overlay is None or self._overlay.get_size() != screen.surface.get_size():
            self._overlay = pygame.Surface(screen.surface.get_size(), pygame.SRCALPHA)
            self._overlay.fill((3, 8, 17, 224))
        screen.blit_native(self._overlay, (0, 0))
        w, h = screen.get_size()
        rect = pygame.Rect((w-880)//2, (h-704)//2, 880, 704)
        panel(screen, rect, PANEL, LINE, 20)
        x, y = rect.x+28, rect.y+22
        text(screen, assets, 'SETTINGS', (x, y), 12, CYAN, True)
        text(screen, assets, 'Make it feel like your world.', (x, y+23), 27, WHITE, True)
        ui.button((rect.right-104, y+5, 76, 34), 'Done', app.toggle_settings, small=True)
        text(screen, assets, 'Changes apply immediately and are saved on this computer.', (x, y+65), 13, MUTED)
        sx = x+183
        settings = app.display.settings

        def heading(label, offset):
            text(screen, assets, label, (x, y+offset+10), 14, WHITE, True)

        def choices(offset, options, key, width=98):
            for index, (value, label) in enumerate(options):
                ui.button((sx+index*(width+7), y+offset, width, 35), label,
                          lambda v=value, k=key: self.change(**{k:v}),
                          selected=settings.get(key)==value, small=True)

        heading('Display mode', 108)
        choices(108, [(False, 'Windowed'), (True, 'Fullscreen · F11')], 'fullscreen', 166)
        heading('Window size', 156)
        for i, size in enumerate(((1280,800), (1920,1080), (2560,1440), (3840,2160))):
            ui.button((sx+i*151, y+156, 144, 35), f'{size[0]} × {size[1]}',
                      lambda s=size:self.change(window_size=list(s)), small=True,
                      selected=tuple(app.display.window_size)==size,
                      disabled=app.display.fullscreen)
        heading('Interface size', 204)
        choices(204, [('auto','Auto'), (1.,'100%'), (1.25,'125%'), (1.5,'150%'),
                      (1.75,'175%'), (2.,'200%'), (2.5,'250%'), (3.,'300%')], 'ui_scale', 69)
        text(screen, assets, 'Automatically fits the interface to your window. Map zoom is independent.',
             (sx, y+245), 11, MUTED, max_width=615)
        heading('Frame limit', 275)
        choices(275, [(60,'60'),(120,'120'),(144,'144'),(165,'165'),(240,'240')], 'fps', 73)
        ui.button((sx+411, y+275, 186, 35), 'FPS counter: '+('On' if settings.get('show_fps') else 'Off'),
                  lambda:self.change(show_fps=not settings.get('show_fps',False)),
                  selected=settings.get('show_fps',False), small=True)

        heading('World zoom', 341)
        ui.button((sx, y+341, 40, 35), '−', lambda:app.change_zoom(-.5), disabled=app.world.zoom<=1)
        text(screen, assets, f'{app.world.zoom:g}×', (sx+90, y+358), 19, LIME, True, center=True)
        ui.button((sx+137, y+341, 40, 35), '+', lambda:app.change_zoom(.5), disabled=app.world.zoom>=8)
        ui.button((sx+192, y+341, 116, 35), 'Fit level · 1×', lambda:app.set_zoom(1), small=True)
        text(screen, assets, 'Up to 8× · + / − keys · Mouse wheel over the field', (sx+323, y+351), 11, MUTED, max_width=295)
        text(screen, assets, 'Nearest-pixel artwork • Native-resolution text • No stretched widescreen maps',
             (sx, y+382), 11, CYAN, max_width=615)

        for offset, key, label in ((420, 'music_volume', 'Music volume'), (472, 'effects_volume', 'Effects volume')):
            heading(label, offset)
            ui.button((sx,y+offset,40,35), '−', lambda k=key:self.volume(k,-.05))
            bar(screen, pygame.Rect(sx+57,y+offset+14,344,7), settings[key], 1, CYAN)
            text(screen, assets, f'{round(settings[key]*100)}%', (sx+449,y+offset+17), 15, WHITE, center=True)
            ui.button((sx+491,y+offset,40,35), '+', lambda k=key:self.volume(k,.05))
        pw, ph = app.display.surface.get_size()
        text(screen, assets, f'{pw} × {ph} native pixels  /  {app.display.ui_scale*100:.0f}% effective UI  /  {settings["fps"]} FPS limit',
             (x, rect.bottom-83), 13, CYAN, True, max_width=rect.width-56)
        text(screen, assets, 'Fullscreen uses your current desktop resolution. Esc closes settings; Alt + Enter also toggles fullscreen.',
             (x, rect.bottom-55), 12, MUTED, max_width=rect.width-56)
        if app.display.warning:
            text(screen, assets, app.display.warning, (x, rect.bottom-31), 11, GOLD, max_width=rect.width-56)
