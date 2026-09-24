# Retired setup guide

The former external-database password workflow does not apply to this release.
Use [SETUP.md](SETUP.md) and
[../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md).

This fresh server owns its bundled MySQL 8.4.11 process. All production saves
stay in `mysql/data`; credentials are generated during setup. No previous
administrator account, password or database is required.

Build the source on Windows x64, extract the generated server outside `dist`,
and run **01_SETUP_SERVER.bat**. Daily use starts with **START_MYSQL.bat** and
**START_WORLD_SERVER_CONSOLE.bat**. Use **STOP_SERVER.bat** for clean shutdown and
wait for success before manually zipping the entire server folder.
