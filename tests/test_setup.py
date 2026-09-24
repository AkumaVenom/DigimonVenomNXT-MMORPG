"""TLS trust, credential separation and distribution regressions (no MySQL service needed)."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from tools.build import archive
from tools.setup import hosting_setup, mysql_setup


class HostingTests(unittest.IsolatedAsyncioTestCase):
    async def test_bundled_ca_connects_wrong_hostname_rejected_and_renewal_preserves_trust(self):
        with tempfile.TemporaryDirectory(prefix="venom setup ") as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config/server.json").write_text(json.dumps({"database": {"password": "private-database-secret"}}), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                kit = hosting_setup(root, {"host": "localhost", "port": 8765, "bind": "127.0.0.1"}, interactive=False)
            with zipfile.ZipFile(kit) as zipped:
                self.assertEqual(["config/client.json", "config/server-ca.pem"], sorted(zipped.namelist()))
                client = json.loads(zipped.read("config/client.json"))
                self.assertTrue(client["tls"])
                for name in zipped.namelist():
                    self.assertNotIn(b"PRIVATE KEY", zipped.read(name))
                    self.assertNotIn(b"private-database-secret", zipped.read(name))
            ca_before = (root / "config/server-ca.pem").read_bytes()
            with redirect_stdout(io.StringIO()):
                hosting_setup(root, {"host": "localhost", "port": 8765}, interactive=False)
            self.assertEqual(ca_before, (root / "config/server-ca.pem").read_bytes())
            self.assertEqual("private-database-secret", json.loads((root / "config/server.json").read_text())["database"]["password"])
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(root / "config/server-cert.pem", root / "config/server-key.pem")
            client_context = ssl.create_default_context(cafile=str(root / "config/server-ca.pem"))

            async def echo(reader, writer):
                try:
                    writer.write(await reader.readexactly(4))
                    await writer.drain()
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except ConnectionError:
                        pass

            server = await asyncio.start_server(echo, "127.0.0.1", 0, ssl=server_context)
            port = server.sockets[0].getsockname()[1]
            async with server:
                reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=client_context, server_hostname="localhost")
                writer.write(b"test")
                await writer.drain()
                self.assertEqual(b"test", await reader.readexactly(4))
                writer.close()
                await writer.wait_closed()
                # A deliberately rejected handshake may report ConnectionResetError server-side.
                loop = asyncio.get_running_loop()
                previous = loop.get_exception_handler()
                rejected = asyncio.Event()
                def expected_rejection(loop, context):
                    if isinstance(context.get("exception"), ConnectionResetError):
                        rejected.set()
                    else:
                        loop.default_exception_handler(context)
                loop.set_exception_handler(expected_rejection)
                try:
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        await asyncio.open_connection("127.0.0.1", port, ssl=client_context, server_hostname="wrong.example")
                    try:
                        await asyncio.wait_for(rejected.wait(), timeout=1)
                    except TimeoutError:
                        pass  # Some TLS implementations close without a server-side callback.
                finally:
                    loop.set_exception_handler(previous)


class MySQLSetupTests(unittest.TestCase):
    def test_provisioning_delegates_to_owned_manager(self):
        with tempfile.TemporaryDirectory(prefix="server with spaces ") as temporary:
            root = Path(temporary)
            answers = {"password": "Game password!"}
            callback = MagicMock()
            expected = {"driver": "mysql", "portable": True, "port": 3307}
            with patch("tools.portable_mysql.setup_database", return_value=expected) as provision:
                result = mysql_setup(root, answers, interactive=False, stage_callback=callback)
            self.assertEqual(expected, result)
            provision.assert_called_once_with(root.resolve(), answers=answers, stage_callback=callback)

    def test_manager_failure_does_not_write_configuration_from_wrapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("tools.portable_mysql.setup_database", side_effect=RuntimeError("owned instance unavailable")):
                with self.assertRaisesRegex(RuntimeError, "owned instance unavailable"):
                    mysql_setup(root, {}, interactive=False)
            self.assertFalse((root / "config/server.json").exists())


class DistributionTests(unittest.TestCase):
    def test_setup_cli_handles_explicit_distribution_root_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="venom portability ") as temporary:
            root = Path(temporary) / "Windows Server x64"
            answers = Path(temporary) / "hosting answers.json"
            answers.write_text(json.dumps({"host": "127.0.0.1", "port": 9876, "bind": "127.0.0.1"}))
            result = subprocess.run([sys.executable, "-m", "tools.setup", "--root", str(root), "hosting", "--answers", str(answers)], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, check=False)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((root / "Public_Player_Connection_Kit.zip").is_file())
            self.assertEqual(9876, json.loads((root / "config/client.json").read_text())["port"])

    def test_distribution_zip_extracts_directly_to_client_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = root / "Windows_Client_x64"
            (client / "config").mkdir(parents=True)
            (client / "config/client.json").write_text("{}")
            (client / "DigimonVenomNXT.exe").write_bytes(b"fixture")
            output = root / "Windows_Client_x64.zip"
            archive(client, output)
            with zipfile.ZipFile(output) as zipped:
                self.assertEqual(["DigimonVenomNXT.exe", "config/client.json"], sorted(zipped.namelist()))


if __name__ == "__main__":
    unittest.main()
