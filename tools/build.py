"""Reproducible Windows x64 distribution builder; integrity checks work everywhere."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD_VERSION = "0.3.0-alpha"


def safe_asset(root: Path, name: str) -> Path:
    if not isinstance(name, str) or "\\" in name or Path(name).is_absolute():
        raise ValueError(f"Invalid manifest path: {name!r}")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or ".." in Path(name).parts:
        raise ValueError(f"Manifest path escapes source tree: {name!r}")
    return path


def catalog_paths(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from catalog_paths(child)
    elif isinstance(value, list):
        for child in value:
            yield from catalog_paths(child)
    elif isinstance(value, str) and value.startswith(("assets/", "data/")):
        yield value


def verify_assets(root: Path = ROOT) -> dict:
    manifest_path = root / "data/asset_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Missing data/asset_manifest.json. Run the asset import first; no assets will be guessed or downloaded.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Asset manifest contains no files.")
    listed = set()
    total = 0
    problems = []
    print(f"Verifying {len(rows):,} asset / catalog SHA-256 records...", flush=True)
    for row in rows:
        name = row.get("path")
        path = safe_asset(root, name)
        if name in listed:
            problems.append(f"Duplicate manifest record: {name}")
        listed.add(name)
        if not path.is_file():
            problems.append(f"Missing: {name}")
            continue
        if path.stat().st_size != row.get("size"):
            problems.append(f"Size mismatch: {name}")
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != row.get("sha256"):
            problems.append(f"SHA-256 mismatch: {name}")
        total += path.stat().st_size
    catalog_path = root / "data/catalog.json"
    if catalog_path.is_file():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        refs = set(catalog_paths(catalog)) | {"data/catalog.json"}
        for name in sorted(refs - listed):
            problems.append(f"Catalog asset has no integrity record: {name}")
        for section in ("species", "tamers", "maps"):
            if not isinstance(catalog.get(section), list) or not catalog[section]:
                problems.append(f"Catalog {section} list is empty.")
    else:
        problems.append("Missing data/catalog.json")
    for path in (root / "assets").rglob("*"):
        if path.is_file() and path.relative_to(root).as_posix() not in listed:
            problems.append(f"Unverified asset: {path.relative_to(root).as_posix()}")
    if problems:
        raise RuntimeError("Asset verification failed:\n" + "\n".join(problems[:40]) + (f"\n... {len(problems) - 40} additional errors" if len(problems) > 40 else ""))
    result = {"files": len(rows), "bytes": total, "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    print(f"Verified {len(rows):,} files ({total / 1024 / 1024:.1f} MiB).", flush=True)
    return result


def run(args: list[str], cwd: Path = ROOT):
    subprocess.run(args, cwd=cwd, check=True)


def copy_tree(source: Path, destination: Path):
    shutil.copytree(source, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))


def archive(folder: Path, output: Path):
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as out:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                out.write(path, path.relative_to(folder))


def build(args) -> None:
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required.")
    verified = verify_assets(ROOT)
    if args.verify_only:
        return
    if sys.platform != "win32" or struct.calcsize("P") != 8 or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Windows x64 executables must be built on Windows x64 using 64-bit Python. Integrity verification succeeded; cross-compiling with Linux PyInstaller is not supported.")
    env = ROOT / ".venv-build"
    python = env / "Scripts/python.exe"
    if not python.exists():
        print("Creating isolated build environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(env)
    if not args.offline:
        run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
        run([str(python), "-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-build.txt"])
    run([str(python), "-m", "pip", "check"])
    run([str(python), "-m", "compileall", "-q", "venom", "tools"])
    work = ROOT / ".build"
    frozen = work / "frozen"
    output = ROOT / "dist"
    work.mkdir(exist_ok=True)
    output.mkdir(exist_ok=True)
    entries = {
        "DigimonVenomNXT": ("venom.client.main", "--windowed"),
        "VenomWorldServer": ("venom.server.main", "--console"),
        "VenomSetup": ("tools.setup", "--console"),
    }
    for name, (module, mode) in entries.items():
        entry = work / f"entry_{name}.py"
        entry.write_text(f"from {module} import main\nif __name__ == '__main__':\n    raise SystemExit(main())\n", encoding="utf-8")
        command = [str(python), "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", mode,
                   "--name", name, "--paths", str(ROOT), "--distpath", str(frozen),
                   "--workpath", str(work / "pyinstaller" / name), "--specpath", str(work),
                   "--collect-all", "websockets", "--hidden-import", "pymysql", "--hidden-import", "cryptography", str(entry)]
        if name == "DigimonVenomNXT":
            command[-1:-1] = ["--manifest", str(ROOT / "tools/windows_client.manifest"),
                              "--icon", str(ROOT / "tools/windows_client.ico")]
        if name == "VenomSetup":
            command[-1:-1] = ["--collect-all", "tkinter", "--hidden-import", "tkinter.ttk",
                              "--hidden-import", "tools.setup_wizard",
                              "--hidden-import", "tools.setup_service",
                              "--hidden-import", "tools.setup_diagnostics",
                              "--copy-metadata", "PyMySQL",
                              "--manifest", str(ROOT / "tools/windows_client.manifest")]
        run(command)
    client = output / "Windows_Client_x64"
    server = output / "Windows_Server_x64"
    for destination, product in ((client, "DigimonVenomNXT"), (server, "VenomWorldServer")):
        # Build output is recreated; keep live installations outside source/dist.
        if destination.exists():
            shutil.rmtree(destination)
        copy_tree(frozen / product, destination)
        copy_tree(ROOT / "data", destination / "data")
        (destination / "config").mkdir(exist_ok=True)
        (destination / "docs").mkdir(exist_ok=True)
        shutil.copy2(ROOT / "PASSWORD_SETUP_FIX.txt", destination / "PASSWORD_SETUP_FIX.txt")
        for name in ("SETUP.md", "RIVALS_UPGRADE.md", "RIVALS_AND_RANKED.md",
                     "REARISE_RULES_RESEARCH.md", "RELEASE_STATUS.md", "VALIDATION.md",
                     "RIVALS_BENCHMARK.md", "RIVALS_BENCHMARK.json", "PASSWORD_SETUP_FIX.md"):
            shutil.copy2(ROOT / "docs" / name, destination / "docs" / name)
    for name in ("CONTROLS.md", "DISPLAY_UPGRADE.md"):
        if (ROOT / "docs" / name).is_file():
            shutil.copy2(ROOT / "docs" / name, client / "docs" / name)
    copy_tree(ROOT / "assets", client / "assets")
    # Only map collision data is needed by the authoritative world server.
    catalog = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))
    for map_row in catalog["maps"]:
        if map_row.get("walkable"):
            name = map_row["walkable"]
            destination = safe_asset(server, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_asset(ROOT, name), destination)
    # Keep setup's own _internal directory isolated from the world server bundle.
    copy_tree(frozen / "VenomSetup", server / "admin")
    for name in ("01_SETUP_SERVER.bat", "02_SETUP_MYSQL.bat", "03_SETUP_PUBLIC_HOSTING.bat", "START_WORLD_SERVER_CONSOLE.bat"):
        shutil.copy2(ROOT / name, server / name)
    shutil.copy2(ROOT / "PLAY_DIGIMON_VENOM_NXT.bat", client / "PLAY_DIGIMON_VENOM_NXT.bat")
    client_config = {"host": "localhost", "port": 8765, "ca_file": "config/server-ca.pem", "server_name": "localhost", "tls": True}
    (client / "config/client.json").write_text(json.dumps(client_config, indent=2) + "\n", encoding="utf-8")
    (client / "READ_ME_FIRST.txt").write_text(
        "DIGIMON VENOM NXT 0.3.0 - CLIENT\n\n"
        "Start the game: PLAY_DIGIMON_VENOM_NXT.bat\n"
        "Use the dedicated server from this release for matching game and setup behavior.\n"
        "Existing installation: copy your existing client config folder into this complete new client folder.\n"
        "Keep its client.json and trusted server-ca.pem. Your saved display preferences remain in Local AppData.\n"
        "New installation: extract the host's Public_Player_Connection_Kit.zip INTO this folder, merging config.\n"
        "Built clients need no Python installation or manual Windows certificate trust.\n"
        "R: Ranked Arena. V: Rivals Hub. O: Bot Activity. Click a map rival to inspect them.\n"
        "F10: display/audio settings. F11: fullscreen/windowed.\n"
        "Upgrade steps: docs/RIVALS_UPGRADE.md. Game rules: docs/RIVALS_AND_RANKED.md.\n",
        encoding="utf-8")
    (server / "READ_ME_FIRST.txt").write_text(
        "DIGIMON VENOM NXT 0.3.0 - DEDICATED SERVER\n\n"
        "START THE SERVER: START_WORLD_SERVER_CONSOLE.bat\n\n"
        "UPGRADE FROM A WORKING SERVER\n"
        "1. Stop the old world server and back up its database and entire private config folder.\n"
        "2. Copy that config folder into this complete new server folder, preserving credentials and all TLS keys.\n"
        "3. Start MySQL/MariaDB in XAMPP, then run START_WORLD_SERVER_CONSOLE.bat.\n"
        "4. Wait for the rival population to finish starting, then use the updated client.\n"
        "The new tables are created automatically; accounts and passwords are retained.\n"
        "Use 01_SETUP_SERVER.bat to check or repair your saved configuration when needed.\n"
        "Keep the existing database name and CA. See docs/RIVALS_UPGRADE.md.\n\n"
        "FRESH INSTALLATION\n"
        "1. Start MySQL/MariaDB in XAMPP.\n"
        "2. Run 01_SETUP_SERVER.bat for the complete 0.3.0 setup wizard.\n"
        "3. Test the XAMPP connection using its existing administrator password (blank is allowed).\n"
        "4. Create the game login automatically, choose local/public hosting, then review readiness.\n"
        "5. Apply the generated Public_Player_Connection_Kit.zip inside the client folder.\n"
        "6. Run START_WORLD_SERVER_CONSOLE.bat. Forward the selected TCP port for Internet hosting.\n"
        "02_SETUP_MYSQL.bat and 03_SETUP_PUBLIC_HOSTING.bat reopen the corresponding wizard page.\n"
        "If a check fails, retain the on-screen error code or logs/setup-latest.json; never send passwords.\n\n"
        "Default population: 5,000 rivals. Configure rivals.count / rivals.enabled in config/server.json.\n"
        "Keep the whole server folder private: it contains database credentials and certificate private keys.\n"
        "Only share the configured client and public player connection kit.\n",
        encoding="utf-8")
    metadata = {"version": BUILD_VERSION, "platform": "Windows-x64", "python": platform.python_version(), "assets": verified}
    for directory in (client, server):
        (directory / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    for directory in (client, server):
        archive(directory, output / f"{directory.name}.zip")
    print("\nBuild complete. Independent packages:\n  dist/Windows_Client_x64.zip\n  dist/Windows_Server_x64.zip\nNew host: run 01_SETUP_SERVER.bat in the server folder. Existing host: follow docs/RIVALS_UPGRADE.md and preserve your config.\nStart the server with START_WORLD_SERVER_CONSOLE.bat; this release updates BOTH server and client.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Verify every imported asset and catalog hash without installing or building; works on any OS.")
    parser.add_argument("--offline", action="store_true", help="Use an already populated .venv-build without downloading packages.")
    args = parser.parse_args(argv)
    try:
        build(args)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"\nBUILD FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
