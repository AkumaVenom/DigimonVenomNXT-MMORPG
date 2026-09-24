"""Display, audio and camera preferences in the shared native UI language."""
import pygame
from .render import draw
from .widgets import WHITE, LIME, GOLD, text, bar


class SettingsPanel:
    def __init__(self, app):
        self.app = app
        self._overlay = None

    def change(self, **values):
        self.app.apply_display(**values)

    def volume(self, kind, delta):
        current = self.app.display.settings[kind]
        self.change(**{kind: round(max(0., min(1., current+delta)), 2)})

    def draw(self):
        app, ui, assets, art = self.app, self.app.ui, self.app.assets, self.app.presentation
        screen, settings = app.screen, app.display.settings
        # All pointer targets belong to this modal; live world updates continue.
        ui.actions, ui.fields = [], []
        if self._overlay is None or self._overlay.get_size() != screen.surface.get_size():
            self._overlay = pygame.Surface(screen.surface.get_size(), pygame.SRCALPHA)
            self._overlay.fill((3, 8, 17, 238))
        screen.blit_native(self._overlay, (0, 0))
        w, h = screen.get_size()
        width, height = min(1120, w-64), min(742, h-54)
        rect = pygame.Rect((w-width)//2, (h-height)//2, width, height)
        p = art.colors('settings')
        body = art.shell(rect, 'settings', 'Make it feel like your world.',
                         'Changes apply immediately and are saved on this computer.',
                         'VENOM NXT  /  SETTINGS', header_height=128)

        def button(rect, label, callback, **kwargs):
            ui.button(rect, label, callback, accent=p['accent'], **kwargs)

        button((rect.right-116, rect.y+36, 82, 34), 'Done', app.toggle_settings, small=True)
        gap = 16
        left_width = int((body.width-gap)*.66)
        cards_h = body.height-81
        display_card = pygame.Rect(body.x, body.y, left_width, cards_h)
        right_width = body.width-left_width-gap
        audio_card = pygame.Rect(display_card.right+gap, body.y, right_width, 231)
        camera_card = pygame.Rect(audio_card.x, audio_card.bottom+14, right_width, cards_h-245)
        for area, label, number in ((display_card, 'Display & performance', '01'),
                                    (audio_card, 'Sound & atmosphere', '02'),
                                    (camera_card, 'World camera', '03')):
            art.card(area, 'settings', accent=True)
            text(screen, assets, number, (area.x+17, area.y+17), 10, p['accent'], True)
            text(screen, assets, label, (area.x+47, area.y+13), 19, WHITE, True, area.width-64)
            draw.line(screen, p['line'], (area.x+17, area.y+46), (area.right-17, area.y+46))

        x, y, available = display_card.x+18, display_card.y+60, display_card.width-36

        def label(value, top):
            text(screen, assets, value.upper(), (x, top), 10, p['muted'], True)

        def choices(top, options, key, width=None):
            width = width or (available-6*(len(options)-1))//len(options)
            for index, (value, title) in enumerate(options):
                button((x+index*(width+6), top, width, 33), title,
                       lambda v=value, k=key: self.change(**{k:v}),
                       selected=settings.get(key) == value, small=True)

        label('Display mode', y)
        choices(y+20, [(False, 'Windowed'), (True, 'Fullscreen · F11')], 'fullscreen', 178)
        label('Window size', y+75)
        size_width = (available-18)//4
        for index, size in enumerate(((1280, 800), (1920, 1080), (2560, 1440), (3840, 2160))):
            button((x+index*(size_width+6), y+95, size_width, 33), f'{size[0]} × {size[1]}',
                   lambda value=size: self.change(window_size=list(value)), small=True,
                   selected=tuple(app.display.window_size) == size, disabled=app.display.fullscreen)
        label('Interface size', y+150)
        choices(y+170, [('auto', 'Auto'), (1., '100%'), (1.25, '125%'), (1.5, '150%'),
                        (1.75, '175%'), (2., '200%'), (2.5, '250%'), (3., '300%')], 'ui_scale')
        text(screen, assets, 'Auto fits the interface to your window. World zoom stays independent.',
             (x, y+215), 11, p['muted'], max_width=available)
        label('Frame limit', y+256)
        fps_width = (available-184-30)//5
        choices(y+276, [(60, '60'), (120, '120'), (144, '144'), (165, '165'), (240, '240')], 'fps', fps_width)
        button((x+5*(fps_width+6), y+276, 184, 33), 'FPS counter: '+('On' if settings.get('show_fps') else 'Off'),
               lambda: self.change(show_fps=not settings.get('show_fps', False)),
               selected=settings.get('show_fps', False), small=True)
        draw.line(screen, p['line'], (x, display_card.bottom-57), (display_card.right-18, display_card.bottom-57))
        text(screen, assets, 'NATIVE PIXELS. CRISP PARTNERS.', (x, display_card.bottom-42), 10, p['accent'], True, available)
        text(screen, assets, 'Nearest-pixel artwork · Native-resolution text', (x, display_card.bottom-23), 10, p['muted'], max_width=available)

        for offset, key, label_text in ((65, 'music_volume', 'Music volume'), (139, 'effects_volume', 'Effects volume')):
            ax, ay, aw = audio_card.x+18, audio_card.y+offset, audio_card.width-36
            text(screen, assets, label_text.upper(), (ax, ay), 10, p['muted'], True)
            text(screen, assets, f'{round(settings[key]*100)}%', (audio_card.right-40, ay+6), 13,
                 p['accent'], True, center=True)
            button((ax, ay+25, 31, 30), '−', lambda k=key: self.volume(k, -.05))
            button((ax+aw-31, ay+25, 31, 30), '+', lambda k=key: self.volume(k, .05))
            bar(screen, pygame.Rect(ax+45, ay+36, aw-90, 7), settings[key], 1, p['accent'])

        cx, cy, cw = camera_card.x+18, camera_card.y+62, camera_card.width-36
        at_farm = bool(app.state and app.state.get('in_farm'))
        zoom = app.farm_screen.zoom if at_farm else app.world.zoom
        text(screen, assets, 'DIGIFARM ZOOM' if at_farm else 'WORLD ZOOM', (cx, cy), 10, p['muted'], True)
        button((cx, cy+25, 37, 34), '−', lambda: app.change_zoom(-.5), disabled=zoom <= 1)
        text(screen, assets, f'{zoom:g}×', (cx+cw/2, cy+42), 24, LIME, True, center=True)
        button((cx+cw-37, cy+25, 37, 34), '+', lambda: app.change_zoom(.5), disabled=zoom >= 8)
        button((cx, cy+74, cw, 31), 'Fit level · 1×', lambda: app.set_zoom(1), small=True)
        text(screen, assets, 'Up to 8× · + / − keys · Mouse wheel', (cx, cy+116), 10, p['muted'], max_width=cw)
        text(screen, assets, 'No stretched widescreen maps', (cx, cy+134), 10, p['accent'], max_width=cw)

        native_width, native_height = app.display.surface.get_size()
        footer = body.bottom-64
        text(screen, assets, f'{native_width} × {native_height} native pixels  /  {app.display.ui_scale*100:.0f}% effective UI  /  {settings["fps"]} FPS limit',
             (body.x+2, footer), 12, p['accent'], True, body.width-4)
        text(screen, assets, 'Fullscreen uses your desktop resolution. Esc closes settings; Alt + Enter also toggles fullscreen.',
             (body.x+2, footer+23), 11, p['muted'], max_width=body.width-4)
        if app.display.warning:
            text(screen, assets, app.display.warning, (body.x+2, footer+43), 10, GOLD, max_width=body.width-4)
