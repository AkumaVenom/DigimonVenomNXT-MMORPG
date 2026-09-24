"""Authoritative population, ranked service and player-facing community gateway."""
from __future__ import annotations

import copy
import logging
import math
import secrets
import threading
import time

from venom.common.game import GameEngine
from venom.server.database import DatabaseError

LOG = logging.getLogger('venom.community')


def bounded_int(value, default, lower, upper):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError('Use a whole number for this option.')
    return max(lower, min(upper, value))


class Community:
    def __init__(self, engine, database, config):
        from .community_store import CommunityStore
        self.root, self.config = engine.root, config
        self.store = CommunityStore(database)
        rivals = dict(config.get('rivals', {}))
        if not rivals.get('enabled', True):
            rivals['count'] = 0
        rivals['count'] = bounded_int(rivals.get('count'), 5000, 0, 5000)
        self.rivals_config = rivals
        self.ranked = self.bots = None
        self.lock = threading.RLock()
        self.token = secrets.token_hex(32)
        self.ready = False
        self.lease_owned = False
        self.last_lease = 0.
        self.last_season = 0.
        self.challenges = {}
        self.next_invite = {}

    def initialize(self):
        from .ranked import RankedService
        from .bots import BotManager
        with self.lock:
            self.store.initialize()
            if not self.store.acquire_world(self.token, lease_seconds=90):
                raise DatabaseError('Another server owns this database\'s rival population. Stop that server or wait for its lease to expire.')
            self.store.owner_token = self.token
            self.lease_owned = True
            try:
                # Each engine owns its RNG; initialize only after tables and lease.
                self.ranked = RankedService(GameEngine(self.root), self.store, self.config.get('ranked', {}))
                self.bots = BotManager(GameEngine(self.root), self.store, self.ranked, self.rivals_config)
                self.ranked.tick()
                self.bots.initialize()
                self.last_lease = time.monotonic()
                self.ready = True
            except Exception:
                self.store.release_world(self.token)
                self.lease_owned = False
                raise

    def step(self, now, dt):
        with self.lock:
            if not self.ready:
                return
            if now-self.last_lease >= 20:
                if not self.store.renew_world(self.token, lease_seconds=90):
                    self.ready = self.lease_owned = False
                    raise DatabaseError('The rival simulation lease was lost; stopping to protect saved progress.')
                self.last_lease = now
            if now-self.last_season >= 5:
                self.ranked.tick()
                self.last_season = now
            self.bots.tick(now=now, dt=dt, budget=160)
            self.challenges = {key:value for key,value in self.challenges.items() if value['expires_at']>time.time()}

    def shutdown(self):
        with self.lock:
            self.ready = False
            if self.lease_owned:
                try:
                    if self.store.renew_world(self.token, lease_seconds=90):
                        self.bots.flush(force=True)
                    else:
                        raise DatabaseError('Rival lease expired or changed owner; final rival checkpoint was not saved.')
                finally:
                    self.store.release_world(self.token)
                    self.lease_owned = False

    def snapshots(self, map_ids, now):
        if not self.ready:
            return {}
        return {map_id:self.bots.snapshot(map_id, now=now) for map_id in map_ids}

    @staticmethod
    def player_id(state):
        return 'player:'+state['username'].lower()

    def register_player(self, state):
        ident = self.player_id(state)
        self.ranked.register_participant(ident, {
            'name':state['username'], 'tamer':state['tamer'], 'kind':'player',
            'party':copy.deepcopy(state['party']), 'map_id':state['map_id']})
        return ident

    @staticmethod
    def _peace(state):
        if state.get('battle') or state.get('in_lab'):
            raise ValueError('Return to the field and finish your current battle before challenging a rival.')

    def _profile(self, bot_id):
        if not isinstance(bot_id, str) or not bot_id.startswith('bot:') or len(bot_id)>32:
            raise ValueError('Choose a valid tamer rival.')
        profile = self.bots.profile(bot_id)
        if not profile:
            raise ValueError('This rival is not available on the server.')
        return profile

    def _nearby(self, state, now):
        if state.get('in_lab') or state.get('in_farm'):
            return []
        actors = self.bots.snapshot(state['map_id'], now=now)
        point = (state['x'],state['y'])
        return sorted(actors,key=lambda p:math.dist(point,(p['x'],p['y'])))[:50]

    def _challenge_bot(self, state, bot_id, require_nearby=True):
        self._peace(state)
        if state.get('in_farm'):
            raise ValueError('Return to the field before challenging a nearby rival.')
        profile = self._profile(bot_id)
        actors = {p.get('id'):p for p in self._nearby(state,time.monotonic())}
        actor = actors.get(bot_id)
        if actor is None or (require_nearby and math.dist((state['x'],state['y']),(actor['x'],actor['y']))>360):
            raise ValueError('Move closer to this rival in the same sector before challenging them.')
        if actor.get('battle') or actor.get('in_lab'):
            raise ValueError('This rival is busy. Let them finish their current activity first.')
        return profile

    def _pending(self, player_id):
        now = time.time()
        return [dict(row) for row in self.challenges.values()
                if row['player_id']==player_id and row['expires_at']>now and not row.get('completed')]

    def _offer(self, state, now):
        ident = self.player_id(state)
        if (state.get('battle') or state.get('in_lab') or state.get('in_farm')
                or self._pending(ident) or now<self.next_invite.get(ident,0)):
            return
        self.next_invite[ident] = now+120
        nearby = self._nearby(state,now)
        candidate = next((p for p in nearby if not p.get('battle') and not p.get('in_lab')
                          and math.dist((state['x'],state['y']),(p['x'],p['y']))<=360),None)
        if candidate:
            key = secrets.token_hex(16)
            self.challenges[key] = {'id':key,'challenge_id':key,'player_id':ident,
                'bot_id':candidate['id'],'name':candidate['username'], 'map_id':state['map_id'],
                'created_at':time.time(),'expires_at':time.time()+180,'ranked':False}

    def invitations(self, states, now):
        with self.lock:
            for state in states:
                self._offer(state,now)

    def request(self, state, message, session_token):
        """Called on a worker, while the caller holds the human session lock."""
        with self.lock:
            if not self.ready:
                raise ValueError('The rival population is still starting. Please try again shortly.')
            action = message.get('action','ranked')
            if not isinstance(action,str):
                raise ValueError('Choose a valid community action.')
            player_id = self.register_player(state)
            if action=='ranked':
                data = self.ranked.overview(player_id)
                data['opponents'] = self.ranked.available_opponents(player_id,limit=15)
            elif action=='ladder':
                scope = message.get('scope','current')
                if scope not in ('current','career','history'):
                    raise ValueError('Choose the current season, career or an archived season.')
                data = self.ranked.leaderboard(scope=scope,season_id=message.get('season_id'),limit=100)
            elif action=='seasons':
                data = self.ranked.seasons(limit=50)
            elif action=='match':
                self._peace(state)
                opponent = message.get('opponent_id')
                if opponent is not None and (not isinstance(opponent,str) or len(opponent)>64):
                    raise ValueError('Choose an available ranked opponent.')
                match_id = f'human:{session_token[:20]}:{message["rid"]}'
                data = self.ranked.start_match(player_id,opponent,match_id=match_id,ranked=True)
            elif action=='profile':
                data = self._profile(message.get('bot_id'))
                data['ranked'] = self.ranked.overview(message['bot_id'])
            elif action=='activity':
                data = self.bots.activity(limit=100)
            elif action=='rivals':
                query = message.get('query','')
                if not isinstance(query,str) or len(query)>64:
                    raise ValueError('Keep the rival search under 65 characters.')
                offset = bounded_int(message.get('offset'),0,0,5000)
                self._offer(state,time.monotonic())
                page = self.bots.directory(query=query,offset=offset,limit=50)
                data = {'challenges':[] if state.get('in_farm') else self._pending(player_id),
                    'history':self.store.rival_history(player_id,limit=100),
                    'nearby':self._nearby(state,time.monotonic()),
                    'directory':page['entries'], 'total':page['total'],
                    'offset':page['offset']}
            elif action in ('challenge','accept','decline'):
                challenge = None
                if action in ('accept','decline'):
                    challenge = self.challenges.get(message.get('challenge_id'))
                    if not challenge or challenge['player_id']!=player_id or challenge['expires_at']<=time.time():
                        raise ValueError('That challenge expired. Check the hub for a new invitation.')
                    if action=='decline':
                        self.challenges.pop(challenge['id'],None)
                        return {'action':action,'data':{'declined':True}}
                    bot_id = challenge['bot_id']
                else:
                    bot_id = message.get('bot_id')
                self._challenge_bot(state,bot_id,require_nearby=challenge is None)
                match_id = 'challenge:'+challenge['id'] if challenge else f'friendly:{session_token[:20]}:{message["rid"]}'
                data = self.ranked.start_match(player_id,bot_id,match_id=match_id,ranked=False)
                if challenge:
                    challenge['completed'] = True
            else:
                raise ValueError('Unknown community action.')
            if action in ('match','challenge','accept') and not data.get('duplicate'):
                self.bots.record_ranked_result(data)
            return {'action':action,'data':data}
