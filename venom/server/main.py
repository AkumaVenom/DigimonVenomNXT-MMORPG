"""Dedicated authoritative WSS world server for Digimon Venom NXT."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
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

from venom.common.game import GameEngine
from venom.common.paths import root_path
from venom.server.database import Database, DatabaseError, validate_credentials

LOG = logging.getLogger("venom.server")
VERSION = "0.2.0"
MOVE_SPEED = 180.0
MAX_MESSAGE = 65_536
GAME_OPS = {"encounter", "battle", "digilab", "materialize", "evolve", "party", "shop", "item", "travel"}


def project_root():
    return root_path()


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


class WorldServer:
    def __init__(self, engine, database, config):
        self.engine, self.database, self.config = engine, database, config
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
        self.community_rate = {}

    async def initialize_community(self):
        from .community import Community
        LOG.info('Starting ranked seasons and persistent tamer rivals...')
        service = Community(self.engine, self.database, self.config)
        await asyncio.to_thread(service.initialize)
        self.community = service
        LOG.info('Tamer rivals ready. Ranked history and population progress are persistent.')

    async def send(self, ws, message, timeout=5):
        # Bound backpressure so an unresponsive peer can't stall shutdown or a map.
        await asyncio.wait_for(ws.send(json.dumps(message, separators=(",", ":"), allow_nan=False)), timeout=timeout)

    async def result(self, ws, rid, ok=True, **fields):
        await self.send(ws, {"op": "result", "rid": rid, "ok": ok, **fields})

    async def save(self, session):
        # Caller holds session.lock; all writes serialize with gameplay and logout.
        snapshot = copy.deepcopy(session.state)
        try:
            session.revision = await asyncio.to_thread(
                self.database.save, session.key, snapshot, session.revision, session.token)
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
            async with self.session_lock:
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
                    session = Session(ws, key, token, state, revision)
                    if self.community and self.community.ready:
                        await asyncio.to_thread(self.community.register_player, copy.deepcopy(state))
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
                "features": ["ranked", "rivals", "bot_activity"] if self.community else [],
                "registration": self.config.get("allow_registration", True)})
            while not self.stopping:
                try:
                    # Unauthenticated sockets cannot occupy a slot forever.
                    raw = await asyncio.wait_for(ws.recv(), timeout=None if session else 30)
                except asyncio.TimeoutError:
                    await ws.close(1000, "Connection idle")
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
                        if op == "move":
                            changed = self.move(session, message)
                            if changed:
                                await self.save(session)
                                await self.result(ws, rid, state=session.state)
                            else:
                                await self.result(ws, rid, position={key: session.state[key]
                                    for key in ("map_id", "x", "y")})
                        elif op == "chat":
                            await self.chat(session, message)
                            await self.result(ws, rid)
                        elif op == "community":
                            if not self.community:
                                raise ValueError("This server does not have ranked rivals enabled. Start the updated server first.")
                            bucket = self.community_rate.setdefault(session.key, TokenBucket(2, 8))
                            if not bucket.take():
                                raise ValueError("Please wait a moment before refreshing the community screens.")
                            # No client can submit a battle outcome or change any bot state.
                            payload = await asyncio.to_thread(self.community.request,
                                copy.deepcopy(session.state), message, session.token)
                            await self.result(ws, rid, community=payload)
                        elif op in GAME_OPS:
                            if not session.action_rate.take():
                                raise ValueError("Please wait a moment between actions.")
                            if op == "encounter" and time.monotonic() - session.last_encounter < 2:
                                raise ValueError("Take a breath before searching again.")
                            # Invalid actions cannot partially mutate a live save.
                            candidate = copy.deepcopy(session.state)
                            self.engine.handle(candidate, op, message)
                            previous = session.state
                            session.state = candidate
                            try:
                                await self.save(session)
                            except Exception:
                                session.state = previous
                                raise
                            if op == "encounter":
                                session.last_encounter = time.monotonic()
                            if op in ("digilab", "travel"):
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
                except Exception:
                    LOG.exception("Request failed for %s", session.key if session else "login")
                    await self.result(ws, rid, ok=False, error="The server could not complete that request. Please try again.")
        except (ConnectionClosed, asyncio.TimeoutError):
            pass
        finally:
            self.connections_by_ip[ip] -= 1
            if not self.connections_by_ip[ip]:
                self.connections_by_ip.pop(ip, None)
            if session:
                try:
                    async with session.lock:
                        await self.save(session)
                        if self.community and self.community.ready:
                            await asyncio.to_thread(self.community.register_player, copy.deepcopy(session.state))
                except Exception:
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
        now = time.monotonic()
        session.move_credit = min(0.15, session.move_credit + max(0, now - session.last_move))
        session.last_move = now
        dt = min(requested_dt, session.move_credit)
        session.move_credit -= dt
        state = session.state
        state["events"] = []
        if state.get("battle") or state.get("in_lab"):
            session.dx = session.dy = 0
            return False
        length = math.hypot(dx, dy)
        if length > 1:
            dx, dy = dx / length, dy / length
        session.dx, session.dy = dx, dy
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
        raw = message.get("text")
        if not isinstance(raw, str) or not 1 <= len(raw) <= 240:
            raise ValueError("Chat messages must contain 1–240 characters.")
        text = "".join(c for c in raw if c.isprintable()).strip()
        if not text:
            raise ValueError("Chat message is empty.")
        now = time.monotonic()
        if now - session.last_chat < 0.75:
            raise ValueError("Please wait a moment before chatting again.")
        session.last_chat = now
        data = {"op": "chat", "username": session.state["username"], "text": text}
        peers = [s for s in self.sessions.values() if self.same_place(session, s)]
        await asyncio.gather(*(self.send(s.websocket, data) for s in peers), return_exceptions=True)

    @staticmethod
    def same_place(a, b):
        return (a.state["map_id"], bool(a.state.get("in_lab"))) == (b.state["map_id"], bool(b.state.get("in_lab")))

    async def broadcast_once(self):
        sessions = list(self.sessions.values())
        groups = {}
        snapshot_places = {}
        now = time.monotonic()
        for s in sessions:
            state = s.state
            group = (state["map_id"], bool(state.get("in_lab")))
            snapshot_places[s.key] = group
            moving = now - s.last_move < 0.2 and not state.get("battle")
            groups.setdefault(group, []).append({"username": state["username"], "tamer": state["tamer"],
                "map_id": state["map_id"], "x": state["x"], "y": state["y"],
                "dx": s.dx if moving else 0, "dy": s.dy if moving else 0,
                "lead": state["party"][0]["species_id"] if state.get("party") else None,
                "battle": bool(state.get("battle")), "in_lab": bool(state.get("in_lab"))})
        if self.community and self.community.ready:
            # Each occupied field has one shared bot snapshot at the same server
            # timestamp. No client receives the entire 5,000-rival population.
            fields = {map_id for map_id, in_lab in groups if not in_lab}
            rivals = await asyncio.to_thread(self.community.snapshots, fields, now)
            for group, actors in groups.items():
                if not group[1]:
                    actors.extend(rivals.get(group[0], []))
        # Per-recipient async sends avoid the unbounded-buffer broadcast helper.
        stamp = time.time()
        encoded = {group:json.dumps({"op":"world", "players":actors, "server_time":stamp},
                   separators=(",", ":"), allow_nan=False) for group,actors in groups.items()}
        async def deliver(s):
            try:
                group = snapshot_places[s.key]
                await asyncio.wait_for(s.websocket.send(encoded[group]), timeout=0.06)
            except (ConnectionClosed, asyncio.TimeoutError):
                with contextlib.suppress(Exception):
                    await s.websocket.close(1013, "Slow connection")
        await asyncio.gather(*(deliver(s) for s in sessions))

    async def world_loop(self):
        while not self.stopping:
            start = time.monotonic()
            await self.broadcast_once()
            await asyncio.sleep(max(0.005, 0.1 - (time.monotonic() - start)))

    async def autosave_loop(self):
        while not self.stopping:
            await asyncio.sleep(20)
            for session in list(self.sessions.values()):
                try:
                    async with session.lock:
                        await self.save(session)
                        if self.community and self.community.ready:
                            await asyncio.to_thread(self.community.register_player, copy.deepcopy(session.state))
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
                    states = [copy.deepcopy(s.state) for s in self.sessions.values()]
                    await asyncio.to_thread(self.community.invitations, states, started)
                    next_invites = started+10
            except Exception:
                LOG.exception('Community simulation stopped to protect persistent progress.')
                if self.stop_signal is not None:
                    self.stop_signal.set()
                return
            previous = started
            await asyncio.sleep(max(.005, .1-(time.monotonic()-started)))


def read_config(path, dev=False):
    root = project_root()
    path = Path(path) if path else root / "config/server.json"
    if path.is_file():
        config = json.loads(path.read_text(encoding="utf-8"))
    elif dev:
        config = {}
    else:
        raise ValueError("Server is not configured. Run 02_SETUP_MYSQL.bat and 03_SETUP_PUBLIC_HOST.bat first.")
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
    context = None if dev else tls_context(config, root)
    db = Database(config["database"], dev=dev)
    await asyncio.to_thread(db.initialize)
    try:
        engine = GameEngine(root)
        world = WorldServer(engine, db, config)
        await world.initialize_community()
    except Exception:
        await asyncio.to_thread(db.close)
        raise
    stop = stop or asyncio.Event()
    world.stop_signal = stop
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop.set)
    tasks = []
    try:
        async with serve(world.connection, config.get("host", "0.0.0.0"), int(config.get("port", 8765)),
                         ssl=context, origins=[None], max_size=MAX_MESSAGE, max_queue=16,
                         compression=None, ping_interval=20, ping_timeout=20, close_timeout=5,
                         open_timeout=10, server_header=None):
            tasks = [asyncio.create_task(world.world_loop()), asyncio.create_task(world.autosave_loop()),
                     asyncio.create_task(world.community_loop())]
            LOG.info("Digimon Venom NXT %s | %s://%s:%s | %s", VERSION, "ws (LOCAL DEV)" if dev else "wss",
                     config.get("host"), config.get("port"), db.driver)
            LOG.info("World ready. Ctrl+C saves players and shuts down.")
            await stop.wait()
            world.stopping = True
    finally:
        world.stopping = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if world.community:
                await asyncio.to_thread(world.community.shutdown)
        finally:
            # serve's context has awaited connection finalizers and their saves.
            # Release the connection even if the final bot checkpoint fails.
            await asyncio.to_thread(db.close)
        LOG.info("World stopped. Player sessions closed.")


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
