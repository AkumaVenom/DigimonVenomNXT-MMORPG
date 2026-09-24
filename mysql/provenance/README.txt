MYSQL RUNTIME ORIGIN AND VERIFICATION

Product: Oracle MySQL Community Server 8.4.11, Windows x64
Original archive: mysql-8.4.11-winx64.zip
Archive SHA-256:
a492371d687d2bab088b0062581144a0044b8964baefdf4faa579292b423d25c

Official binary archive:
https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-8.4.11-winx64.zip
Official matching detached signature:
https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-8.4.11-winx64.zip.asc
Upstream source packages:
https://dev.mysql.com/downloads/mysql/8.4.html?os=src

The original archive was verified using its detached OpenPGP signature.
GnuPG reported a Good signature by MySQL Release Engineering.
Signing key fingerprint:
BCA4 3417 C3B4 85DD 128E C6D4 B7B3 B788 A8D3 785C
The fingerprint was checked against Oracle's official signature guidance:
https://dev.mysql.com/doc/refman/8.4/en/checking-gpg-signature.html

runtime-manifest.json records each included file's size and SHA-256.
The upstream LICENSE, README, docs, release binaries, release DLLs,
plugins and support files are included unchanged. Developer headers,
static/import libraries, debug binaries and debug symbols are omitted.
The retained runtime includes the optional release tools and plugins so
standard recovery and diagnostic utilities remain available.

Windows requirements:
A compatible Windows x64 system and the Microsoft Visual C++ v14 x64
Redistributable are required. This is a Windows runtime prerequisite;
no installed MySQL service, XAMPP installation or global MySQL PATH is
required by the bundled server launchers. Microsoft documents the latest
compatible package and provides the official download:
https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
https://aka.ms/vc14/vc_redist.x64.exe

If the prerequisite is missing, run:
mysql\prerequisites\INSTALL_VC_RUNTIME.bat
It downloads directly from Microsoft, verifies a valid Authenticode
signature with publisher Microsoft Corporation, and opens Microsoft's
normal installer. Allow its normal Windows administrator prompt. The
helper does not change PowerShell execution policy. A machine with a
restricted policy can use the official download link above directly.
The installer is downloaded to a temporary folder and removed afterward.
Internet access is required only for this optional prerequisite step.

The MSVC runtime is not part of Oracle's ZIP. This bundle does not copy
DLLs from another application's installation. windows-imports.json records
the static DLL imports from the release EXEs and DLLs for traceability.

Reference documentation:
Manual Windows ZIP installation and layout:
https://dev.mysql.com/doc/refman/8.4/en/windows-installation.html
Start and stop a standalone Windows process:
https://dev.mysql.com/doc/refman/8.4/en/windows-start-command-line.html
Cold physical backups (slow shutdown, all InnoDB files and configuration):
https://dev.mysql.com/doc/refman/8.4/en/innodb-backup.html

The Windows binaries were checked for archive integrity and DLL imports
on a Linux build host. Native Windows execution still needs a Windows
host; Linux database tests do not substitute for Windows execution.
