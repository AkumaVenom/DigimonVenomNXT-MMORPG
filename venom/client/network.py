"""Threaded asyncio transport. The render thread never waits for the server."""
from __future__ import annotations

import asyncio
import json
import queue
import ssl
import threading
from pathlib import Path

from venom.common.network import network_settings


class Connection:
    def __init__(self, config: dict, root: Path, dev: bool = False):
        self.config, self.root, self.dev = config, root, dev
        self.incoming: queue.Queue = queue.Queue()
        self.outgoing: queue.Queue = queue.Queue(maxsize=100)
        self.connected = False
        self.status = 'Connecting…'
        self.running = True
        self.rid = 0
        self.thread = threading.Thread(target=self._run, daemon=True, name='venom-network')
        self.thread.start()

    def send(self, op: str, **payload):
        self.rid += 1
        message = {'op': op, 'rid': self.rid, **payload}
        try:
            self.outgoing.put_nowait(message)
        except queue.Full:
            if op != 'move':
                self.incoming.put({'op': 'error', 'error': 'Connection is busy. Please try again.'})
        return self.rid

    def _run(self):
        try:
            asyncio.run(self._session())
        except Exception as exc:
            self.connected = False
            self.status = 'Disconnected'
            host, port = self.config.get('host', 'localhost'), self.config.get('port', 8765)
            if isinstance(exc, ssl.SSLCertVerificationError):
                message = 'Server certificate verification failed. Obtain a current player kit from your administrator.'
            elif isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
                message = f'Connection to {host}:{port} timed out. Check your connection and try signing in again.'
            elif isinstance(exc, OSError):
                message = f'Cannot reach {host}:{port}. Check that the world server is running and the hosting address is correct.'
            else:
                message = str(exc)
            if self.running:
                self.incoming.put({'op': 'error', 'error': message, 'detail': str(exc)})

    async def _session(self):
        import websockets
        host = self.config.get('host', 'localhost')
        port = int(self.config.get('port', 8765))
        tls = not self.dev
        if not tls and host not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('Development mode is restricted to a local server.')
        if tls and self.config.get('tls', True) is False:
            raise ValueError('Public connections require TLS. Use the server administrator’s player kit.')
        settings = network_settings(self.config)
        options = {'max_size': 8 * 1024 * 1024,
                   **{name: settings[name] for name in
                      ('ping_interval', 'ping_timeout', 'open_timeout', 'close_timeout')}}
        if tls:
            ca = self.root / self.config.get('ca_file', 'config/server-ca.pem')
            if not ca.is_file():
                raise ValueError('Trusted server certificate missing. Install the public player kit in this folder.')
            context = ssl.create_default_context(cafile=str(ca))
            options.update(ssl=context, server_hostname=self.config.get('server_name') or host)
        url_host = f'[{host}]' if ':' in host and not host.startswith('[') else host
        async with websockets.connect(f'{"wss" if tls else "ws"}://{url_host}:{port}', **options) as socket:
            self.connected, self.status = True, 'Connected'
            self.incoming.put({'op': 'connected'})
            async def send_loop():
                while self.running:
                    try:
                        message = self.outgoing.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(.008)
                        continue
                    await socket.send(json.dumps(message, separators=(',', ':')))
                await socket.close()
            async def receive_loop():
                async for raw in socket:
                    try:
                        message = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if isinstance(message, dict):
                        self.incoming.put(message)
            sender = asyncio.create_task(send_loop())
            receiver = asyncio.create_task(receive_loop())
            try:
                done, pending = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
            finally:
                for task in (sender, receiver):
                    if not task.done(): task.cancel()
                await asyncio.gather(sender, receiver, return_exceptions=True)
                self.connected = False
                self.status = 'Disconnected'
        # Only report a normal remote close here. Errors propagate to _run(),
        # which reports the actual cause once instead of a second generic error.
        if self.running:
            code = getattr(socket, 'close_code', None)
            reason = getattr(socket, 'close_reason', '') or ''
            message = 'Connection closed. Return to sign in to reconnect.'
            if reason:
                message = f'{reason}. Return to sign in to reconnect.'
            self.incoming.put({'op': 'error', 'error': message,
                               'detail': f'WebSocket close code={code}; reason={reason}'})

    def close(self):
        self.running = False
