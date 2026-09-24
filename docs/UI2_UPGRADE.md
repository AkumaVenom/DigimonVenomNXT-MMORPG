# UI2 — complete interface upgrade

Release `0.3.2-portable-ui2` extends the accepted UI1 screens and FPS1 rendering
work. Native high-DPI rendering, artwork, bots and authoritative gameplay rules
are retained. The server and database require no migration.

## Upgrade your existing installation

These downloads contain source code and assets. No Windows executable was
compiled on the Linux validation host.

1. Keep your current portable server, accounts and saves. Back up the client,
   including `config/client.json` and its trusted `config/server-ca.pem`.
2. Extract the full UI2 source, or merge the cumulative patch's `DigimonVenomNXT`
   contents into your matching source folder. The patch supports the originally
   supplied portable MySQL baseline, FPS1 and UI1. Keep files absent from the
   patch; it includes the earlier FPS and UI work.
3. On Windows x64, with 64-bit Python 3.11 or newer installed, run
   `BUILD_ALL.bat`. The first build installs its Python dependencies. Keep your
   live installation outside `dist`, whose build outputs are recreated.
4. Extract the **complete** rebuilt `dist/Windows_Client_x64.zip` into a new
   folder, then copy your previous client `config` folder into it. New `assets`
   and `data` files are required; replacing an executable alone is insufficient.
5. Run `PLAY_DIGIMON_VENOM_NXT.bat` and connect to your current server. Do not run
   fresh database/server setup for this client upgrade. Saved display and audio
   preferences remain in Local AppData.

For the full source download, place all four parts together and open `.001`
with 7-Zip. Alternatively, combine them in Windows Command Prompt:

```bat
copy /b VenomNXT_UI2_Full.zip.001+VenomNXT_UI2_Full.zip.002+VenomNXT_UI2_Full.zip.003+VenomNXT_UI2_Full.zip.004 VenomNXT_UI2_Full.zip
```

Extract the resulting ZIP. The complete source already includes the patch.

## Screens and controls

| Destination | UI2 changes |
|---|---|
| DigiLab / F1 | Illustrated sanctuary, six recovery bays, party/scan/bank metrics, healing and service links |
| Scan & materialize | Portrait gallery, search, stage/variant/ready filters, 200% progress bars and real reconstruction availability |
| DigiDex / J | Matching searchable species library, data/ownership counts and paging |
| Partners / P | Partner dossier, six formation slots, HP/SP and combat stats, lead/deposit controls |
| Digivolution | Illustrated route cards, actual stat requirements, eligibility and resulting level/ABI; separate up/down route filters |
| DigiBank | Searchable stored-partner cards, stable source indices, capacity and withdrawal controls |
| Worlds / M | Native-aspect sector thumbnails, local species, search/paging and current destination |
| Battle | Native arena plate, coherent command buttons, illustrated skills and enemy targeting; all six item recipients retained |
| Sign-in / registration | Illustrated gateway, preserved account fields, connection status and validation |
| Tamer / starter selection | Larger supplied artwork, search and clear selection cards |
| Settings / F10 | Matching display, audio and camera cards; all existing settings retained |
| Field | Matching navigation, partner cards and world feed |
| Shop / B | Exact supplied transparent `shopkeeper.png`, replacing the former Sorcermon merchant |

The accepted Shop, Ranked Arena, Rivals Hub and Bot Activity compositions remain
in place. Cyber circuitry and sparse downward-moving digits 0–9 surround the
screens, with text and controls protected by clipping. Artwork stays crisp and
native-resolution. Success cards temporarily block the controls they cover.

Closing a screen in DigiLab returns to the lab interface. Leaving the lab uses
its explicit **Return to field** action and waits for the server response.
Materialization, evolution and storage actions retain their lab/battle/capacity
restrictions. References informed appearance only, not new progression rules.

## Music and effects

The eight UI1 destination tracks remain unchanged. Separate supplied loops now
cover scanning, Digivolution, DigiBank, sign-in, character selection and Settings.
A distinct skills track is assigned for noncombat use; live battles and replays
retain combat music across command and item screens. Music uses one streaming
channel with a nonblocking transition; mute and volume settings still apply.
Confirmed scan reconstruction, evolution and purchase operations have specific
feedback. Rejected operations do not play success sounds or show success cards.

`data/ui_audio.json` records every assignment and source-file hash. Supplied
OGG files are retained unchanged. The exact hooded merchant is recorded in
`data/ui_assets.json`; the ROM extraction provenance remains separate.

## Validation and performance

See `UI2_VALIDATION.json` for the final test and visual results, and
`UI2_PERFORMANCE.json` for the crowded-world comparison and new screen timings.
Earlier measurements are retained in `FPS_FIX.md`, `FPS_BENCHMARK.json` and
`UI_PERFORMANCE.json`. No bots or artwork were removed to reduce frame time.
Native presentation caches are bounded; atlas thumbnails have a 12 MiB budget,
and the battle plate has a 32 MiB budget with native direct-draw fallback.

Reproduce the checks from the source folder:

```sh
python tools/build.py --verify-only
python -m pytest -q
python tools/preview_ui_screens.py --suite ui2 --output previews --empty --native4k --sizes 1180x800 1280x800 2048x1152
```

Screenshots use isolated synthetic QA records, including states generated by the
real game rules. They do not represent live accounts. Headless Linux timings
measure CPU frame preparation, not Windows display FPS. Audio decoding and
routing were checked through SDL's dummy driver; speaker/headphone listening,
Windows executable launch and target-PC frame pacing still require Windows.
