"""Local-console administrative service. Never registered as a network operation.

Every character write uses the same session lock, account lease and revision
checks as gameplay. This module never evaluates shell commands or player chat.
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
from dataclasses import dataclass
import logging
import math
import os
import re
import secrets
import shlex
import time

from .database import DatabaseError, USERNAME, validate_credentials
from .admin_game import AdminGame
from .admin_store import AdminStore
from .moderation import jail_state, clear_jail

LOG = logging.getLogger('venom.admin')
LEVELS = {'PLAYER': 0, 'MODERATOR': 10, 'GAME_MASTER': 20, 'ADMIN': 30, 'DEVELOPER': 40, 'OWNER': 50}


@dataclass(frozen=True)
class Command:
    permission: str
    usage: str
    description: str
    minimum: int = 0
    maximum: int | None = None


COMMANDS = {
    'help': Command('PLAYER', '/help [command]', 'List local console commands.', 0, 1),
    'permissions': Command('PLAYER', '/permissions', 'Show this console operator\'s permission tier.', 0, 0),
    'players': Command('PLAYER', '/players', 'List currently connected account names.', 0, 0),
    'broadcast': Command('ADMIN', '/broadcast "message"', 'Send a server notice to every connected player.', 1),
    'digimon': Command('PLAYER', '/digimon <player>', 'Inspect owned Digimon and stable partner selectors.', 1, 1),
    'team': Command('PLAYER', '/team <player>', 'Inspect the player\'s active party.', 1, 1),
    'bag': Command('PLAYER', '/bag <player>', 'Inspect item quantities.', 1, 1),
    'digimoninfo': Command('PLAYER', '/digimoninfo <species>', 'Inspect an exact catalog species name or ID.', 1),
    'givedigimon': Command('GAME_MASTER', '/givedigimon <player> <species> [level]', 'Grant a new partner, respecting party and farm capacity.', 2),
    'removedigimon': Command('GAME_MASTER', '/removedigimon <player> <partner>', 'Remove one exact partner; preserve at least one party member.', 2),
    'heal': Command('GAME_MASTER', '/heal <player>', 'Restore the player\'s party outside active combat.', 1, 1),
    'healall': Command('GAME_MASTER', '/healall', 'Restore eligible online parties; report busy players.', 0, 0),
    'evolve': Command('GAME_MASTER', '/evolve <player> <partner> [target]', 'Force a valid evolution route, bypassing progression gates.', 2),
    'devolve': Command('GAME_MASTER', '/devolve <player> <partner> [target]', 'Force a valid reverse evolution route.', 2),
    'setlevel': Command('GAME_MASTER', '/setlevel <player> <partner> <1-99>', 'Set level and refresh partner stats.', 3),
    'setexp': Command('GAME_MASTER', '/setexp <player> <partner> <experience>', 'Set progress within the current level.', 3),
    'setabi': Command('GAME_MASTER', '/setabi <player> <partner> <0-200>', 'Set ABI and refresh stats.', 3),
    'setcam': Command('GAME_MASTER', '/setcam <player> <partner> <0-100>', 'Set CAM friendship.', 3),
    'setfriendshiplevel': Command('GAME_MASTER', '/setfriendshiplevel <player> <partner> <0-100>', 'Alias for Digimon CAM friendship.', 3),
    'setparadox': Command('GAME_MASTER', '/setparadox <player> <partner> <true|false>', 'Switch to the actual catalog counterpart, if one exists.', 3),
    'setshiny': Command('GAME_MASTER', '/setshiny <player> <partner> <true|false>', 'Switch to the actual Shiny catalog counterpart, if one exists.', 3),
    'setfirewall': Command('GAME_MASTER', '/setfirewall <player> <partner> <true|false>', 'Switch to the actual FireWall catalog counterpart, if one exists.', 3),
    'clonedigimon': Command('DEVELOPER', '/clonedigimon <player> <partner>', 'Clone a partner for testing with a new unique identity.', 2),
    'giveitem': Command('GAME_MASTER', '/giveitem <player> <item> <amount>', 'Add a valid item without exceeding its cap.', 3),
    'removeitem': Command('GAME_MASTER', '/removeitem <player> <item> <amount>', 'Remove a valid item without negative quantities.', 3),
    'setitem': Command('GAME_MASTER', '/setitem <player> <item> <0-999>', 'Set an exact valid item quantity.', 3),
    'clearinventory': Command('ADMIN', '/clearinventory <player>', 'Prepare a revision-bound confirmation to clear the bag.', 1, 1),
    'money': Command('PLAYER', '/money <player>', 'Inspect ordinary credits.', 1, 1),
    'balance': Command('PLAYER', '/balance <player>', 'Alias for ordinary credit balance.', 1, 1),
    'givemoney': Command('GAME_MASTER', '/givemoney <player> <amount>', 'Add ordinary credits.', 2, 2),
    'removemoney': Command('GAME_MASTER', '/removemoney <player> <amount>', 'Remove ordinary credits.', 2, 2),
    'setmoney': Command('ADMIN', '/setmoney <player> <amount>', 'Set ordinary credits exactly.', 2, 2),
    'teleportplayer': Command('GAME_MASTER', '/teleportplayer <player> <location>', 'Move to a catalog map\'s validated spawn.', 2),
    'spawn': Command('GAME_MASTER', '/spawn <player> <species> [level]', 'Start an interactive wild battle for that player.', 2),
    'warn': Command('MODERATOR', '/warn <player> <reason>', 'Persist a warning and notify the connected player.', 2),
    'warnings': Command('MODERATOR', '/warnings <player>', 'Show the most recent 20 recorded warnings.', 1, 1),
    'kick': Command('MODERATOR', '/kick <player> [reason]', 'Save and disconnect a connected player.', 1),
    'ban': Command('MODERATOR', '/ban <player> <duration|permanent> <reason>', 'Persist a timed or permanent account ban and disconnect.', 3),
    'unban': Command('MODERATOR', '/unban <player>', 'Remove an account ban.', 1, 1),
    'jail': Command('MODERATOR', '/jail <player> <duration|permanent> <reason>', 'Detain in a private cell; preserve any paused battle.', 3),
    'unjail': Command('MODERATOR', '/unjail <player>', 'Release and restore the exact suspended activity.', 1, 1),
    'ipinfo': Command('ADMIN', '/ipinfo <player>', 'Print current connection endpoint locally; never broadcast it.', 1, 1),
    'createaccount': Command('ADMIN', '/createaccount <username>', 'Create an account using hidden password prompts.', 1, 1),
    'deleteaccount': Command('OWNER', '/deleteaccount <username>', 'Prepare confirmation to delete an offline account and its saves.', 1, 1),
    'resetpassword': Command('ADMIN', '/resetpassword <username>', 'Replace an offline account password using hidden prompts.', 1, 1),
    'confirm': Command('PLAYER', '/confirm <token>', 'Confirm one pending local action; original permission still applies.', 1, 1),
    'memory': Command('PLAYER', '/memory', 'Show this world process\'s memory usage.', 0, 0),
    'saveall': Command('ADMIN', '/saveall', 'Checkpoint online players and the rival population.', 0, 0),
    'shutdown': Command('ADMIN', '/shutdown [seconds|cancel]', 'Schedule a graceful saved shutdown.', 0, 1),
    'restart': Command('ADMIN', '/restart [seconds|cancel]', 'Schedule a graceful saved world restart in this console.', 0, 1),
    'addtitle': Command('ADMIN', '/addtitle <title>', 'Create a reusable player nameplate title (1-32 characters).', 1),
    'titles': Command('PLAYER', '/titles', 'List the server\'s available player titles.', 0, 0),
    'settitle': Command('GAME_MASTER', '/settitle <player> <title|none>', 'Grant and equip a title, or clear the selected title.', 2),
}
READ_GAME = {'digimon', 'team', 'bag', 'money', 'balance'}
WRITE_GAME = {'givedigimon', 'removedigimon', 'heal', 'evolve', 'devolve', 'setlevel', 'setexp',
              'setabi', 'setcam', 'setfriendshiplevel', 'setparadox', 'setshiny', 'setfirewall', 'clonedigimon', 'giveitem',
              'removeitem', 'setitem', 'givemoney', 'removemoney', 'setmoney', 'teleportplayer', 'spawn'}


def account_key(value):
    if not isinstance(value, str) or not USERNAME.fullmatch(value):
        raise ValueError('Use an exact player account name (3-24 letters, digits or underscores).')
    return value.lower()


def clean_text(value, maximum=240):
    value = value.strip()
    if not value or len(value) > maximum or not all(c.isprintable() for c in value):
        raise ValueError(f'Text must contain 1-{maximum} printable characters.')
    return value


def duration(value, now=None):
    """Real seconds for moderation; never reads or changes fictional Season time."""
    if value.casefold() in {'permanent', 'perm', 'forever'}:
        return None
    match = re.fullmatch(r'(\d{1,9})([smhdw]?)', value.casefold())
    if not match:
        raise ValueError('Use a duration such as 30m, 2h, 7d, or permanent; bare numbers mean seconds.')
    seconds = int(match[1]) * {'': 1, 's': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}[match[2]]
    if not 1 <= seconds <= 10 * 366 * 86400:
        raise ValueError('Duration must be at least one second and at most ten years; use permanent for longer.')
    return (time.time() if now is None else now) + seconds


class AdminConsole:
    def __init__(self, world, role='OWNER'):
        self.world = world
        self.role = str(role).strip().upper().replace(' ', '_')
        if self.role not in LEVELS:
            raise ValueError('Unknown local console permission tier.')
        self.store = getattr(world, 'admin_store', None) or AdminStore(world.database)
        self.game = AdminGame(world.engine)
        self.pending = {}
        self._lock = asyncio.Lock()
        self._scheduled = None
        self.closed = False

    @staticmethod
    def required_permission(command):
        spec = COMMANDS.get(command.lower().lstrip('/'))
        return spec.permission if spec else 'OWNER'

    def can_execute(self, command):
        name = command.lower().lstrip('/')
        return name in COMMANDS and LEVELS[self.role] >= LEVELS[COMMANDS[name].permission]

    async def close(self):
        self.closed = True
        if self._scheduled is not None and self._scheduled is not asyncio.current_task():
            self._scheduled.cancel()
            await asyncio.gather(self._scheduled, return_exceptions=True)
        async with self._lock:
            pass

    async def _audit(self, action, target, status):
        try:
            await asyncio.to_thread(self.store.audit, action, target=target, permission=self.role, status=status)
        except Exception:
            # Never include raw command text, credentials or connection metadata.
            LOG.error('Local console audit write failed for operation %s.', action)

    async def execute(self, line, password=None):
        """Return console-only output. Credentials are supplied out of band."""
        async with self._lock:
            if self.closed or self.world.stopping:
                return 'ERROR: The world is stopping; no new administrative action was accepted.'
            name, target = 'unknown', None
            try:
                if not isinstance(line, str) or len(line) > 2048 or any(not c.isprintable() for c in line):
                    raise ValueError('Use one printable command line, at most 2048 characters.')
                parts = shlex.split(line.strip(), posix=True)
                if not parts:
                    return ''
                name, args = parts[0].lstrip('/').lower(), parts[1:]
                spec = COMMANDS.get(name)
                if spec is None:
                    name = 'unknown'
                    raise ValueError('Unknown local console command. Type /help.')
                if not self.can_execute(name):
                    await self._audit(name, None, 'denied')
                    return f'DENIED: /{name} requires {spec.permission}; this local console is {self.role}.'
                if len(args) < spec.minimum or spec.maximum is not None and len(args) > spec.maximum:
                    raise ValueError('Usage: ' + spec.usage)
                if password is not None and name not in {'createaccount', 'resetpassword'}:
                    raise ValueError('Hidden credentials are accepted only by account password commands.')
                if args and USERNAME.fullmatch(args[0]) and (name in READ_GAME | WRITE_GAME or name in {
                    'warn', 'warnings', 'kick', 'ban', 'unban', 'jail', 'unjail', 'ipinfo',
                    'createaccount', 'deleteaccount', 'resetpassword', 'clearinventory', 'settitle'}):
                    target = args[0].lower()
                result = await self._execute(name, args, password)
                await self._audit('prepare_'+name if name in {'clearinventory', 'deleteaccount'} else name, target, 'success')
                return result
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                await self._audit(name, target, 'error')
                if name in {'createaccount', 'resetpassword'} and password is not None:
                    return 'ERROR: Account action failed. Check the username/password format, account existence and offline status; no credentials were logged.'
                return 'ERROR: ' + (str(exc) if isinstance(exc, ValueError) else 'Invalid command fields.')
            except DatabaseError:
                await self._audit(name, target, 'error')
                return 'ERROR: The operation could not safely acquire or save that account. No unsaved change was published; check the server database and session ownership.'
            except Exception:
                # Do not interpolate exception text: it may contain submitted data.
                LOG.error('Local console operation %s failed unexpectedly.', name)
                await self._audit(name, target, 'error')
                return 'ERROR: The command could not be completed. Existing saves were protected.'
            finally:
                password = None

    async def _read(self, username):
        key = account_key(username)
        async with self.world.session_lock:
            session = self.world.sessions.get(key)
            if session:
                async with session.lock:
                    return copy.deepcopy(session.state), session.revision, True
            state, revision = await asyncio.to_thread(self.world.database.load, key)
            return state, revision, False

    async def _mutate(self, username, operation, *, revision=None):
        key = account_key(username)
        async with self.world.session_lock:
            session = self.world.sessions.get(key)
            if session:
                if session.closing:
                    raise ValueError('This player is disconnecting; wait until the save is complete.')
                async with session.lock:
                    if revision is not None and revision != session.revision:
                        raise ValueError('The player save changed. Request a new confirmation.')
                    candidate = copy.deepcopy(session.state)
                    candidate['events'] = []
                    message = operation(candidate)
                    self.world.engine._refresh(candidate)
                    # Broadcasts read state without this lock. Publish only
                    # after the detached candidate has committed successfully.
                    committing = copy.copy(session)
                    committing.state = candidate
                    await self.world.save(committing)
                    session.state, session.revision = committing.state, committing.revision
                    session.dx = session.dy = 0
                    session.walked = 0
                    await self._refresh_profile(candidate, key)
                    try:
                        # Keep the lock through delivery so a later gameplay
                        # result cannot arrive before this older snapshot.
                        await self.world.send(session.websocket, {'op': 'result', 'rid': 0, 'ok': True, 'state': candidate})
                        await self._notice('Your character was updated by the local server administrator.', 'admin', session)
                    except Exception:
                        LOG.info('Administrative update saved for %s; client delivery was unavailable.', key)
            else:
                token = 'console-' + secrets.token_hex(20)
                if not await asyncio.to_thread(self.world.database.acquire_session, key, token):
                    raise ValueError('Account not found or leased by another server. No change was made.')
                try:
                    candidate, current = await asyncio.to_thread(self.world.database.load, key)
                    if revision is not None and current != revision:
                        raise ValueError('The player save changed. Request a new confirmation.')
                    candidate['events'] = []
                    message = operation(candidate)
                    self.world.engine._refresh(candidate)
                    await asyncio.to_thread(self.world.database.save, key, candidate, current, token)
                    await self._refresh_profile(candidate, key)
                finally:
                    await asyncio.to_thread(self.world.database.release_session, key, token)
        return str(message)

    async def _refresh_profile(self, saved, key):
        community = self.world.community
        if community and community.ready and self.world.shared_profile(saved):
            try:
                def refresh():
                    with community.lock:
                        community.register_player(copy.deepcopy(saved))
                await asyncio.to_thread(refresh)
            except Exception:
                LOG.warning('Saved character %s will refresh its community profile at the next checkpoint.', key)

    async def _notice(self, text, kind='admin', session=None):
        recipients = [session] if session is not None else list(self.world.sessions.values())
        packet = {'op': 'notice', 'kind': kind, 'text': clean_text(text)}
        results = await asyncio.gather(*(self.world.send(s.websocket, packet) for s in recipients if not s.closing), return_exceptions=True)
        return sum(not isinstance(result, BaseException) for result in results)

    async def _disconnect(self, username, reason, *, force=False):
        key = account_key(username)
        saved = True
        async with self.world.session_lock:
            session = self.world.sessions.get(key)
            if session is None:
                return False
            async with session.lock:
                try:
                    await self.world.save(session)
                except Exception:
                    if not force:
                        raise
                    saved = False
                    LOG.error('Banned session %s checkpoint failed; disconnecting and retaining final-save recovery.', key)
                await self._notice(reason, 'warning', session)
                session.closing = True
        await session.websocket.close(1008, 'Disconnected by local server administrator')
        return 'saved' if saved else 'checkpoint_failed'

    async def _prepare_confirmation(self, name, username):
        state, revision, online = await self._read(username)
        if name == 'deleteaccount' and online:
            raise ValueError('Account deletion requires the player offline. Kick them, wait for their save, then retry.')
        if name == 'clearinventory' and (state.get('battle') or state.get('in_season') or state.get('in_story') or state.get('admin_jail')):
            raise ValueError('Finish the battle and leave Story Mode, Season Mode or detention before clearing inventory.')
        now = time.monotonic()
        self.pending = {k:v for k,v in self.pending.items() if v['expires'] > now}
        if len(self.pending) >= 32:
            raise ValueError('Too many pending confirmations; wait one minute.')
        token = secrets.token_hex(4)
        self.pending[token] = {'command': name, 'target': account_key(username), 'revision': revision, 'expires': now+60}
        action = 'DELETE the account, character, Season archives and associated account records' if name == 'deleteaccount' else 'CLEAR every inventory item'
        return f'CONFIRM REQUIRED: {action} for {state["username"]}. Type /confirm {token} within 60 seconds. Any intervening save invalidates this confirmation.'

    async def _confirm(self, token):
        pending = self.pending.pop(token, None)
        if not pending or pending['expires'] <= time.monotonic():
            raise ValueError('Unknown or expired confirmation. Start the command again.')
        name, target = pending['command'], pending['target']
        if not self.can_execute(name):
            raise ValueError('The original command permission is still required.')
        if name == 'clearinventory':
            result = await self._mutate(target, lambda s:self.game.execute(name,s,[]), revision=pending['revision'])
        else:
            async with self.world.session_lock:
                if target in self.world.sessions:
                    raise ValueError('The account is online. Request deletion again after it disconnects.')
                lease = 'console-' + secrets.token_hex(20)
                if not await asyncio.to_thread(self.world.database.acquire_session, target, lease):
                    raise ValueError('Account is missing or leased by another world; deletion was refused.')
                try:
                    community = self.world.community
                    def delete_and_forget():
                        # Community and ranked activity use these lock orders.
                        # SQL and cached matchmaking identity disappear together.
                        with community.lock if community and community.ready else contextlib.nullcontext():
                            ranked = community.ranked if community and community.ready else None
                            with ranked.lock if ranked else contextlib.nullcontext():
                                self.world.database.delete_account(target, lease, pending['revision'])
                                if ranked:
                                    ident = 'player:'+target
                                    ranked.profiles.pop(ident, None)
                                    ranked._power_order = []
                                    ranked._indexed_ids = set()
                                    ranked._power_at = -math.inf
                                    ranked._generation += 1
                                    ranked._standings_cache.clear()
                                    community.next_invite.pop(ident, None)
                                    community.challenges = {k:v for k,v in community.challenges.items() if v.get('player_id') != ident}
                    await asyncio.to_thread(delete_and_forget)
                    self._invalidate_confirmations(target)
                finally:
                    await asyncio.to_thread(self.world.database.release_session, target, lease)
            result = f'Deleted offline account {target} and its character/Season saves.'
        await self._audit(name, target, 'success')
        return result

    def _invalidate_confirmations(self, target):
        self.pending = {k:v for k,v in self.pending.items() if v['target'] != target}

    async def _execute(self, name, args, password):
        if name == 'help':
            if args:
                key = args[0].lstrip('/').lower()
                if key not in COMMANDS or not self.can_execute(key):
                    raise ValueError('Command unavailable at this console tier.')
                spec = COMMANDS[key]
                return f'{spec.usage} [{spec.permission}]\n{spec.description}'
            return 'LOCAL WORLD CONSOLE ONLY — player chat has no commands.\n' + '\n'.join(
                f'{s.usage} [{s.permission}] — {s.description}' for k,s in COMMANDS.items() if self.can_execute(k))
        if name == 'permissions':
            return f'Console tier: {self.role}. Hierarchy: '+ ' < '.join(LEVELS) + '. PLAYER means local read-only inspection; no player account receives console powers.'
        if name == 'players':
            return 'Online: ' + (', '.join(s.state['username'] for s in self.world.sessions.values() if not s.closing) or '(none)')
        if name == 'digimoninfo':
            return self.game.species_info(args)
        if name in READ_GAME:
            state, _, _ = await self._read(args[0])
            return self.game.execute(name, state, args[1:])
        if name in WRITE_GAME:
            return await self._mutate(args[0], lambda s:self.game.execute(name,s,args[1:]))
        if name in {'clearinventory', 'deleteaccount'}:
            return await self._prepare_confirmation(name, args[0])
        if name == 'confirm':
            return await self._confirm(args[0])
        if name == 'healall':
            done, skipped = [], []
            for key in list(self.world.sessions):
                try:
                    await self._mutate(key, lambda s:self.game.execute('heal',s,[]))
                    done.append(key)
                except (ValueError, DatabaseError) as exc:
                    skipped.append(key+': '+str(exc))
            return f'Healed {len(done)} online parties. '+ ('Skipped: '+'; '.join(skipped) if skipped else 'No busy parties skipped.')
        if name == 'broadcast':
            count = await self._notice(clean_text(' '.join(args)), 'broadcast')
            return f'Broadcast delivered to {count} connected players.'
        if name == 'warn':
            key, reason = account_key(args[0]), clean_text(' '.join(args[1:]))
            row = await asyncio.to_thread(self.store.add_warning,key,reason)
            session = self.world.sessions.get(key)
            if session: await self._notice(reason,'warning',session)
            return f'Warning {row["id"]} recorded for {key}'+ ('. Player notified.' if session else '. Player is offline.')
        if name == 'warnings':
            rows = await asyncio.to_thread(self.store.warnings,account_key(args[0]))
            return '\n'.join(f'#{r["id"]} '+time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime(r['created_at']))+' — '+r['reason'] for r in rows) or 'No recorded warnings.'
        if name == 'kick':
            reason = clean_text(' '.join(args[1:]) or 'Disconnected by the local server administrator.')
            if not await self._disconnect(args[0], reason): raise ValueError('That player is not connected.')
            return f'Saved and disconnected {account_key(args[0])}.'
        if name == 'ban':
            key, until, reason = account_key(args[0]), duration(args[1]), clean_text(' '.join(args[2:]))
            async with self.world.session_lock:
                await asyncio.to_thread(self.store.set_ban,key,until,reason)
            checkpoint = await self._disconnect(key,reason,force=True)
            result = f'Banned {key} '+('permanently.' if until is None else 'until '+time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime(until))+'.')
            if checkpoint == 'checkpoint_failed':
                result += ' The latest checkpoint failed; the connection was closed and final-save recovery will retry. Check the server log.'
            return result
        if name == 'unban':
            removed = await asyncio.to_thread(self.store.unban,account_key(args[0]))
            return 'Ban removed.' if removed else 'No ban was recorded for that account.'
        if name == 'jail':
            until, reason = duration(args[1]), clean_text(' '.join(args[2:]))
            def detain(state):
                jail_state(self.world.engine,state,until,reason)
                return f'{state["username"]} detained. Any active battle is paused and will resume after release.'
            return await self._mutate(args[0],detain)
        if name == 'unjail':
            def release(state):
                if not state.get('admin_jail'): raise ValueError('This player is not detained.')
                clear_jail(state)
                return f'{state["username"]} released to the saved activity.'
            return await self._mutate(args[0],release)
        if name == 'ipinfo':
            session = self.world.sessions.get(account_key(args[0]))
            if not session: raise ValueError('Connection information is available only for a currently connected player.')
            endpoint = getattr(session.websocket,'remote_address',None)
            latency = getattr(session.websocket,'latency',None)
            return f'LOCAL ONLY / {session.state["username"]}: peer={endpoint!r}; latency_seconds={latency!r}. This command does not maintain an IP history.'
        if name == 'createaccount':
            if password is None: raise ValueError('Use the interactive local console; the password is collected through hidden prompts.')
            validate_credentials(args[0],password)
            async with self.world.session_lock:
                state = self.world.engine.new_player(args[0],next(iter(self.world.engine.tamers)),self.world.engine.starters[0])
                await asyncio.to_thread(self.world.database.register,args[0],password,state)
                self._invalidate_confirmations(account_key(args[0]))
            return f'Created {args[0]} with the default valid tamer/starter. No credentials were logged.'
        if name == 'resetpassword':
            if password is None: raise ValueError('Use the interactive local console; the password is collected through hidden prompts.')
            key=validate_credentials(args[0],password)
            async with self.world.session_lock:
                if key in self.world.sessions: raise ValueError('Password reset requires the player offline. Kick them and wait for their final save.')
                lease='console-'+secrets.token_hex(20)
                if not await asyncio.to_thread(self.world.database.acquire_session,key,lease): raise ValueError('Account missing or leased elsewhere; reset refused.')
                try:
                    await asyncio.to_thread(self.world.database.reset_password,key,password,lease)
                finally:
                    await asyncio.to_thread(self.world.database.release_session,key,lease)
            return f'Password reset for {key}. No credentials were logged.'
        if name == 'addtitle':
            title=await asyncio.to_thread(self.store.add_title,clean_text(' '.join(args),32))
            return f'Title available: {title["name"]} (id {title["id"]}).'
        if name == 'titles':
            rows=await asyncio.to_thread(self.store.titles)
            return '\n'.join(f'{r["id"]} — {r["name"]}' for r in rows) or 'No titles yet. An administrator can use /addtitle.'
        if name == 'settitle':
            wanted=' '.join(args[1:])
            title=None if wanted.casefold()=='none' else await asyncio.to_thread(self.store.find_title,wanted)
            if title is None and wanted.casefold()!='none': raise ValueError('Unknown title. Use /titles or create it with /addtitle.')
            def equip(state):
                if title:
                    owned=state.setdefault('titles',[])
                    if title['name'] not in owned: owned.append(title['name'])
                    state['active_title']=title['name']
                else: state['active_title']=''
                return f'{state["username"]}: active title '+(title['name'] if title else 'cleared')+'.'
            return await self._mutate(args[0],equip)
        if name == 'memory':
            return self._memory()
        if name == 'saveall':
            count=0
            for session in list(self.world.sessions.values()):
                async with session.lock:
                    if not session.closing:
                        await self.world.save(session)
                        count+=1
            community=self.world.community
            if community and community.ready:
                def checkpoint():
                    with community.lock:
                        if not community.store.renew_world(community.token,lease_seconds=90): raise DatabaseError('Rival lease unavailable.')
                        community.bots.flush(force=True)
                await asyncio.to_thread(checkpoint)
            return f'Saved {count} online player(s) and checkpointed the enabled rival population.'
        if name in {'shutdown','restart'}:
            return await self._schedule(name,args)
        raise ValueError('Unknown local command.')

    def _memory(self):
        detail='Memory measurement unavailable on this host.'
        try:
            if os.name=='nt':
                import ctypes
                from ctypes import wintypes
                class Counters(ctypes.Structure):
                    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
                counters=Counters();counters.cb=ctypes.sizeof(counters)
                current=ctypes.windll.kernel32.GetCurrentProcess;current.restype=wintypes.HANDLE
                get=ctypes.windll.psapi.GetProcessMemoryInfo;get.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
                if get(current(),ctypes.byref(counters),counters.cb): detail=f'Working set: {counters.WorkingSetSize/1048576:.1f} MiB; peak: {counters.PeakWorkingSetSize/1048576:.1f} MiB.'
            else:
                from pathlib import Path
                fields=Path('/proc/self/status').read_text().splitlines()
                rss=next(int(line.split()[1]) for line in fields if line.startswith('VmRSS:'))
                detail=f'Resident memory: {rss/1024:.1f} MiB.'
        except (OSError,ValueError,StopIteration,AttributeError):
            pass
        return f'World PID {os.getpid()}; {len(self.world.sessions)} connected sessions. '+detail

    async def _schedule(self, kind, args):
        if args and args[0].casefold()=='cancel':
            if self._scheduled is None or self._scheduled.done(): return 'No pending shutdown or restart.'
            self._scheduled.cancel();await asyncio.gather(self._scheduled,return_exceptions=True)
            self._scheduled=None
            await self._notice('The scheduled server shutdown/restart was cancelled.','shutdown')
            return 'Scheduled shutdown/restart cancelled.'
        if not getattr(self.world,'stop_signal',None): raise ValueError('This world is not attached to its production lifecycle.')
        if self._scheduled and not self._scheduled.done(): raise ValueError('An action is already scheduled. Use /shutdown cancel or /restart cancel first.')
        raw=args[0] if args else '10'
        if not re.fullmatch(r'\d{1,5}',raw) or not 0<=int(raw)<=86400: raise ValueError('Choose a whole number of seconds from 0 to 86400.')
        seconds=int(raw)
        await self._notice(f'Server {kind} in {seconds} seconds. Your progress will be saved.','shutdown')
        async def countdown():
            deadline=time.monotonic()+seconds
            sent=set()
            while True:
                remaining=max(0,math.ceil(deadline-time.monotonic()))
                if remaining==0: break
                if remaining in {60,30,10,5,3,2,1} and remaining!=seconds and remaining not in sent:
                    sent.add(remaining)
                    await self._notice(f'Server {kind} in {remaining} seconds.','shutdown')
                await asyncio.sleep(min(1,max(0,deadline-time.monotonic())))
            self.world.restart_requested=(kind=='restart')
            self.world.stop_signal.set()
        self._scheduled=asyncio.create_task(countdown())
        return f'Graceful {kind} scheduled in {seconds} seconds.'
