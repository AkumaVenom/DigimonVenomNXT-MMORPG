"""Battle command decks with explicit current actor, targets and recipients."""
from __future__ import annotations

import pygame

from .varieties import name_color
from .render import draw
from .widgets import text, bar, WHITE, CYAN, LIME, RED, MUTED


class CombatMenu:
    def __init__(self, app):
        self.app = app

    def busy(self):
        return bool(self.app.action_pending or self.app.animations)

    def cast(self, index):
        app = self.app
        battle = app.state.get('battle')
        if not battle or self.busy():
            return
        actor = battle.get('actor', 0)
        party = app.state.get('party', [])
        if not 0 <= actor < len(party):
            return
        skills = party[actor].get('skills', [])
        enemies = battle.get('enemies', [])
        if (not 0 <= index < len(skills) or party[actor].get('sp', 0) < skills[index].get('sp', 0)
                or not 0 <= app.target < len(enemies) or enemies[app.target].get('hp', 0) <= 0):
            return
        app.close_menu()
        app.send('battle', action='skill', target=app.target, party_index=actor, skill_index=index)

    def use(self, item_id):
        app = self.app
        if (not app.state.get('battle') or self.busy() or not app.state.get('inventory', {}).get(item_id)
                or not app.state.get('party')):
            return
        app.close_menu()
        app.battle_action('item', item_id)

    def draw(self, rect, kind='skills'):
        app, rect = self.app, pygame.Rect(rect)
        battle = app.state.get('battle')
        if not battle:
            app.close_menu()
            return
        party = app.state.get('party', [])
        actor_index = battle.get('actor', 0)
        if not 0 <= actor_index < len(party):
            app.close_menu()
            return
        actor = party[actor_index]
        enemies = battle.get('enemies', [])
        if enemies and (not 0 <= app.target < len(enemies) or enemies[app.target].get('hp', 0) <= 0):
            app.target = next((index for index, enemy in enumerate(enemies) if enemy.get('hp', 0) > 0), 0)
        skills = kind == 'skills'
        theme = 'skills' if skills else 'battle'
        art, p = app.presentation, app.presentation.colors(theme)
        title = 'Make every move count.' if skills else 'A little recovery. A stronger team.'
        subtitle = ('Choose a skill and an enemy target. Skill points are spent when your command resolves.' if skills
                    else 'Choose a capsule and its recipient. Using an item spends the current battle turn.')
        body = art.shell(rect, theme, title, subtitle, 'VENOM NXT  /  BATTLE COMMAND', header_height=128)
        text(app.screen, app.assets, f"TURN {battle.get('turn', 0)}  /  {actor.get('name', 'Partner').upper()}",
             (body.x+1, body.y+10), 12, p['accent'], True, body.width-306)
        app.ui.button((body.right-284, body.y, 136, 34), 'Battle items' if skills else 'Skills',
                      lambda:self.switch('battle_items' if skills else 'skills'),
                      disabled=self.busy(), small=True, accent=p['accent'])
        app.ui.button((body.right-136, body.y, 136, 34), 'Battle  Esc', app.close_menu,
                      small=True, accent=p['accent'])
        side_width = min(312, max(270, int(body.width*.26)))
        side = pygame.Rect(body.right-side_width, body.y+48, side_width, body.height-48)
        area = pygame.Rect(body.x, body.y+48, side.x-body.x-18, body.height-48)
        if skills:
            self.skills(area, actor)
            self.actor_targets(side, actor, battle)
        else:
            self.items(area)
            self.recipients(side, party, actor)
        message = ('Waiting for the current battle action to finish.' if self.busy()
                   else 'Your live match is saved after every command. Close this screen to use Attack for 0 SP.'
                   if battle.get('season') or battle.get('kind') == 'season'
                   or (battle.get('kind') == 'story' and not battle.get('story_training'))
                   else 'Your server confirms every command. Close this screen to use Attack for 0 SP, or Flee.')
        text(app.screen, app.assets, message, (rect.x+25, rect.bottom-18), 10,
             p['muted'], max_width=rect.width-50)

    def switch(self, menu):
        self.app.menu, self.app.scroll = menu, 0
        self.app.ui.actions, self.app.ui.fields = [], []
        self.app.audio.cue('tab', now=self.app.now)

    def skills(self, rect, actor):
        app, art = self.app, self.app.presentation
        p = art.colors('skills')
        entries = list(enumerate(actor.get('skills', [])))
        columns = 2
        rows = max(1, min(3, (len(entries)+1)//2))
        page_size = rows*columns
        app.scroll = min(max(0, app.scroll), max(0, len(entries)-page_size))
        width, height = (rect.width-12)//2, (rect.height-12*(rows-1))//rows
        enemies = app.state['battle'].get('enemies', [])
        has_target = 0 <= app.target < len(enemies) and enemies[app.target].get('hp', 0) > 0
        for pos, (index, skill) in enumerate(entries[app.scroll:app.scroll+page_size]):
            card = pygame.Rect(rect.x+(pos%columns)*(width+12), rect.y+(pos//columns)*(height+12), width, height)
            art.card(card, 'skills')
            resource = str(skill.get('attribute', 'neutral')).lower()
            icon = {'neutral': 'physical', 'thunder': 'electric'}.get(resource, resource)
            if icon in ('fire', 'water', 'electric', 'wind', 'light', 'dark', 'physical'):
                art.image((card.x+17, card.y+18, 45, 45), 'assets/ui/extracted/attribute_'+icon+'.png')
            else:
                art.icon((card.x+17,card.y+18,45,45), 'radar', 'skills')
            text(app.screen, app.assets, skill.get('name', 'Skill'), (card.x+73, card.y+19),
                 18, WHITE, True, card.width-87)
            text(app.screen, app.assets, f"{resource.upper()}  /  {str(skill.get('kind', 'attack')).upper()}",
                 (card.x+73, card.y+47), 10, p['muted'], max_width=card.width-87)
            cost = skill.get('sp', 0)
            ready = actor.get('sp', 0) >= cost
            if card.height >= 170:
                text(app.screen, app.assets, f'{cost} SP', (card.x+18, card.y+87), 26,
                     CYAN if ready else RED, True)
                text(app.screen, app.assets, f"Available {actor.get('sp', 0)} / {actor.get('max_sp', 0)} SP",
                     (card.x+18, card.y+126), 11, p['muted'], max_width=card.width-36)
                if card.height >= 235:
                    bar(app.screen, pygame.Rect(card.x+18, card.y+157, card.width-36, 6),
                        actor.get('sp', 0), actor.get('max_sp', 1), CYAN)
                if card.height >= 330:
                    portrait = pygame.Rect(card.x+44, card.y+187, card.width-88, card.height-282)
                    center = (portrait.centerx, portrait.bottom-11)
                    draw.ellipse(app.screen, p['glow'], (portrait.x+17, center[1]-15, portrait.width-34, 29))
                    draw.ellipse(app.screen, p['line'], (portrait.x+5, center[1]-21, portrait.width-10, 42), 1)
                    art.sprite(portrait, actor.get('species_id'), motion='attack', now=app.now)
                    power = skill.get('power')
                    caption = f'POWER {power:g}×  /  {str(skill.get("kind", "attack")).upper()}' if isinstance(power, (float, int)) else 'PARTNER TECHNIQUE'
                    text(app.screen, app.assets, caption, (card.centerx, card.bottom-70),
                         10, p['muted'], max_width=card.width-36, center=True)
            else:
                text(app.screen, app.assets, f'{cost} SP', (card.x+18, card.bottom-37), 15,
                     CYAN if ready else RED, True, card.width-150)
            button_width = card.width-36 if card.height >= 170 else min(119, card.width-110)
            app.ui.button((card.right-18-button_width, card.bottom-45, button_width, 32),
                          'Use skill' if ready else 'Not enough SP', lambda i=index:self.cast(i),
                          primary=ready, disabled=bool(not ready or not has_target or self.busy()),
                          small=True, accent=p['accent'])
        if not entries:
            art.card(rect, 'skills')
            text(app.screen, app.assets, 'No skills available for this partner.',
                 (rect.centerx, rect.centery-18), 19, WHITE, True, rect.width-40, True)
            text(app.screen, app.assets, 'Return to battle to use Attack. It costs 0 SP.',
                 (rect.centerx, rect.centery+17), 13, p['muted'], max_width=rect.width-40, center=True)

    def actor_targets(self, rect, actor, battle):
        app, art = self.app, self.app.presentation
        p = art.colors('skills')
        art.card(rect, 'skills', accent=True)
        text(app.screen, app.assets, 'CURRENT ACTOR', (rect.x+16, rect.y+14), 10, p['accent'], True)
        art.sprite((rect.x+18, rect.y+43, 87, 89), actor.get('species_id'), now=app.now)
        text(app.screen, app.assets, actor.get('name', 'Partner'), (rect.x+114, rect.y+47), 17,
             name_color(actor, app.assets.species, WHITE), True, rect.width-130)
        text(app.screen, app.assets, f"Lv.{actor.get('level', 1)}  ·  Slot {battle.get('actor', 0)+1}",
             (rect.x+114, rect.y+76), 11, p['muted'], max_width=rect.width-130)
        text(app.screen, app.assets, f"SP {actor.get('sp', 0)} / {actor.get('max_sp', 0)}",
             (rect.x+114, rect.y+103), 12, CYAN, True, rect.width-130)
        bar(app.screen, pygame.Rect(rect.x+16, rect.y+148, rect.width-32, 6),
            actor.get('sp', 0), actor.get('max_sp', 1), CYAN)
        text(app.screen, app.assets, 'SELECT ENEMY TARGET', (rect.x+16, rect.y+174), 10, p['accent'], True)
        enemies = battle.get('enemies', [])
        if enemies and (not 0 <= app.target < len(enemies) or enemies[app.target].get('hp', 0) <= 0):
            app.target = next((index for index, enemy in enumerate(enemies) if enemy.get('hp', 0) > 0), 0)
        height = min(79, max(58, (rect.height-209)//max(1, len(enemies))))
        for index, enemy in enumerate(enemies):
            card = pygame.Rect(rect.x+13, rect.y+199+index*height, rect.width-26, height-7)
            alive = enemy.get('hp', 0) > 0
            art.card(card, 'skills', selected=index == app.target and alive)
            art.sprite((card.x+8, card.y+7, 43, card.height-14), enemy.get('species_id'), now=app.now)
            text(app.screen, app.assets, enemy.get('name', 'Enemy'), (card.x+58, card.y+9),
                 13, name_color(enemy, app.assets.species, WHITE) if alive else MUTED, True, card.width-69)
            text(app.screen, app.assets, 'TARGETED' if index == app.target and alive else 'DEFEATED' if not alive else f"Lv.{enemy.get('level', 1)}",
                 (card.x+58, card.y+30), 9, p['accent'] if alive else MUTED, max_width=card.width-69)
            bar(app.screen, pygame.Rect(card.x+58, card.bottom-10, card.width-70, 4),
                enemy.get('hp', 0), enemy.get('max_hp', 1), RED)
            if alive and not self.busy():
                app.ui.actions.append((card, lambda i=index:setattr(app, 'target', i)))

    def items(self, rect):
        app, art = self.app, self.app.presentation
        p = art.colors('battle')
        entries = [(item_id, item) for item_id, item in app.shop_data().items()
                   if item.get('category') != 'digimeat']
        columns, rows, gap = 3, 2, 12
        page_size = columns*rows
        app.scroll = min(max(0, app.scroll), max(0, len(entries)-page_size))
        width, height = (rect.width-2*gap)//3, (rect.height-gap)//2
        for index, (item_id, item) in enumerate(entries[app.scroll:app.scroll+page_size]):
            card = pygame.Rect(rect.x+(index%3)*(width+gap), rect.y+(index//3)*(height+gap), width, height)
            art.card(card, 'battle')
            resource = item.get('resource', 'hp')
            color = (247,151,185) if resource == 'hp' else CYAN
            quality = {'s':1, 'm':2, 'l':3}.get(item_id.rsplit('_', 1)[-1], 1)
            band = min(93, max(60, card.height-122))
            art.capsule((card.x+12, card.y+9, 60, band), resource, quality, 'battle')
            count = app.state.get('inventory', {}).get(item_id, 0)
            text(app.screen, app.assets, f"{resource.upper()} · {item_id.rsplit('_', 1)[-1].upper()}",
                 (card.x+80, card.y+20), 21, color, True, card.width-91)
            text(app.screen, app.assets, f'OWNED {count}', (card.x+81, card.y+54), 10,
                 p['muted'], True, card.width-91)
            text(app.screen, app.assets, item.get('name', item_id), (card.x+14, card.y+band+16),
                 15, WHITE, True, card.width-28)
            text(app.screen, app.assets, f"Restore {item.get('amount', 0):,} {resource.upper()}",
                 (card.x+14, card.y+band+42), 11, color, max_width=card.width-28)
            app.ui.button((card.x+13, card.bottom-44, card.width-26, 32), 'Use capsule' if count else 'None owned',
                          lambda key=item_id:self.use(key), primary=bool(count),
                          disabled=bool(not count or self.busy() or not app.state.get('party')),
                          small=True, accent=p['accent'])

    def recipients(self, rect, party, actor):
        app, art = self.app, self.app.presentation
        p = art.colors('battle')
        art.card(rect, 'battle', accent=True)
        text(app.screen, app.assets, 'SELECT A RECIPIENT', (rect.x+16, rect.y+15), 11, p['accent'], True)
        text(app.screen, app.assets, f"{actor.get('name', 'Your partner')}'s turn", (rect.x+16, rect.y+39),
             11, p['muted'], max_width=rect.width-32)
        app.selected_party = min(max(0, app.selected_party), max(0, len(party)-1))
        height = min(74, (rect.height-75)//6)
        for index, mon in enumerate(party[:6]):
            card = pygame.Rect(rect.x+12, rect.y+64+index*height, rect.width-24, height-6)
            art.card(card, 'battle', selected=app.selected_party == index)
            art.sprite((card.x+6, card.y+5, 43, card.height-11), mon.get('species_id'), now=app.now)
            text(app.screen, app.assets, f"{index+1}  {mon.get('name', 'Partner')}", (card.x+57, card.y+7),
                 12, name_color(mon, app.assets.species, WHITE), True, card.width-69)
            text(app.screen, app.assets, f"HP {mon.get('hp', 0)}/{mon.get('max_hp', 0)}  ·  SP {mon.get('sp', 0)}/{mon.get('max_sp', 0)}",
                 (card.x+57, card.y+28), 9, p['muted'], max_width=card.width-69)
            bar(app.screen, pygame.Rect(card.x+57, card.bottom-8, card.width-70, 3),
                mon.get('hp', 0), mon.get('max_hp', 1), LIME)
            if not self.busy():
                app.ui.actions.append((card, lambda i=index:setattr(app, 'selected_party', i)))
