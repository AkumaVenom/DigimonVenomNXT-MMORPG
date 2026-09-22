"""Wizard service against an isolated real MariaDB; never touches an installed DB.

Set VENOM_TEST_MARIADB_ROOT as described in test_setup_mysql_live.py.
These exercise successful SQL and actual privilege/authentication failures. They
do not claim to reproduce an unidentified error from a user's XAMPP installation.
"""
from __future__ import annotations

import json
import secrets
import socket
import zipfile

import pytest

from test_setup_mysql_live import (
    isolated_mariadb, admin_connection, app_connection, answers,
)


def service_at(path):
    from tools.setup_service import SetupService
    return SetupService(path)


def snapshot_server(server):
    with admin_connection(server) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT User, Host, authentication_string FROM mysql.user ORDER BY User, Host")
        users = cursor.fetchall()
        cursor.execute("SHOW DATABASES")
        databases = cursor.fetchall()
    return users, databases


def test_connection_test_is_read_only_and_reports_actual_server(isolated_mariadb, tmp_path):
    service = service_at(tmp_path)
    settings = answers(isolated_mariadb, secrets.token_hex(4), "not-created!")
    config = tmp_path / "config/server.json"
    config.parent.mkdir(parents=True)
    original = '{"port": 9321, "custom": "retain bytes"}\n'
    config.write_text(original)
    before = snapshot_server(isolated_mariadb)
    result = service.test_database(settings)
    assert result["server_version"] == isolated_mariadb["version"]
    assert result["account"] == "root@localhost"
    assert result["host"] == settings["host"]
    assert result["port"] == settings["port"]
    assert snapshot_server(isolated_mariadb) == before
    assert config.read_text() == original
    report = service.report_text()
    assert settings["admin_password"] not in report
    assert settings["password"] not in report


def test_connection_failure_can_be_edited_and_retried_in_same_service(isolated_mariadb, tmp_path):
    from tools.setup_service import SetupFailure
    service = service_at(tmp_path)
    settings = answers(isolated_mariadb, secrets.token_hex(4), "unused")
    with socket.socket() as closed_endpoint:
        closed_endpoint.bind(("127.0.0.1", 0))
        wrong = settings | {"port": closed_endpoint.getsockname()[1]}
        with pytest.raises(SetupFailure) as failure:
            service.test_database(wrong)
    assert failure.value.stage == "endpoint"
    assert failure.value.action
    assert service.test_database(settings)["account"] == "root@localhost"
    assert not (tmp_path / "config/server.json").exists()


def test_wrong_administrator_is_named_and_correctable_without_game_creation(isolated_mariadb, tmp_path):
    from tools.setup_service import SetupFailure
    service = service_at(tmp_path)
    settings = answers(isolated_mariadb, secrets.token_hex(4), "new-game-password!")
    before = snapshot_server(isolated_mariadb)
    wrong_password = "wrong-for-this-disposable-db!"
    with pytest.raises(SetupFailure) as failure:
        service.test_database(settings | {"admin_password": wrong_password})
    assert failure.value.stage == "administrator"
    assert failure.value.code in (1045, 1698)
    assert snapshot_server(isolated_mariadb) == before
    assert wrong_password not in service.report_text()
    assert service.test_database(settings)["account"] == "root@localhost"
    db = service.configure_database(settings)
    with app_connection(db) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM venom_schema")
        assert cursor.fetchone() == (1,)


@pytest.mark.parametrize("password", ["short!", "é漢字 'quote' \\"])
def test_chosen_game_password_runs_runtime_and_preserves_unrelated_settings(isolated_mariadb, tmp_path, password):
    from venom.server.database import Database
    service = service_at(tmp_path)
    settings = answers(isolated_mariadb, secrets.token_hex(4), password)
    config = tmp_path / "config/server.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"port": 9123, "rivals": {"count": 23}, "custom": "keep"}))
    db = service.configure_database(settings)
    saved = json.loads(config.read_text())
    assert saved["database"] == db
    assert db["password"] == password
    assert saved["port"] == 9123 and saved["rivals"] == {"count": 23}
    assert saved["custom"] == "keep"
    assert settings["admin_password"] not in config.read_text()
    assert password not in service.report_text()
    runtime = Database(db)
    try:
        runtime.initialize()
        runtime.register("WizardTamer", "example-tamer-password", {"party": [], "marker": 924})
        assert runtime.authenticate("WizardTamer", "example-tamer-password") == "wizardtamer"
        assert runtime.load("WizardTamer")[0]["marker"] == 924
    finally:
        runtime.close()


def test_blank_game_password_satisfies_real_mariadb_policy(isolated_mariadb, tmp_path):
    service = service_at(tmp_path)
    settings = answers(isolated_mariadb, secrets.token_hex(4), "")
    with admin_connection(isolated_mariadb) as connection, connection.cursor() as cursor:
        cursor.execute("INSTALL SONAME 'simple_password_check'")
    try:
        db = service.configure_database(settings)
        assert len(db["password"]) >= 43
        with app_connection(db) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT version FROM venom_schema")
            assert cursor.fetchone() == (1,)
        assert db["password"] not in service.report_text()
    finally:
        with admin_connection(isolated_mariadb) as connection, connection.cursor() as cursor:
            cursor.execute("UNINSTALL SONAME 'simple_password_check'")


def test_occupied_username_preserves_other_mmo_password_grants_and_data(isolated_mariadb, tmp_path):
    import pymysql
    suffix = secrets.token_hex(4)
    service = service_at(tmp_path)
    settings = answers(isolated_mariadb, suffix, "new-game-password!")
    other_db = "other_mmo_" + suffix
    shared_password = "other-mmo-password!"
    with admin_connection(isolated_mariadb) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE USER %s@'localhost' IDENTIFIED BY %s", (settings["user"], shared_password))
        cursor.execute(f"CREATE DATABASE `{other_db}`")
        cursor.execute(f"CREATE TABLE `{other_db}`.saved_players (value INTEGER)")
        cursor.execute(f"INSERT INTO `{other_db}`.saved_players VALUES (618)")
        cursor.execute(f"GRANT SELECT ON `{other_db}`.* TO %s@'localhost'", (settings["user"],))
        cursor.execute("SHOW GRANTS FOR %s@'localhost'", (settings["user"],))
        original_grants = cursor.fetchall()
    db = service.configure_database(settings)
    assert db["user"] != settings["user"]
    assert db["password"] == settings["password"]
    with pymysql.connect(host=settings["host"], port=settings["port"], user=settings["user"],
                         password=shared_password, database=other_db) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT value FROM saved_players")
        assert cursor.fetchone() == (618,)
        cursor.execute("SHOW GRANTS")
        assert cursor.fetchall() == original_grants
    with app_connection(db) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM venom_schema")
        assert cursor.fetchone() == (1,)


@pytest.mark.parametrize("denied_stage", ["game_account", "grants"])
def test_restricted_administrator_reports_actual_failing_stage_and_can_retry(isolated_mariadb, tmp_path, denied_stage):
    from tools.setup_service import SetupFailure
    service = service_at(tmp_path)
    suffix = secrets.token_hex(4)
    settings = answers(isolated_mariadb, suffix, "new-password!")
    limited_user = "wizard_admin_" + suffix
    limited_password = "limited-admin-password!"
    config = tmp_path / "config/server.json"
    config.parent.mkdir(parents=True)
    original = '{"port": 9222, "custom": "preserve exactly"}\n'
    config.write_text(original)
    with admin_connection(isolated_mariadb) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE USER %s@'localhost' IDENTIFIED BY %s", (limited_user, limited_password))
        cursor.execute(f"GRANT CREATE ON `{settings['name']}`.* TO %s@'localhost'", (limited_user,))
        if denied_stage == "grants":
            cursor.execute("GRANT CREATE USER ON *.* TO %s@'localhost'", (limited_user,))
    restricted = settings | {"admin_user": limited_user, "admin_password": limited_password}
    assert service.test_database(restricted)["account"] == limited_user + "@localhost"
    with pytest.raises(SetupFailure) as failure:
        service.configure_database(restricted)
    assert failure.value.stage == denied_stage
    assert isinstance(failure.value.code, int)
    assert failure.value.action
    assert config.read_text() == original
    with admin_connection(isolated_mariadb) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM mysql.user WHERE User=%s", (settings["user"],))
        assert cursor.fetchone() == (0,)
    assert limited_password not in service.report_text()
    assert settings["password"] not in service.report_text()
    db = service.configure_database(settings)
    with app_connection(db) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM venom_schema")
        assert cursor.fetchone() == (1,)


def test_complete_database_hosting_and_verification_flow(isolated_mariadb, tmp_path):
    service = service_at(tmp_path)
    settings = answers(isolated_mariadb, secrets.token_hex(4), "")
    assert service.test_database(settings)["server_version"] == isolated_mariadb["version"]
    db = service.configure_database(settings)
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        game_port = reserve.getsockname()[1]
    kit = service.configure_hosting({"host": "localhost", "port": game_port, "bind": "127.0.0.1"})
    with zipfile.ZipFile(kit) as archive:
        assert sorted(archive.namelist()) == ["config/client.json", "config/server-ca.pem"]
        for name in archive.namelist():
            content = archive.read(name)
            assert b"PRIVATE KEY" not in content
            assert db["password"].encode("utf-8") not in content
            assert settings["admin_password"].encode("utf-8") not in content
    verified = service.verify_installation()
    assert verified["ready"] is True
    assert verified["database"] == db["name"]
    assert verified["user"] == db["user"]
    assert verified["host"] == "localhost" and verified["port"] == game_port
    assert verified["tls"] in ("TLSv1.2", "TLSv1.3")
    assert verified["player_kit"] == str(kit)
    report = service.report_text()
    assert db["password"] not in report
    assert settings["admin_password"] not in report
    assert service.diagnostic_path.read_text() == report
