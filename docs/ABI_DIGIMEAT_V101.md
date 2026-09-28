# Digimon Venom NXT — v1.0.1 ABI DigiMeat

ABI DigiMeat gives partners a permanent way to earn ABI even when their species
has no available de-digivolution. Each owned treat adds **+1 ABI** without
resetting the partner's level. Buy it in the regular shop with either currency.

| Item | Credits | DigiRubies | Effect |
| --- | ---: | ---: | --- |
| ABI DigiMeat | 6,000 | 30 | +1 permanent ABI, up to 200 |

The DigiRuby price uses the shop's existing rate of one ruby per 200 credits of
item value. This is separate from the Ranked Arena exchange, which still gives
100 credits per ruby. For this item, paying 30 rubies directly in the shop costs
fewer rubies than converting them into 6,000 credits first.

## Feeding and evolution

Visit the **DigiLab or DigiFarm** outside battle. Open **Shop → ABI growth**,
buy the item using your chosen currency, select a party partner and choose
**Use**. The panel previews current and next ABI before feeding. The evolution
screen also offers **ABI DigiMeat shop** and **Use +1 ABI** when relevant.
In **All supplies** or **DigiMeat**, the item's **Choose** button opens the ABI
recipient panel first so you can review the partner before using the treat.
For stored residents, choose **Feed a farm resident** or select a resident in
the farm manager and choose **Feed one treat** with ABI DigiMeat selected.

Party feeding works even for your only party member; no deposit is needed.
Purchase and feeding use the existing shop, inventory and partner systems,
with ownership and conditions checked by the server.

Each consumed item adds exactly one ABI. The increase belongs to that
individual partner and survives evolution, de-digivolution, storage transfers,
save/load and a clean server restart. Feeding preserves the current species,
level, XP, CAM, identity and permanent training bonuses. The normal ABI effect
on battle stats is recalculated immediately. ABI is separate from the DigiFarm's
per-stat and combined training-bonus limits.

ABI remains capped at **200**. Feeding at the cap, submitting more treats than
the remaining ABI capacity, or trying to feed during a battle consumes nothing.
A rejected request does not change the partner. Other DigiMeat retains its
existing feeding rules.

ABI DigiMeat addresses the ABI requirement; the selected evolution must still
meet its displayed level, CAM and stat requirements. It does not add new
evolution routes or remove the requirements from existing ones. For example,
a partner that needs 50 ABI and currently has 40 needs ten treats, costing
60,000 credits or 300 DigiRubies.

## Upgrade from the corrected v1.0.0 baseline

These downloads contain **source, not prebuilt Windows executables**. Run
**BUILD_ALL.bat** and deploy **both rebuilt applications**. The server defines
the new item and applies its permanent effect; updating the client alone does
not add those rules to a running v1.0.0 server.

1. Run **STOP_SERVER.bat** and wait for the world server and MySQL to stop.
   Back up the complete stopped server folder.
2. Extract the full v1.0.1 source into a separate writable folder, or merge the
   update ZIP's `DigimonVenomNXT` directory into a copy of the complete corrected
   **v1.0.0 source**. Keep unchanged assets and the bundled MySQL runtime. For the
   full source download, extract both ZIP parts into the same parent folder,
   merging their `DigimonVenomNXT` directories.
3. On **Windows x64**, use 64-bit Python 3.11 or newer with Tcl/Tk support and run
   **BUILD_ALL.bat**. The first build needs internet access for Python build
   dependencies. The new packages are `dist/Windows_Server_x64.zip` and
   `dist/Windows_Client_x64.zip`. Keep live installations outside `dist`.
4. Work on a copy of the stopped server. Replace application components from
   the new server package: `VenomWorldServer.exe`, `_internal`, `admin`,
   `assets`, top-level `data`, `docs`, `mysql/manager`, launchers, build metadata
   and readmes. Replace application directories in full.
5. Preserve **`config`**, **`mysql/data`**, `mysql/instance.json`,
   `mysql/game-login.json`, private MySQL configuration, **`mysql/runtime`** and
   runtime logs. Top-level `data` contains game content; **`mysql/data` holds
   the saved database**. No database schema reset, fresh setup or deletion of
   player/rival records is needed.
6. Extract the complete rebuilt client into a separate folder and copy the old
   client `config` folder into it, including `client.json` and `server-ca.pem`.
   Saved display preferences remain in Local AppData. Distribute this client
   to players.
7. Start **START_MYSQL.bat**, then **START_WORLD_SERVER_CONSOLE.bat**. Wait for
   **World ready** and connect with the new client. Confirm **v1.0.1**, the
   existing partners and currencies, and ABI DigiMeat's **6,000 / 30** prices.
8. Use an owned treat on a partner below 200 ABI at the DigiLab or DigiFarm.
   Confirm the +1 ABI and one-item consumption, then perform a clean server
   restart and check that the increase remains. Existing level, XP, stories,
   training bonuses and collection should remain intact.

The corrected v1.0.0 battle cards, cyber-blue arena, Fanglongmon artwork, both
story campaigns, existing economy, 3,000-rival maximum, 12-hour Bot Activity
window and startup/network repairs remain part of this baseline.

## Verification

Current development evidence is recorded in
[validation/release_v101](validation/release_v101/README.md). The complete suite
finished with **938 passed and 10 skipped** in **236.43 seconds**, with no
failures or errors. The skips are one opt-in live-MySQL check and nine graphical
setup-wizard checks. Historical v1.0.0 reports retain their original scope and
results. Native Windows executables
and a playtest on the intended host are separate checks; this source release
does not claim a Windows build or deployment was performed here.
