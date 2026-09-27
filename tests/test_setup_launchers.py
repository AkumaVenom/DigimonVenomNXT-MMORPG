"""Package the redesigned setup in a simulated Windows build.

External PyInstaller execution is replaced; this does not claim that Windows
executables or CMD launchers were executed on the development host.
"""
from pathlib import Path
from types import SimpleNamespace
import json
import shutil
import zipfile

from tools import build


SOURCE = Path(__file__).resolve().parents[1]


def test_windows_build_includes_whole_wizard_and_current_launchers(tmp_path, monkeypatch):
    root = tmp_path / "Source with spaces"
    root.mkdir()
    (root / ".venv-build" / "Scripts").mkdir(parents=True)
    (root / ".venv-build" / "Scripts" / "python.exe").touch()
    (root / "tools").mkdir()
    (root / "data").mkdir()
    (root / "assets").mkdir()
    (root / "assets" / "walk.json").write_text("[]")
    (root / "assets" / "sprite.png").write_bytes(b"example-client-asset")
    farm_assets = ("ui/digifarm/level.png", "ui/digifarm/digimeat.png",
                   "audio/original/digifarm_home.ogg")
    for name in farm_assets:
        asset = root / "assets" / name
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(b"example-farm-asset")
    (root / "data" / "catalog.json").write_text(json.dumps({"maps": [{"walkable": "assets/walk.json"}]}))
    (root / "docs").mkdir()
    for source in (SOURCE / "docs").glob("*"):
        if source.is_file():
            shutil.copy2(source, root / "docs" / source.name)
    for name in ("01_SETUP_SERVER.bat", "02_SETUP_MYSQL.bat", "03_SETUP_PUBLIC_HOSTING.bat",
                 "_RUN_SETUP.bat", "_RUN_MYSQL.bat", "START_WORLD_SERVER_CONSOLE.bat", "START_MYSQL.bat", "STOP_MYSQL.bat",
                 "MYSQL_STATUS.bat", "STOP_SERVER.bat", "START_SERVER.bat", "PLAY_DIGIMON_VENOM_NXT.bat"):
        shutil.copy2(SOURCE / name, root / name)
    for name in ("windows_client.manifest", "windows_client.ico"):
        (root / "tools" / name).touch()

    (root / "mysql" / "runtime" / "bin").mkdir(parents=True)
    (root / "mysql" / "runtime" / "bin" / "mysqld.exe").write_bytes(b"runtime")
    (root / "mysql" / "data").mkdir()
    (root / "mysql" / "data" / "private-save.ibd").write_bytes(b"never-package")
    (root / "mysql" / "credentials.json").write_text("private")
    from tools import portable_mysql
    monkeypatch.setattr(portable_mysql, "ensure_runtime", lambda *args, **kwargs: None)
    commands = []

    def simulate_tool(command):
        commands.append(command)
        if "PyInstaller" in command:
            name = command[command.index("--name") + 1]
            output = Path(command[command.index("--distpath") + 1]) / name
            (output / "_internal").mkdir(parents=True)
            (output / f"{name}.exe").write_bytes(b"simulated-executable")
            (output / "_internal" / "dependency.bin").write_bytes(name.encode())

    monkeypatch.setattr(build, "ROOT", root)
    monkeypatch.setattr(build, "run", simulate_tool)
    monkeypatch.setattr(build, "verify_assets", lambda _: {"files": 2, "bytes": 22})
    monkeypatch.setattr(build.sys, "platform", "win32")
    monkeypatch.setattr(build.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(build.struct, "calcsize", lambda _: 8)

    build.build(SimpleNamespace(verify_only=False, offline=True))

    setup_command = next(command for command in commands
                         if "PyInstaller" in command and "VenomSetup" in command)
    imports = [setup_command[index + 1] for index, value in enumerate(setup_command)
               if value == "--hidden-import"]
    assert {"tools.setup_wizard", "tools.setup_service", "tools.setup_diagnostics"} <= set(imports)
    collect_all = [setup_command[index + 1] for index, value in enumerate(setup_command)
                   if value == "--collect-all"]
    assert "tkinter" in collect_all
    metadata = [setup_command[index + 1] for index, value in enumerate(setup_command)
                if value == "--copy-metadata"]
    assert "PyMySQL" in metadata
    assert "--console" in setup_command  # Keep advanced console flows available.
    server = root / "dist" / "Windows_Server_x64"
    client = root / "dist" / "Windows_Client_x64"
    assert (server / "admin" / "VenomSetup.exe").is_file()
    assert (server / "admin" / "_internal" / "dependency.bin").read_bytes() == b"VenomSetup"
    assert (server / "_internal" / "dependency.bin").read_bytes() == b"VenomWorldServer"
    for name in ("01_SETUP_SERVER.bat", "02_SETUP_MYSQL.bat", "03_SETUP_PUBLIC_HOSTING.bat"):
        assert (server / name).read_bytes() == (SOURCE / name).read_bytes()
    assert (server / "_RUN_MYSQL.bat").is_file()
    assert (server / "_RUN_SETUP.bat").is_file()
    assert (server / "mysql" / "manager" / "VenomMySQL.exe").is_file()
    assert (server / "mysql" / "runtime" / "bin" / "mysqld.exe").read_bytes() == b"runtime"
    assert not (server / "mysql" / "data").exists()
    assert not (server / "mysql" / "credentials.json").exists()
    assert "01_SETUP_SERVER.bat" in (server / "READ_ME_FIRST.txt").read_text()
    assert json.loads((server / "build-info.json").read_text())["version"] == "0.12.0"
    assert json.loads((client / "build-info.json").read_text())["version"] == "0.12.0"
    assert (client / "docs" / "FPS_FIX.md").is_file()
    assert (client / "docs" / "UI_UPGRADE.md").is_file()
    assert (client / "docs" / "UI2_UPGRADE.md").is_file()
    for package in (client, server):
        assert (package / "docs" / "DIGIFARM_V060.md").is_file()
        assert (package / "docs" / "SEASON_MODE_V070.md").is_file()
        assert (package / "docs" / "STORY_MODE_V090.md").is_file()
        assert (package / "docs" / "WORLD_DS_V0100.md").is_file()
        assert (package / "docs" / "WORLD_DS_STORY_V0110.md").is_file()
        assert (package / "docs" / "DIGIRUBY_ECONOMY_V0120.md").is_file()
        assert (package / "docs" / "WORLD_DS_STORY_VALIDATION_V0110.json").is_file()
        assert (package / "docs" / "ADMIN_CONSOLE_V080.md").is_file()
    assert "Both the client and world server must be updated" in (client / "READ_ME_FIRST.txt").read_text()
    assert "Upgrade steps: docs/DIGIRUBY_ECONOMY_V0120.md" in (client / "READ_ME_FIRST.txt").read_text()
    assert "preserve mysql/data, mysql credentials and config" in (server / "READ_ME_FIRST.txt").read_text()
    assert "Upgrade steps: docs/RIVAL_MOVEMENT_UPGRADE.md" not in (client / "READ_ME_FIRST.txt").read_text()
    assert (client / "assets" / "sprite.png").is_file()
    for name in farm_assets:
        assert (client / "assets" / name).read_bytes() == b"example-farm-asset"
    assert not (server / "assets" / "sprite.png").exists()
    assert (server / "assets" / "walk.json").is_file()
    with zipfile.ZipFile(root / "dist" / "Windows_Server_x64.zip") as archive:
        assert archive.testzip() is None
        assert "01_SETUP_SERVER.bat" in archive.namelist()
        assert "admin/VenomSetup.exe" in archive.namelist()


def test_database_launcher_cannot_prefer_an_obsolete_repair_payload():
    launcher = (SOURCE / "02_SETUP_MYSQL.bat").read_text()
    assert 'if exist "setup_fix' not in launcher.lower()
    assert "FIX_MYSQL_SETUP.bat" not in launcher
    assert "DisableDelayedExpansion" in launcher
    assert 'set "SETUP_COMMAND=wizard --stage database"' in launcher
    assert 'set "SETUP_COMMAND=mysql"' in launcher
    assert '%SETUP_COMMAND% %*' in launcher


def test_rebuild_refuses_to_erase_configured_server_or_database(tmp_path):
    import pytest
    for marker in ("config/server.json", "mysql/instance.json", "mysql/game-login.json", "mysql/data/player.ibd"):
        destination = tmp_path / marker.replace("/", "_")
        live_file = destination / marker
        live_file.parent.mkdir(parents=True)
        live_file.write_bytes(b"preserve every byte")
        with pytest.raises(RuntimeError, match="will not delete saved progress"):
            build.check_server_build_destination(destination)
        assert live_file.read_bytes() == b"preserve every byte"
