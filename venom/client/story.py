"""Private story campaigns; the server owns dialogue, progression and rewards."""
from __future__ import annotations
import math
import pygame
from .render import draw
from .widgets import text, wrap, panel, WHITE, MUTED, GOLD

ACCENT = (115, 230, 224)
BADGE_COLORS = ((106,232,177),(112,210,250),(255,183,102),(177,146,255),
                (243,135,174),(247,218,115),(109,170,255),(228,237,250))


class StoryScreen:
    TABS = (('quest','Journey'),('atlas','Region atlas'),('badges','DigiBadges'),('league','Championship'))

    def __init__(self, app):
        self.app = app
        self.reset()

    def reset(self):
        self.tab, self.page, self.result = 'quest', 0, None
        self.pending_journal = False
        self.npc_page = 0

    @property
    def data(self):
        return ((self.app.state or {}).get('story') or {}).get('view') or {}

    @property
    def active(self):
        return bool((self.app.state or {}).get('in_story'))

    @property
    def dialogue(self):
        return self.data.get('dialogue') if self.active else None

    @property
    def modal(self):
        return bool((self.dialogue or self.result) and not (self.app.state or {}).get('battle'))

    @property
    def badge_count(self):
        return self.data.get('badge_count', sum(bool(row.get('earned')) for row in self.data.get('badges', [])))

    @property
    def paradox(self):
        return self.data.get('campaign_id', ((self.app.state or {}).get('story') or {}).get('campaign_id')) == 'world_ds_paradox'

    @property
    def title(self):
        return 'PARADOX CHRONICLE' if self.paradox else 'DAWN RELAY'

    @property
    def badge_total(self):
        return int(self.data.get('badge_total', 17 if self.paradox else 8))

    @property
    def tabs(self):
        return (('quest','Journey'),('atlas','World DS atlas'),('badges','Paradox Crests'),('league','Convergence')) if self.paradox else self.TABS

    def toggle(self):
        app = self.app
        if not app.state or app.action_pending:
            return
        if app.in_jail():
            app.toast('Activities are paused while you are detained.', GOLD)
        elif app.state.get('in_season'):
            app.toast('Save & Return to World before starting your story.')
        elif app.state.get('battle'):
            app.toast('Complete this battle first. Exit saves your exact progress.', GOLD)
        elif self.active:
            self.command('return')
        else:
            app.set_menu('story')

    def journal(self, tab=None):
        if self.app.action_pending or self.app.state.get('battle') or self.modal:
            return
        if tab:
            self.tab, self.page = tab, 0
        self.app.set_menu('story')

    def command(self, action, **payload):
        if not self.app.action_pending:
            self.app.send('story', action=action, **payload)

    def choose(self, choice):
        if self.result and choice == 'leave':
            self.dismiss_result()
            return
        dialogue = self.dialogue or {}
        if choice in {entry.get('id') for entry in dialogue.get('choices', [])}:
            self.command('dialogue', token=dialogue.get('token'), choice=choice)

    def advance_dialogue(self):
        if self.result:
            if self.app.now >= self.app.battle_until:
                self.dismiss_result()
            return
        choices = (self.dialogue or {}).get('choices', [])
        if any(row.get('id') == 'next' for row in choices):
            self.choose('next')
        elif len(choices) == 1:
            self.choose(choices[0].get('id'))

    def talk(self, npc_id):
        if self.modal or self.app.menu or not self.active:
            return
        self.command('talk', npc_id=npc_id)

    def exit(self, exit_id):
        if self.modal or self.app.menu or not self.active:
            return
        self.command('exit', exit_id=exit_id)

    def interact(self):
        if self.modal:
            self.advance_dialogue()
            return
        nearby = getattr(self.app.world, 'nearest_story_interaction', None)
        if nearby is not None:
            found = nearby()
            if found:
                kind, row = found
                self.exit(row['id']) if kind == 'exit' else self.talk(row['id'])
            else:
                self.app.toast('Walk closer to a character or route gate, then press E.')
            return
        npcs = self.data.get('npcs', [])
        if not npcs:
            return
        here = self.app.position
        npc = min(npcs, key=lambda row:(float(row.get('x',0))-here.x)**2+(float(row.get('y',0))-here.y)**2)
        distance = math.hypot(float(npc.get('x',0))-here.x,float(npc.get('y',0))-here.y)
        if distance <= self.data.get('talk_radius',128):
            self.talk(npc['id'])
        else:
            self.app.toast('Walk closer to a story character, then press E to talk.')

    def confirmed(self, previous, state):
        previous = previous or {}
        if bool(previous.get('in_story')) != bool(state.get('in_story')):
            self.result, self.pending_journal = None, False
            self.app.menu = None
            self.app.ui.focus = None
            self.app.ui.actions, self.app.ui.fields = [], []
            pygame.key.stop_text_input()
            self.app.farm_screen.manager_open = self.app.farm_screen.home_confirmation = False
            self.app.partner_screen.pending_exchange = None
            self.app.battle_old = None
            self.app.animations.clear()
            self.app.audio.cue('story_enter' if state.get('in_story') else 'back',now=self.app.now)
        old = ((previous.get('story') or {}).get('view') or {})
        if old.get('dialogue') != self.data.get('dialogue'):
            self.app.ui.focus = None
            self.app.ui.actions, self.app.ui.fields = [], []
            if self.dialogue:
                self.app.menu = None
            elif self.pending_journal:
                self.pending_journal = False
                self.app.menu, self.tab = 'story', 'quest'
        old_battle = previous.get('battle') or {}
        if old_battle.get('kind') == 'story' and not old_battle.get('story_training') and not state.get('battle') and state.get('in_story'):
            recent = self.data.get('recent') or []
            if recent:
                self.result = dict(recent[0])
                self.result['narrative'] = next((event.get('text') for event in reversed(state.get('events',[])) if event.get('kind') == 'story_result'),'')
                old_ids = {row['id'] for row in old.get('badges',[]) if row.get('earned')}
                self.result['badge'] = next((row for row in self.data.get('badges',[]) if row.get('earned') and row['id'] not in old_ids),None)
                self.app.audio.cue('story_badge' if self.result.get('badge') else 'story_victory' if self.result.get('won') else 'back',now=self.app.now)

    def write(self,value,pos,size=14,color=WHITE,bold=False,width=None,center=False):
        return text(self.app.screen,self.app.assets,value,pos,size,color,bold,width,center)

    def card(self,rect,selected=False):
        self.app.presentation.card(rect,'story',selected=selected)

    def button(self,rect,label,action,**kwargs):
        self.app.ui.button(rect,label,action,small=True,accent=ACCENT,**kwargs)

    def select_tab(self,key):
        self.tab,self.page = key,0
        self.app.ui.actions,self.app.ui.fields = [],[]
        self.app.audio.cue('tab',now=self.app.now)

    def turn_page(self, page):
        self.page = max(0, page)
        self.app.ui.actions, self.app.ui.fields = [], []
        self.app.audio.cue('tab', now=self.app.now)

    def paged(self, rect, records, per_page, label):
        """Reserve navigation space before laying out cards, including the last page."""
        pages = max(1, math.ceil(len(records)/per_page))
        self.page = min(self.page, pages-1)
        content = pygame.Rect(rect)
        if pages > 1:
            content.height -= 43
            self.button((rect.x,rect.bottom-33,120,32),'Previous',lambda:self.turn_page(self.page-1),disabled=self.page==0)
            self.button((rect.right-120,rect.bottom-33,120,32),'Next',lambda:self.turn_page(self.page+1),disabled=self.page>=pages-1)
            start, end = self.page*per_page+1,min(len(records),(self.page+1)*per_page)
            self.write(f'{label} {start}–{end} of {len(records)}  ·  Page {self.page+1} / {pages}',
                       (rect.centerx,rect.bottom-17),11,MUTED,width=rect.width-270,center=True)
        return content, list(enumerate(records))[self.page*per_page:(self.page+1)*per_page]

    def npc_from_journal(self, npc):
        self.app.close_menu()
        if self.app.state.get('in_lab') or self.app.state.get('in_farm'):
            self.app.toast('Return to the story field to meet '+npc.get('name','this character')+'.')
            return
        distance = math.hypot(float(npc.get('x',0))-self.app.position.x,float(npc.get('y',0))-self.app.position.y)
        if distance <= self.data.get('talk_radius',128):
            self.talk(npc['id'])
        else:
            self.app.toast('Walk to '+npc.get('name','this character')+' and press E to talk.')

    def badge_color(self,index):
        badges = self.data.get('badges', [])
        value = badges[index].get('color') if 0 <= index < len(badges) else None
        try:
            return tuple(pygame.Color(value))[:3] if value else BADGE_COLORS[index%8]
        except (TypeError, ValueError):
            return BADGE_COLORS[index%8]

    def badge(self,center,index,earned,radius=30):
        color = self.badge_color(index) if earned else (66,88,106)
        points = [(center[0]+math.cos(i*math.tau/6-math.pi/2)*radius,
                   center[1]+math.sin(i*math.tau/6-math.pi/2)*radius) for i in range(6)]
        draw.polygon(self.app.screen,(17,42,54) if earned else (18,28,43),points)
        draw.polygon(self.app.screen,color,points,2)
        x,y,r = center[0],center[1],radius*.55
        def line(points,closed=False,width=2):
            draw.lines(self.app.screen,color,closed,[(x+px*r,y+py*r) for px,py in points],width)
        shape = index%8
        if shape == 0:
            line([(math.cos(i*math.pi/5-math.pi/2)*(1 if i%2==0 else .43),
                   math.sin(i*math.pi/5-math.pi/2)*(1 if i%2==0 else .43)) for i in range(10)],True)
        elif shape == 1:
            line([(-.7,.8),(-.85,-.1),(-.2,-.8),(.9,-.9),(.75,.2),(0,.75)],True)
            line([(-.75,.85),(.65,-.65)]);line([(-.3,.3),(-.45,-.35)]);line([(.05,-.05),(.65,.15)])
        elif shape == 2:
            for offset in (-.42,.25):
                line([(t/10,offset+math.sin(t/10*math.pi*1.3)*.2) for t in range(-10,11)])
        elif shape == 3:
            for offset in (-.45,0,.45):
                line([(-.9,offset),(0,offset-.28),(.9,offset),(0,offset+.28),(-.9,offset)])
        elif shape == 4:
            for offset in (-.5,0,.5):
                line([(offset-.16,-.85),(offset+.12,-.4),(offset-.12,.25),(offset+.16,.85)])
        elif shape == 5:
            line([(math.cos(i*math.tau/24)*(1 if i%4 in (0,1) else .74),
                   math.sin(i*math.tau/24)*(1 if i%4 in (0,1) else .74)) for i in range(24)],True)
            draw.circle(self.app.screen,color,(x,y),r*.37,2)
        elif shape == 6:
            line([(-.75,.3),(-.55,-.5),(-.15,-.15),(.15,-1),(.6,-.3),(.85,.4),(.4,.85),(-.35,.85)],True)
            line([(-.25,.55),(0,-.05),(.35,.55)])
        else:
            draw.circle(self.app.screen,color,(x,y),r*.86,2)
            draw.circle(self.app.screen,(17,42,54) if earned else (18,28,43),(x+r*.35,y-r*.28),r*.7)
            draw.arc(self.app.screen,color,(x-r*.37,y-r*.99,r*1.4,r*1.4),math.pi*.52,math.pi*1.48,2)

    def crown(self,center,radius=43):
        x,y = center
        points = [(x-radius,y-radius*.35),(x-radius*.6,y+radius*.55),(x+radius*.6,y+radius*.55),
                  (x+radius,y-radius*.35),(x+radius*.35,y),(x,y-radius*.75),(x-radius*.35,y)]
        draw.polygon(self.app.screen,(45,42,31),points)
        draw.polygon(self.app.screen,GOLD,points,2)
        draw.line(self.app.screen,GOLD,(x-radius*.56,y+radius*.72),(x+radius*.56,y+radius*.72),3)

    def draw(self,rect):
        rect = pygame.Rect(rect)
        if not self.active:
            self.draw_entry(rect)
            return
        data = self.data
        body = self.app.presentation.shell(rect,'story',self.title,
            f"{data.get('chapter_name','Your journey')}  /  {self.badge_count} of {self.badge_total} {'Paradox Crests' if self.paradox else 'DigiBadges'}",
            'WORLD DS  /  YOUR PRIVATE ADVENTURE' if self.paradox else 'STORY MODE  /  YOUR PRIVATE ADVENTURE',header_height=128)
        back_label = 'Back to DigiLab' if self.app.state.get('in_lab') else 'Back to DigiFarm' if self.app.state.get('in_farm') else 'Back to the field'
        self.button((rect.right-362,rect.y+67,140,32),back_label,self.app.close_menu)
        self.button((rect.right-211,rect.y+67,185,32),'Save & Return to MMO',lambda:self.command('return'),disabled=self.app.action_pending)
        width = (body.width-24)//4
        for i,(key,name) in enumerate(self.tabs):
            self.button((body.x+i*(width+8),body.y,width,34),name,lambda k=key:self.select_tab(k),selected=self.tab==key)
        content = pygame.Rect(body.x,body.y+47,body.width,body.height-55)
        getattr(self,'draw_'+self.tab)(content)
        self.write('AUTO-SAVED  /  Your own partners, bag and credits. DigiLab and DigiFarm stay available.',
                   (rect.x+25,rect.bottom-18),10,MUTED,width=rect.width-50)

    def draw_entry(self,rect):
        body = self.app.presentation.shell(rect,'story','CHOOSE YOUR STORY',
            'Two adventures. Your partners. Progress saved separately.','PRIVATE STORY MODES',header_height=128)
        self.button((rect.right-175,rect.y+66,148,34),'Back to the world',self.app.close_menu)
        profiles = dict((self.app.state or {}).get('story_campaigns') or {})
        active = (self.app.state or {}).get('story') or {}
        if active:
            profiles[active.get('campaign_id','dawn_relay')] = active
        width = (body.width-16)//2
        campaigns = (
            ('dawn_relay','DAWN RELAY','The championship awaits',
             'Explore the Dawn regions, meet their tamers and earn eight DigiBadges. Win the championship, then defend your crown.',
             '8 DigiBadges  ·  A living championship','DigiBadges',8),
            ('world_ds_paradox','WORLD DS','Paradox Chronicle',
             'Begin at a safe World DS hub. Restore 17 fields through quests, tamer duels and Paradox guardians. Gather every Crest to summon the final trio.',
             '18 maps  ·  Lv.10–100  ·  17 Paradox Crests','Paradox Crests',17))
        for i,(ident,kicker,title,description,detail,badge_name,total) in enumerate(campaigns):
            cell = pygame.Rect(body.x+i*(width+16),body.y,width,body.height-43)
            self.card(cell, i==1)
            self.write(kicker,(cell.x+25,cell.y+24),11,ACCENT,True)
            self.write(title,(cell.x+24,cell.y+51),26,WHITE,True,cell.width-48)
            self.write(detail,(cell.x+25,cell.y+98),12,GOLD,True,cell.width-50)
            wrap(self.app.screen,self.app.assets,description,(cell.x+25,cell.y+134),cell.width-50,17,MUTED,5)
            reward = 'Permanent +20% scan gain on wild Paradox wins' if i else 'A championship career with repeat title defenses'
            self.write('COMPLETION REWARD',(cell.x+25,cell.bottom-151),10,ACCENT,True)
            wrap(self.app.screen,self.app.assets,reward,(cell.x+25,cell.bottom-128),cell.width-50,14,WHITE,2)
            profile = profiles.get(ident) or {}
            earned = len(profile.get('badges') or [])
            self.write(f'{earned} / {total} {badge_name} collected' if profile else 'A new adventure is ready',
                       (cell.x+25,cell.bottom-83),11,MUTED,width=cell.width-50)
            label = ('Continue ' if profile else 'Begin ')+('Dawn Relay' if not i else 'Paradox Chronicle')
            self.button((cell.x+24,cell.bottom-57,cell.width-48,38),label,
                        lambda c=ident:self.command('enter',campaign_id=c),primary=True,disabled=self.app.action_pending)
        self.write('Shared partners, evolution, items, credits, DigiLab and DigiFarm. Choose either story whenever you return to the MMO.',
                   (body.centerx,body.bottom-17),11,MUTED,width=body.width-12,center=True)

    def draw_quest(self,rect):
        data,app = self.data,self.app
        side = min(300,int(rect.width*.29))
        main = pygame.Rect(rect.x,rect.y,rect.width-side-15,rect.height)
        self.card(main)
        self.write('CURRENT OBJECTIVE',(main.x+23,main.y+20),11,ACCENT,True)
        wrap(app.screen,app.assets,data.get('objective','Explore the region and speak to its tamers.'),
             (main.x+23,main.y+52),main.width-46,22,WHITE,3)
        self.write('CHARACTERS IN THIS AREA',(main.x+23,main.y+147),10,MUTED,True)
        npcs = data.get('npcs',[])
        npc_pages = max(1,math.ceil(len(npcs)/4))
        self.npc_page = min(self.npc_page,npc_pages-1)
        if npc_pages > 1:
            self.button((main.right-152,main.y+139,127,26),f'Characters {self.npc_page+1}/{npc_pages}',
                        lambda:setattr(self,'npc_page',(self.npc_page+1)%npc_pages))
        for i,npc in enumerate(npcs[self.npc_page*4:(self.npc_page+1)*4]):
            cell = pygame.Rect(main.x+18,main.y+175+i*61,main.width-36,54)
            panel(app.screen,cell,(15,33,47),(37,72,85),7)
            sprite = (app.assets.sprite(npc['display_species'],(43,48),now=app.now) if npc.get('display_species') else
                      app.assets.tamer(npc.get('tamer_id',npc.get('tamer','')),'down',False,app.now,(41,48)))
            if sprite:
                app.screen.blit(sprite,sprite.get_rect(center=(cell.x+29,cell.centery)))
            self.write(npc.get('name','Tamer'),(cell.x+61,cell.y+8),14,WHITE,True,cell.width-167)
            status = {'ready':'Quest available','active':'Quest in progress','turn_in':'Ready to report',
                      'complete':'Complete','cleared':'Cleared','locked':'Not ready yet','service':'Here to help'}.get(npc.get('status'),npc.get('status',npc.get('role','Story character')).replace('_',' ').title())
            self.write(status,(cell.x+61,cell.y+31),11,ACCENT,width=cell.width-167)
            near = not (app.state.get('in_lab') or app.state.get('in_farm')) and math.hypot(float(npc.get('x',0))-app.position.x,float(npc.get('y',0))-app.position.y)<=data.get('talk_radius',128)
            self.button((cell.right-89,cell.y+11,77,32),'Talk' if near else 'Find',
                        lambda n=npc:self.npc_from_journal(n),disabled=app.action_pending)
        self.write('E talks to nearby characters. Find returns you to their field.',
                   (main.x+23,main.bottom-26),11,MUTED,width=main.width-46)
        aside = pygame.Rect(main.right+15,rect.y,side,rect.height)
        self.card(aside)
        self.write('ADVENTURE KIT',(aside.x+20,aside.y+22),11,ACCENT,True)
        self.write(f"{app.state.get('credits',0):,} ¥",(aside.x+20,aside.y+56),28,GOLD,True)
        self.write('Your credits',(aside.x+20,aside.y+96),11,MUTED)
        actions = [('Partners & evolution  P',lambda:app.set_menu('party')),
                   ('Shop & bag  B',lambda:app.set_menu('shop')),('Recover your team',lambda:self.command('heal')),
                   ('DigiLab camp  F1',app.enter_lab),('DigiFarm  F2',app.enter_farm)]
        if data.get('training_available',not data.get('hub')):
            if app.state.get('in_lab') or app.state.get('in_farm'):
                actions.append(('Return to story field',lambda:self.command('field')))
            else:
                actions.append((f"Training battle · Lv.{data.get('training_level',5)}",lambda:self.command('train')))
        for i,(label,callback) in enumerate(actions):
            self.button((aside.x+17,aside.y+124+i*41,aside.width-34,34),label,callback,disabled=app.action_pending)
        hint = 'A safe hub with no battles. Prepare your team, then choose your first field in the atlas.' if data.get('hub') else 'Your normal team, inventory and services stay with you throughout the story.'
        wrap(app.screen,app.assets,hint,(aside.x+19,aside.bottom-65),aside.width-38,11,MUTED,3)

    def draw_atlas(self,rect):
        rect, chapters = self.paged(rect,self.data.get('chapters',[]),9,'Maps' if self.paradox else 'Regions')
        gap = 11
        width,height = (rect.width-gap*2)//3,(rect.height-gap*2)//3
        for slot,(i,chapter) in enumerate(chapters):
            cell = pygame.Rect(rect.x+(slot%3)*(width+gap),rect.y+(slot//3)*(height+gap),width,height)
            self.card(cell,chapter.get('index')==self.data.get('chapter'))
            unlocked = chapter.get('unlocked',False)
            self.write(f"{'✓' if chapter.get('complete') else str(i+1).zfill(2)}  {chapter.get('name','Region')}",
                       (cell.x+15,cell.y+12),15,ACCENT if unlocked else MUTED,True,cell.width-30)
            level = 'SAFE HUB · No battles' if chapter.get('hub') or self.paradox and i==0 else f"Recommended Lv.{chapter.get('level','?')}"
            self.write(f"{level}  ·  {'OPEN' if unlocked else 'LOCKED'}",
                       (cell.x+15,cell.y+39),10,MUTED,width=cell.width-30)
            maps = chapter.get('maps') or [{'id':chapter.get('map_id'),'name':'Travel to region','unlocked':unlocked}]
            for j,location in enumerate(maps[:2]):
                self.button((cell.x+13,cell.y+64+j*32,cell.width-26,27),
                            ('● ' if location.get('active') else '→ ')+location.get('name','Explore'),
                            lambda c=chapter,m=location:self.command('travel',chapter=c['index'],map_id=m['id']),
                            disabled=not unlocked or not location.get('unlocked',unlocked) or self.app.action_pending,
                            selected=bool(location.get('active')))
            if self.paradox:
                requirement = 'Services and story introduction' if i==0 else 'Crest secured' if chapter.get('complete') else 'Quest → Tamer → Paradox guardian'
                self.write(requirement,(cell.x+15,cell.bottom-20),10,ACCENT if chapter.get('complete') else MUTED,width=cell.width-30)

    def draw_badges(self,rect):
        badges,chapters = self.data.get('badges',[]),self.data.get('chapters',[])
        if self.paradox:
            grid, records = self.paged(rect,badges,9,'Crests')
            gap = 11
            width,height = (grid.width-gap*2)//3,(grid.height-gap*2)//3
            for slot,(i,record) in enumerate(records):
                won = bool(record.get('earned'))
                cell = pygame.Rect(grid.x+(slot%3)*(width+gap),grid.y+(slot//3)*(height+gap),width,height)
                self.card(cell,won)
                self.badge((cell.x+41,cell.y+49),i,won,27)
                self.write(f'CREST {i+1:02d}  /  '+('EARNED' if won else 'NOT YET EARNED'),
                           (cell.x+82,cell.y+16),10,self.badge_color(i) if won else MUTED,True,cell.width-94)
                wrap(self.app.screen,self.app.assets,record.get('name',f'Paradox Crest {i+1}'),
                     (cell.x+82,cell.y+40),cell.width-94,14,WHITE if won else MUTED,2)
                chapter_index = record.get('chapter',i+1)
                chapter = next((row for row in chapters if row.get('index')==chapter_index),{})
                self.write(chapter.get('name',record.get('map_name','World DS field')),
                           (cell.x+14,cell.bottom-35),11,MUTED,width=cell.width-28)
                self.write('Permanently collected' if won else 'Finish the local quest and defeat its guardian',
                           (cell.x+14,cell.bottom-18),9,ACCENT if won else MUTED,width=cell.width-28)
            return
        gap = 13
        width,height = (rect.width-3*gap)//4,(rect.height-gap)//2
        for i in range(8):
            record = badges[i] if i<len(badges) else {}
            won = bool(record.get('earned'))
            cell = pygame.Rect(rect.x+(i%4)*(width+gap),rect.y+(i//4)*(height+gap),width,height)
            self.card(cell,won)
            self.badge((cell.centerx,cell.y+61),i,won,37)
            self.write(record.get('name',f'DigiBadge {i+1}'),(cell.centerx,cell.y+124),16,
                       WHITE if won else MUTED,True,cell.width-20,True)
            self.write('EARNED' if won else 'AWAITING YOUR CHALLENGE',(cell.centerx,cell.y+157),
                       10,self.badge_color(i) if won else MUTED,True,cell.width-20,True)
            if i<len(chapters):
                self.write(chapters[i].get('name',''),(cell.centerx,cell.bottom-24),11,MUTED,width=cell.width-20,center=True)

    def draw_league(self,rect):
        if self.paradox:
            self.draw_convergence(rect)
            return
        data,app = self.data,self.app
        champ,stats = data.get('champion') or {},data.get('stats') or {}
        left = pygame.Rect(rect.x,rect.y,int(rect.width*.43),rect.height)
        self.card(left)
        self.write('DAWN CHAMPIONSHIP',(left.x+24,left.y+23),12,GOLD,True)
        self.crown((left.centerx,left.y+104),43)
        self.write(str(champ.get('holder') or 'The reigning champion'),(left.centerx,left.y+177),24,WHITE,True,left.width-44,True)
        self.write(str(champ.get('status') or 'Earn all 8 DigiBadges').replace('_',' ').title(),
                   (left.centerx,left.y+216),14,GOLD,True,left.width-44,True)
        wrap(app.screen,app.assets,'The championship continues after your first victory. Defend your crown against new challengers, or reclaim it after a defeat.',
             (left.x+24,left.y+260),left.width-48,14,MUTED,5)
        self.button((left.x+24,left.bottom-62,left.width-48,36),'Open championship region',
                    lambda:self.command('travel',chapter=8),disabled=self.badge_count<8 or app.action_pending)
        right = pygame.Rect(left.right+15,rect.y,rect.width-left.width-15,rect.height)
        self.card(right)
        self.write('YOUR STORY RECORD',(right.x+23,right.y+23),11,ACCENT,True)
        metrics = [('Wins',stats.get('wins',0)),('Losses',stats.get('losses',0)),('Reigns',champ.get('reigns',0)),('Defenses',champ.get('defenses',0))]
        for i,(name,value) in enumerate(metrics):
            x,y = right.x+23+(i%2)*(right.width//2),right.y+60+(i//2)*81
            self.write(str(value),(x,y),29,WHITE,True)
            self.write(name.upper(),(x,y+39),10,MUTED,True)
        self.write(f"DEFENSE STREAK  /  {champ.get('streak',0):,} current  ·  {champ.get('best_streak',0):,} best",
                   (right.x+23,right.y+211),11,GOLD,width=right.width-46)
        self.write('RECENT CHAPTERS IN YOUR CAREER',(right.x+23,right.y+235),10,ACCENT,True)
        recent = data.get('recent',[])
        if not recent:
            self.write('Your first victory is still ahead.',(right.x+23,right.y+268),14,MUTED,width=right.width-46)
        for i,row in enumerate(recent[:4]):
            label = (('WIN' if row.get('won') else 'LOSS')+' · '+str(row.get('opponent','Story battle'))+f"  +{row.get('credits',0):,} ¥") if isinstance(row,dict) else str(row)
            self.write(label,(right.x+23,right.y+268+i*38),12,WHITE,width=right.width-46)
        self.write(f"Training wins {stats.get('training_wins',0):,}  ·  Career earnings {stats.get('credits_earned',0):,} ¥",
                   (right.x+23,right.bottom-28),11,MUTED,width=right.width-46)

    def draw_convergence(self,rect):
        data,app = self.data,self.app
        complete = bool(data.get('completed'))
        ready = self.badge_count >= self.badge_total
        left = pygame.Rect(rect.x,rect.y,int(rect.width*.42),rect.height)
        right = pygame.Rect(left.right+14,rect.y,rect.width-left.width-14,rect.height)
        self.card(left,complete)
        self.card(right)
        self.write('THE FINAL CONVERGENCE',(left.x+23,left.y+22),11,GOLD,True)
        self.crown((left.centerx,left.y+98),38)
        self.write('Chronicle complete' if complete else 'The gate is ready' if ready else 'Seventeen keys. One final rift.',
                   (left.centerx,left.y+164),20,WHITE,True,left.width-40,True)
        self.write(f'{self.badge_count} / {self.badge_total} PARADOX CRESTS',
                   (left.centerx,left.y+201),13,ACCENT,True,left.width-40,True)
        bar = pygame.Rect(left.x+24,left.y+226,left.width-48,9)
        draw.rect(app.screen,(30,49,63),bar,border_radius=4)
        fill = bar.copy();fill.width = round(bar.width*min(1,self.badge_count/max(1,self.badge_total)))
        if fill.width: draw.rect(app.screen,GOLD if complete else ACCENT,fill,border_radius=4)
        description = ('The World DS story is complete. Your Crests and permanent scan reward are yours to keep.' if complete else
                       f"Return to the final field and speak to {data.get('final_name','the Convergence NPC')}. Summon the three Mega bosses when your team is ready." if ready else
                       'Complete each field’s quest, defeat its tamer and overcome its Paradox guardian. All 17 Crests unlock the final summon.')
        wrap(app.screen,app.assets,description,(left.x+24,left.y+257),left.width-48,14,MUTED,5)
        self.button((left.x+23,left.bottom-62,left.width-46,37),'Visit the Convergence',
                    lambda:self.command('travel',chapter=17,map_id=data.get('final_map_id')),disabled=not ready or app.action_pending)
        self.write('FINAL BOSS TEAM  /  THREE MEGA DIGIMON',(right.x+23,right.y+22),11,ACCENT,True,right.width-46)
        team = data.get('final_team') or []
        for i in range(3):
            member = team[i] if i<len(team) else {}
            y = right.y+54+i*72
            cell = pygame.Rect(right.x+19,y,right.width-38,64)
            panel(app.screen,cell,(14,31,46),(47,72,91),7)
            sprite = app.assets.sprite(member.get('species_id',''),(56,55),now=app.now)
            if sprite: app.screen.blit(sprite,sprite.get_rect(center=(cell.x+35,cell.centery)))
            name = member.get('name',f'Paradox Mega {i+1}').replace('ImperialdramonPaladinMode','Imperialdramon Paladin Mode')
            wrap(app.screen,app.assets,name,(cell.x+76,cell.y+8),cell.width-90,14,WHITE,2)
            self.write('Lv.100  ·  PARADOX  ·  MEGA',(cell.x+76,cell.y+48),9,GOLD,True,cell.width-90)
        reward = pygame.Rect(right.x+19,right.y+285,right.width-38,right.height-304)
        panel(app.screen,reward,(16,43,48),(61,126,115) if complete else (42,81,87),8)
        self.write('PERMANENT REWARD  /  '+('UNLOCKED' if data.get('scan_bonus',0) else 'AWAITING VICTORY'),
                   (reward.x+17,reward.y+16),10,ACCENT,True,reward.width-34)
        self.write('+20% PARADOX SCAN',(reward.x+17,reward.y+43),23,GOLD,True,reward.width-34)
        wrap(app.screen,app.assets,'Earn 20% more scan progress from every wild Paradox battle you win. The bonus stays active after returning to the MMO.',
             (reward.x+17,reward.y+83),reward.width-34,12,MUTED,3)

    def draw_feed(self,rect):
        rect = pygame.Rect(rect)
        self.card(rect)
        self.write(self.title+'  /  CURRENT OBJECTIVE',(rect.x+16,rect.y+12),10,ACCENT,True)
        wrap(self.app.screen,self.app.assets,self.data.get('objective','Explore this region and meet its tamers.'),
             (rect.x+16,rect.y+37),rect.width-211,14,WHITE,3)
        self.button((rect.right-179,rect.y+16,162,31),'Story journal  J',self.journal)
        self.button((rect.right-179,rect.y+57,162,31),'Interact nearby  E',self.interact,disabled=self.app.action_pending)
        self.write('WASD move  ·  E interact  ·  J journal  ·  F4 save & return',(rect.x+16,rect.bottom-22),10,MUTED,width=rect.width-32)

    def draw_dialogue(self):
        if self.result and not self.app.settings_open and not self.app.in_jail():
            if self.app.now>=self.app.battle_until:
                self.draw_result()
            return
        if not self.modal or self.app.menu or self.app.settings_open or self.app.in_jail():
            return
        app,data = self.app,self.dialogue
        w,h = app.screen.get_size()
        choices = data.get('choices',[])
        columns = min(3,max(1,len(choices)))
        rows = max(1,math.ceil(len(choices)/columns))
        height = 254+(rows-1)*41
        rect = pygame.Rect(37,h-height-30,w-74,height)
        # Covered map characters and navigation never receive a choice click.
        app.ui.actions,app.ui.fields = [],[]
        panel(app.screen,rect,(9,25,40),ACCENT,12)
        draw.line(app.screen,GOLD,(rect.x+22,rect.y+1),(rect.x+173,rect.y+1),3)
        portrait = pygame.Rect(rect.x+20,rect.y+23,116,157)
        panel(app.screen,portrait,(17,46,57),(42,88,102),8)
        if data.get('display_species'):
            sprite = app.assets.sprite(data['display_species'],(portrait.width-18,portrait.height-22),now=app.now)
            if sprite: app.screen.blit(sprite,sprite.get_rect(center=portrait.center))
        else:
            tamer = app.assets.tamers.get(data.get('tamer_id',data.get('tamer','')), {})
            frames = tamer.get('frames',{}).get('down') or []
            if isinstance(frames,str):
                frames = [frames]
            if frames:
                app.presentation.image(portrait.inflate(-27,-24),frames[0])
        x = portrait.right+24
        self.write(data.get('name','Story character'),(x,rect.y+23),21,ACCENT,True,rect.width-405)
        self.write(self.title,(rect.right-204,rect.y+30),9,MUTED,True,width=180)
        wrap(app.screen,app.assets,data.get('text',''),(x,rect.y+65),rect.right-x-28,17,WHITE,5)
        width = min(267,(rect.width-190-(columns-1)*10)//columns)
        for i,choice in enumerate(choices):
            self.button((x+(i%columns)*(width+10),rect.bottom-55-(rows-1)*41+(i//columns)*41,width,35),choice.get('label','Continue'),
                        lambda c=choice['id']:self.choose(c),primary=choice.get('id') in ('next','challenge','accept_quest','complete_quest'),disabled=app.action_pending)
        self.write(f"{int(data.get('page',1))} / {max(1,int(data.get('pages',1)))}",(portrait.centerx,rect.bottom-36),11,MUTED,center=True)

    def dismiss_result(self,journal=False):
        self.result = None
        self.app.ui.actions,self.app.ui.fields = [],[]
        if journal:
            if self.dialogue:
                self.pending_journal = True
            else:
                self.app.menu,self.tab = 'story','quest'

    def excerpt(self,value,position,width,size,limit):
        # The following NPC dialogue preserves the complete text. Mark the
        # compact celebration excerpt explicitly when it needs more room.
        scale = getattr(self.app.screen,'scale',1)
        font = self.app.assets.font(max(1,round(size*scale)))
        lines, line = [], ''
        for word in str(value).split():
            candidate = (line+' '+word).strip()
            if line and font.size(candidate)[0] > width*scale:
                lines.append(line);line=word
            else:
                line=candidate
        if line: lines.append(line)
        for i,line in enumerate(lines[:limit]):
            if i == limit-1 and len(lines) > limit: line += '…'
            self.write(line,(position[0],position[1]+i*(size+7)),size,WHITE,width=width)

    def draw_result(self):
        app,result = self.app,self.result
        w,h = app.screen.get_size()
        rect = pygame.Rect((w-700)//2,(h-492)//2+25,700,492)
        app.ui.actions,app.ui.fields = [],[]
        panel(app.screen,rect,(10,25,42),GOLD if result.get('won') else ACCENT,15)
        won,badge = result.get('won'),result.get('badge')
        champion = result.get('role')=='champion'
        finale = self.paradox and result.get('role')=='final'
        title = ('PARADOX CREST EARNED' if self.paradox else 'DIGIBADGE EARNED') if badge else 'PARADOX CHRONICLE COMPLETE' if finale and won else 'CHAMPIONSHIP VICTORY' if champion and won else 'STORY VICTORY' if won else 'YOUR JOURNEY CONTINUES'
        self.write(title,(rect.centerx,rect.y+32),13,GOLD if won else ACCENT,True,center=True)
        if badge:
            badge_index = next((i for i,row in enumerate(self.data.get('badges',[])) if row.get('id')==badge.get('id')),int(badge.get('chapter',0)))
            self.badge((rect.centerx,rect.y+102),badge_index,True,42)
            heading = badge.get('name','DigiBadge')
        else:
            if champion or finale:
                self.crown((rect.centerx,rect.y+105),42)
            else:
                sprite = app.assets.tamer(app.state.get('tamer',app.tamer),'down',False,app.now,(78,96))
                if sprite:
                    app.screen.blit(sprite,sprite.get_rect(center=(rect.centerx,rect.y+110)))
            heading = 'The Convergence is restored' if finale and won else 'Your title is yours to defend' if champion and won else result.get('opponent','Story battle')
        self.write(heading,(rect.centerx,rect.y+172),27,WHITE,True,rect.width-58,True)
        self.write(f"+{result.get('credits',0):,} credits  ·  Partners recovered" if won else 'Progress saved  ·  Partners recovered  ·  Ready to try again',
                   (rect.centerx,rect.y+216),13,GOLD if won else ACCENT,True,rect.width-50,True)
        narrative = result.get('narrative') or ('A new challenge awaits your team.' if won else 'Every tamer faces setbacks. Prepare your partners and return when you are ready.')
        self.excerpt(narrative,(rect.x+35,rect.y+251),rect.width-70,16,2)
        items = result.get('items') or []
        if finale and won:
            self.write('PERMANENT REWARD  /  +20% scan gain on every wild Paradox win',
                       (rect.x+35,rect.y+310),13,GOLD,True,width=rect.width-70)
        elif items:
            self.write('SUPPLIES  /  '+'  ·  '.join(f"{row['name']} ×{row['quantity']}" for row in items),
                       (rect.x+35,rect.y+310),11,GOLD,width=rect.width-70)
        partner = result.get('partner')
        if partner:
            self.write(f"COMPANION  /  {partner['name']} → {partner['destination']}",(rect.x+35,rect.y+331),11,ACCENT,width=rect.width-70)
        self.write('NEXT OBJECTIVE',(rect.x+35,rect.y+357),10,ACCENT,True)
        wrap(app.screen,app.assets,self.data.get('objective','Explore the region.'),(rect.x+35,rect.y+379),rect.width-70,13,MUTED,2)
        self.button((rect.x+35,rect.bottom-61,300,37),'Continue conversation' if self.dialogue else 'Continue exploring',self.dismiss_result,primary=True)
        self.button((rect.x+348,rect.bottom-61,317,37),'Journal after dialogue' if self.dialogue else 'Open story journal',lambda:self.dismiss_result(True))
