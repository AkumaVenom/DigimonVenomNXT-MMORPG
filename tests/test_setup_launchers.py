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
    (root / "data" / "catalog.json").write_text(json.dumps({"maps": [{"walkable": "assets/walk.json"}]}))
    (root / "docs").mkdir()
    for source in (SOURCE / "docs").glob("*"):
        if source.is_file():
            shutil.copy2(source, root / "docs" / source.name)
    for name in ("PASSWORD_SETUP_FIX.txt", "01_SETUP_SERVER.bat", "02_SETUP_MYSQL.bat",
                 "03_SETUP_PUBLIC_HOSTING.bat", "START_WORLD_SERVER_CONSOLE.bat",
                 "PLAY_DIGIMON_VENOM_NXT.bat"):
        shutil.copy2(SOURCE / name, root / name)
    for name in ("windows_client.manifest", "windows_client.ico"):
        (root / "tools" / name).touch()

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
    assert (server / "PASSWORD_SETUP_FIX.txt").read_bytes() == (SOURCE / "PASSWORD_SETUP_FIX.txt").read_bytes()
    assert "01_SETUP_SERVER.bat" in (server / "READ_ME_FIRST.txt").read_text()
    assert json.loads((server / "build-info.json").read_text())["version"] == "0.3.0-alpha"
    assert (client / "assets" / "sprite.png").is_file()
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
