# Season Mode v0.7.0

Season Mode adds a private, server-saved league to the existing MMORPG. One
human tamer competes with a persistent roster of AI tamers. Each account owns
its own calendar, fixture cards, standings, rivalries and Solo Season World
Champion. Other players may be decades ahead or behind you without changing
anything in your league.

## Play a career

1. Choose **Season Mode** in the top-left navigation (or press **F3**). Your first visit creates
   the league; later visits continue the same career.
2. Review **This Week** and your scheduled opponent. The card marks your match
   and championship bouts. The calendar begins Monday, 1 January, Year 1.
3. Start your match and use the existing live battle controls. Attacks, skills,
   items, targeting and the server's turn order keep their normal behavior.
   There is no player autoplay or replay resolution. **Flee is unavailable**.
4. Finish your match to reveal the other fixtures and see the updated league.
   A loss continues your career; it never ends or resets it.
5. Choose **Next Week** after reviewing the results. The next booking week is
   immediately available, without any real-world timer or waiting period.
6. Use **Save & Return to World** between matches to resume the MMO from your
   prior location. Prepare partners, visit the DigiFarm, use the DigiLab, or
   play the separate Ranked Arena before coming back.

During a match, finish it before returning to another activity. If you need to
stop playing, log out: the current enemies, HP/SP, initiative queue and next
player decision are saved. Reconnecting restores the same match. Closing the
client does not simulate a result or count as a loss.

## Calendar and persistence

The date displays a weekday, day, full month and increasing year, together
with the booking week. Booking weeks are consecutive seven-day periods and can
cross month and year boundaries. The calendar uses Gregorian leap years:
divisible by four, except centuries not divisible by 400. Year 10,000 is a leap
year. Fictional time uses Python integer counters and calendar arithmetic,
independent of timestamps or platform date limits. There is no final year or
annual restart.

Only your explicit Season actions advance the date. Logging out, shutting down
the server, changing the computer clock or returning after a long absence does
not advance the league. The annual event preserves the champion, current reign,
rivalries, roster and career totals.

The current league lives in the character save. Completed week records move
into the account's private archive when you continue to the next week. Archive
writes and the character update commit in one database transaction. History
pages are bounded; old results remain in the archive rather than being deleted
to keep the save small. Existing saves acquire a career on their first visit;
accounts which never enter Season Mode retain their existing progression.

The server owns booking, AI results, championship changes, rewards and all
combat. The client cannot submit its own winner. Current card tokens and battle
turn checks reject stale or repeated actions. An active match is saved after
every accepted command using the existing session ownership and revision guards.

## League rules

The league contains your tamer and 15 persistent AI competitors. Every tamer
receives one fixture per booking week. Your match is scheduled for Tuesday;
the other results become visible when your battle finishes. Rankings track
wins, losses and rating. Rivalry heat grows through repeated meetings and title
matches, and influences future bookings. AI partners train and can digivolve
as their careers develop.

Championship cards occur regularly and at calendar month boundaries, with a
Grand Championship card at year end. The reigning champion faces the highest
ranked available challenger. A title bout either extends the current reign or
crowns its winner. Ordinary non-title losses do not transfer the championship.

League bouts restore both sides before the opening turn and recover your
partners after the result. Your opponent fields as many active partners as you,
up to three. Victory grants the normal formula's XP, credits and CAM gains;
capsules still come from your inventory. Tamer-owned opponents do not grant
wild scan data or Friendship DigiMeat drops. Wins/losses also update your normal
character record. None of these results award Ranked points or DigiRubies.

## Other activities and audio

This league does not use the shared Ranked Arena ladder, weekly UTC season
clock, energy, DigiRuby rewards or multiplayer championship ownership. The
shared rival population continues to have its own careers. A Solo Season World
Champion is the champion of one player's private league.

The native career screens reuse the shipped Digimon and tamer artwork, cyber
interface elements, battle music and sound cues. Audio mute and volume controls
continue to apply. Leaving the league returns to the appropriate world, farm
or lab soundtrack. The game content and original asset collection are retained.

## Upgrade from the supplied v0.6.2 source

This is a **source release**. Windows applications must be built on Windows x64
with 64-bit Python 3.11 or newer. Update **both client and world server**.

1. Run **STOP_SERVER.bat** in the existing server installation and wait for
   successful world and MySQL shutdown. Back up the complete stopped server
   folder and the client `config` folder.
2. Extract the complete v0.7.0 source into a separate writable source folder.
   Alternatively, merge the patch's `DigimonVenomNXT` folder into a copy of the
   exact supplied v0.6.2 source, replacing included files. The patch requires
   the original assets and bundled database runtime; it is not a standalone
   game. Keep any live installation outside the source `dist` directory.
3. Run **BUILD_ALL.bat**. The existing builder verifies game content and builds
   both `dist/Windows_Client_x64.zip` and `dist/Windows_Server_x64.zip`.
4. Extract the complete new client into a new folder, then copy the old client
   `config` folder into it, including `client.json` and `server-ca.pem`.
5. On a copy of the complete stopped server backup, replace the application
   components from the newly built server: `VenomWorldServer.exe`, `_internal`,
   `admin`, `assets`, `data`, `docs`, `mysql/manager`, launchers, build metadata
   and readme files. Replace those application directories in full.
6. Preserve the entire server `config` folder, `mysql/data`,
   `mysql/instance.json`, `mysql/game-login.json`, private MySQL configuration,
   and bundled `mysql/runtime`. The top-level `data` folder contains game
   content; `mysql/data` contains the saved database. **Do not run fresh database
   setup for an upgrade.**
7. Start MySQL and the updated world server, then connect with the updated
   client. The private archive table is created automatically. Check your
   existing character, farm and world progress, then enter Season Mode.

For a fresh installation, use the README and PORTABLE_SERVER_README.md setup
instructions after building. For development, the existing `--dev` flow uses
an explicitly separate SQLite database.

## Verification

The automated checks exercise calendar boundaries and large years, private
rosters and saves, normal interactive battle commands, invalid/stale actions,
return/reconnect behavior, archives and the server protocol. Native headless
pygame renders check the screens at supported layouts. See
`SEASON_VALIDATION.md` for the results recorded for this release.

Linux source and protocol tests do not constitute a Windows binary build or
an interactive hardware playtest. The bundled Windows MySQL executable cannot
be run on the Linux validation host. Perform the Windows build and an
installation smoke test on the target Windows machine before replacing the
working production copy.
