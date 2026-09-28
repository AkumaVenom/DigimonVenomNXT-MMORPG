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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BUILD_VERSION = "1.0.0"


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


def check_server_build_destination(destination: Path):
    """A release rebuild must never erase an installation used for actual play."""
    if ((destination / "config/server.json").exists()
            or (destination / "mysql/instance.json").exists()
            or (destination / "mysql/game-login.json").exists()
            or (destination / "mysql/data").exists()):
        raise RuntimeError(
            "dist/Windows_Server_x64 contains database or configured server state. "
            "Stop it cleanly and move the complete installation outside dist before "
            "building again. The builder will not delete saved progress.")


def build(args) -> None:
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required.")
    verified = verify_assets(ROOT)
    if args.verify_only:
        return
    if sys.platform != "win32" or struct.calcsize("P") != 8 or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Windows x64 executables must be built on Windows x64 using 64-bit Python. Integrity verification succeeded; cross-compiling with Linux PyInstaller is not supported.")
    check_server_build_destination(ROOT / "dist" / "Windows_Server_x64")
    from tools.portable_mysql import ensure_runtime
    ensure_runtime(ROOT, offline=args.offline)
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
        "VenomMySQL": ("tools.portable_mysql", "--console"),
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
                              "--hidden-import", "tools.portable_mysql",
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
        for name in ("SETUP.md", "SERVER.md", "RIVALS_UPGRADE.md", "RIVAL_MOVEMENT_UPGRADE.md",
                     "RIVAL_MOVEMENT_UPGRADE.txt", "RIVALS_AND_RANKED.md",
                     "REARISE_RULES_RESEARCH.md", "RELEASE_STATUS.md", "DIGIFARM_V060.md", "SEASON_MODE_V070.md", "SEASON_VALIDATION.md", "VALIDATION.md",
                     "RIVALS_BENCHMARK.md", "RIVALS_BENCHMARK.json",
                     "RIVAL_FIX_VALIDATION.json", "RIVAL_TRAINING_VALIDATION.json",
                     "ADMIN_CONSOLE_V080.md", "STORY_MODE_V090.md", "WORLD_DS_V0100.md", "WORLD_DS_STORY_V0110.md", "DIGIRUBY_ECONOMY_V0120.md", "RESTART_REPAIR_V0121.md", "BOT_ACTIVITY_V0122.md", "POPULATION_V0123.md", "RELEASE_V100.md", "FANGLONGMON_V100.md",
                     "WORLD_DS_STORY_VALIDATION_V0110.json"):
            shutil.copy2(ROOT / "docs" / name, destination / "docs" / name)
        copy_tree(ROOT / "docs" / "validation" / "restart_v0121",
                  destination / "docs" / "validation" / "restart_v0121")
        copy_tree(ROOT / "docs" / "validation" / "activity_v0122",
                  destination / "docs" / "validation" / "activity_v0122")
        copy_tree(ROOT / "docs" / "validation" / "population_v0123",
                  destination / "docs" / "validation" / "population_v0123")
        copy_tree(ROOT / "docs" / "validation" / "release_v100",
                  destination / "docs" / "validation" / "release_v100")
    for name in ("CONTROLS.md", "DISPLAY_UPGRADE.md", "FPS_FIX.md", "FPS_BENCHMARK.json",
                 "UI_UPGRADE.md", "UI_VALIDATION.json", "UI_PERFORMANCE.json",
                 "UI2_UPGRADE.md", "UI2_VALIDATION.json", "UI2_PERFORMANCE.json"):
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
    copy_tree(frozen / "VenomMySQL", server / "mysql" / "manager")
    # Runtime binaries are distributable; mysql/data and private credentials are not.
    copy_tree(ROOT / "mysql" / "runtime", server / "mysql" / "runtime")
    if (ROOT / "mysql" / "provenance").is_dir():
        copy_tree(ROOT / "mysql" / "provenance", server / "mysql" / "provenance")
    for path in (ROOT / "mysql" / "prerequisites").glob("*"):
        if path.is_file() and path.suffix.lower() in {".bat", ".ps1", ".md", ".txt"}:
            (server / "mysql" / "prerequisites").mkdir(exist_ok=True)
            shutil.copy2(path, server / "mysql" / "prerequisites" / path.name)
    if (ROOT / "PORTABLE_SERVER_README.md").is_file():
        shutil.copy2(ROOT / "PORTABLE_SERVER_README.md", server / "PORTABLE_SERVER_README.md")
    for path in (ROOT / "mysql").iterdir():
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            shutil.copy2(path, server / "mysql" / path.name)
    for name in ("PORTABLE_MYSQL.md", "PORTABLE_MYSQL_VALIDATION.md", "PORTABLE_MYSQL_VALIDATION.json"):
        if (ROOT / "docs" / name).is_file():
            shutil.copy2(ROOT / "docs" / name, server / "docs" / name)
    for name in ("01_SETUP_SERVER.bat", "02_SETUP_MYSQL.bat", "03_SETUP_PUBLIC_HOSTING.bat", "_RUN_SETUP.bat", "_RUN_MYSQL.bat",
                 "START_WORLD_SERVER_CONSOLE.bat", "START_MYSQL.bat", "STOP_MYSQL.bat", "MYSQL_STATUS.bat",
                 "STOP_SERVER.bat", "START_SERVER.bat"):
        shutil.copy2(ROOT / name, server / name)
    shutil.copy2(ROOT / "PLAY_DIGIMON_VENOM_NXT.bat", client / "PLAY_DIGIMON_VENOM_NXT.bat")
    client_config = {"host": "localhost", "port": 8765, "ca_file": "config/server-ca.pem", "server_name": "localhost", "tls": True}
    (client / "config/client.json").write_text(json.dumps(client_config, indent=2) + "\n", encoding="utf-8")
    (client / "READ_ME_FIRST.txt").write_text(
        f"DIGIMON VENOM NXT {BUILD_VERSION} - CLIENT\n\n"
        "Start the game: PLAY_DIGIMON_VENOM_NXT.bat\n"
        f"Connect to the v{BUILD_VERSION} server. Rebuild and deploy BOTH the client and server for the v1.0.0 artwork and content.\n"
        "Existing installation: copy your existing client config folder into this complete new client folder.\n"
        "New in v1.0.0: blue cyber-grid battle scenery and supplied Fanglongmon / Paradox Fanglongmon animation.\n"
        "Shop / B: pay with credits or DigiRubies for every capsule and DigiMeat.\n"
        "Ranked Arena / R: DigiRuby Exchange gives 100 credits per DigiRuby.\n"
        "Attack is free at 0 SP. The redundant Struggle option has been removed.\n"
        "Bot Activity / O: activity counters cover the latest 12 hours; the feed keeps the latest 100 events in that window.\n"
        "See docs/RELEASE_V100.md; preserve existing server saves and credentials.\n"
        "Keep its client.json and trusted server-ca.pem. Your saved display preferences remain in Local AppData.\n"
        "New installation: extract the host's Public_Player_Connection_Kit.zip INTO this folder, merging config.\n"
        "Built clients need no Python installation or manual Windows certificate trust.\n"
        "DigiFarm / F2: use the top-left home button. Click a farm Digimon to inspect and feed it.\n"
        "Worlds: shared Dawn or World DS maps. Story F4: choose Dawn Relay or Paradox Chronicle.\n"
        "Season F3 remains a separate private career. Each story keeps its own progress.\n"
        "R: Ranked Arena. V: Rivals Hub. O: Bot Activity. Click a map rival to inspect them.\n"
        "F10: display/audio settings. F11: fullscreen/windowed.\n"
        "Upgrade steps: docs/RELEASE_V100.md. Interface history: docs/UI2_UPGRADE.md. Game rules: docs/RIVALS_AND_RANKED.md.\n",
        encoding="utf-8")
    (server / "READ_ME_FIRST.txt").write_text(
        f"DIGIMON VENOM NXT {BUILD_VERSION} - PORTABLE DEDICATED SERVER\n\n"
        "UPGRADING AN EXISTING SERVER\n"
        "Read docs/RELEASE_V100.md first. Stop and back up the complete existing server.\n"
        "Rebuild and deploy BOTH the client and server for the v1.0.0 artwork and content.\n"
        "Saved-world loading still has no overall startup deadline.\n"
        "Preserve mysql/data, mysql credentials, config and mysql/runtime.\n"
        "Do not run a fresh database setup or replace your saves for this upgrade.\n\n"
        "FRESH SETUP\n"
        "1. Extract the COMPLETE server folder into a writable directory.\n"
        "2. Run 01_SETUP_SERVER.bat. It prepares the bundled MySQL process, creates\n"
        "   a fresh game database and sets up local/public player connections.\n"
        "3. Extract Public_Player_Connection_Kit.zip into each client's folder.\n"
        "4. Run START_MYSQL.bat, then START_WORLD_SERVER_CONSOLE.bat.\n"
        "   The world launcher also checks and starts this folder's MySQL automatically.\n\n"
        "ALL DATABASE FILES AND PLAYER SAVES: mysql/data\n"
        "MYSQL PROCESS: mysql/runtime/bin/mysqld.exe, loopback port 3307\n"
        "No separately installed database or Windows database service is needed.\n\n"
        "BACK UP / MOVE TO ANOTHER PC\n"
        "Run STOP_SERVER.bat to stop the world and MySQL cleanly. Wait for\n"
        "confirmation, then ZIP or copy the entire server\n"
        "folder, including mysql and config. Extract it on the other Windows x64 PC\n"
        "and use the same launchers. Never ZIP live database files.\n"
        "Do not delete mysql/data, private database settings, or config when updating.\n"
        "Keep the complete server folder private; share only the client and player kit.\n\n"
        "Setup: 02_SETUP_MYSQL.bat / 03_SETUP_PUBLIC_HOSTING.bat\n"
        "Database status: MYSQL_STATUS.bat. Database logs: mysql/logs.\n"
        "For public hosting, forward only the game TCP port (default 8765).\n"
        "Default and maximum population: 3,000 rivals. Older counts above 3,000 are capped automatically; lower counts and rivals.enabled remain supported.\n",
        encoding="utf-8")
    metadata = {"version": BUILD_VERSION, "platform": "Windows-x64", "python": platform.python_version(), "assets": verified}
    for directory in (client, server):
        (directory / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    for directory in (client, server):
        archive(directory, output / f"{directory.name}.zip")
    print("\nBuild complete. Digimon Venom NXT v1.0.0 packages:\n  dist/Windows_Client_x64.zip\n  dist/Windows_Server_x64.zip\nRebuild and deploy BOTH the client and server for the v1.0.0 artwork and content. Preserve the database, credentials, config and MySQL runtime.\nUpgrade steps: docs/RELEASE_V100.md. For a NEW server only: follow PORTABLE_SERVER_README.md.", flush=True)


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
