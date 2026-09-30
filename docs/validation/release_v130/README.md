# v1.3.0 validation evidence

**Full suite: 2,978 passed, 10 host-specific skips, zero failures (475.47 seconds).**

The complete release suite is recorded in `pytest.log` and machine-readable
`pytest.xml`. `release_summary.json` records the final counts and checks.

## Coverage

- All 96 supplied playable fields: exact base artwork, collision dimensions and
  polarity, twenty separated safe arrivals, closed safe patrols, foreground
  reconstruction and bridge visibility.
- Every 502-species normal/Paradox/Shiny set has habitats in the new region.
  Stage bands, normal encounter levels, rarity boundaries and separate capture
  progression are checked. The old regions' habitat fingerprints are unchanged.
- Each new map supports real travel, encounters and hub returns. A fresh Rookie
  earns and materializes a recruit through ordinary fights. A real WebSocket
  walk triggers a Shiny encounter; actual victory earns five scan points and
  survives a server/database connection restart.
- The 3,000-bot upgrade fixture starts from saved mature teams capable of all
  field levels. Bots rebalance through real travel to six per map, with safe
  paths and unchanged rosters, inventories, scans and careers after another
  durable restart. Separate activity tests exercise battles, earning scans,
  recruitment, healing, shopping, training and ranked participation. Runtime
  coverage remains strength-aware and permits temporary occupancy differences.
- All 20 supplied recordings decode. Intro and loop segments preserve source
  frame boundaries; SDL queue playback, volume/mute behavior, battle return,
  region routing and original soundtracks are tested.
- Native client previews and visual review at 960×600 and 1280×800 are in `ui/`.
  Interactive layout checks additionally cover 1920×1080 and 3840×2160. Preview
  accounts and bots are explicitly synthetic; art and navigation are production
  assets and code.
- `asset_preservation.json` confirms every existing asset record is unchanged.
  The source build verifier independently hashes all shipped assets/data.

## Reproduce

```bat
python -m pip install -r requirements-dev.txt
python -m pytest -q
python tools/build.py --verify-only
python tools/import_varieties_v120.py --verify --decode-images
python tools/preview_xros.py --output docs/validation/release_v130/ui
```

Use the prepared source Python environment. Tests use temporary synthetic
accounts/databases and do not connect to an existing live server. The optional
MySQL test requires its documented explicit configuration.

Windows executable builds and interactive playback on the target Windows audio
device remain target-host checks. The headless Linux run does not certify a
production MySQL deployment or a built Windows binary.
