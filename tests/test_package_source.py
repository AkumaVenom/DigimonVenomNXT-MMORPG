"""Release source packaging includes the owned runtime and excludes live state."""
import zipfile

from tools import package_source


def test_clean_package_includes_runtime_provenance_but_not_live_state(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    public = ["README.md", "PORTABLE_SERVER_README.md", "START_MYSQL.bat", "venom/module.py",
              "mysql/runtime/bin/mysqld.exe", "mysql/provenance/runtime.json",
              "mysql/prerequisites/INSTALL_RUNTIME.bat", "mysql/README.md"]
    private = ["mysql/data/player.ibd", "mysql/instance.json", "mysql/game-login.json",
               "mysql/my.ini", "mysql/logs/mysql-error.log", "config/server.json"]
    for name in public + private:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    monkeypatch.setattr(package_source, "ROOT", root)
    output = tmp_path / "source.zip"
    digest = package_source.package(output)
    assert len(digest) == 64
    with zipfile.ZipFile(output) as archive:
        names = {name.removeprefix("DigimonVenomNXT/") for name in archive.namelist()}
    assert names == set(public)
