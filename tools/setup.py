"""Configure MySQL and trusted TLS hosting without changing the XAMPP root password."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sys
import zipfile

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
        temporary.replace(path)
        path.chmod(0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def save_json(path: Path, value):
    private_write(path, (json.dumps(value, indent=2) + "\n").encode("utf-8"))


def choice(answers, key, label, default=None, secret=False, interactive=True):
    if key in answers:
        return answers[key]
    if not interactive:
        if default is not None:
            return default
        raise ValueError(f"Missing required setting {key!r} in the answers JSON.")
    prompt = label + (f" [{default}]" if default is not None and not secret else "") + ": "
    value = getpass.getpass(prompt) if secret else input(prompt)
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


def mysql_setup(root: Path, answers: dict, interactive=True):
    import pymysql
    from venom.server.database import initialize_database

    config_path = root / "config/server.json"
    config = read_json(config_path)
    old = config.get("database", {})
    print("\nDigimon Venom NXT - MySQL / XAMPP setup\nStart MySQL or MariaDB before continuing. The existing administrator password will not be changed.\n")
    host = str(choice(answers, "host", "MySQL host", old.get("host", "127.0.0.1"), interactive=interactive))
    port = validated_port(choice(answers, "port", "MySQL port", old.get("port", 3306), interactive=interactive))
    name = validated_identifier(choice(answers, "name", "Game database name", old.get("name", "digimon_venom_nxt"), interactive=interactive), "Database name")
    admin_user = str(choice(answers, "admin_user", "MySQL administrator username", "root", interactive=interactive))
    admin_password = choice(answers, "admin_password", "Existing XAMPP / administrator password (Enter for blank)", "", secret=True, interactive=interactive)
    app_user = validated_identifier(choice(answers, "user", "Dedicated game database username", old.get("user", "venom"), interactive=interactive), "Database username", 32)
    if app_user.lower() in {"root", "mysql", "mariadb", admin_user.lower()}:
        raise ValueError("Use a separate game database account, not the administrator account.")
    default_password = old.get("password") or secrets.token_urlsafe(32)
    app_password = choice(answers, "password", "Game database password (Enter to preserve / securely generate)", default_password, secret=True, interactive=interactive)
    if not isinstance(app_password, str) or len(app_password) < 12:
        raise ValueError("The dedicated game database password must contain at least 12 characters.")
    account_host = str(choice(answers, "account_host", "MySQL account host (localhost for a local game server)", old.get("account_host", "localhost"), interactive=interactive))
    if not account_host or any(c in account_host for c in ("'", '"', ";", "\x00", "\n")):
        raise ValueError("Invalid MySQL account host.")
    db = {"driver": "mysql", "host": host, "port": port, "user": app_user, "password": app_password, "name": name, "account_host": account_host}
    admin = pymysql.connect(host=host, port=port, user=admin_user, password=admin_password or "", charset="utf8mb4", connect_timeout=10, autocommit=True)
    created = False
    try:
        with admin.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            try:
                cursor.execute("CREATE USER %s@%s IDENTIFIED BY %s", (app_user, account_host, app_password))
                created = True
            except pymysql.err.OperationalError as exc:
                if exc.args[0] != 1396:
                    raise
                print("Reusing the existing dedicated account; its password has not been changed.")
            cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON `{name}`.* TO %s@%s", (app_user, account_host))
        # Validate the dedicated credentials and initialize the actual server schema.
        initialize_database(db)
    except pymysql.MySQLError:
        if not created:
            print("If the dedicated account already exists, supply its existing password or choose a new username.", file=sys.stderr)
        raise
    finally:
        admin.close()
    config.setdefault("host", "0.0.0.0")
    config.setdefault("port", 8765)
    config.setdefault("tls_cert", "config/server-cert.pem")
    config.setdefault("tls_key", "config/server-key.pem")
    config.setdefault("allow_registration", True)
    config["database"] = db
    save_json(config_path, config)
    print(f"\nDatabase schema is ready. Dedicated credentials saved in {config_path}.\nNext run 03_SETUP_PUBLIC_HOSTING.bat. Administrator credentials were not saved.")
    return db


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
    parser.add_argument("--root", type=Path, default=ROOT, help="Source or server distribution directory.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, description in (("mysql", "Provision a dedicated MySQL account and initialize the schema."), ("hosting", "Create / renew a hostname-verified TLS certificate and public player kit.")):
        child = sub.add_parser(name, help=description, description=description)
        child.add_argument("--answers", type=Path, help="Read settings from a JSON file without prompting. This file may contain secrets; do not distribute it.")
        if name == "hosting":
            child.add_argument("--output", type=Path, help="Path of the two-file public connection ZIP.")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        answers = read_json(args.answers) if args.answers else {}
        if args.answers and not args.answers.is_file():
            raise ValueError("The requested answers JSON does not exist.")
        if not isinstance(answers, dict):
            raise ValueError("The answers JSON must contain an object.")
        if args.command == "mysql":
            mysql_setup(root, answers, interactive=args.answers is None)
        else:
            hosting_setup(root, answers, interactive=args.answers is None, output=args.output)
    except (Exception, KeyboardInterrupt) as exc:
        # Database drivers redact password values in errors; never dump the answers/config dict.
        print(f"\nSETUP FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
