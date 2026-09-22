"""Real loopback greeting fixtures and injected authentication/setup failures.

The loopback fixture is a tiny protocol peer, not a MySQL database. Actual
MariaDB provisioning is covered separately by test_setup_mysql_live.py.
"""
from contextlib import contextmanager
import json
import socket
import struct
import threading
import time
from unittest.mock import MagicMock

import pymysql
import pytest

from tools import setup_service
from tools.setup_diagnostics import SetupFailure
from tools.setup_service import SetupService, find_xampp_configs, inspect_mysql_endpoint


def packet(payload, sequence=0, declared_length=None):
    length = len(payload) if declared_length is None else declared_length
    return length.to_bytes(3, "little") + bytes([sequence]) + payload


def mysql_greeting(version="5.5.5-10.11.14-MariaDB"):
    flags = 0x00088200  # PROTOCOL_41 | SECURE_CONNECTION | PLUGIN_AUTH
    payload = (
        b"\x0a" + version.encode("ascii") + b"\0" + struct.pack("<I", 42)
        + b"12345678\0" + struct.pack("<H", flags & 0xffff)
        + b"\x2d" + struct.pack("<H", 2) + struct.pack("<H", flags >> 16)
        + b"\x15" + b"\0" * 10 + b"abcdefghijkl\0" + b"mysql_native_password\0"
    )
    return packet(payload)


@contextmanager
def greeting_peer(payload=b"", close_output=False):
    """Listen once and capture every client byte; no credentials are expected."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    received = bytearray()
    errors = []

    def serve():
        try:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(2)
                if payload:
                    connection.sendall(payload)
                if close_output:
                    connection.shutdown(socket.SHUT_WR)
                while True:
                    data = connection.recv(4096)
                    if not data:
                        return
                    received.extend(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client rejects a bad service before consuming its payload.
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield listener.getsockname()[1], received
    finally:
        worker.join(timeout=2.5)
        listener.close()
        assert not worker.is_alive(), "greeting fixture did not close"
        assert not errors, f"greeting fixture failed: {type(errors[0]).__name__ if errors else ''}"


def saved_configuration(root):
    target = root / "config" / "server.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    original = b'{"port": 8765, "database": {"password": "SavedPrivateValue"}}\n'
    target.write_bytes(original)
    return target, original


def test_real_socket_valid_greeting_reports_version_without_sending_client_bytes():
    with greeting_peer(mysql_greeting()) as (port, received):
        assert inspect_mysql_endpoint("127.0.0.1", port, timeout=0.5) == "5.5.5-10.11.14-MariaDB"
    assert not received


@pytest.mark.parametrize("payload,close_output,expected", [
    (b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n", False, "NOT_MYSQL"),
    (b"", True, "NO_GREETING"),
    (packet(b"\x0a8.0.36\0", declared_length=50), True, "NO_GREETING"),
    (packet(b"\x09unsupported\0"), False, "NOT_MYSQL"),
    (packet(b"\x0a8.0.36\0"), False, "NOT_MYSQL"),
    (packet(b"\x0a8.0.36\0", sequence=1), False, "NOT_MYSQL"),
])
def test_bad_or_truncated_greetings_are_bounded_and_send_no_credentials(payload, close_output, expected):
    started = time.monotonic()
    with greeting_peer(payload, close_output=close_output) as (port, received):
        with pytest.raises(SetupFailure) as failure:
            inspect_mysql_endpoint("127.0.0.1", port, timeout=0.2)
    assert failure.value.stage == "endpoint"
    assert failure.value.code == expected
    assert time.monotonic() - started < 1.5
    assert not received


def test_silent_service_times_out_without_waiting_for_mysql_default_timeout():
    started = time.monotonic()
    with greeting_peer() as (port, received):
        with pytest.raises(SetupFailure) as failure:
            inspect_mysql_endpoint("127.0.0.1", port, timeout=0.08)
    assert failure.value.code == "NO_GREETING"
    assert time.monotonic() - started < 1.0
    assert not received


def test_real_greeting_error_1043_reaches_report_without_authentication_or_config_mutation(tmp_path, monkeypatch):
    # Fault injection: an endpoint sends a real MySQL ERR packet containing a
    # secret-like message. This does not claim to reproduce the user's server.
    target, original = saved_configuration(tmp_path)
    connect = MagicMock()
    monkeypatch.setattr(pymysql, "connect", connect)
    service = SetupService(tmp_path)
    payload = b"\xff" + struct.pack("<H", 1043) + b"#08S01password=DoNotCopyThis"
    with greeting_peer(packet(payload)) as (port, received):
        with pytest.raises(SetupFailure) as failure:
            service.test_database({"host": "127.0.0.1", "port": port,
                                   "admin_password": "PrivateAdministratorPassword"})
    assert failure.value.code == 1043 and failure.value.stage == "endpoint"
    assert "handshake" in failure.value.message
    assert target.read_bytes() == original
    connect.assert_not_called()
    assert not received
    report = service.report_text()
    assert "DoNotCopyThis" not in report
    assert "PrivateAdministratorPassword" not in report
    assert "SavedPrivateValue" not in report
    assert json.loads(report)["events"][-1]["error_code"] == 1043


def test_connection_retry_retains_failure_history_and_never_selects_or_mutates_database(tmp_path, monkeypatch):
    target, original = saved_configuration(tmp_path)
    monkeypatch.setattr(setup_service, "inspect_mysql_endpoint", lambda *args: "MariaDB greeting fixture")
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("10.11.14-MariaDB", "root@localhost")
    connect = MagicMock(side_effect=[
        pymysql.OperationalError(1045, "rejected password=WrongPasswordSecret"), connection,
    ])
    monkeypatch.setattr(pymysql, "connect", connect)
    service = SetupService(tmp_path)
    with pytest.raises(SetupFailure) as failure:
        service.test_database({"admin_password": "WrongPasswordSecret"})
    assert failure.value.code == 1045 and service._tested is None
    result = service.test_database({"admin_user": " root ", "admin_password": "CorrectPasswordSecret?é"})
    assert result["account"] == "root@localhost"
    assert connect.call_args.kwargs["user"] == "root"
    assert connect.call_args.kwargs["password"] == "CorrectPasswordSecret?é".encode("utf-8")
    assert "database" not in connect.call_args.kwargs
    cursor.execute.assert_called_once_with("SELECT VERSION(), CURRENT_USER()")
    connection.close.assert_called_once()
    assert target.read_bytes() == original
    report = service.report_text()
    assert "WrongPasswordSecret" not in report and "CorrectPasswordSecret" not in report
    events = json.loads(report)["events"]
    assert any(event["status"] == "failure" and event["error_code"] == 1045 for event in events)
    assert events[-1]["status"] == "success"


@pytest.mark.parametrize("settings", [
    {"host": "http://localhost:3306/"}, {"host": "localhost:3306"},
    {"port": 0}, {"port": 65536}, {"port": "not a port"},
    {"admin_user": "   "}, {"admin_user": "root\n"},
    {"admin_password": {"password": "NestedSecret"}}, {"admin_password": "\ud800"},
])
def test_invalid_connection_settings_do_not_contact_network_or_write_config(tmp_path, monkeypatch, settings):
    inspect = MagicMock()
    monkeypatch.setattr(setup_service, "inspect_mysql_endpoint", inspect)
    service = SetupService(tmp_path)
    with pytest.raises(SetupFailure) as failure:
        service.test_database(settings)
    assert failure.value.stage == "validate"
    inspect.assert_not_called()
    assert not (tmp_path / "config").exists()
    assert "NestedSecret" not in service.report_text()


def test_config_detection_uses_only_mysqld_port_and_ignores_password_values(tmp_path):
    ini = tmp_path / "my.ini"
    ini.write_text('[client]\nport=9999\npassword=ClientSecret\n'
                   '[mysqld]\nport="3317" ; active server port\npassword=ServerSecret\n'
                   '[mysql]\nport=9998\npassword=ShellSecret\n', encoding="utf-8-sig")
    results = find_xampp_configs(tmp_path, [ini, ini, tmp_path / "absent.ini"])
    assert results == [{"host": "127.0.0.1", "port": 3317, "path": str(ini)}]
    assert "Secret" not in json.dumps(results)


@pytest.mark.parametrize("contents", [
    "[client]\nport=3310\n", "[mysqld]\nport=oops\n", "[mysqld]\nport=0\n",
    "[mysqld]\nport=99999\n", "[mysqld]\nport\n", "not an ini file",
])
def test_malformed_xampp_configs_are_skipped_without_failing_discovery(tmp_path, contents):
    ini = tmp_path / "my.ini"
    ini.write_text(contents, encoding="utf-8")
    assert find_xampp_configs(tmp_path, [ini]) == []


def test_occupied_game_port_stops_before_hosting_files_or_certificates_change(tmp_path, monkeypatch):
    target, original = saved_configuration(tmp_path)
    hosting = MagicMock()
    monkeypatch.setattr(setup_service.setup, "hosting_setup", hosting)
    service = SetupService(tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as owner:
        owner.bind(("127.0.0.1", 0))
        owner.listen(1)
        with pytest.raises(SetupFailure) as failure:
            service.configure_hosting({"host": "localhost", "bind": "127.0.0.1", "port": owner.getsockname()[1]})
    assert failure.value.stage == "hosting" and failure.value.code == "BIND_FAILED"
    hosting.assert_not_called()
    assert target.read_bytes() == original
    assert not (tmp_path / "config" / "server-key.pem").exists()
    assert not (tmp_path / "Public_Player_Connection_Kit.zip").exists()


def test_free_game_port_is_released_after_check():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as port_picker:
        port_picker.bind(("127.0.0.1", 0))
        port = port_picker.getsockname()[1]
    setup_service.check_game_port("127.0.0.1", port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as actual_server:
        actual_server.bind(("127.0.0.1", port))


def test_configuration_uses_tested_connection_then_reports_nested_database_failure(tmp_path, monkeypatch):
    service = SetupService(tmp_path)
    settings = {"admin_password": "AdminSecret", "password": "GameSecret"}
    service._tested = service._connection_key(service._connection_settings(settings))
    connection_test = MagicMock()
    monkeypatch.setattr(service, "test_database", connection_test)

    def provision(root, answers, interactive, stage_callback):
        assert not interactive
        assert answers["admin_password"] == "AdminSecret"
        assert answers["password"] == "GameSecret"
        stage_callback("grants")
        try:
            raise pymysql.OperationalError(1142, "GRANT with password=GameSecret")
        except pymysql.MySQLError as exc:
            raise ValueError("wrapper AdminSecret") from exc

    monkeypatch.setattr(setup_service.setup, "mysql_setup", provision)
    with pytest.raises(SetupFailure) as failure:
        service.configure_database(settings)
    connection_test.assert_not_called()
    assert failure.value.stage == "grants" and failure.value.code == 1142
    assert "AdminSecret" not in service.report_text()
    assert "GameSecret" not in service.report_text()
    assert not (tmp_path / "config").exists()


def test_corrupt_saved_configuration_is_in_startup_report(tmp_path):
    import json
    from tools.setup_service import SetupService, SetupFailure
    config = tmp_path / 'config/server.json'
    config.parent.mkdir()
    config.write_text('{invalid fixture configuration')
    service = SetupService(tmp_path)
    with pytest.raises(SetupFailure) as failure:
        service.defaults()
    assert failure.value.code == 'CONFIG_INVALID'
    report = json.loads(service.report_text())
    assert report['events'][-1]['error_code'] == 'CONFIG_INVALID'
    assert config.read_text() == '{invalid fixture configuration'


def test_dns_failure_reports_hostname_action_without_driver_text():
    import socket
    from tools.setup_diagnostics import describe_failure
    failure = describe_failure('endpoint', socket.gaierror(-2, 'raw secret-like driver fixture'))
    assert failure.code == -2
    assert 'hostname' in failure.message.lower()
    assert '127.0.0.1' in failure.action
    assert 'secret-like' not in str(failure)
