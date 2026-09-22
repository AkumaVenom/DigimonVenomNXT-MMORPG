"""Rebuild the original native executable icon from the same vector window art."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
from PIL import Image
import pygame
from venom.client.icon import get_icon


def main():
    sizes = (16, 24, 32, 48, 64, 128, 256)
    frames = [Image.frombytes('RGBA', (size, size), pygame.image.tobytes(get_icon(size), 'RGBA')) for size in sizes]
    frames[-1].save(ROOT / 'tools/windows_client.ico', format='ICO', sizes=[(size, size) for size in sizes], append_images=frames[:-1])
    print('Wrote tools/windows_client.ico (16 through 256 pixels).')


if __name__ == '__main__':
    main()
