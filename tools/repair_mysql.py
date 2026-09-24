"""Bootstrap the portable database setup dependencies for source installations."""
from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path
import subprocess
import sys
import venv


REQUIRED = {"PyMySQL": "1.1.1", "cryptography": "46.0.0"}


def dependencies_ready() -> bool:
    """Reuse the build environment when its tested setup dependencies are present."""
    try:
        return all(importlib.metadata.version(name) == version
                   for name, version in REQUIRED.items())
    except importlib.metadata.PackageNotFoundError:
        return False


def payload_paths(script: Path) -> tuple[Path, Path]:
    directory = script.resolve().parent
    if (directory / "tools" / "setup.py").is_file():
        return directory, directory / "requirements.txt"
    if directory.name == "tools" and (directory / "setup.py").is_file():
        return directory.parent, directory / "repair_templates" / "requirements.txt"
    raise ValueError("The setup files are incomplete. Extract the complete server source folder again.")


def environment_python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def validate_root(root: Path) -> Path:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("The selected server folder does not exist.")
    if not ((root / "VenomWorldServer.exe").is_file()
            or (root / "tools" / "setup.py").is_file()):
        raise ValueError("Run 01_SETUP_SERVER.bat from the complete extracted server or source folder.")
    return root


def bootstrap(root: Path, requirements: Path, script: Path, console_passwords=False, command="mysql", forwarded=()) -> int:
    if not requirements.is_file():
        raise ValueError("The setup dependency list is missing. Extract the complete source folder again.")
    environment = root / ".venv-setup"
    python = environment_python(environment)
    if not python.is_file():
        print("Preparing an isolated setup environment. Your game does not need to be rebuilt.", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    print("Installing the two setup dependencies (PyMySQL and cryptography).", flush=True)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                    "--requirement", str(requirements)], check=True)
    # No credentials are accepted here or passed through the shell, environment,
    # command line or child process arguments. Only the wizard asks for them.
    invocation = [str(python), str(script), "--root", str(root), "--prepared", "--command", command]
    if console_passwords:
        invocation.append("--console-passwords")
    return subprocess.call([*invocation, *forwarded])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path,
                        help="Existing Windows_Server_x64 or source folder to configure.")
    parser.add_argument("--prepared", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--console-passwords", action="store_true",
                        help="Use console setup; database credentials are generated automatically.")
    parser.add_argument("--command", choices=("wizard", "mysql", "hosting"), default="mysql")
    args, forwarded = parser.parse_known_args(argv)
    try:
        if sys.version_info < (3, 11):
            raise ValueError("Setup needs Python 3.11 or newer. Install it with Tcl/Tk support, then run setup again.")
        root = validate_root(args.root)
        script = Path(__file__).resolve()
        import_root, requirements = payload_paths(script)
        if not dependencies_ready():
            if args.prepared:
                raise ValueError("The isolated setup dependencies are incomplete. Run 01_SETUP_SERVER.bat again with internet access.")
            return bootstrap(root, requirements, script, console_passwords=args.console_passwords, command=args.command, forwarded=forwarded)
        sys.path.insert(0, str(import_root))
        from tools.setup import main as setup_main

        print(f"\nPreparing portable server setup for: {root}", flush=True)
        command = ["--root", str(root), args.command, *forwarded]
        if args.console_passwords:
            command.append("--console-passwords")
        return setup_main(command)
    except KeyboardInterrupt:
        print("\nSetup cancelled.", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"\nSETUP BOOTSTRAP FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
