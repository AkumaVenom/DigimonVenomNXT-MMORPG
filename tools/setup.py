"""Configure MySQL and trusted TLS hosting without changing the XAMPP root password."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sys
import zipfile

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
if getattr(sys, "frozen", False) and ROOT.name.lower() == "admin" and (ROOT.parent / "VenomWorldServer.exe").is_file():
    ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.password_prompt import PasswordCancelled, read_password

SETUP_VERSION = "0.3.0"


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


def _probe_game_login(db):
    """Verify the exact account selected by MySQL, without requiring DB grants."""
    import pymysql
    try:
        connection = pymysql.connect(
            host=db["host"], port=db["port"], user=db["user"],
            password=db["password"].encode("utf-8"), charset="utf8mb4",
            connect_timeout=10, read_timeout=15, write_timeout=15, autocommit=True)
    except pymysql.MySQLError as exc:
        if exc.args and exc.args[0] in (1045, 1698):
            return False
        raise
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CURRENT_USER()")
            row = cursor.fetchone()
        return bool(row and row[0] == f'{db["user"]}@{db["account_host"]}')
    finally:
        connection.close()


def _grant_database(cursor, name, user, account_host):
    # In default MySQL/MariaDB, underscores in database grants are wildcards,
    # even inside backticks. MySQL partial_revokes=ON instead uses literal names.
    cursor.execute("SHOW VARIABLES LIKE 'partial_revokes'")
    row = cursor.fetchone()
    literal_names = bool(row and str(row[1]).upper() in ("ON", "1"))
    grant_name = name if literal_names else name.replace("_", "\\_")
    cursor.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON `{grant_name}`.* TO %s@%s",
        (user, account_host))


def _cleanup_created_accounts(admin, accounts):
    """Only remove identities whose CREATE USER succeeded in this invocation."""
    for user, account_host in accounts:
        try:
            with admin.cursor() as cursor:
                cursor.execute("DROP USER IF EXISTS %s@%s", (user, account_host))
        except Exception:
            print("An unused setup login could not be removed. A later setup run can recover automatically.", file=sys.stderr)
    accounts.clear()


def _configure_game_account(admin, db, created_accounts):
    import pymysql
    if _probe_game_login(db):
        print(f'Using the working game database login: {db["user"]}.')
        return
    requested_user = db["user"]
    database_tag = hashlib.sha256(db["name"].encode("utf-8")).hexdigest()[:8]
    for attempt in range(6):
        user = requested_user if attempt == 0 else f"venom_nxt_{database_tag}_{secrets.token_hex(3)}"
        try:
            with admin.cursor() as cursor:
                cursor.execute("CREATE USER %s@%s IDENTIFIED BY %s", (user, db["account_host"], db["password"]))
        except pymysql.MySQLError as exc:
            if not exc.args or exc.args[0] != 1396:
                raise
            if attempt == 0:
                print("That database username is already occupied. Creating a separate NXT login with your chosen password.")
            continue
        created_accounts.append((user, db["account_host"]))
        db["user"] = user
        if not _probe_game_login(db):
            raise ValueError("MySQL created the game login but rejected its connection. Check the MySQL account-host setting: use localhost when MySQL and the game server are on the same computer. No existing account password was changed.")
        print(f"Created and verified game database login: {user}.")
        return
    raise ValueError("MySQL could not reserve a game login after several name conflicts. Run setup again; the existing database and account passwords are unchanged.")


def _game_password(answers, default, interactive, password_mode, label):
    value = choice(answers, "password", label, default, secret=True,
                   interactive=interactive, password_mode=password_mode)
    if value == "":
        value = default
    if not isinstance(value, str) or not value:
        raise ValueError("The game database password must be text. Leave the field blank to generate or retain a password.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("The game database password contains an incomplete Unicode character. Clear the field and paste the complete password.") from None
    return value


def _generated_game_password():
    # Retain 256 random bits and satisfy common character-class policies.
    return "Aa9!" + secrets.token_urlsafe(32)


def mysql_setup(root: Path, answers: dict, interactive=True, password_mode="auto", stage_callback=None):
    import pymysql
    from venom.server.database import initialize_database

    def stage(name, status="started"):
        if stage_callback is not None:
            stage_callback(name, status)

    stage("validate")
    config_path = root / "config/server.json"
    config = read_json(config_path)
    old = config.get("database", {})
    print(f"\nDigimon Venom NXT {SETUP_VERSION} - MySQL / XAMPP setup\nStart MySQL or MariaDB before continuing. Setup creates the game database login with the password you choose. Player accounts are registered inside the game.\n")
    host = hostname(choice(answers, "host", "MySQL host", old.get("host", "127.0.0.1"), interactive=interactive))
    port = validated_port(choice(answers, "port", "MySQL port", old.get("port", 3306), interactive=interactive))
    name = validated_identifier(choice(answers, "name", "Game database name", old.get("name", "digimon_venom_nxt"), interactive=interactive), "Database name")
    admin_user = str(choice(answers, "admin_user", "MySQL administrator username", "root", interactive=interactive)).strip()
    if not admin_user or any(ord(c) < 32 for c in admin_user):
        raise ValueError("Enter the MySQL administrator username.")
    admin_password = choice(answers, "admin_password", "Existing XAMPP / administrator password (leave blank only if XAMPP has no password)", "", secret=True, interactive=interactive, password_mode=password_mode)
    if not isinstance(admin_password, str):
        raise ValueError("Enter the XAMPP administrator password as text, or leave it blank.")
    stage("administrator")
    try:
        admin = pymysql.connect(host=host, port=port, user=admin_user,
                                password=admin_password.encode("utf-8"), charset="utf8mb4",
                                connect_timeout=10, read_timeout=15, write_timeout=15, autocommit=True)
    except pymysql.MySQLError as exc:
        code = exc.args[0] if exc.args else "unknown"
        if code in (1045, 1698):
            raise ValueError("XAMPP administrator login was rejected. Enter the EXISTING XAMPP administrator password. Game-account creation has not started and no configuration was changed.") from exc
        raise ValueError(f"Could not connect to MySQL (error {code}). Check that XAMPP MySQL is running and its host/port are correct. No configuration was changed.") from exc
    stage("administrator", "passed")
    print("XAMPP administrator connection verified. Now choose the game's database login.")
    created_accounts = []
    try:
        stage("validate")
        app_user = validated_identifier(choice(answers, "user", "Game database username to create or reuse", old.get("user", "venom_nxt"), interactive=interactive), "Database username", 32)
        if app_user.lower() in {"root", "mysql", "mariadb", admin_user.lower()}:
            raise ValueError("Choose a separate game database username, such as venom_nxt, instead of the administrator username.")
        keep_saved = old.get("user") == app_user and old.get("host") == host and int(old.get("port", 3306)) == port
        default_password = (old.get("password") if keep_saved else None) or _generated_game_password()
        hint = "leave blank to keep the saved setting" if keep_saved and old.get("password") else "leave blank to generate one automatically"
        app_password = _game_password(answers, default_password, interactive, password_mode,
                                      f"Choose the GAME database password ({hint}). Setup creates this login for you.")
        account_host = str(choice(answers, "account_host", "MySQL account host (localhost when MySQL and the game server share this computer)", old.get("account_host", "localhost"), interactive=interactive)).strip().lower()
        if not account_host or any(c in account_host for c in ("'", '\"', ";", "\x00", "\n", "\r")):
            raise ValueError("Invalid MySQL account host.")
        stage("create_database")
        with admin.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        stage("create_database", "passed")
        while True:
            db = {"driver": "mysql", "host": host, "port": port, "user": app_user,
                  "password": app_password, "name": name, "account_host": account_host}
            try:
                stage("game_account")
                _configure_game_account(admin, db, created_accounts)
                stage("game_account", "passed")
                stage("grants")
                with admin.cursor() as cursor:
                    _grant_database(cursor, name, db["user"], account_host)
                stage("grants", "passed")
                stage("schema")
                initialize_database(db)
                stage("schema", "passed")
                break
            except pymysql.MySQLError as exc:
                if exc.args and exc.args[0] == 1819 and interactive and "password" not in answers:
                    _cleanup_created_accounts(admin, created_accounts)
                    print("MySQL's own password policy rejected that game password. Choose another password below; the XAMPP connection is still open.")
                    app_password = _game_password({}, _generated_game_password(), True, password_mode,
                        "Choose another GAME database password to satisfy MySQL's password policy, or leave blank to generate one.")
                    continue
                raise
        config.setdefault("host", "0.0.0.0")
        config.setdefault("port", 8765)
        config.setdefault("tls_cert", "config/server-cert.pem")
        config.setdefault("tls_key", "config/server-key.pem")
        config.setdefault("allow_registration", True)
        config["database"] = db
        stage("save_config")
        save_json(config_path, config)
        stage("save_config", "passed")
    except pymysql.MySQLError as exc:
        _cleanup_created_accounts(admin, created_accounts)
        code = exc.args[0] if exc.args else "unknown"
        if code == 1819:
            raise ValueError("MySQL's password policy rejected the chosen GAME database password. Choose a password that satisfies your MySQL policy, or leave it blank to generate one. Saved configuration was not changed.") from exc
        raise ValueError(f"Game database setup failed (MySQL error {code}). The XAMPP login succeeded; check the administrator's CREATE USER and database permissions, account host, and MySQL availability. Saved server configuration was not changed.") from exc
    except BaseException:
        _cleanup_created_accounts(admin, created_accounts)
        raise
    finally:
        admin.close()
    print(f"\nDatabase schema and game login are ready. Settings saved in {config_path}.\nNext run 03_SETUP_PUBLIC_HOSTING.bat. Administrator credentials were not saved.")
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
    parser.add_argument("--version", action="version", version=f"Digimon Venom NXT setup {SETUP_VERSION}")
    parser.add_argument("--root", type=Path, default=ROOT, help="Source or server distribution directory.")
    sub = parser.add_subparsers(dest="command")
    wizard = sub.add_parser("wizard", help="Open the guided desktop setup window.")
    wizard.add_argument("--stage", choices=("database", "hosting"), default="database")
    wizard.add_argument("--wizard", action="store_true", help=argparse.SUPPRESS)
    for name, description in (("mysql", "Provision a dedicated MySQL account and initialize the schema."), ("hosting", "Create / renew a hostname-verified TLS certificate and public player kit.")):
        child = sub.add_parser(name, help=description, description=description)
        child.add_argument("--answers", type=Path, help="Read settings from a JSON file without prompting. This file may contain secrets; do not distribute it.")
        if name == "mysql":
            child.add_argument("--console-passwords", "--console", action="store_true", help="Use masked Windows console input instead of password windows.")
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
            report.record(stage, "success" if status == "passed" else status)

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
