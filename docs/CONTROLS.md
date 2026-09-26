# Native client controls

Run `PLAY_DIGIMON_VENOM_NXT.bat` after building, or launch the player kit's client executable. The SDL2 desktop application renders its interface at the window's physical pixel resolution and restores your saved display preferences. The initial window is 1280 × 800; the minimum physical window is 960 × 600, with interface scaling to fit. Maps use the supplied x2 artwork with nearest-neighbor sampling and preserved proportions. See `DISPLAY_UPGRADE.md` for the client upgrade procedure and 4K setup.

## Display and camera

Press **F11** or **Alt + Enter** for borderless fullscreen at the current Windows desktop resolution. Press again to restore the previous window size. A 4K fullscreen view requires Windows to be set to 3840 × 2160.

**Settings / F10** opens display and audio preferences. Select window size, automatic or manual interface size, a 60/120/144/165/240 FPS limit, the FPS counter, map zoom, and separate music/effects volume in 5% steps. Changes apply immediately. The default frame limit is 120; achieved FPS depends on the computer and display. Auto interface size is 125% at 1080p and 250% at 4K, constrained to keep controls visible. Text renders at the effective native size.

At **1×**, the complete level fits within the field, with borders where needed. **− / +** buttons, the keyboard's minus/plus keys, or the mouse wheel over the field zoom toward or away from your tamer, up to **8× relative to the fitted view**. **Fit level / 0** returns to 1×. Map zoom is independent of interface size. Fractional fit scales preserve the source colors with nearest sampling, but uniform source-pixel replication occurs only at integer enlargement factors.

The DigiFarm uses these same camera controls over its island. At closer zoom the
camera follows your tamer. Farm zoom is saved separately from field zoom, so
visiting home preserves your preferred camera scale for each location.

Preferences are stored at `%LOCALAPPDATA%\DigimonVenomNXT\display.json` for the current Windows user. To reset them, close the game and rename that file. Connection settings and certificates remain in the separate client `config` folder.

## Sign in and create a tamer

Use **Create account**, enter a username of 3–24 ASCII letters, numbers or underscores and a password of at least eight characters. Click the tamer or rookie selector. Search and scroll to choose any imported playable tamer or eligible ordinary rookie. One partner joins your new account. Registration signs you in automatically.

The client reads `config/client.json` and trusts only the bundled `config/server-ca.pem` while checking the server hostname. Install your administrator's public player kit before connecting. The server uses its configured MySQL password; players do not need database credentials or to install a certificate into Windows. **Reconnect** retries the configured server. **Exit** returns to sign in; closing the window closes the game.

## In the field

| Control | Action |
|---|---|
| WASD or arrow keys | Move in the field or DigiFarm, including diagonal movement |
| E / Search for Digimon | Start a wild encounter in this zone |
| F1 / DigiLab | Enter the lab, restore all partners and remember your exact field location |
| J or Tab / Digidex | Browse scan data and materialize partners in the DigiLab |
| P / Partners | Inspect stats, choose a leader, manage storage and evolution |
| B / Shop | Buy recovery capsules and optional DigiMeat |
| Home · DigiFarm / F2 (top left) | Return to your private home; an active battle requires confirming abandonment |
| Click a DigiFarm resident | Open its management card and choose optional meat to feed |
| M / Worlds | Search and transfer to an imported world map |
| R / Ranked Arena | Open ranked opponents, season/career ladders and rewards |
| V / Rivals Hub | View nearby rivals, invitations, rival directory and head-to-head history |
| O / Bot Activity | View population activity, totals and the latest 100 events |
| Click a rival tamer | Inspect that rival's party, progress, location and record |
| Enter | Focus the world chat field; Enter again sends your message |
| Escape | Close the current menu/settings; open settings from a clear screen |
| Settings / F10 | Open or close display and audio preferences |
| F11 / Alt + Enter | Toggle borderless fullscreen |
| − / + buttons or keys | Zoom the field or DigiFarm from whole-level 1× to close-up 8× |
| Fit level / 0 | Restore whole-level 1× camera view |
| Mouse wheel | Zoom over the playable field; scroll lists and appearance selectors elsewhere |
| Music note | Mute or restore audio |

Walking also triggers encounters after sufficient travel. Map collision is enforced on the dedicated server and predicted locally. The lead partner follows your tamer; other players and AI rivals in the same zone use shared server positions. AI tamers are identified as rivals rather than presented as human players. Typing, menus, battles and lab visits suspend field movement.

## At home in the DigiFarm

Your selected tamer walks around the island with the same eight-direction
animation and speed as in the field, with your lead partner following. The
grass shoreline is enforced by the client and server. Home is private and
walking there never starts a wild encounter. Your farm position is saved
separately, preserving the world location you left behind.

Click a stored Digimon to open its management and feeding card. Close the card
to resume walking. Feeding, search entry, menus, settings and confirmation
dialogs pause movement. The mouse wheel scrolls menus and lists when the pointer
is over them; use it over the island to zoom. **0** restores the whole-island
view, and the zoomed camera follows your tamer.

## Private Season Mode

Choose **Season Mode** in the top-left navigation (or press **F3**) to create or continue your
private career. Review the weekly card, play your scheduled match with the
normal combat controls, reveal the other results, then select **Next Week**.
**Save & Return to World** pauses the career between matches. Flee and activity
switching are disabled during a league match; logging out saves the exact turn
for your next login. No fictional time passes while you are away. See
[SEASON_MODE_V070.md](SEASON_MODE_V070.md) for the calendar, rules and upgrade.

## Ranked battles and tamer rivals

**Ranked Arena / R** opens the Battle Park system and displays your DigiRuby balance, season points, earned grade, season/career wins and losses, recovering battle energy, and opponents. Ranked matches automatically resolve against saved defender teams using the actual partners' stats, SP, skills and type/attribute matchups. The first three partners start; up to three reserves replace defeated partners. Both teams use restored copies, so an arena battle does not spend your field HP/SP or consume inventory. You prepare the team before entering; arena turns are automatic. During the replay, **1× playback** toggles 2× speed; **Show result** skips the remaining replay. **Return to hub** leaves the result screen.

The default season changes on **Monday at 00:00 UTC**. Start and complete at least one ranked attack that season to qualify for automatic DigiRuby rewards; passive defenses alone do not qualify. Use **My arena**, **Top 100** and **Season history** to browse your competition. The ladder offers **Current season**, **Overall career** and **Past seasons**. A points threshold opens a promotion opportunity; a subsequent attacking win earns the next grade. The complete points, energy and reward tables are in `RIVALS_AND_RANKED.md`.

**Rivals Hub / V** offers **Challenges**, **Rival directory** and **Battle history**. Accept or decline a bot invitation, or inspect a nearby map rival and choose **Challenge rival**. **Find rival** searches the directory; **Prev / Next** browse pages of 50. The server checks availability and location when a challenge starts, so a rival who has moved away or entered another activity may ask you to try again. Friendly challenges do not consume ranked energy or change ranked points, ranked records or rewards; they do update head-to-head history.

**Bot Activity / O** offers **Live activity** and **Map population**. It shows population, activity phases, map distribution and cumulative counters, including wild/ranked wins and losses, scan data, materializations, earned levels, evolution, recovery, purchases and travel. Use **More counters** for additional totals and **All / Wild / Ranked / Progress / Travel** to filter the latest 100 events. Fresh bots start with one Rookie at a sector-appropriate seed level; this initial level is shown separately from levels actually earned through training. Walking positions and activity come from the server, so different clients see the same population. **Escape** or **Field** closes a community screen.

## Battles

Click a living enemy to select the gold target. The server chooses the active partner by speed initiative; **YOUR TURN** identifies the acting partner. The first three party members participate. Defeated active partners remain down until healed; reserves are managed outside battle.

- **Attack** (also Space) is a free basic attack.
- **Skill · SP** opens the actor's skill list, costs SP and displays each skill's attribute and physical/magical class.
- **Struggle · 0 SP** is a weaker free attack available even without SP.
- **Items** opens the inventory. Select the recipient in the right party panel, then use a capsule. This consumes the acting partner's turn.
- **Flee** leaves the encounter without victory XP or credits.

Attack poses, contact movement, genuine decoded Dawn effect frames and additional particles show each hit. Floating integers show damage/healing and the effectiveness multiplier. Controls briefly wait while the current hit sequence plays. Defeating Digimon awards scan data; normal scan data increases faster than Paradox data. Scan, rewards and saves are server authoritative.

## DigiLab, partners and inventory

Entering the DigiLab fully restores the party. **Return to field** restores the map and exact location recorded on entry. **Heal all partners** is free and can also be used inside the lab.

Digidex lists the full imported catalog, with scanned species sorted first. At 100% or more scan data, **Materialize** creates a partner in the DigiFarm or DigiLab. At most six partners travel with you; up to 100 additional partners live in DigiFarm storage. Legacy over-cap collections are preserved; withdraw residents until space is available before adding more. When your party is full, DigiBank lets you choose a named party slot and confirm a stored-partner swap. Swaps work at full farm capacity and with archived partners, without increasing either collection count. Evolution routes display the server's level, ABI, CAM and stat requirements. Select a partner on the right, then choose an eligible Digivolve or De-digivolve route at the farm or lab. Scroll below routes to withdraw stored partners. **Make leader** moves the selected partner to slot one; repeated use also lets you arrange the active trio.

The shop sells small, medium and large HP and SP capsules, Friendship DigiMeat and training DigiMeat. Prices, effects and inventory counts come from the server. Select a party partner before using a capsule. Feed DigiMeat through a stored resident's management card in your private DigiFarm. See [DIGIFARM_V060.md](DIGIFARM_V060.md) for prices, permanent bonuses, capacity and upgrade steps.

## Development and visual checks

`python -m venom.client.main --dev` connects only to a local plaintext development server. It uses the configured port, default 8765. Public connections always use TLS.

`--demo` is a clearly marked offline visual preview; it does not create an account or save gameplay. `--demo --demo-battle` previews the battle layout. `--frames 60 --screenshot path.png` saves the rendered window and exits after sixty frames. `--size 3840x2160 --ui-scale auto` checks a 4K-sized drawable; `--fullscreen`, `--zoom 2` and `--fps 120` select corresponding display settings. `--settings PATH` selects a separate display-preferences file. Demo/automated runs ignore and do not overwrite ordinary display preferences unless an explicit settings path is provided. Screenshots are visual checks, not proof of a Windows executable build, hardware frame rate or multiplayer load capacity.

This alpha uses the actual imported sprite and map assets. Consult `RELEASE_STATUS.md` and `MECHANICS.md` for source provenance, original/custom rules, audio-rendering approximations and features outside this release.
