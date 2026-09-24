"""Repair the selected existing server without leaking credentials to a launcher."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tools import repair_mysql


def server_folder(tmp_path):
    root = tmp_path / "Server with spaces"
    root.mkdir()
    (root / "VenomWorldServer.exe").touch()
    return root


@pytest.mark.parametrize("console", [False, True])
def test_repair_configures_explicit_server_not_payload_or_working_directory(tmp_path, monkeypatch, console):
    root = server_folder(tmp_path)
    payload = root / "setup_fix"
    (payload / "tools").mkdir(parents=True)
    (payload / "tools" / "setup.py").touch()
    script = payload / "repair_mysql.py"
    script.touch()
    unrelated = tmp_path / "other_mmo"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    monkeypatch.setattr(repair_mysql, "__file__", str(script))
    monkeypatch.setattr(repair_mysql, "dependencies_ready", lambda: True)
    monkeypatch.setattr(sys, "path", list(sys.path))
    calls = []
    monkeypatch.setitem(sys.modules, "tools.setup", SimpleNamespace(main=lambda argv: calls.append(argv) or 0))

    flags = ["--console-passwords"] if console else []
    assert repair_mysql.main(["--root", str(root)] + flags) == 0
    assert calls == [["--root", str(root.resolve()), "mysql"] + flags]
    assert sys.path[0] == str(payload.resolve())
    assert not (unrelated / "config").exists()
    assert not (payload / "config").exists()


@pytest.mark.parametrize("console", [False, True])
def test_repair_bootstrap_installs_only_setup_deps_then_preserves_root(tmp_path, monkeypatch, console):
    root = server_folder(tmp_path)
    payload = root / "setup_fix"
    payload.mkdir()
    requirements = payload / "requirements.txt"
    requirements.write_text("PyMySQL==1.1.1\ncryptography==46.0.0\n")
    script = payload / "repair_mysql.py"
    calls = []
    created = []
    monkeypatch.setattr(repair_mysql.venv, "EnvBuilder", lambda **kwargs: SimpleNamespace(create=created.append))
    monkeypatch.setattr(repair_mysql.subprocess, "run", lambda argv, **kwargs: calls.append((argv, kwargs)))
    monkeypatch.setattr(repair_mysql.subprocess, "call", lambda argv: calls.append((argv, {})) or 0)

    assert repair_mysql.bootstrap(root, requirements, script, console_passwords=console) == 0
    assert created == [root / ".venv-setup"]
    python = str(repair_mysql.environment_python(root / ".venv-setup"))
    assert calls == [
        ([python, "-m", "pip", "install", "--disable-pip-version-check", "--requirement", str(requirements)], {"check": True}),
        ([python, str(script), "--root", str(root), "--prepared", "--command", "mysql"] + (["--console-passwords"] if console else []), {}),
    ]
    assert not any("password" in argument.lower() and argument != "--console-passwords"
                   for argv, _ in calls for argument in argv)


def test_repair_refuses_admin_subfolder_and_missing_root(tmp_path):
    root = server_folder(tmp_path)
    admin = root / "admin"
    admin.mkdir()
    with pytest.raises(ValueError, match="complete extracted"):
        repair_mysql.validate_root(admin)
    with pytest.raises(ValueError, match="does not exist"):
        repair_mysql.validate_root(tmp_path / "missing")
    with pytest.raises(SystemExit) as exc:
        repair_mysql.main([])
    assert exc.value.code == 2


def test_incomplete_prepared_environment_does_not_loop(tmp_path, monkeypatch, capsys):
    root = server_folder(tmp_path)
    monkeypatch.setattr(repair_mysql, "dependencies_ready", lambda: False)
    monkeypatch.setattr(repair_mysql, "bootstrap", lambda *args: pytest.fail("must not recursively bootstrap"))
    assert repair_mysql.main(["--root", str(root), "--prepared"]) == 1
    assert "dependencies are incomplete" in capsys.readouterr().err


def test_payload_resolves_in_both_download_and_source_layouts(tmp_path):
    payload = tmp_path / "setup_fix"
    (payload / "tools").mkdir(parents=True)
    (payload / "tools" / "setup.py").touch()
    assert repair_mysql.payload_paths(payload / "repair_mysql.py") == (payload, payload / "requirements.txt")
    source = tmp_path / "source"
    (source / "tools").mkdir(parents=True)
    (source / "tools" / "setup.py").touch()
    assert repair_mysql.payload_paths(source / "tools" / "repair_mysql.py") == (
        source, source / "tools" / "repair_templates" / "requirements.txt")
    with pytest.raises(ValueError, match="incomplete"):
        repair_mysql.payload_paths(tmp_path / "unknown" / "repair_mysql.py")
