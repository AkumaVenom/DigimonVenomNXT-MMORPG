"""Render World DS story previews using a fresh, in-memory GameEngine character.

No account database, saves, network connection, or gameplay rewards are changed.
The locked atlas/Crests/finale are shown exactly as a new character receives them.
Usage: python -m tools.preview_world_ds_story --size 1280x800
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from venom.client.app import App
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas
from venom.common.game import GameEngine
from venom.common import story


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', default='1280x800')
    parser.add_argument('--output', type=Path, default=Path('docs/previews/world_ds_story'))
    options = parser.parse_args()
    size = tuple(int(value) for value in options.size.lower().split('x'))
    if len(size) != 2 or min(size) <= 0:
        parser.error('Use a positive WIDTHxHEIGHT.')
    root = Path(__file__).resolve().parents[1]
    options.output.mkdir(parents=True, exist_ok=True)
    args = SimpleNamespace(demo=True, demo_battle=False, dev=False, config=None,
                           size='1280x800', frames=0, screenshot=None, ui_scale='auto', show_fps=False)
    app = App(root, args)
    try:
        app.screen = NativeCanvas(pygame.display.set_mode(size),effective_ui_scale(size,'auto'))
        app.ui.screen = app.screen
        engine = GameEngine(root, seed=6110)
        app.state = engine.new_player('StoryPreview',app.tamer,app.starter)
        app.now = 5.0
        app.animations, app.toasts = [], []
        app.menu = 'story'

        def capture(name):
            app.reset_scene_position()
            app.draw()
            pygame.image.save(app.screen.surface,options.output / (name+'.png'))

        capture('01_campaign_chooser')
        engine.handle(app.state,'story',dict(action='enter',campaign_id=story.DS_CAMPAIGN))
        app.story_screen.tab = 'quest'
        capture('02_hub_journal')
        app.story_screen.tab, app.story_screen.page = 'atlas',1
        capture('03_atlas_second_page')
        app.story_screen.tab, app.story_screen.page = 'badges',1
        capture('04_crests_second_page')
        app.story_screen.tab, app.story_screen.page = 'league',0
        capture('05_convergence')
        engine.handle(app.state,'story',dict(action='travel',chapter=1))
        quest = next(npc for npc in app.state['story']['view']['npcs'] if npc['role']=='quest')
        # The authored arrival is already within the quest giver's talk radius.
        engine.handle(app.state,'story',dict(action='talk',npc_id=quest['id']))
        app.menu = None
        capture('06_quest_dialogue')
        print(f'Rendered six fresh-character previews to {options.output.resolve()}')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
