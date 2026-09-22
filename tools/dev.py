"""Bootstrap a separate local-only development environment and run one application."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("server", "client"))
    args, forwarded = parser.parse_known_args(argv)
    try:
        if sys.version_info < (3, 11) or struct.calcsize("P") != 8:
            raise RuntimeError("Use 64-bit Python 3.11 or newer.")
        environment = ROOT / ".venv-dev"
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        marker = environment / "runtime-requirements.sha256"
        required = hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest()
        installed = marker.read_text() if marker.is_file() else ""
        if args.role == "client" and (not python.is_file() or installed != required):
            raise RuntimeError("Run START_LOCAL_DEV.bat first and wait for the local world server to start; then launch PLAY_LOCAL_DEV.bat.")
        if not python.is_file():
            venv.EnvBuilder(with_pip=True).create(environment)
        if installed != required:
            print("Installing dependencies for the isolated local development environment...", flush=True)
            subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], cwd=ROOT, check=True)
            subprocess.run([str(python), "-m", "pip", "check"], cwd=ROOT, check=True)
            marker.write_text(required)
        print("LOCAL DEVELOPMENT ONLY - loopback connection and SQLite. Public hosting settings are unchanged.", flush=True)
        return subprocess.call([str(python), "-m", f"venom.{args.role}.main", "--dev", *forwarded], cwd=ROOT)
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"LOCAL DEVELOPMENT FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
