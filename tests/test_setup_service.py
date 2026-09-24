"""Real loopback greeting fixtures and injected authentication/setup failures.

The loopback fixture is a tiny protocol peer, not a MySQL database. Actual
Owned MySQL lifecycle checks are covered by the portable database suite.
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
from tools.setup_service import SetupService, inspect_mysql_endpoint


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


def test_prepare_uses_owned_root_and_ignores_external_endpoint(tmp_path, monkeypatch):
    from tools import portable_mysql
    calls = []
    monkeypatch.setattr(portable_mysql, "prepare", lambda root: calls.append(root) or {
        "host": "127.0.0.1", "port": 3307, "server_version": "8.4", "account": "root@127.0.0.1"})
    service = SetupService(tmp_path)
    result = service.test_database({"host": "external.example", "port": 3306, "admin_password": "must-not-be-used"})
    assert calls == [tmp_path.resolve()]
    assert result["port"] == 3307
    assert "must-not-be-used" not in service.report.text()


def test_configure_passes_only_game_login_options_to_manager(tmp_path, monkeypatch):
    calls = []
    def provision(root, answers, **kwargs):
        calls.append((root, answers))
        return {"portable": True, "name": answers["name"]}
    monkeypatch.setattr(setup_service.setup, "mysql_setup", provision)
    service = SetupService(tmp_path)
    result = service.configure_database({"name": "fresh_game", "user": "venom_nxt", "password": "chosen", "host": "other-pc", "admin_password": "external"})
    assert result["portable"] is True
    assert calls == [(tmp_path.resolve(), {"name": "fresh_game", "user": "venom_nxt", "password": "chosen"})]
    assert "chosen" not in service.report.text()
    assert "external" not in service.report.text()


def test_defaults_do_not_select_external_database_endpoint(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/server.json").write_text(json.dumps({"database": {"host": "other-pc", "port": 3306}}))
    defaults = SetupService(tmp_path).defaults()
    assert defaults["host"] == "127.0.0.1"
    assert defaults["port"] == 3307
    assert defaults["account_host"] == "127.0.0.1"
