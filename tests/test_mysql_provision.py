"""Provisioning regressions for fresh installs and shared MySQL instances.

The live MariaDB smoke test covers actual authentication; these tests exercise
fault paths without changing the operator's database or shared accounts.
"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pymysql
import pytest

from tools import setup
from tools.password_prompt import PasswordCancelled
from venom.server.database import Database


@pytest.fixture
def provision(tmp_path, monkeypatch):
    admin = MagicMock()
    cursor = admin.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = None  # MariaDB has no partial_revokes variable.
    connect = MagicMock(return_value=admin)
    probe = MagicMock(side_effect=[False, True])
    initialize = MagicMock()
    monkeypatch.setattr(pymysql, "connect", connect)
    monkeypatch.setattr(setup, "_probe_game_login", probe)
    monkeypatch.setattr("venom.server.database.initialize_database", initialize)
    answers = {
        "host": "127.0.0.1", "port": 3306, "name": "venom_game",
        "admin_user": "root", "admin_password": "AdminFixture!",
        "user": "venom", "password": "short", "account_host": "localhost",
    }
    output = io.StringIO()

    def run(overrides=None, interactive=False):
        selected = dict(answers)
        if overrides:
            selected.update(overrides)
        with redirect_stdout(output), redirect_stderr(output):
            return setup.mysql_setup(tmp_path, selected, interactive=interactive)

    return SimpleNamespace(root=tmp_path, path=tmp_path / "config/server.json",
                           admin=admin, cursor=cursor, connect=connect,
                           probe=probe, initialize=initialize, answers=answers,
                           output=output, run=run)


def sql_calls(fixture, prefix):
    return [call for call in fixture.cursor.execute.call_args_list
            if call.args[0].startswith(prefix)]


def test_fresh_install_uses_chosen_short_password_without_a_previous_account(provision):
    db = provision.run()
    assert db["password"] == "short"
    assert db["user"] == "venom"
    assert json.loads(provision.path.read_text())["database"] == db
    creation = sql_calls(provision, "CREATE USER")
    assert len(creation) == 1
    assert creation[0].args[1] == ("venom", "localhost", "short")
    provision.initialize.assert_called_once_with(db)
    assert "short" not in provision.output.getvalue()
    assert not sql_calls(provision, "ALTER USER")
    assert not sql_calls(provision, "SET PASSWORD")


def test_matching_existing_credentials_are_reused_without_create_or_password_change(provision):
    provision.probe.side_effect = None
    provision.probe.return_value = True
    db = provision.run()
    assert db["user"] == "venom"
    assert not sql_calls(provision, "CREATE USER")
    assert not sql_calls(provision, "ALTER USER")
    assert not sql_calls(provision, "DROP USER")
    assert len(sql_calls(provision, "GRANT")) == 1


@pytest.mark.parametrize("saved_password", [None, "OldPass!"])
def test_blank_game_password_generates_or_preserves_saved_password(provision, saved_password):
    if saved_password is not None:
        provision.path.parent.mkdir()
        provision.path.write_text(json.dumps({"database": {
            "host": "127.0.0.1", "port": 3306, "user": "venom",
            "password": saved_password, "account_host": "localhost"}}))
    db = provision.run({"password": ""})
    assert isinstance(db["password"], str) and db["password"]
    if saved_password is not None:
        assert db["password"] == saved_password
    else:
        assert len(db["password"]) >= 32
    assert db["password"] not in provision.output.getvalue()


def test_schema_failure_drops_only_the_account_created_here_and_keeps_config(provision):
    provision.path.parent.mkdir()
    original = '{"port": 8769, "database": {"password": "saved"}}'
    provision.path.write_text(original)
    provision.initialize.side_effect = RuntimeError("schema fixture failed")
    with pytest.raises(RuntimeError, match="schema fixture failed"):
        provision.run()
    assert provision.path.read_text() == original
    drops = sql_calls(provision, "DROP USER")
    assert len(drops) == 1
    assert drops[0].args[1] == ("venom", "localhost")
    assert not sql_calls(provision, "DROP DATABASE")
    provision.admin.close.assert_called_once()


def test_schema_failure_never_drops_a_reused_account(provision):
    provision.probe.side_effect = None
    provision.probe.return_value = True
    provision.initialize.side_effect = pymysql.err.OperationalError(1142, "driver fixture secret")
    with pytest.raises(ValueError) as raised:
        provision.run()
    assert not provision.path.exists()
    assert not sql_calls(provision, "DROP USER")
    assert not sql_calls(provision, "CREATE USER")
    assert "driver fixture secret" not in str(raised.value)


def test_failed_atomic_save_cleans_only_new_account(provision, monkeypatch):
    provision.path.parent.mkdir()
    original = '{"port": 8769, "database": {"password": "saved"}}'
    provision.path.write_text(original)
    monkeypatch.setattr(setup, "save_json", MagicMock(side_effect=OSError("disk fixture full")))
    with pytest.raises(OSError, match="disk fixture full"):
        provision.run()
    assert provision.path.read_text() == original
    assert len(sql_calls(provision, "DROP USER")) == 1
    assert not sql_calls(provision, "DROP DATABASE")


def test_non_authentication_probe_failure_does_not_create_more_accounts(provision):
    provision.probe.side_effect = pymysql.err.OperationalError(2003, "driver fixture secret")
    with pytest.raises(ValueError) as raised:
        provision.run()
    assert not sql_calls(provision, "CREATE USER")
    assert not sql_calls(provision, "GRANT")
    assert not provision.path.exists()
    assert "driver fixture secret" not in str(raised.value)


def test_created_account_with_wrong_host_is_removed_without_repeated_accounts(provision):
    provision.probe.side_effect = [False, False]
    with pytest.raises(ValueError) as raised:
        provision.run()
    assert "host" in str(raised.value).lower()
    assert len(sql_calls(provision, "CREATE USER")) == 1
    assert len(sql_calls(provision, "DROP USER")) == 1
    assert not sql_calls(provision, "GRANT")
    assert not provision.path.exists()


def test_repeated_name_collisions_are_bounded_without_touching_existing_accounts(provision):
    provision.probe.side_effect = None
    provision.probe.return_value = False

    def execute(sql, parameters=None):
        if sql.startswith("CREATE USER"):
            raise pymysql.err.OperationalError(1396, "occupied")

    provision.cursor.execute.side_effect = execute
    with pytest.raises(ValueError, match="name conflicts"):
        provision.run()
    creations = sql_calls(provision, "CREATE USER")
    assert len(creations) == 6
    assert creations[0].args[1][0] == "venom"
    for call in creations[1:]:
        assert call.args[1][0].startswith("venom_nxt_")
        assert len(call.args[1][0]) <= 32
    assert not sql_calls(provision, "DROP USER")
    assert not sql_calls(provision, "GRANT")
    assert not provision.path.exists()


def test_password_policy_retry_keeps_admin_session_and_reprompts_only_new_password(provision, monkeypatch):
    provision.answers.pop("password")
    entered = MagicMock(side_effect=["short", "NewPolicyFixture!123456"])
    monkeypatch.setattr(setup, "read_password", entered)
    created = []
    attempts = []

    def execute(sql, parameters=None):
        if sql.startswith("CREATE USER"):
            attempts.append(parameters)
            if len(attempts) == 1:
                raise pymysql.err.OperationalError(1819, "driver included short")
            created.append(parameters)

    provision.cursor.execute.side_effect = execute
    provision.probe.side_effect = lambda db: bool(created)
    db = provision.run(interactive=True)
    assert db["password"] == "NewPolicyFixture!123456"
    assert entered.call_count == 2
    assert provision.connect.call_count == 1
    assert len(created) == 1
    assert len(sql_calls(provision, "GRANT")) == 1
    assert "driver included" not in provision.output.getvalue()
    assert "NewPolicyFixture!123456" not in provision.output.getvalue()


def test_password_policy_cancellation_preserves_config_and_shared_accounts(provision, monkeypatch):
    provision.answers.pop("password")
    monkeypatch.setattr(setup, "read_password", MagicMock(side_effect=["short", PasswordCancelled]))
    provision.probe.side_effect = None
    provision.probe.return_value = False

    def execute(sql, parameters=None):
        if sql.startswith("CREATE USER"):
            raise pymysql.err.OperationalError(1819, "policy")

    provision.cursor.execute.side_effect = execute
    with pytest.raises(PasswordCancelled):
        provision.run(interactive=True)
    assert not provision.path.exists()
    assert not sql_calls(provision, "ALTER USER")
    assert not sql_calls(provision, "DROP USER")
    provision.admin.close.assert_called_once()


def test_password_policy_noninteractive_error_is_finite_and_redacted(provision):
    provision.probe.side_effect = None
    provision.probe.return_value = False

    def execute(sql, parameters=None):
        if sql.startswith("CREATE USER"):
            raise pymysql.err.OperationalError(1819, "driver includes short")

    provision.cursor.execute.side_effect = execute
    with pytest.raises(ValueError) as raised:
        provision.run()
    assert "password" in str(raised.value).lower()
    assert "driver includes short" not in str(raised.value)
    assert len(sql_calls(provision, "CREATE USER")) == 1
    assert not provision.path.exists()


@pytest.mark.parametrize("variable, expected", [
    (None, r"`venom\_game`"),
    (("partial_revokes", "OFF"), r"`venom\_game`"),
    (("partial_revokes", "0"), r"`venom\_game`"),
    (("partial_revokes", "ON"), "`venom_game`"),
    (("partial_revokes", "1"), "`venom_game`"),
])
def test_grant_scopes_literal_database_in_both_mysql_modes(variable, expected):
    cursor = MagicMock()
    cursor.fetchone.return_value = variable
    setup._grant_database(cursor, "venom_game", "venom", "localhost")
    grants = [call for call in cursor.execute.call_args_list if call.args[0].startswith("GRANT")]
    assert len(grants) == 1
    assert f" ON {expected}.* " in grants[0].args[0]
    assert grants[0].args[1] == ("venom", "localhost")
    assert not any("SET GLOBAL" in call.args[0] for call in cursor.execute.call_args_list)


@pytest.mark.parametrize("actual, accepted", [("venom@localhost", True), ("venom@%", False), ("other@localhost", False)])
def test_probe_uses_utf8_bytes_and_checks_the_account_that_authenticated(monkeypatch, actual, accepted):
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (actual,)
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(pymysql, "connect", connect)
    db = {"host": "127.0.0.1", "port": 3306, "user": "venom",
          "password": "é漢!", "name": "venom_game", "account_host": "localhost"}
    assert setup._probe_game_login(db) is accepted
    assert connect.call_args.kwargs["password"] == "é漢!".encode("utf-8")
    assert not connect.call_args.kwargs.get("database")
    connection.close.assert_called_once()


@pytest.mark.parametrize("code", [1045, 1698])
def test_probe_authentication_rejections_are_recoverable(monkeypatch, code):
    monkeypatch.setattr(pymysql, "connect", MagicMock(side_effect=pymysql.err.OperationalError(code, "rejected")))
    db = {"host": "127.0.0.1", "port": 3306, "user": "venom", "password": "pass", "account_host": "localhost"}
    assert setup._probe_game_login(db) is False


def test_runtime_database_uses_the_same_utf8_password_bytes_as_provisioning(monkeypatch):
    connection = MagicMock()
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(pymysql, "connect", connect)
    db = Database({"driver": "mysql", "password": "é漢!"})
    try:
        db._connect()
    finally:
        db.close()
    assert connect.call_args.kwargs["password"] == "é漢!".encode("utf-8")
    connection.close.assert_called_once()
