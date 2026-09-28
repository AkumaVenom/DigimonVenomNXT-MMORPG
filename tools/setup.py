"""Set up the server-owned portable MySQL instance and trusted TLS hosting."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
if getattr(sys, "frozen", False) and ROOT.name.lower() == "admin" and (ROOT.parent / "VenomWorldServer.exe").is_file():
    ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.password_prompt import PasswordCancelled, read_password

from venom.version import VERSION as SETUP_VERSION


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else ({} if default is None else default)


def private_write(path: Path, value: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".new")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(value)
        temporary.chmod(0o600)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def save_json(path: Path, value):
    private_write(path, (json.dumps(value, indent=2) + "\n").encode("utf-8"))


def choice(answers, key, label, default=None, secret=False, interactive=True, password_mode="auto"):
    if key in answers:
        return answers[key]
    if not interactive:
        if default is not None:
            return default
        raise ValueError(f"Missing required setting {key!r} in the answers JSON.")
    prompt = label + (f" [{default}]" if default is not None and not secret else "") + ": "
    value = read_password(label, mode=password_mode) if secret else input(prompt)
    return value if value else default


def validated_identifier(value, label, maximum=64):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0," + str(maximum - 1) + r"}", value):
        raise ValueError(f"{label} must start with a letter and contain only letters, numbers and underscores (maximum {maximum}).")
    return value


def validated_port(value):
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("Ports must be between 1 and 65535.")
    return port


def mysql_setup(root: Path, answers: dict, interactive=True, password_mode="auto", stage_callback=None):
    """Provision only this folder's MySQL instance; never select another service.

    The UI compatibility parameters remain accepted so existing launchers can use
    the same command. Database credentials are managed by the portable service.
    """
    from tools.portable_mysql import setup_database
    print("Preparing Digimon Venom NXT's portable MySQL database...", flush=True)
    database = setup_database(Path(root).resolve(), answers=answers, stage_callback=stage_callback)
    print("Database ready. Saves are stored in mysql/data inside this server folder.\n"
          "Next run 03_SETUP_PUBLIC_HOSTING.bat. To back up, stop the world server "
          "and MySQL cleanly before copying the complete server folder.", flush=True)
    return database


def hostname(value: str):
    value = str(value).strip().strip("[]")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if len(value) > 253 or "://" in value or "/" in value or ":" in value:
        raise ValueError("Enter a DNS hostname or IP address, without a URL scheme, path or port.")
    try:
        value = value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("Invalid DNS hostname.") from exc
    if not value or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in value.split(".")):
        raise ValueError("Invalid DNS hostname.")
    return value


def create_certificates(root: Path, server_name: str):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(timezone.utc)
    config_dir = root / "config"
    ca_key_path = config_dir / "authority/server-ca-key.pem"
    ca_path = config_dir / "server-ca.pem"
    if ca_key_path.exists() != ca_path.exists():
        raise ValueError("The existing CA certificate / private key pair is incomplete. Restore the missing file before renewing hosting certificates.")
    if ca_key_path.exists():
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(ca_path.read_bytes())
        if ca_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != ca_cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
            raise ValueError("The saved CA certificate and private key do not match.")
        if ca_cert.not_valid_after_utc < now + timedelta(days=400):
            raise ValueError("The server CA expires within 400 days. Back up and deliberately rotate the CA, then distribute a new connection kit to all players.")
    else:
        ca_key = ec.generate_private_key(ec.SECP384R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Digimon Venom NXT Private Server CA")])
        ca_cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
                   .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                   .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
                   .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
                   .sign(ca_key, hashes.SHA384()))
        private_write(ca_key_path, ca_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        private_write(ca_path, ca_cert.public_bytes(serialization.Encoding.PEM))
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    try:
        san = x509.IPAddress(ipaddress.ip_address(server_name))
    except ValueError:
        san = x509.DNSName(server_name)
    certificate = (x509.CertificateBuilder()
                   .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, server_name[:64])]))
                   .issuer_name(ca_cert.subject).public_key(leaf_key.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
                   .not_valid_after(now + timedelta(days=397))
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .add_extension(x509.SubjectAlternativeName([san]), critical=False)
                   .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
                   .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                   .sign(ca_key, hashes.SHA384()))
    private_write(config_dir / "server-key.pem", leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    private_write(config_dir / "server-cert.pem", certificate.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(serialization.Encoding.PEM))
    return ca_path, certificate.not_valid_after_utc


def hosting_setup(root: Path, answers: dict, interactive=True, output: Path | None = None):
    print("\nDigimon Venom NXT - Public hosting and player connection kit\nUse the address players will actually connect to. DNS is recommended for a changing public IP.\n")
    old_client = read_json(root / "config/client.json")
    public_host = hostname(choice(answers, "host", "Public DNS hostname or public IP", old_client.get("host", "localhost"), interactive=interactive))
    port = validated_port(choice(answers, "port", "Game TCP port", old_client.get("port", 8765), interactive=interactive))
    bind = str(choice(answers, "bind", "Server bind address", "0.0.0.0", interactive=interactive))
    ipaddress.ip_address(bind)
    config_path = root / "config/server.json"
    server_config = read_json(config_path)
    ca_path, expiry = create_certificates(root, public_host)
    client_config = {"host": public_host, "port": port, "ca_file": "config/server-ca.pem", "server_name": public_host, "tls": True}
    server_config.update({"host": bind, "port": port, "tls_cert": "config/server-cert.pem", "tls_key": "config/server-key.pem"})
    server_config.setdefault("allow_registration", True)
    save_json(config_path, server_config)
    save_json(root / "config/client.json", client_config)
    kit = output or root / "Public_Player_Connection_Kit.zip"
    kit.parent.mkdir(parents=True, exist_ok=True)
    # Deliberate two-file allowlist: no private keys, administrator settings or credentials.
    with zipfile.ZipFile(kit, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("config/client.json", json.dumps(client_config, indent=2) + "\n")
        archive.write(ca_path, "config/server-ca.pem")
    print(f"\nPublic player kit created: {kit}\nServer: wss://{public_host}:{port}\nTLS certificate expires: {expiry.date()} (run hosting setup again before expiry).\n\nExtract this kit INTO the Windows client folder, merging its config folder.\nPlayers trust only this bundled CA automatically; hostname verification remains enabled.\nShare the updated client folder / ZIP with players. Keep the entire server folder private.\nAllow TCP {port} through the host firewall and forward TCP {port} on the router if needed.\nStart the server with START_WORLD_SERVER_CONSOLE.bat.")
    if not server_config.get("database"):
        print("\nMySQL has not been configured yet. Run 02_SETUP_MYSQL.bat before starting the public server.")
    return kit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"Digimon Venom NXT setup {SETUP_VERSION}")
    parser.add_argument("--root", type=Path, default=ROOT, help="Source or server distribution directory.")
    sub = parser.add_subparsers(dest="command")
    wizard = sub.add_parser("wizard", help="Open the guided desktop setup window.")
    wizard.add_argument("--stage", choices=("database", "hosting"), default="database")
    wizard.add_argument("--wizard", action="store_true", help=argparse.SUPPRESS)
    for name, description in (("mysql", "Prepare this server folder's portable MySQL and game schema."), ("hosting", "Create / renew a hostname-verified TLS certificate and public player kit.")):
        child = sub.add_parser(name, help=description, description=description)
        child.add_argument("--answers", type=Path, help="Read settings from a JSON file without prompting. This file may contain secrets; do not distribute it.")
        if name == "mysql":
            child.add_argument("--console-passwords", "--console", action="store_true", help="Run console setup; private database credentials are generated automatically.")
        if name == "hosting":
            child.add_argument("--output", type=Path, help="Path of the two-file public connection ZIP.")
            child.add_argument("--console", action="store_true", help="Use the console hosting setup.")
    args = parser.parse_args(argv)
    report = None
    current_stage = "validate"
    try:
        root = args.root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        if args.command in (None, "wizard"):
            from tools.setup_wizard import run
            return run(root, initial_stage=getattr(args, "stage", "database"))
        from tools.setup_diagnostics import DiagnosticReport
        report = DiagnosticReport(root)

        def progress(stage, status="started"):
            nonlocal current_stage
            current_stage = stage
            report.record(stage, "success" if status in ("passed", "ok") else status)

        progress("validate")
        answers = read_json(args.answers) if args.answers else {}
        if args.answers and not args.answers.is_file():
            raise ValueError("The requested answers JSON does not exist.")
        if not isinstance(answers, dict):
            raise ValueError("The answers JSON must contain an object.")
        if args.command == "mysql":
            mysql_setup(root, answers, interactive=args.answers is None, password_mode="console" if args.console_passwords else "auto", stage_callback=progress)
        else:
            progress("hosting")
            hosting_setup(root, answers, interactive=args.answers is None, output=args.output)
            progress("hosting", "passed")
    except (PasswordCancelled, KeyboardInterrupt):
        print("\nSETUP CANCELLED. No password was submitted for the cancelled field.", file=sys.stderr)
        return 130
    except Exception as exc:
        if report is not None:
            failure = report.failure(current_stage, exc)
            print(f"\nSETUP FAILED: {failure}\nDiagnostic report: {report.path}", file=sys.stderr)
        else:
            # Window initialization failures cannot contain database credentials.
            print("\nSETUP WINDOW COULD NOT OPEN. Install Python with Tcl/Tk enabled, rebuild, or run 02_SETUP_MYSQL.bat --console. Your configuration has not been changed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
