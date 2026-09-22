"""python -m venom.client.main"""
from __future__ import annotations
import argparse
import os


def main():
    from .display import configure_windows_dpi, parse_size, parse_ui_scale, FRAME_CAPS
    configure_windows_dpi()
    parser = argparse.ArgumentParser(description='Digimon Venom NXT native desktop client')
    parser.add_argument('--dev', action='store_true', help='Connect to localhost without TLS for local development only')
    parser.add_argument('--config', help='Client configuration JSON path')
    parser.add_argument('--demo', action='store_true', help='Clearly marked, offline visual preview; no account progress')
    parser.add_argument('--demo-battle', action='store_true', help='Preview a battle layout with --demo')
    parser.add_argument('--screenshot', help='Write a PNG screenshot on exit')
    parser.add_argument('--frames', type=int, default=0, help='Exit after this many frames (for automated visual checks)')
    parser.add_argument('--size', type=parse_size, help='Window size in native pixels, e.g. 1920x1080 or 3840x2160')
    parser.add_argument('--ui-scale', type=parse_ui_scale, help='Native UI scale: auto, a factor such as 1.5, or 150%%')
    parser.add_argument('--fullscreen', action='store_true', help='Start in borderless fullscreen at the current desktop resolution; F11 toggles')
    parser.add_argument('--settings', help='Optional display-preferences JSON path; never contains account credentials')
    parser.add_argument('--zoom', type=float, help='World camera zoom from full-map 1x to close-up 8x')
    parser.add_argument('--fps', type=int, choices=FRAME_CAPS, help='Frame cap (default: 120)')
    args = parser.parse_args()
    if args.zoom is not None and not 1 <= args.zoom <= 8:
        parser.error('--zoom must be between 1 and 8')
    from venom.common.paths import root_path
    root = root_path()
    os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
    from .app import App
    App(root,args).run()


if __name__ == '__main__':
    main()
