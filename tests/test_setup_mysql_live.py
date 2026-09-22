"""Real MariaDB setup regressions, using a disposable server started by this test.

Opt in with VENOM_TEST_MARIADB_ROOT=/path/to/an/extracted/usr directory.
The binary must be mariadbd, with bin/mariadb-install-db and share/mysql.
No existing server, credentials, configuration or database is ever used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

import pytest

from tools.setup import mysql_setup


@pytest.fixture(scope="module")
def isolated_mariadb(tmp_path_factory):
    supplied = os.environ.get("VENOM_TEST_MARIADB_ROOT")
    if not supplied:
        pytest.skip("Set VENOM_TEST_MARIADB_ROOT to run disposable real-MariaDB tests.")
    pymysql = pytest.importorskip("pymysql")
    base = Path(supplied).resolve()
    binary = base / "sbin/mariadbd"
    installer = base / "bin/mariadb-install-db"
    assert binary.is_file() and installer.is_file(), "Incomplete portable MariaDB directory."
    runtime = tmp_path_factory.mktemp("isolated_mariadb")
    datadir = runtime / "data"
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = str(base / "lib/x86_64-linux-gnu") + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    import pwd
    os_user = pwd.getpwuid(os.getuid()).pw_name
    initialized = subprocess.run([
        str(installer), "--no-defaults", f"--basedir={base}",
        f"--datadir={datadir}", f"--user={os_user}",
        "--auth-root-authentication-method=normal", "--skip-test-db",
    ], env=env, capture_output=True, text=True, timeout=30)
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log_path = runtime / "mariadb.log"
    with log_path.open("w") as log:
        process = subprocess.Popen([
            str(binary), "--no-defaults", f"--basedir={base}",
            f"--datadir={datadir}", f"--port={port}",
            f"--plugin-dir={base / 'lib/mysql/plugin'}",
            "--bind-address=127.0.0.1", "--socket=",
            f"--pid-file={runtime / 'mariadb.pid'}", f"--user={os_user}",
            "--max-connections=30", "--innodb-buffer-pool-size=32M", "--skip-log-bin",
        ], env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    connection = pymysql.connect(host="127.0.0.1", port=port, user="root", password="", autocommit=True)
                    break
                except pymysql.MySQLError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        pytest.fail("Disposable MariaDB did not start: " + log_path.read_text())
                    time.sleep(0.05)
            admin_password = secrets.token_urlsafe(24)
            with connection.cursor() as cursor:
                cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (admin_password,))
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()[0]
            connection.close()
            yield {"host": "127.0.0.1", "port": port, "admin_user": "root", "admin_password": admin_password, "version": version}
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def admin_connection(server):
    import pymysql
    return pymysql.connect(host=server["host"], port=server["port"], user=server["admin_user"],
                           password=server["admin_password"], charset="utf8mb4", autocommit=True)


def app_connection(db, database=None):
    import pymysql
    return pymysql.connect(host=db["host"], port=db["port"], user=db["user"], password=db["password"].encode("utf-8"),
                           database=database or db["name"], charset="utf8mb4", autocommit=True)


def answers(server, suffix, password):
    return {key: value for key, value in server.items() if key != "version"} | {
        "name": "venom_live_" + suffix, "user": "venom_live_" + suffix,
        "password": password, "account_host": "localhost",
    }


@pytest.mark.parametrize("password", ["short!", "one", "quotes'\"\\ spaces £$%!?;", "é漢字Password!"])
def test_fresh_chosen_password_creates_usable_database(isolated_mariadb, tmp_path, password):
    supplied = answers(isolated_mariadb, secrets.token_hex(4), password)
    db = mysql_setup(tmp_path, supplied, interactive=False)
    saved_text = (tmp_path / "config/server.json").read_text()
    saved = json.loads(saved_text)
    assert saved["database"] == db
    assert db["password"] == password
    assert isolated_mariadb["admin_password"] not in saved_text
    with app_connection(db) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM venom_schema")
        assert cursor.fetchone() == (1,)
        cursor.execute("SHOW TABLES")
        assert {"venom_schema", "venom_accounts", "venom_players"} <= {row[0] for row in cursor.fetchall()}


@pytest.mark.parametrize("shared_account", [False, True])
def test_fresh_folder_collision_is_recovered_without_changing_existing_account(isolated_mariadb, tmp_path, shared_account):
    supplied = answers(isolated_mariadb, secrets.token_hex(4), "selected!")
    old_password = "old-shared-account!"
    old_user = supplied["user"]
    with admin_connection(isolated_mariadb) as admin, admin.cursor() as cursor:
        cursor.execute("CREATE USER %s@'localhost' IDENTIFIED BY %s", (old_user, old_password))
        if shared_account:
            cursor.execute("CREATE DATABASE other_mmo_shared")
            cursor.execute("CREATE TABLE other_mmo_shared.keep_me (value INTEGER)")
            cursor.execute("INSERT INTO other_mmo_shared.keep_me VALUES (991)")
            cursor.execute("GRANT SELECT ON other_mmo_shared.* TO %s@'localhost'", (old_user,))
        cursor.execute("SHOW GRANTS FOR %s@'localhost'", (old_user,))
        original_grants = cursor.fetchall()
    db = mysql_setup(tmp_path, supplied, interactive=False)
    assert db["user"] != old_user
    assert db["password"] == "selected!"
    assert json.loads((tmp_path / "config/server.json").read_text())["database"] == db
    with app_connection(db) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM venom_schema")
        assert cursor.fetchone() == (1,)
    import pymysql
    with pymysql.connect(host=isolated_mariadb["host"], port=isolated_mariadb["port"], user=old_user, password=old_password) as original:
        if shared_account:
            with original.cursor() as cursor:
                cursor.execute("SELECT value FROM other_mmo_shared.keep_me")
                assert cursor.fetchone() == (991,)
    with admin_connection(isolated_mariadb) as admin, admin.cursor() as cursor:
        cursor.execute("SHOW GRANTS FOR %s@'localhost'", (old_user,))
        assert cursor.fetchall() == original_grants


def test_existing_correct_password_and_rebuild_preserve_configuration_and_data(isolated_mariadb, tmp_path):
    supplied = answers(isolated_mariadb, "rebuild", "tiny!")
    first = mysql_setup(tmp_path, supplied, interactive=False)
    config_path = tmp_path / "config/server.json"
    saved = json.loads(config_path.read_text())
    saved["port"] = 9876
    saved["rivals"] = {"count": 17}
    config_path.write_text(json.dumps(saved))
    with app_connection(first) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE TABLE saved_sentinel (value INTEGER)")
        cursor.execute("INSERT INTO saved_sentinel VALUES (742)")
    second = mysql_setup(tmp_path, {key: value for key, value in isolated_mariadb.items() if key != "version"}, interactive=False)
    assert second == first
    after = json.loads(config_path.read_text())
    assert after["port"] == 9876 and after["rivals"] == {"count": 17}
    with app_connection(second) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT value FROM saved_sentinel")
        assert cursor.fetchone() == (742,)


def test_database_grant_matches_underscores_literally(isolated_mariadb, tmp_path):
    supplied = answers(isolated_mariadb, "grant_case", "short!")
    sibling = supplied["name"].replace("_", "X")
    with admin_connection(isolated_mariadb) as admin, admin.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE `{sibling}`")
        cursor.execute(f"CREATE TABLE `{sibling}`.private_data (value INTEGER)")
        cursor.execute(f"INSERT INTO `{sibling}`.private_data VALUES (931)")
    db = mysql_setup(tmp_path, supplied, interactive=False)
    import pymysql
    with app_connection(db) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM venom_schema")
        assert cursor.fetchone() == (1,)
        with pytest.raises(pymysql.MySQLError) as denied:
            cursor.execute(f"SELECT value FROM `{sibling}`.private_data")
        assert denied.value.args[0] in (1044, 1142)


def test_wrong_administrator_password_keeps_existing_configuration(isolated_mariadb, tmp_path):
    path = tmp_path / "config/server.json"
    path.parent.mkdir()
    original = '{"port": 8765, "custom": "preserve exactly"}\n'
    path.write_text(original)
    supplied = answers(isolated_mariadb, "bad_admin", "short!")
    supplied["admin_password"] = "deliberately-wrong-local-test-password"
    with pytest.raises(ValueError, match="administrator"):
        mysql_setup(tmp_path, supplied, interactive=False)
    assert path.read_text() == original


def test_schema_failure_preserves_data_config_and_removes_only_new_account(isolated_mariadb, tmp_path):
    from venom.server.database import DatabaseError
    supplied = answers(isolated_mariadb, "bad_schema", "short!")
    path = tmp_path / "config/server.json"
    path.parent.mkdir()
    original = '{"port": 9877, "custom": "preserve exactly"}\n'
    path.write_text(original)
    with admin_connection(isolated_mariadb) as admin, admin.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE `{supplied['name']}`")
        cursor.execute(f"CREATE TABLE `{supplied['name']}`.venom_schema (version INTEGER)")
        cursor.execute(f"INSERT INTO `{supplied['name']}`.venom_schema VALUES (999)")
    with pytest.raises((ValueError, DatabaseError), match="[Ss]chema"):
        mysql_setup(tmp_path, supplied, interactive=False)
    assert path.read_text() == original
    with admin_connection(isolated_mariadb) as admin, admin.cursor() as cursor:
        cursor.execute(f"SELECT version FROM `{supplied['name']}`.venom_schema")
        assert cursor.fetchone() == (999,)
        cursor.execute("SELECT COUNT(*) FROM mysql.user WHERE User=%s", (supplied["user"],))
        assert cursor.fetchone() == (0,)


def test_saved_account_runs_player_and_rival_schema(isolated_mariadb, tmp_path):
    from venom.common.game import GameEngine
    from venom.common.paths import root_path
    from venom.server.community import Community
    from venom.server.database import Database
    supplied = answers(isolated_mariadb, "world", "é漢字!")
    config = mysql_setup(tmp_path, supplied, interactive=False)
    database = Database(config)
    community = None
    try:
        database.initialize()
        database.register("LiveTamer", "dummy-tamer-pass", {"party": [], "marker": 421})
        assert database.authenticate("LiveTamer", "dummy-tamer-pass") == "livetamer"
        assert database.load("LiveTamer")[0]["marker"] == 421
        community = Community(GameEngine(root_path(), seed=7), database, {"rivals": {"count": 8}})
        community.initialize()
        assert community.ready
        assert len(community.bots.bots) == 8
        community.step(time.monotonic() + 5, 0.1)
    finally:
        if community is not None:
            community.shutdown()
        database.close()


@pytest.mark.parametrize("replacement", ["ValidChosenPassword234!", ""])
def test_real_password_policy_retries_game_password_without_restarting_setup(isolated_mariadb, tmp_path, monkeypatch, replacement):
    import tools.setup as setup
    supplied = answers(isolated_mariadb, "password_policy", "unused")
    supplied.pop("password")
    chosen = iter(["short!", replacement])
    prompts = []

    def enter_password(label, **kwargs):
        prompts.append(label)
        return next(chosen)

    monkeypatch.setattr(setup, "read_password", enter_password)
    with admin_connection(isolated_mariadb) as admin, admin.cursor() as cursor:
        cursor.execute("INSTALL SONAME 'simple_password_check'")
    try:
        db = mysql_setup(tmp_path, supplied, interactive=True)
        assert len(prompts) == 2
        if replacement:
            assert db["password"] == replacement
        else:
            assert len(db["password"]) >= 43
        assert json.loads((tmp_path / "config/server.json").read_text())["database"] == db
        with app_connection(db) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT version FROM venom_schema")
            assert cursor.fetchone() == (1,)
    finally:
        with admin_connection(isolated_mariadb) as admin, admin.cursor() as cursor:
            cursor.execute("UNINSTALL SONAME 'simple_password_check'")
