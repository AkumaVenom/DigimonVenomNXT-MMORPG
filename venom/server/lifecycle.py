"""Local, authenticated stop requests and a crash-safe world/maintenance lock.

The operating system releases the lock after a crash; a leftover PID file is
never used as proof that a process is alive or that it exited cleanly.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import secrets
import time


class WorldControlError(RuntimeError):
    pass


def _atomic_json(path, payload):
    path = Path(path)
    temporary = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def read_world_control(root):
    try:
        value = json.loads((Path(root) / "runtime/world-control.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise WorldControlError("Could not read the world shutdown status.") from exc
    if not isinstance(value, dict):
        raise WorldControlError("The world shutdown status is invalid.")
    return value


class WorldProcessLock:
    """Hold for the entire world lifetime, or maintenance with publish=False.

    Maintenance takes the same lock while stopping MySQL so
    a world cannot start halfway through those operations. Never delete the
    lock file: its identity must remain stable across processes.
    """
    def __init__(self, root, publish=True):
        self.root = Path(root)
        self.publish = publish
        self.token = secrets.token_hex(32)
        self.stream = None
        self.clean = False

    def __enter__(self):
        runtime = self.root / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        stream = (runtime / "world.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(stream.fileno()).st_size == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            raise WorldControlError("The world is already running, or server maintenance is in progress.") from exc
        self.stream = stream
        try:
            if self.publish:
                self.update("starting")
        except BaseException:
            self._release()
            raise
        return self

    def update(self, state, **details):
        if not self.publish or self.stream is None:
            raise WorldControlError("This lock does not own the world status.")
        _atomic_json(self.root / "runtime/world-control.json", {
            "pid": os.getpid(), "token": self.token, "state": state,
            "updated_at": time.time(), **details,
        })

    def stop_requested(self):
        try:
            value = json.loads((self.root / "runtime/world-stop.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(value, dict) and value.get("token") == self.token

    def mark_stopped(self):
        self.update("stopped", clean=True)
        self.clean = True

    def _release(self):
        if self.stream is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()
            self.stream = None

    def __exit__(self, kind, error, traceback):
        try:
            if self.publish and (kind is not None or not self.clean):
                self.update("failed", clean=False,
                            error=str(error or "World exited before all saves were confirmed.")[:500])
        finally:
            self._release()


def is_world_running(root):
    try:
        with WorldProcessLock(root, publish=False):
            return False
    except WorldControlError:
        return True


def request_world_stop(root, timeout=120):
    """Wait for confirmed final saves and the released lock, never kill a PID.

    A server that has never run needs no shutdown. Stale/crashed/failed records
    are deliberately not treated as successful stops for backup purposes.
    """
    root = Path(root)
    control = read_world_control(root)
    if not is_world_running(root):
        if control is None or (control.get("state") == "stopped" and control.get("clean") is True):
            return
        raise WorldControlError("The previous world did not confirm a clean save. Restart it and stop it cleanly before backup.")
    if not control or not isinstance(control.get("token"), str):
        raise WorldControlError("The world or maintenance is running without a readable stop token. Try again shortly.")
    if control.get("state") not in {"starting", "running", "stopping"}:
        raise WorldControlError("Server maintenance is in progress or the world shutdown status is inconsistent.")
    token = control["token"]
    _atomic_json(root / "runtime/world-stop.json", {"token": token, "requested_at": time.time()})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_world_running(root):
            final = read_world_control(root)
            if final and final.get("token") == token and final.get("state") == "stopped" and final.get("clean") is True:
                return
            raise WorldControlError("The world exited without confirming all saves. MySQL has been left running for recovery.")
        time.sleep(0.15)
    raise WorldControlError("The world is still saving or shutting down. MySQL has been left running; check runtime/logs/server.log.")
