"""Stage-specific, secret-free diagnostics and recoverable report storage."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path

import pymysql
import pytest

from tools.setup_diagnostics import DiagnosticReport, SetupFailure, describe_failure


def test_handshake_failure_is_not_a_password_rejection():
    handshake = describe_failure("administrator", pymysql.OperationalError(1043, "Bad handshake"))
    authentication = describe_failure("administrator", pymysql.OperationalError(1045, "Access denied"))
    assert handshake.code == 1043
    assert "handshake" in handshake.message
    assert "3307" in handshake.action and "8765" in handshake.action
    assert authentication.code == 1045
    assert "sign-in" in authentication.message
    assert "mysql/data" in authentication.action
    assert "administrator" in str(handshake) and "1043" in str(handshake)


def test_game_account_rejection_does_not_demand_an_existing_game_password():
    failure = describe_failure("game_account", pymysql.OperationalError(1045, "secret driver detail"))
    assert "fresh install does not require" in failure.action
    assert "secret driver detail" not in str(failure)


def test_nested_suppressed_context_keeps_actual_numeric_error_code():
    try:
        try:
            raise pymysql.OperationalError(1043, "password=DoNotExposeMe!")
        except pymysql.MySQLError:
            raise ValueError("wrapper contains another password") from None
    except ValueError as exc:
        failure = describe_failure("administrator", exc)
    assert failure.code == 1043
    assert "DoNotExposeMe" not in str(failure)
    assert "wrapper" not in str(failure)


def test_explicit_cause_takes_precedence_over_context_and_cycles_are_bounded():
    outer = RuntimeError("arbitrary sensitive message")
    outer.__cause__ = pymysql.OperationalError(1044, "permission failure")
    outer.__context__ = pymysql.OperationalError(1045, "authentication failure")
    outer.__cause__.__context__ = outer
    assert describe_failure("grants", outer).code == 1044


def test_authored_failure_is_preserved_including_nested_wrappers():
    safe = SetupFailure("endpoint", "PORT", "Enter a database port.", "Use a port between 1 and 65535.")
    assert describe_failure("verify", safe) is safe
    wrapper = RuntimeError("private details")
    wrapper.__cause__ = safe
    assert describe_failure("verify", wrapper) is safe
    assert "PORT" in str(safe) and "endpoint" in str(safe)


@pytest.mark.parametrize("stage,code,expected", [
    ("grants", 1044, "permission"),
    ("schema", 1142, "permission"),
    ("game_account", 1819, "password policy"),
    ("endpoint", 2003, "reach"),
    ("endpoint", 2005, "hostname"),
    ("administrator", 2013, "timed out"),
    ("administrator", 2026, "TLS"),
    ("administrator", 1524, "authentication method"),
])
def test_known_error_categories(stage, code, expected):
    failure = describe_failure(stage, pymysql.OperationalError(code, "never copy this driver message"))
    assert expected in failure.message
    assert failure.code == code and failure.stage == stage


def test_report_ignores_driver_sql_secrets_unapproved_keys_and_arbitrary_objects(tmp_path):
    class Sensitive:
        def __str__(self):
            raise AssertionError("metadata must not stringify arbitrary objects")

    report = DiagnosticReport(tmp_path)
    report.record("administrator", "started", host="127.0.0.1", port=3306,
                  password="MyTopSecret", admin_password="AdminSecret",
                  sql="CREATE USER IDENTIFIED BY 'SqlSecret'", params=["ParamSecret"],
                  config={"password": "ConfigSecret"}, traceback="TracebackSecret",
                  user=Sensitive(), server_version={"password": "NestedSecret"})
    failure = report.failure("game_account", pymysql.OperationalError(
        1064, "CREATE USER IDENTIFIED BY 'DriverPassword'"))
    raw = report.text()
    for secret in ("MyTopSecret", "AdminSecret", "SqlSecret", "ParamSecret", "ConfigSecret",
                   "TracebackSecret", "NestedSecret", "DriverPassword", "CREATE USER"):
        assert secret not in raw
        assert secret not in str(failure)
    data = json.loads(raw)
    assert data["setup_version"] == "0.12.0"
    assert set(data["environment"]) == {"python", "platform", "pymysql"}
    assert data["events"][0]["host"] == "127.0.0.1"
    assert data["events"][1]["error_code"] == 1064
    assert json.loads(report.path.read_text(encoding="utf-8")) == data
    assert not report.write_error


def test_report_write_failure_preserves_diagnostics_and_original_error(tmp_path, monkeypatch):
    report = DiagnosticReport(tmp_path)
    report.record("administrator", "success", server_version="MariaDB fixture")
    disk_before = report.path.read_bytes()

    def denied(*args, **kwargs):
        raise PermissionError("secret OS path and PasswordSecret")

    with monkeypatch.context() as failed:
        failed.setattr(os, "replace", denied)
        original = pymysql.OperationalError(1043, "PrivateDriverMessage")
        failure = report.failure("game_account", original)
        assert failure.code == 1043
        assert report.write_error
        assert "PasswordSecret" not in report.write_error
        assert report.path.read_bytes() == disk_before
        assert json.loads(report.text())["events"][-1]["error_code"] == 1043
        assert not list(report.path.parent.glob(".setup-report-*.tmp"))
    report.record("game_account", "success", user="venom_nxt")
    assert not report.write_error
    events = json.loads(report.path.read_text())["events"]
    assert [event["status"] for event in events] == ["success", "failure", "success"]


def test_unwritable_log_folder_never_prevents_success_report_in_memory(tmp_path):
    (tmp_path / "logs").write_text("not a directory", encoding="utf-8")
    report = DiagnosticReport(tmp_path)
    report.record("verify", "success", database="digimon_venom_nxt")
    assert report.write_error
    assert json.loads(report.text())["events"][0]["status"] == "success"


def test_threaded_history_is_bounded_atomic_and_keeps_failure_followed_by_success(tmp_path):
    report = DiagnosticReport(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda index: report.record("verify", "running", version=str(index)), range(110)))
    report.failure("verify", pymysql.OperationalError(1045, "secret"))
    report.record("verify", "success")
    data = json.loads(report.path.read_text())
    assert len(data["events"]) == 100
    assert data == json.loads(report.text())
    assert data["events"][-2]["status"] == "failure"
    assert data["events"][-1]["status"] == "success"
    assert all("+00:00" in event["timestamp"] for event in data["events"])
    assert not list(report.path.parent.glob(".setup-report-*.tmp"))


def test_unknown_exception_text_and_nested_non_scalar_codes_are_not_logged(tmp_path):
    report = DiagnosticReport(tmp_path)
    failure = report.failure("save_config", ValueError({"password": "DictionarySecret"}))
    report.record("verify", "SensitiveStatus", error_code={"password": "CodeSecret"})
    assert failure.code is None
    assert "DictionarySecret" not in report.text()
    assert "CodeSecret" not in report.text()
    assert "SensitiveStatus" not in report.text()
    assert "configuration" in failure.message


def test_portable_errors_keep_actionable_authored_text(tmp_path):
    from tools.portable_mysql import PortableError
    report = DiagnosticReport(tmp_path)
    failure = report.failure("start", PortableError("Port 3307 belongs to a different database."))
    assert failure.code == "PORTABLE_MYSQL"
    assert "different database" in failure.message
    assert "different database" in report.text()
