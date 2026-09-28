"""Dedicated authoritative WSS world server for Digimon Venom NXT."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import hashlib
from dataclasses import dataclass, field
import json
import logging
import math
from pathlib import Path
import secrets
import signal
import ssl
import sys
import time

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from websockets.extensions.permessage_deflate import ServerPerMessageDeflateFactory

from venom.common.game import GameEngine
from venom.common.economy import economy_view
from venom.common.farm import move_farm_position, normalize_farm_position
from venom.common.paths import root_path
from venom.common.network import network_settings
from venom.version import VERSION
from venom.server.database import Database, DatabaseError, validate_credentials
from venom.server.lifecycle import WorldProcessLock
from venom.server.moderation import clear_jail, is_jailed, jail_expired

LOG = logging.getLogger("venom.server")
MOVE_SPEED = 180.0
MAX_MESSAGE = 65_536
GAME_OPS = {"encounter", "battle", "digilab", "digifarm", "materialize", "evolve", "party", "shop", "item", "travel", "season", "story"}


def project_root():
    return root_path()


def transport_extensions():
    """Compress repeated map fields without retaining another message's data.

    Native clients already offer this standard WebSocket extension. A client
    without the extension keeps receiving the identical uncompressed protocol.
    Small windows and the fastest compression level bound per-connection work;
    both dictionaries are discarded after every message, including login.
    """
    return [ServerPerMessageDeflateFactory(
        server_no_context_takeover=True, client_no_context_takeover=True,
        server_max_window_bits=12, client_max_window_bits=12,
        compress_settings={"level": 1, "memLevel": 5})]


class TokenBucket:
    def __init__(self, rate, capacity):
        self.rate, self.capacity = rate, capacity
        self.tokens = float(capacity)
        self.updated = time.monotonic()

    def take(self, amount=1):
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + max(0, now - self.updated) * self.rate)
        self.updated = now
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True


@dataclass
class Session:
    websocket: object
    key: str
    token: str
    state: dict
    revision: int
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_move: float = field(default_factory=time.monotonic)
    move_credit: float = 0.1
    dx: float = 0
    dy: float = 0
    walked: float = 0
    next_encounter: float = 850
    last_encounter: float = 0
    last_chat: float = 0
    action_rate: TokenBucket = field(default_factory=lambda: TokenBucket(6, 12))
    # World messages are complete visual snapshots, not transactions. Keep
    # only the newest waiting snapshot while this player's send is blocked.
    world_updates: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1), repr=False)
    world_sender: asyncio.Task | None = field(default=None, repr=False, compare=False)
    closing: bool = False


class WorldServer:
    def __init__(self, engine, database, config=None):
        config = config or {}
        self.engine, self.database, self.config = engine, database, config
        self.network = network_settings(config)
        self.sessions: dict[str, Session] = {}
        self.session_lock = asyncio.Lock()
        self.authentication_slots = asyncio.Semaphore(4)
        self.auth_limits = {}
        self.connections_by_ip = {}
        self.masks = {}
        self.root = Path(getattr(engine, "root", project_root()))
        self.stopping = False
        self.community = None
        self.stop_signal = None
        self.persistence_failed = False
        self.community_rate = {}
        self.world_sequence = 0
        self.restart_requested = False
        self.admin_store = None
        if database is not None and hasattr(database, "_sql"):
            from venom.server.admin_store import AdminStore
            self.admin_store = AdminStore(database)

    async def check_ban(self, key):
        if self.admin_store is not None:
            ban = await asyncio.to_thread(self.admin_store.ban_status, key)
            if ban:
                raise ValueError("This account is banned. " + str(ban.get("reason", "Contact the server administrator.")))

    async def expire_jail(self, session, notify=True):
        """Caller holds session.lock; publish release only after a durable save."""
        if session.closing or not jail_expired(session.state):
            return False
        candidate = copy.deepcopy(session.state)
        clear_jail(candidate)
        # World snapshots read without session.lock. Keep release invisible
        # until the same revision/lease-aware save has committed successfully.
        proposed = copy.copy(session)
        proposed.state = candidate
        await self.save(proposed)
        session.state, session.revision = proposed.state, proposed.revision
        session.dx = session.dy = 0
        session.walked = 0
        if notify:
            await self.result(session.websocket, 0, state=session.state)
            await self.send(session.websocket, {"op": "notice", "kind": "admin",
                "text": "Your holding-cell time has ended. Your previous activity has been restored."})
        return True

    async def initialize_community(self):
        from .community import Community
        LOG.info('Starting ranked seasons and persistent tamer rivals...')
        service = Community(self.engine, self.database, self.config)
        started = time.monotonic()
        def load_saved_world():
            # A healthy large query or one-time history index build must not
            # hit the normal gameplay socket timeout during restoration.
            with self.database.loading_io():
                service.initialize()
        loading = asyncio.create_task(asyncio.to_thread(load_saved_world))
        try:
            while not loading.done():
                # This interval prints progress; it never cancels loading.
                # Large saved worlds have no overall startup time limit.
                done, _ = await asyncio.wait({loading}, timeout=15)
                if not done:
                    LOG.info('Still loading saved ranked seasons and rivals (%d seconds elapsed). '
                             'Loading has no overall timeout; keep this window open.',
                             round(time.monotonic() - started))
            await loading
        except asyncio.CancelledError:
            # Never close the database underneath a synchronous restore worker.
            # Finish its owned transaction/cleanup before propagating shutdown.
            try:
                await asyncio.shield(loading)
            finally:
                if service.ready:
                    await asyncio.to_thread(service.shutdown)
            raise
        self.community = service
        LOG.info('Tamer rivals ready after %.1f seconds. Ranked history and population progress are persistent.',
                 time.monotonic() - started)

    async def _send_encoded(self, ws, encoded, timeout=None):
        """Bound backpressure, closing a stalled socket before cancelling send."""
        limit = self.network["send_timeout"] if timeout is None else timeout
        task = asyncio.create_task(ws.send(encoded))
        try:
            done, _ = await asyncio.wait((task,), timeout=limit)
            if not done:
                LOG.warning("Closing stalled connection: peer=%r send_timeout=%gs last_ping_rtt_seconds=%r",
                            getattr(ws, "remote_address", None), limit, getattr(ws, "latency", None))
                # Cancelling a send is not a retry mechanism. Close first so
                # a partially transmitted message cannot be reused/replayed.
                with contextlib.suppress(Exception):
                    await ws.close(1013, f"Send stalled for {limit:g}s")
                raise asyncio.TimeoutError(f"Send stalled for {limit:g}s")
            task.result()
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def send(self, ws, message, timeout=None):
        encoded = json.dumps(message, separators=(",", ":"), allow_nan=False)
        await self._send_encoded(ws, encoded, timeout)

    async def _world_sender(self, session):
        """One bounded sender per player; never await it from the world tick."""
        try:
            while not self.stopping and not session.closing:
                group, encoded = await session.world_updates.get()
                try:
                    # Don't send a queued snapshot for a map the player left.
                    if group == self.place(session):
                        await self._send_encoded(session.websocket, encoded)
                finally:
                    session.world_updates.task_done()
        except (ConnectionClosed, asyncio.TimeoutError):
            # The socket is already closed (or _send_encoded closed it).
            pass
        except Exception:
            LOG.exception("World update failed for %s", session.key)
            with contextlib.suppress(Exception):
                await session.websocket.close(1011, "World update failed")
        finally:
            session.closing = True

    def _queue_world(self, session, group, encoded):
        if self.stopping or session.closing:
            return
        if session.world_sender is None:
            session.world_sender = asyncio.create_task(self._world_sender(session))
        elif session.world_sender.done():
            return
        if session.world_updates.full():
            session.world_updates.get_nowait()
            session.world_updates.task_done()
        session.world_updates.put_nowait((group, encoded))

    async def _stop_world_sender(self, session):
        session.closing = True
        task = session.world_sender
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        while not session.world_updates.empty():
            session.world_updates.get_nowait()
            session.world_updates.task_done()

    async def result(self, ws, rid, ok=True, **fields):
        await self.send(ws, {"op": "result", "rid": rid, "ok": ok, **fields})

    def economy_enabled(self):
        return bool(self.community and self.community.ready)

    async def refresh_wallet(self, session, notify=False):
        """Expose SQL wallet data without registering a private Story profile."""
        if self.community is None:
            # Preserve the legacy/offline-server state contract. Missing
            # feature/config metadata keeps newer clients' ruby controls off.
            session.state.pop("digirubies", None)
            session.state.pop("economy", None)
            return False
        before = (session.state.get("digirubies"), session.state.get("economy"))
        try:
            balance = (await asyncio.to_thread(self.database.wallet_balance, session.key)
                       if hasattr(self.database, "wallet_balance") else 0)
            session.state["digirubies"] = balance
            session.state["economy"] = economy_view(self.economy_enabled())
        except Exception:
            # A display refresh must never report a committed purchase/match as
            # failed. Disable checkout controls until the next successful read.
            LOG.warning("Wallet display refresh failed for %s", session.key, exc_info=True)
            session.state.setdefault("digirubies", 0)
            session.state["economy"] = economy_view(False)
        changed = before != (session.state["digirubies"], session.state["economy"])
        if notify and changed:
            await self.result(session.websocket, 0, wallet={"digirubies": session.state["digirubies"]},
                              economy=session.state["economy"])
        return changed

    async def checkout(self, session, message, operation):
        if not self.economy_enabled():
            raise ValueError("DigiRuby checkout is unavailable while the community service is offline.")
        reference = message.get("transaction_id")
        if reference is None:
            # Old clients still get per-session request idempotency; current
            # clients retain a transaction_id for retries across reconnects.
            reference = hashlib.sha256(f"{session.token}:{message['rid']}".encode()).hexdigest()
        result = await asyncio.to_thread(self.database.economy_transaction,
            session.key, session.state, session.revision, session.token,
            reference, operation, message, self.engine)
        # Publish the grant only after the SQL wallet/player/receipt commit.
        session.state, session.revision = result["state"], result["revision"]
        return result["receipt"]

    async def save(self, session):
        # Caller holds session.lock; all writes serialize with gameplay and logout.
        snapshot = copy.deepcopy(session.state)
        try:
            session.revision = await asyncio.to_thread(
                self.database.save, session.key, snapshot, session.revision, session.token)
            # Database.save commits the copied queue together with the player
            # revision. The live queue can be cleared only after that succeeds.
            session.state.pop("_season_archive_pending", None)
        except DatabaseError:
            raise
        except Exception as exc:
            raise DatabaseError("The player save could not be committed.") from exc

    async def authenticate(self, ws, ip, message):
        username, password = message.get("username"), message.get("password")
        key = validate_credentials(username, password)
        limiter = self.auth_limits.setdefault(ip, TokenBucket(1 / 10, 12))
        if not limiter.take():
            raise ValueError("Too many sign-in attempts. Please wait a minute.")
        # Expire old IP entries, but never evict live/active limits prematurely.
        if len(self.auth_limits) > 4096:
            cutoff = time.monotonic() - 1800
            self.auth_limits = {k: v for k, v in self.auth_limits.items() if v.updated > cutoff}
        async with self.authentication_slots:
            if message["op"] == "register":
                if not self.config.get("allow_registration", True):
                    raise ValueError("New account registration is disabled on this server.")
                state = self.engine.new_player(username, message.get("tamer"), message.get("starter"))
                await asyncio.to_thread(self.database.register, username, password, state)
            else:
                authenticated = await asyncio.to_thread(self.database.authenticate, username, password)
                if not authenticated:
                    raise ValueError("Tamer name or password is incorrect.")
            await self.check_ban(key)
            async with self.session_lock:
                # Local bans share this lock. Recheck after credentials and
                # serialization so a concurrent ban cannot race a new login.
                await self.check_ban(key)
                if key in self.sessions:
                    raise ValueError("This account is already online. Close the other client first.")
                if len(self.sessions) >= int(self.config.get("max_players", 500)):
                    raise ValueError("This world server is full. Try again shortly.")
                token = secrets.token_hex(32)
                if not await asyncio.to_thread(self.database.acquire_session, key, token):
                    raise ValueError("This account is already online. After a connection failure, wait up to 90 seconds.")
                try:
                    state, revision = await asyncio.to_thread(self.database.load, key)
                    state["events"] = []
                    # Add farm metadata to old saves without changing their location,
                    # existing battles, inventory or legacy storage contents.
                    if hasattr(self.engine, "_refresh"):
                        self.engine._refresh(state)
                    session = Session(ws, key, token, state, revision)
                    await self.expire_jail(session, notify=False)
                    if self.community and self.community.ready and self.shared_profile(session.state):
                        await asyncio.to_thread(self.community.register_player, copy.deepcopy(session.state))
                    await self.refresh_wallet(session)
                    self.sessions[key] = session
                except Exception:
                    await asyncio.to_thread(self.database.release_session, key, token)
                    raise
        LOG.info("Player connected: %s", key)
        return session

    async def connection(self, ws):
        remote = ws.remote_address
        ip = str(remote[0]) if remote else "unknown"
        self.connections_by_ip[ip] = self.connections_by_ip.get(ip, 0) + 1
        if self.stopping or self.connections_by_ip[ip] > 16:
            self.connections_by_ip[ip] -= 1
            await ws.close(1013, "Server connection limit reached")
            return
        session = None
        limiter = TokenBucket(80, 100)
        invalid_messages = 0
        try:
            await self.send(ws, {"op": "hello", "version": VERSION,
                "game": "Digimon Venom NXT", "tick_hz": 10, "movement_speed": MOVE_SPEED,
                "features": ["digifarm", "season", "story", "world_ds_story", "server_notices", "player_titles"] + (["ranked", "rivals", "bot_activity"] if self.community else []) + (["digiruby_economy"] if self.economy_enabled() else []),
                "registration": self.config.get("allow_registration", True)})
            while not self.stopping:
                try:
                    # Unauthenticated sockets cannot occupy a slot forever.
                    raw = await asyncio.wait_for(
                        ws.recv(), timeout=None if session else self.network["login_timeout"])
                except asyncio.TimeoutError:
                    await ws.close(1000, "Sign-in timed out")
                    break
                rid = 0
                try:
                    if not limiter.take():
                        await ws.close(1008, "Message rate exceeded")
                        break
                    if not isinstance(raw, str):
                        raise ValueError("Send a JSON text message.")
                    message = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON number.")))
                    if not isinstance(message, dict):
                        raise ValueError("A request must be a JSON object.")
                    rid = message.get("rid", 0)
                    if isinstance(rid, bool) or not isinstance(rid, int) or not 0 <= rid <= 2**31 - 1:
                        rid = 0
                        raise ValueError("Invalid request identifier.")
                    invalid_messages = max(0, invalid_messages - 1)
                    op = message.get("op")
                    if not isinstance(op, str) or len(op) > 32:
                        raise ValueError("Invalid operation.")
                    if op == "ping":
                        if session is not None and jail_expired(session.state):
                            async with session.lock:
                                if session.closing:
                                    raise ValueError("This session is disconnecting; no further actions are accepted.")
                                await self.expire_jail(session)
                        await self.result(ws, rid, server_time=time.time())
                        continue
                    if session is None:
                        if op not in ("register", "login"):
                            raise ValueError("Sign in before entering the Digital World.")
                        session = await self.authenticate(ws, ip, message)
                        await self.result(ws, rid, state=session.state)
                        continue
                    if op in ("login", "register"):
                        raise ValueError("You are already signed in.")
                    if op == "logout":
                        await self.result(ws, rid)
                        break
                    async with session.lock:
                        if session.closing:
                            raise ValueError("This session is disconnecting; no further actions are accepted.")
                        await self.expire_jail(session)
                        if is_jailed(session.state) and (op in GAME_OPS or op == "community"):
                            raise ValueError("You are in a private holding cell. Activities resume after release.")
                        if op == "move":
                            changed = self.move(session, message)
                            if changed:
                                await self.save(session)
                                await self.result(ws, rid, state=session.state)
                            else:
                                if session.state.get("in_farm"):
                                    position = {"space": "farm", **normalize_farm_position(session.state)}
                                else:
                                    position = {"space": "field", **{key: session.state[key]
                                        for key in ("map_id", "x", "y")}}
                                await self.result(ws, rid, position=position)
                        elif op == "chat":
                            await self.chat(session, message)
                            await self.result(ws, rid)
                        elif op == "community":
                            if self.in_story(session.state):
                                raise ValueError("Save & Return to World before visiting Ranked Arena or shared rivals.")
                            if self.in_season(session.state):
                                raise ValueError("Save & Return to World before visiting Ranked Arena or shared rivals.")
                            if not self.community:
                                raise ValueError("This server does not have ranked rivals enabled. Start the updated server first.")
                            bucket = self.community_rate.setdefault(session.key, TokenBucket(2, 8))
                            if not bucket.take():
                                raise ValueError("Please wait a moment before refreshing the community screens.")
                            if message.get("action") == "exchange":
                                receipt = await self.checkout(session, message, "exchange")
                                await self.result(ws, rid, state=session.state,
                                    community={"action": "exchange", "data": receipt})
                                continue
                            # No client can submit a battle outcome or change any bot state.
                            payload = await asyncio.to_thread(self.community.request,
                                copy.deepcopy(session.state), message, session.token)
                            await self.refresh_wallet(session)
                            await self.result(ws, rid, community=payload,
                                wallet={"digirubies": session.state["digirubies"]}, economy=session.state["economy"])
                        elif op == "season" and message.get("action") == "history":
                            if self.in_story(session.state):
                                raise ValueError("Save & Return to World before visiting your Season career.")
                            if not session.action_rate.take():
                                raise ValueError("Please wait a moment before refreshing career history.")
                            history = await asyncio.to_thread(self.database.season_history,
                                session.key, message.get("page", 0), message.get("page_size", 10))
                            await self.result(ws, rid, season_history=history)
                        elif op in GAME_OPS:
                            if not session.action_rate.take():
                                raise ValueError("Please wait a moment between actions.")
                            if op == "encounter" and time.monotonic() - session.last_encounter < 2:
                                raise ValueError("Take a breath before searching again.")
                            if op == "encounter" and self.in_story(session.state):
                                raise ValueError("Use Story training to search for Digimon on your private adventure.")
                            if op == "encounter" and self.in_season(session.state):
                                raise ValueError("Save & Return to World before searching for wild Digimon.")
                            if op == "shop" and message.get("currency") == "digirubies":
                                receipt = await self.checkout(session, message, "shop")
                                await self.result(ws, rid, state=session.state, economy_result=receipt)
                                continue
                            if op in ("shop", "digilab", "digifarm", "story", "season"):
                                await self.refresh_wallet(session)
                            # Invalid actions cannot partially mutate a live save.
                            candidate = copy.deepcopy(session.state)
                            self.engine.handle(candidate, op, message)
                            # Mode transitions must stay private until their
                            # save commits: the world tick reads without this
                            # session lock and must never publish an uncommitted
                            # return to the shared field.
                            committing = copy.copy(session)
                            committing.state = candidate
                            await self.save(committing)
                            session.state, session.revision = committing.state, committing.revision
                            if op == "encounter":
                                session.last_encounter = time.monotonic()
                            if op in ("digilab", "digifarm", "travel", "season", "story"):
                                session.dx = session.dy = 0
                                session.walked = 0
                            await self.result(ws, rid, state=session.state)
                        else:
                            raise ValueError("Unknown operation.")
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    invalid_messages += 1
                    detail = str(exc)[:240] if isinstance(exc, ValueError) else "Invalid request fields."
                    await self.result(ws, rid, ok=False, error=detail)
                    if invalid_messages > 80:
                        await ws.close(1008, "Too many invalid requests")
                        break
                except DatabaseError:
                    LOG.exception("Persistence/session failure for %s", session.key if session else "login")
                    await self.result(ws, rid, ok=False, error="The server could not safely save your session. Please reconnect.")
                    await ws.close(1011, "Save unavailable")
                    break
                except (ConnectionClosed, asyncio.TimeoutError):
                    raise
                except Exception:
                    LOG.exception("Request failed for %s", session.key if session else "login")
                    await self.result(ws, rid, ok=False, error="The server could not complete that request. Please try again.")
        except (ConnectionClosed, asyncio.TimeoutError) as exc:
            LOG.info("Connection ended for %s (%s): %s",
                     session.key if session else "not signed in", ip, exc)
        finally:
            LOG.info("Connection closed: player=%s peer=%s code=%s reason=%r",
                     session.key if session else "not signed in", ip,
                     getattr(ws, "close_code", None), getattr(ws, "close_reason", ""))
            self.connections_by_ip[ip] -= 1
            if not self.connections_by_ip[ip]:
                self.connections_by_ip.pop(ip, None)
            if session:
                await self._stop_world_sender(session)
                try:
                    async with session.lock:
                        await self.save(session)
                        if self.community and self.community.ready and self.shared_profile(session.state):
                            await asyncio.to_thread(self.community.register_player, copy.deepcopy(session.state))
                except Exception:
                    self.persistence_failed = True
                    LOG.exception("Failed final save for %s; retaining database lease for recovery", session.key)
                else:
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(self.database.release_session, session.key, session.token)
                async with self.session_lock:
                    if self.sessions.get(session.key) is session:
                        self.sessions.pop(session.key, None)
                        self.community_rate.pop(session.key, None)
                LOG.info("Player disconnected: %s", session.key)

    def _walkable(self, map_data, x, y):
        mask_path = map_data.get("walkable")
        if not mask_path:
            return True
        if mask_path not in self.masks:
            from PIL import Image
            with Image.open(self.root / mask_path) as image:
                self.masks[mask_path] = image.convert("L")
        mask = self.masks[mask_path]
        mx = max(0, min(mask.width - 1, int(x * mask.width / map_data["width"])))
        my = max(0, min(mask.height - 1, int(y * mask.height / map_data["height"])))
        return mask.getpixel((mx, my)) >= 128

    def move(self, session, message):
        values = []
        for name in ("dx", "dy", "dt"):
            v = message.get(name, 0)
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v):
                raise ValueError("Movement must contain finite numbers.")
            values.append(float(v))
        dx, dy, requested_dt = values
        if abs(dx) > 1 or abs(dy) > 1 or not 0 <= requested_dt <= 0.1:
            raise ValueError("Movement input is out of bounds.")
        # Late world movement packets cannot move a tamer or start a wild
        # encounter while their private league is open, including mid-battle.
        if self.in_season(session.state) or is_jailed(session.state):
            session.dx = session.dy = 0
            return False
        now = time.monotonic()
        session.move_credit = min(0.15, session.move_credit + max(0, now - session.last_move))
        session.last_move = now
        dt = min(requested_dt, session.move_credit)
        session.move_credit -= dt
        state = session.state
        state["events"] = []
        space = "farm" if state.get("in_farm") else "field"
        requested_space = message.get("space", space)
        if requested_space not in ("farm", "field"):
            raise ValueError("Unknown movement space.")
        # A delayed input queued before Home/Return cannot walk in the new space.
        if requested_space != space or state.get("battle") or state.get("in_lab"):
            session.dx = session.dy = 0
            return False
        length = math.hypot(dx, dy)
        if length > 1:
            dx, dy = dx / length, dy / length
        session.dx, session.dy = dx, dy
        if state.get("in_farm"):
            position = normalize_farm_position(state)
            position["x"], position["y"] = move_farm_position(
                (position["x"], position["y"]), dx, dy, dt, MOVE_SPEED)
            if dx or dy:
                position["direction"] = (("down" if dy > 0 else "up") + ("_right" if dx > 0 else "_left")
                    if dx and dy else ("down" if dy > 0 else "up") if dy else ("right" if dx > 0 else "left"))
            # Regular movement uses the same autosave/disconnect persistence as
            # fields. Home never accrues walking encounters or mutates map x/y.
            return False
        map_data = self.engine.maps[state["map_id"]]
        old_x, old_y = float(state["x"]), float(state["y"])
        x = min(max(12, old_x + dx * MOVE_SPEED * dt), max(12, map_data["width"] - 12))
        y = min(max(12, old_y + dy * MOVE_SPEED * dt), max(12, map_data["height"] - 12))
        # Axis-separated resolution lets players slide along walls instead of stick.
        steps = max(1, math.ceil(max(abs(x - old_x), abs(y - old_y))))
        step_x, step_y = (x - old_x) / steps, (y - old_y) / steps
        for _ in range(steps):
            if self._walkable(map_data, state["x"] + step_x, state["y"]):
                state["x"] += step_x
            if self._walkable(map_data, state["x"], state["y"] + step_y):
                state["y"] += step_y
        state["x"], state["y"] = round(state["x"], 3), round(state["y"], 3)
        # Story keeps normal map collision and walking, but its authored NPC
        # battles and training encounters are the only way to start combat.
        if self.in_story(state):
            session.walked = 0
            return False
        session.walked += math.hypot(state["x"] - old_x, state["y"] - old_y)
        if session.walked >= session.next_encounter and map_data.get("encounters", True):
            candidate = copy.deepcopy(state)
            try:
                self.engine.handle(candidate, "encounter", {})
            except ValueError:
                session.walked = 0
                return False
            session.state = candidate
            session.last_encounter = now
            session.walked = 0
            session.next_encounter = 650 + secrets.randbelow(550)
            session.dx = session.dy = 0
            return True  # Save encounter immediately; regular movement autosaves.
        return False

    async def chat(self, session, message):
        if self.in_season(session.state):
            raise ValueError("Save & Return to World before using world chat.")
        raw = message.get("text")
        if not isinstance(raw, str) or not 1 <= len(raw) <= 240:
            raise ValueError("Chat messages must contain 1–240 characters.")
        text = "".join(c for c in raw if c.isprintable()).strip()
        if not text:
            raise ValueError("Chat message is empty.")
        if text.startswith("/"):
            raise ValueError("Commands are available only in the local world-server console; player chat has no commands.")
        now = time.monotonic()
        if now - session.last_chat < 0.75:
            raise ValueError("Please wait a moment before chatting again.")
        session.last_chat = now
        data = {"op": "chat", "username": session.state["username"], "text": text}
        peers = [s for s in self.sessions.values() if self.same_place(session, s)]
        await asyncio.gather(*(self.send(s.websocket, data) for s in peers), return_exceptions=True)

    @staticmethod
    def in_season(state):
        battle = state.get("battle") or {}
        return bool(state.get("in_season") or battle.get("kind") == "season" or battle.get("season"))

    @staticmethod
    def in_story(state):
        battle = state.get("battle") or {}
        return bool(state.get("in_story") or battle.get("kind") == "story")

    @staticmethod
    def shared_profile(state):
        """Only the active MMO team may be published to shared competitors.

        Detention can temporarily clear an activity flag while its party is
        still active, so every jailed profile is excluded as well.
        """
        return not (WorldServer.in_season(state) or WorldServer.in_story(state) or is_jailed(state))

    @staticmethod
    def place(session):
        state = session.state
        if is_jailed(state):
            return (state["map_id"], "jail", session.key)
        if WorldServer.in_season(state):
            return (state["map_id"], "season", session.key)
        if WorldServer.in_story(state):
            return (state["map_id"], "story", session.key)
        if state.get("in_farm"):
            return (state["map_id"], "farm", session.key)
        return (state["map_id"], "lab" if state.get("in_lab") else "field", None)

    @staticmethod
    def same_place(a, b):
        return WorldServer.place(a) == WorldServer.place(b)

    async def broadcast_once(self):
        sessions = [s for s in self.sessions.values() if not s.closing]
        groups = {}
        snapshot_places = {}
        now = time.monotonic()
        for s in sessions:
            state = s.state
            group = self.place(s)
            snapshot_places[s.key] = group
            moving = now - s.last_move < 0.2 and not (state.get("battle") or state.get("in_farm") or state.get("in_lab") or self.in_season(state) or is_jailed(state))
            groups.setdefault(group, []).append({"username": state["username"], "tamer": state["tamer"],
                "map_id": state["map_id"], "x": state["x"], "y": state["y"],
                "dx": s.dx if moving else 0, "dy": s.dy if moving else 0,
                "lead": state["party"][0]["species_id"] if state.get("party") else None,
                "battle": bool(state.get("battle")), "in_lab": bool(state.get("in_lab")),
                "in_farm": bool(state.get("in_farm")), "in_season": self.in_season(state),
                "in_story": self.in_story(state),
                "in_jail": is_jailed(state), "active_title": str(state.get("active_title") or "")[:32]})
        if self.community and self.community.ready:
            # Each occupied field has one shared bot snapshot at the same server
            # timestamp. No client receives the entire rival population.
            fields = {group[0] for group in groups if group[1] == "field"}
            rivals = await asyncio.to_thread(self.community.snapshots, fields, now)
            for group, actors in groups.items():
                if group[1] == "field":
                    actors.extend(rivals.get(group[0], []))
        # Queue independently: a stalled player must not slow the 10 Hz tick.
        # At most one snapshot is sending and one newer snapshot is waiting.
        stamp = time.time()
        self.world_sequence += 1
        encoded = {group:json.dumps({"op":"world", "players":actors, "server_time":stamp,
                                    "scope":group, "sequence":self.world_sequence},
                   separators=(",", ":"), allow_nan=False) for group,actors in groups.items()}
        for s in sessions:
            group = snapshot_places[s.key]
            self._queue_world(s, group, encoded[group])

    async def world_loop(self):
        while not self.stopping:
            start = time.monotonic()
            await self.broadcast_once()
            await self.pause(max(0.005, 0.1 - (time.monotonic() - start)))

    async def pause(self, delay):
        """Wake promptly for shutdown without cancelling an in-flight SQL worker."""
        if self.stop_signal is None:
            await asyncio.sleep(delay)
        else:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.stop_signal.wait(), delay)

    async def autosave_loop(self):
        while not self.stopping:
            await self.pause(20)
            if self.stopping or (self.stop_signal is not None and self.stop_signal.is_set()):
                break
            for session in list(self.sessions.values()):
                try:
                    async with session.lock:
                        await self.save(session)
                        if self.community and self.community.ready and self.shared_profile(session.state):
                            await asyncio.to_thread(self.community.register_player, copy.deepcopy(session.state))
                        await self.refresh_wallet(session, notify=True)
                except Exception:
                    LOG.exception("Autosave failed for %s", session.key)
                    with contextlib.suppress(Exception):
                        await session.websocket.close(1011, "Autosave unavailable")

    async def community_loop(self):
        previous = time.monotonic()
        next_invites = previous+10
        while not self.stopping:
            started = time.monotonic()
            try:
                await asyncio.to_thread(self.community.step, started, min(1., started-previous))
                if started >= next_invites:
                    states = [copy.deepcopy(s.state) for s in self.sessions.values() if self.shared_profile(s.state)]
                    await asyncio.to_thread(self.community.invitations, states, started)
                    next_invites = started+10
            except Exception:
                self.persistence_failed = True
                LOG.exception('Community simulation stopped to protect persistent progress.')
                if self.stop_signal is not None:
                    self.stop_signal.set()
                return
            previous = started
            await self.pause(max(.005, .1-(time.monotonic()-started)))

    async def moderation_loop(self):
        while not self.stopping:
            for session in list(self.sessions.values()):
                if session.closing or not jail_expired(session.state):
                    continue
                try:
                    async with session.lock:
                        await self.expire_jail(session)
                except (ConnectionClosed, asyncio.TimeoutError):
                    pass
                except Exception:
                    LOG.exception("Could not safely release holding cell for %s", session.key)
                    with contextlib.suppress(Exception):
                        await session.websocket.close(1011, "Moderation save unavailable")
            await self.pause(1)


def read_config(path, dev=False):
    root = project_root()
    path = root / path if path else root / "config/server.json"
    if path.is_file():
        config = json.loads(path.read_text(encoding="utf-8"))
    elif dev:
        config = {}
    else:
        raise ValueError("Server is not configured. Run 01_SETUP_SERVER.bat first.")
    if not isinstance(config, dict):
        raise ValueError("Server configuration must be a JSON object.")
    if dev:
        config.update({"host": "127.0.0.1", "database": {"driver": "sqlite", "path": str(root / "runtime/development.sqlite3")}})
        config.setdefault("port", 8765)
    else:
        if config.get("database", {}).get("driver", "mysql") != "mysql":
            raise ValueError("A public dedicated server requires MySQL.")
        if not config.get("tls_cert") or not config.get("tls_key"):
            raise ValueError("A public dedicated server requires a TLS certificate and private key.")
    return config


def tls_context(config, root=None):
    root = Path(root or project_root())
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(root / config["tls_cert"]), str(root / config["tls_key"]))
    return context


async def run(config, dev=False, stop=None):
    root = project_root()
    from venom.server.local_console import LocalConsole
    options = config.get("console", {})
    if not isinstance(options, dict):
        raise ValueError("The console configuration must be an object.")
    console = LocalConsole(asyncio.get_running_loop()) if options.get("enabled", True) else None
    try:
        with WorldProcessLock(root) as control:
            while True:
                restart = await _run_world(config, root, dev, stop, control, console)
                if not restart or control.stop_requested():
                    break
                LOG.info("Restarting world in this process after all saves and leases were closed...")
                if stop is not None:
                    stop.clear()
                control.update("starting")
            control.mark_stopped()
    finally:
        if console is not None:
            console.close()


async def _run_world(config, root, dev, stop, control, console=None):
    """Finish every database worker and final save before confirming shutdown."""
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    old_handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            previous = signal.getsignal(sig)
            loop.add_signal_handler(sig, stop.set)
            old_handlers[sig] = (previous, True)
        except (NotImplementedError, RuntimeError, ValueError):
            # Windows ProactorEventLoop has no add_signal_handler support.
            # A real signal handler keeps Ctrl+C on the same graceful path as
            # the stop batch file instead of cancelling database worker tasks.
            try:
                previous = signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
                old_handlers[sig] = (previous, False)
            except (ValueError, OSError):
                pass

    async def watch_stop_request():
        while not stop.is_set():
            if control.stop_requested():
                LOG.info("Stop requested. Saving players and rival progress...")
                stop.set()
                return
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), 0.2)

    monitor = asyncio.create_task(watch_stop_request())
    db = None
    world = None
    admin = None
    tasks = []
    try:
        context = None if dev else tls_context(config, root)
        db = Database(config["database"], dev=dev, root=root)
        await asyncio.to_thread(db.initialize)
        engine = GameEngine(root)
        world = WorldServer(engine, db, config)
        world.stop_signal = stop
        await world.initialize_community()
        if console is not None:
            from venom.server.admin_commands import AdminConsole
            admin = AdminConsole(world, role=config.get("console", {}).get("role", "OWNER"))

        def background_finished(task):
            if task.cancelled():
                return
            error = task.exception()
            if error is not None:
                world.persistence_failed = True
                LOG.error("World background task failed; stopping to protect saves.",
                          exc_info=(type(error), error, error.__traceback__))
                stop.set()

        async with serve(world.connection, config.get("host", "0.0.0.0"), int(config.get("port", 8765)),
                         ssl=context, origins=[None], max_size=MAX_MESSAGE, max_queue=16,
                         compression=None, extensions=transport_extensions(),
                         ping_interval=world.network["ping_interval"],
                         ping_timeout=world.network["ping_timeout"], close_timeout=world.network["close_timeout"],
                         open_timeout=world.network["open_timeout"], server_header=None) as listener:
            tasks = [asyncio.create_task(world.world_loop()), asyncio.create_task(world.autosave_loop()),
                     asyncio.create_task(world.community_loop()), asyncio.create_task(world.moderation_loop())]
            for task in tasks:
                task.add_done_callback(background_finished)
            control.update("running")
            LOG.info("Digimon Venom NXT %s | %s://%s:%s | %s", VERSION, "ws (LOCAL DEV)" if dev else "wss",
                     config.get("host"), config.get("port"), db.driver)
            LOG.info("Network seconds: ping_interval=%g ping_timeout=%g open_timeout=%g "
                     "send_timeout=%g login_timeout=%g",
                     world.network["ping_interval"], world.network["ping_timeout"],
                     world.network["open_timeout"], world.network["send_timeout"], world.network["login_timeout"])
            LOG.info("World ready. Ctrl+C saves players and shuts down.")
            if admin is not None and not console.attach(admin):
                LOG.info("Local console disabled: no interactive terminal. The world remains running.")
            await stop.wait()
            world.stopping = True
            control.update("stopping")
            if admin is not None:
                console.detach(admin)
                await admin.close()
            listener.close()
            # Cooperative completion matters: cancelling asyncio.to_thread
            # leaves its SQL operation running in the background.
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        stop.set()
        if world is not None:
            world.stopping = True
        try:
            if admin is not None:
                console.detach(admin)
                await admin.close()
            await asyncio.gather(*tasks, monitor, return_exceptions=True)
            if world is not None and world.community:
                await asyncio.to_thread(world.community.shutdown)
        finally:
            try:
                # The listener has awaited player finalizers; the workers and
                # final rival checkpoint have finished before MySQL can stop.
                if db is not None:
                    await asyncio.to_thread(db.close)
            finally:
                for sig, (previous, used_loop) in old_handlers.items():
                    if used_loop:
                        loop.remove_signal_handler(sig)
                    with contextlib.suppress(ValueError, OSError):
                        signal.signal(sig, previous)
    if world is not None and world.persistence_failed:
        raise DatabaseError("The world stopped with a save error. MySQL must remain running; check runtime/logs/server.log.")
    LOG.info("World stopped cleanly. Players and rival progress are saved.")
    return bool(world is not None and world.restart_requested)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Digimon Venom NXT dedicated world server")
    parser.add_argument("--dev", action="store_true", help="Localhost-only plaintext development server using SQLite")
    parser.add_argument("--config", help="Path to server JSON configuration")
    args = parser.parse_args(argv)
    root = project_root()
    (root / "runtime/logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(root / "runtime/logs/server.log", encoding="utf-8")])
    logging.getLogger("websockets").setLevel(logging.WARNING)
    try:
        config = read_config(args.config, args.dev)
        asyncio.run(run(config, args.dev))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        LOG.error("Server could not start: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
