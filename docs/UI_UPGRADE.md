# UI1 — illustrated screens, cyber backdrop and screen music

This client update builds on FPS1. It keeps the original game content, native
high-DPI rendering, all bots, animations, maps and server rules. No server or
database migration is required.

## Upgrade an existing installation

The downloads contain source code and runtime assets, not a newly compiled
Windows client. Build on Windows x64 with 64-bit Python 3.11 or newer, as in the
baseline. Linux checks do not verify a Windows executable.

1. Keep your current server and saves. Back up your current client folder,
   especially `config/client.json` and `config/server-ca.pem`.
2. Either extract the complete UI1 source package, or merge the contents of the
   patch's `DigimonVenomNXT` folder into your matching source folder, allowing
   replacement of the included files. The patch is cumulative: it includes both
   FPS1 performance fixes and UI1 changes, and supports the originally supplied
   portable MySQL source baseline or its FPS1 version.
3. Run `BUILD_ALL.bat` from the updated source folder. It verifies the supplied
   assets and builds the Windows applications. Build outputs under `dist` are
   replaced, so keep your working installation outside that directory.
4. Extract the complete new `dist/Windows_Client_x64.zip` into a new client
   folder. Copy your backed-up client `config` folder into it. Use the complete
   rebuilt client, including its new `assets` and `data` folders.
5. Run `PLAY_DIGIMON_VENOM_NXT.bat` and connect to your existing server. Do not run
   fresh-server setup for this client upgrade. Account saves remain with your
   existing server, and display/audio preferences remain in Local AppData.

For the multipart full source download, place all four parts in one directory
and open `.001` with 7-Zip to extract. Alternatively, in Windows Command Prompt:

```bat
copy /b VenomNXT_UI1_Full.zip.001+VenomNXT_UI1_Full.zip.002+VenomNXT_UI1_Full.zip.003+VenomNXT_UI1_Full.zip.004 VenomNXT_UI1_Full.zip
```

Then extract the assembled ZIP. The small source patch is a separate option;
you do not need it when using the full UI1 package.

## Screens and controls

| Screen | Key | Changes |
|---|---|---|
| Shop | B | Sorcermon merchant hero; illustrated HP/SP capsules; recovery filters; quantity controls; actual prices, inventory and credits; selectable party recipient with HP/SP bars |
| Ranked Arena | R | Illustrated arena hero; season badge, placement and energy; challenger portraits and teams; themed ladders, season archive and replay |
| Rivals Hub | V | Dawn/Dusk tamer portraits; invitation cards; nearby tamers; directory, profiles, rosters and battle history |
| Bot Activity | O | Tamer observatory hero; population metrics; cumulative counters; filtered event timeline and map occupancy |

Escape returns to the field. Existing actions, filtering, pagination, rank
rules and server permissions remain in place. As before, new supplies can be
purchased while in DigiLab; owned capsules can be used from the field shop.
The shop explains this and offers a DigiLab button. Up to six party recipients
remain accessible at the minimum supported window size.

A dark navy circuit-board background extends around the native interface.
Sparse columns of digits **0–9** fall downward at a time-based rate along the
outer gutters. Their contrast stays low and their clipping protects the text
and controls. Art and fonts remain native-resolution; the framebuffer is never
downscaled to obtain speed.

## Sound

Each destination streams a distinct supplied stereo OGG loop. Subtabs share
their destination theme. The remaining interface destinations also receive
individual tracks:

| Destination | Supplied audio |
|---|---|
| Shop | bgm12 |
| Ranked Arena | bgm30 |
| Rivals Hub | bgm20 |
| Bot Activity | bgm14 |
| DigiDex | bgm15 |
| Partners / Skills | bgm13 |
| Worlds | bgm18 |
| DigiLab | bgm11 |

The client smoothly leaves the old track before starting the new loop. The
transition advances with normal frames and does not block input. Opening,
closing, selecting and changing tabs have short interaction sounds. Music
returns to the current world or DigiLab when a screen closes. Wild battles and
visible combat replays take priority. Existing mute, music-volume and
sound-volume controls apply to the new audio.

These are Venom NXT interface assignments, not claims about which original
Digimon event each track accompanied. Existing world/battle audio is retained.
`data/ui_audio.json` records the selected original filenames and hashes.

## Assets and performance

The supplied UI atlases are retained unchanged under `assets/ui/dawn`. Selected
Dawn-ROM portraits and icons are under `assets/ui/extracted`, with source pack
entries, hashes and image dimensions in `provenance.json`. Only transparent
margins were trimmed from those extracted portraits; colors were retained.
The complete ROM is not required or included in the release.

FPS1's sprite and map caches remain intact. Circuit backdrops, hero art and
capsule illustrations are cached at their final physical resolution. The new
presentation and background caches each have a 64 MiB limit; the background
reserves at most 512 KiB for tiny digit glyphs. Steady frames draw the cached
background and a small number of animated glyphs, rather than recreating a
full-screen translucent effect.

See `UI_PERFORMANCE.json` for the measured baseline comparison and
`UI_VALIDATION.json` for checks and limitations. Original pre-FPS1 measurements
remain in `FPS_FIX.md` and `FPS_BENCHMARK.json`. Headless frame timings indicate
rendering cost on the test host; they do not guarantee FPS on your Windows PC.

## Reproduce the checks

```sh
python tools/build.py --verify-only
python -m pytest -q
python tools/preview_ui_screens.py --output previews --empty --native4k
python tools/preview_ui_screens.py --output six-partner-previews --party-six --views shop shop_field --sizes 1180x800 1280x800
```

Preview fixtures are synthetic server-shaped records, clearly labelled in the
captures. They do not change production data or player progress. Screens were
inspected at 1280×800, 2048×1152 and native 3840×2160, with an additional
1180×800 six-partner shop check. Audio decoding and playback routing were
validated with SDL's dummy audio driver; final speaker/headphone listening and
Windows frame pacing still need a run on the target PC.
