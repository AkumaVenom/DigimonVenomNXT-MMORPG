# Local admin console v0.8.0

Run your server from **START_WORLD_SERVER_CONSOLE.bat**, then type commands at the
`venom>` prompt in that same world-server window on the host PC. Start with
`/help`, `/permissions`, and `/players`.

These commands belong exclusively to the local server terminal. There is no
remote console, player-chat command handler, or in-game staff permission grant.
A player account named Admin gains no special powers. Ordinary player chat
remains available; slash commands entered in chat are rejected.

This update builds on **Season Mode v0.7.0**. Existing characters, DigiFarm,
shared rivals, Ranked Arena, and private careers remain in the same saves.

## Start and configure the console

1. Start your existing portable MySQL and launch **START_WORLD_SERVER_CONSOLE.bat**.
2. Wait for `World ready` and `Local admin console ready. Type /help for commands.`
3. Type one command and press Enter. Server logs may also appear in this window.
4. Use `/help command` for a command's syntax, for example `/help givedigimon`.

An interactive terminal is required. If the world runs without one, the console
reader stays disabled and gameplay continues. Closing console input does not
shut down the world. Use the normal saved shutdown procedure instead.

The console is enabled with the **OWNER** tier when these options are absent.
To make the settings explicit, merge this property into the existing
`config/server.json` object, retaining all database, TLS, hosting and other
settings:

```json
"console": {
  "enabled": true,
  "role": "OWNER"
}
```

This is a JSON property fragment, not a replacement configuration file. Set
`enabled` to `false` to disable terminal commands. Stop and start the server
fully after changing this configuration. `/restart` reuses the configuration
already loaded by the process.

### Permission tiers

Every higher tier includes the lower tiers. These are **local console operator
levels**, not permissions attached to player accounts.

| Tier | Intended use |
|---|---|
| `PLAYER` | Read-only inspection and local help; confirmation still requires the original action's tier. |
| `MODERATOR` | Warnings, kicks, account bans, and private detention. |
| `GAME_MASTER` | Digimon, items, credits, teleportation, encounters, and title assignment. |
| `ADMIN` | Broadcasts, exact balances, inventory clearing, accounts, title creation, and server lifecycle. |
| `DEVELOPER` | All ADMIN abilities plus cloning partners for testing. |
| `OWNER` | All commands, including confirmed deletion of offline accounts. |

The hierarchy is `PLAYER < MODERATOR < GAME_MASTER < ADMIN < DEVELOPER < OWNER`.
`/help` only lists commands allowed at the configured tier. Anyone who can type
into the host terminal has that terminal's configured powers; protect the host
PC and its server files.

## Choose the right player, partner, or item

`<player>` is an exact registered account name, matched without case sensitivity.
Names use 3–24 letters, digits or underscores. `/players` lists connected accounts.
Read and edit commands also support existing offline accounts where noted below.
There are no wildcard, nearest-player, partial-name, or all-player target selectors.

Inspect before editing:

```text
/digimon ShadowStar
/team ShadowStar
/bag ShadowStar
/balance ShadowStar
/digimoninfo agumon
```

An owned **partner** is different from a catalog **species**:

| Selector | Meaning |
|---|---|
| Partner UID printed by `/digimon` | The most reliable choice; identifies that individual Digimon even after roster changes. |
| `party:1` through `party:6` | Occupied party position, counted from 1. A slot can refer to a different partner after rearranging the team. |
| `storage:1` through `storage:100` | Occupied DigiFarm storage position, counted from 1. |
| Exact owned name or species ID | Accepted only when exactly one owned partner matches; duplicates require a UID or slot. |
| Species ID, such as `agumon` | Exact catalog form for a new partner, encounter, evolution target, or `/digimoninfo`. |
| Exact species/item/map name | Accepted without case sensitivity; quote multiword names. If multiple records share a name, use the ID shown in the error. |

Examples using this package's catalog:

```text
/givedigimon ShadowStar agumon 20
/setlevel ShadowStar party:1 30
/setabi ShadowStar party:1 100
/setcam ShadowStar party:1 80
/giveitem ShadowStar "Small HP Capsule" 5
/teleportplayer ShadowStar "Dawn Sector 001"
/spawn ShadowStar greymon 20
```

`/bag` prints item IDs and names. `/digimoninfo` prints exact evolution and
reverse-evolution target IDs. Consult `data/catalog.json` for the full species
and map catalogs. Quote text containing spaces and use straight double quotes.
Numbers must be whole numbers, without commas, decimals, signs, or scientific
notation. The leading `/` is conventional; the local console also accepts the
command name without it.

## Complete command reference

Angle brackets mark required values. Square brackets mark optional values.
Do not type the brackets themselves. Every command below is **host console only**,
including commands whose minimum tier is PLAYER.

### Help, inspection, and notices

| Command | Minimum tier | What it does |
|---|---|---|
| `/help [command]` | PLAYER | List permitted commands, or show one command's syntax. |
| `/permissions` | PLAYER | Show the terminal's tier and hierarchy. |
| `/players` | PLAYER | List currently connected accounts. |
| `/broadcast "message"` | ADMIN | Send a trusted server banner to all connected players, including private Season, DigiFarm and detention scenes. |
| `/digimon <player>` | PLAYER | List party and stored Digimon with UIDs, slots, species IDs, level, XP, ABI, CAM, HP and SP. |
| `/team <player>` | PLAYER | Inspect the active party. |
| `/bag <player>` | PLAYER | List inventory IDs, item names and quantities. |
| `/digimoninfo <species>` | PLAYER | Inspect the exact catalog form, stats and supported evolution routes. |
| `/money <player>` | PLAYER | Show ordinary credits. |
| `/balance <player>` | PLAYER | Alias for `/money`. |

Broadcasts and moderation reasons accept 1–240 printable characters. They appear
as distinct server messages, not player chat. Updated clients provide a **Server
notices** button in the top-left navigation; the latest 256 notices remain
readable during that client session after banners disappear. This session viewer
clears on logout. Persisted warnings remain available to the operator through
`/warnings`.

### Digimon and live encounters

| Command | Minimum tier | What it does |
|---|---|---|
| `/givedigimon <player> <species> [level]` | GAME_MASTER | Create a valid partner at level 1 by default, or level 1–99. Fill an open party slot first, otherwise DigiFarm storage. |
| `/removedigimon <player> <partner>` | GAME_MASTER | Remove the selected individual immediately. The last party member cannot be removed. |
| `/heal <player>` | GAME_MASTER | Restore the party's HP and SP. Does not heal stored partners. |
| `/healall` | GAME_MASTER | Heal eligible connected parties; report players skipped because their activity is busy. |
| `/evolve <player> <partner> [target]` | GAME_MASTER | Force a supported forward route, bypassing progression requirements. Specify the exact target when several routes exist. |
| `/devolve <player> <partner> [target]` | GAME_MASTER | Force a supported reverse route. Forms without a reverse route are refused. |
| `/setlevel <player> <partner> <1-99>` | GAME_MASTER | Set level, reset current XP to zero, and recalculate stats/skills. |
| `/setexp <player> <partner> <experience>` | GAME_MASTER | Set XP within the current level, from zero to one less than the next level's requirement. At level 99, only zero is valid. |
| `/setabi <player> <partner> <0-200>` | GAME_MASTER | Set ABI and recalculate partner stats. |
| `/setcam <player> <partner> <0-100>` | GAME_MASTER | Set CAM friendship. |
| `/setfriendshiplevel <player> <partner> <0-100>` | GAME_MASTER | Alias for `/setcam`; there is no second friendship meter. |
| `/setparadox <player> <partner> <true\|false>` | GAME_MASTER | Switch between a regular form and its actual supported Paradox counterpart. |
| `/clonedigimon <player> <partner>` | DEVELOPER | Copy a partner for testing, with a new UID and the normal party/storage capacity limits. |
| `/teleportplayer <player> <location>` | GAME_MASTER | Move to an exact catalog map's collision-validated entry point. Leaves farm/lab if eligible. |
| `/spawn <player> <species> [level]` | GAME_MASTER | Start a single-enemy live wild encounter, level 1 by default. The tamer must be in the world and have a conscious active partner. |

The party holds six partners and DigiFarm stores 100. Giving or cloning refuses
when both are full. Partner setters retain existing farm bonuses and recalculate
valid species stats; use `/heal` separately when recovery is intended.

Forced evolution uses a real route in this game's catalog. It resets the partner
to level 1, keeps its UID and CAM, retains farm training, records the previous
form, and awards the route's ABI increase. It does not transform a partner into
an arbitrary unrelated form. `/setparadox` changes the species record and its
artwork/stats; it is not a Pokémon shiny flag. Pokémon command names such as
`/givepokemon` are replaced by the Digimon commands above.

`/spawn` uses the existing authoritative battle engine. The player attacks,
chooses skills, targets enemies and uses items normally. It does not submit an
automatically played player replay. The normal wild-battle rules apply, including
fleeing; the existing **no-flee rule remains specific to Season matches**. If an
eligible offline account receives an encounter, its saved encounter appears on
its next login.

### Inventory and ordinary credits

| Command | Minimum tier | What it does |
|---|---|---|
| `/giveitem <player> <item> <amount>` | GAME_MASTER | Add 1–999 of a valid item, provided the resulting quantity is at most 999. |
| `/removeitem <player> <item> <amount>` | GAME_MASTER | Remove 1–999; refuse if that would make the quantity negative. |
| `/setitem <player> <item> <0-999>` | GAME_MASTER | Set the exact quantity of a valid item. |
| `/clearinventory <player>` | ADMIN | Prepare confirmation to set all item quantities to zero. |
| `/givemoney <player> <amount>` | GAME_MASTER | Add ordinary credits. |
| `/removemoney <player> <amount>` | GAME_MASTER | Remove credits without creating a negative balance. |
| `/setmoney <player> <amount>` | ADMIN | Set the exact ordinary credit balance, including zero. |

Credit balances range from 0 to 9,007,199,254,740,991. Give/remove amounts must be
positive. Commands refuse invalid amounts instead of silently changing them.
These commands do not edit Ranked Arena DigiRubies, ranked points, season
payouts, or a private career's championship records.

### Moderation

| Command | Minimum tier | What it does |
|---|---|---|
| `/warn <player> <reason>` | MODERATOR | Persist a warning; notify the player immediately if connected. |
| `/warnings <player>` | MODERATOR | Show the most recent 20 recorded warnings and their real UTC timestamps. |
| `/kick <player> [reason]` | MODERATOR | Save and disconnect a connected player. Uses a default reason when omitted. |
| `/ban <player> <duration\|permanent> <reason>` | MODERATOR | Ban an existing account and disconnect it if online. Future logins are blocked while the ban is active. |
| `/unban <player>` | MODERATOR | Remove the account's ban. |
| `/jail <player> <duration\|permanent> <reason>` | MODERATOR | Move the account into a private holding cell and suspend its current activity. Works for online or offline accounts. |
| `/unjail <player>` | MODERATOR | Release the account and restore its suspended location/activity. |
| `/ipinfo <player>` | ADMIN | Print a connected player's current network endpoint and measured connection latency in this local terminal only. |

Durations use **real elapsed time**: `30s`, `15m`, `2h`, `7d`, or `2w`. Bare
numbers mean seconds. Timed restrictions accept 1 second through 3,660 days;
use `permanent` for an indefinite restriction. `perm` and `forever` are also
accepted. A timed ban expires by its timestamp; a timed jail releases through
the server while connected or when the account next logs in.

```text
/warn ShadowStar "Please keep world chat respectful."
/jail ShadowStar 15m "Please wait while we review the reported issue."
/unjail ShadowStar
/ban ShadowStar 2d "Repeated disruption after a warning."
/unban ShadowStar
```

Detention prevents movement, travel, encounters, ranked/rival activity, farm/lab
activity, Season actions, and gameplay edits. The updated client shows the reason
and release countdown while leaving Settings, Exit and private cell chat
available. Each cell's chat and visibility are isolated. An expired client timer
cannot release the player; the server must confirm it.

Jailing during combat saves the exact suspended battle. Release restores that
battle and activity; it does not award a win, lose a title, advance a Season week,
or discard a farm position. Re-jailing an already detained account updates its
restriction while retaining the original suspended activity. These moderation
clocks remain entirely separate from fictional Season dates and Ranked Arena's
weekly UTC seasons.

`/ipinfo` provides current connection information only. It does not perform an
IP ban or maintain a historical IP lookup, and the endpoint is not broadcast to
players or included in the administrative audit record. Existing world connection
logs may contain peer addresses; protect the server logs along with the server
configuration and backups.

### Accounts and destructive-action confirmation

| Command | Minimum tier | What it does |
|---|---|---|
| `/createaccount <username>` | ADMIN | Prompt twice for a hidden password, then create a normal test/admin-use account with the default valid tamer and starter. |
| `/resetpassword <username>` | ADMIN | Prompt twice for a hidden replacement password for an offline account. |
| `/deleteaccount <username>` | OWNER | Prepare confirmation to delete an offline account, its character/Season saves and associated account records. |
| `/confirm <token>` | PLAYER, plus original command tier | Execute one specific pending destructive action after rechecking permission, expiry, account status and save revision. |

Passwords must contain 8–128 characters, following the normal account rules.
Type them only into the hidden
`New password:` and `Confirm password:` prompts, never after a command. Password
commands refuse to continue if hidden input is unavailable or the entries do
not match. Creating an account does **not** assign staff authority to that account.
For password reset or deletion, first disconnect the target and wait until its
save finishes. An account used by another server cannot be overwritten.

`/clearinventory` and `/deleteaccount` print the exact action and a one-use token:

```text
/clearinventory ShadowStar
/confirm TOKEN_PRINTED_BY_THE_SERVER
```

Use the actual token within **60 seconds**. An intervening save changes the
account revision and invalidates the confirmation, even when the token has not
expired. A connected character's normal autosave can cause this; request a fresh
confirmation after checking the target again. There is no bypass or generic
`yes` command. Deleting an online account is refused. Account deletion removes
that character's private career archive; it does not reset other players'
careers or delete the server-wide title catalog.

### Player nameplate titles

| Command | Minimum tier | What it does |
|---|---|---|
| `/addtitle <title>` | ADMIN | Create a reusable title containing 1–32 printable characters. An existing title name returns the existing entry. |
| `/titles` | PLAYER | List title IDs and names in the shared title catalog. |
| `/settitle <player> <title\|none>` | GAME_MASTER | Grant and equip an existing title by name or ID, or clear the active title with `none`. |

```text
/addtitle "Digital Guardian"
/titles
/settitle ShadowStar "Digital Guardian"
/settitle ShadowStar none
```

Each player displays one equipped title above their unchanged username, with a
secondary gold accent. The title appears for the player and other real players
in the world, on the player's DigiFarm nameplate, and in the account header.
Granted titles and the selected title persist in the character save.

`/addtitle` only creates the catalog entry; `/settitle` grants and equips it.
`none` hides the active title without removing the player's previously granted
titles. Use a different title name from this reserved clear command. Titles are
cosmetic and do not grant staff powers or a Season championship. Players have
no title-changing chat command or authority to edit title metadata.

### Saves, memory, shutdown, and restart

| Command | Minimum tier | What it does |
|---|---|---|
| `/memory` | PLAYER | Show the current world-process PID, session count and memory usage when the host supports measurement. |
| `/saveall` | ADMIN | Save connected characters and checkpoint the enabled rival population. |
| `/shutdown [seconds\|cancel]` | ADMIN | Schedule a graceful saved world shutdown; default 10 seconds, valid range 0–86,400. |
| `/restart [seconds\|cancel]` | ADMIN | Schedule a graceful saved world restart in the same terminal/process, using the same delay range and default. |

```text
/broadcast "Server maintenance in one minute. Your progress will be saved."
/saveall
/restart 60
/restart cancel
```

Only one shutdown/restart can be pending. Either cancel command cancels the
pending lifecycle action. Players receive the scheduled notice and milestone
countdown notices. At the deadline, the listener closes, connections save,
background work and rival checkpoints finish, and database resources close.

`/restart` then creates a fresh world from the saved data in the **same process**.
Players reconnect after it is ready. It does not restart Windows or MySQL,
replace binaries, reload Python modules, or reread `server.json`. For new
binaries or changed configuration, do a full stopped update and relaunch.
A save failure stops the restart path rather than claiming progress was safely
saved.

`/shutdown` stops the world server, not the portable MySQL process. For a backup
or installation update, use **STOP_SERVER.bat** and wait for both world and
MySQL shutdown before copying the complete server folder. `/saveall` alone does
not make a running MySQL directory safe to ZIP.

## What happens when a player is busy or offline

All partner, healing, inventory, credit, teleport and encounter edits refuse
while the character is in an active battle, inside Season Mode, or detained.
Ask the player to finish combat and choose **Save & Return to World**, or release
detention, before trying those commands. This also applies to an offline save
that contains a paused battle or Season activity. Read-only inspection remains
available. Cosmetic title updates and moderation actions use their own rules;
jail deliberately suspends a battle safely.

Online edits hold the same character lock as normal gameplay. Changes save
before the client receives the new state and a server notice. Offline edits
briefly acquire exclusive ownership of the saved account and verify its current
revision when writing. This lease/revision check prevents another world server,
a simultaneous login, or a stale confirmation from overwriting a newer save.
When a safe save cannot be acquired, the command reports an error and does not
publish an unsaved character change.

Accepted operations produce audit metadata containing the command name, target,
terminal tier, result and real timestamp. Raw command lines, passwords and
connection endpoints are not stored in that audit. No command in this release
changes the private Season calendar, advances the shared Ranked Arena season,
or grants a player access to this terminal.

## Upgrade from Season Mode v0.7.0

This is a **source release**. Build both Windows applications with **64-bit
Python 3.11 or newer on Windows x64**. The changed server protocol and native
client presentation belong together.

1. Run **STOP_SERVER.bat** in the working server installation. Wait for confirmed
   world and MySQL shutdown. Back up the entire stopped server folder and the
   client `config` folder.
2. Extract the v0.8.0 complete source into a separate writable source folder, or
   merge the patch's `DigimonVenomNXT` folder into a copy of the working **v0.7.0
   Season Mode source**, replacing included files. The patch needs that baseline's
   assets and bundled database runtime. Keep the live installation outside `dist`.
3. Run **BUILD_ALL.bat**. It creates `dist/Windows_Client_x64.zip` and
   `dist/Windows_Server_x64.zip`; use both newly built packages.
4. Extract the complete new client into a new folder. Copy in the existing client
   `config` folder, including `client.json` and `server-ca.pem`.
5. On a copy of the complete stopped server backup, replace the application
   components from the new server package: `VenomWorldServer.exe`, `_internal`,
   `admin`, `assets`, `data`, `docs`, `mysql/manager`, launchers, build metadata
   and readme files. Replace application directories in full.
6. Preserve the server's entire `config` folder, `mysql/data`,
   `mysql/instance.json`, `mysql/game-login.json`, private MySQL configuration,
   and bundled `mysql/runtime`. The top-level `data` folder is game content;
   **`mysql/data` is the saved database**. Do not run fresh database setup.
7. Start MySQL and the updated world server, then use the updated client. The
   administration metadata tables are added automatically. Existing saves and
   Season archives remain in place. Confirm the original character, career and
   DigiFarm load, then try `/permissions`, `/players`, and a test broadcast.

Existing server configurations do not need a new console entry to use the
OWNER default. For a fresh installation, follow the main README and
`PORTABLE_SERVER_README.md` instead. The optional `--dev` workflow retains its
separate SQLite development database.

## Validation limits

Automated source tests cover command permission checks, account ownership and
revision protection, persistence, moderation, protocol isolation, lifecycle
behavior, and the native client displays. Headless native screenshots exercise
the shipped artwork and layouts. Consult [validation report](ADMIN_CONSOLE_VALIDATION_V080.json) for
the exact results.

Source-level tests and headless rendering are not a Windows executable build or
an interactive hardware playtest. Build both Windows packages and smoke-test the
upgrade on the target machine before replacing the working installation.
