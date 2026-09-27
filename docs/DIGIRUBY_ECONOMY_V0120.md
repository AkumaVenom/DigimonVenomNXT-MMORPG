# DigiRuby Economy — v0.12.0

Spend the DigiRubies you earn in Ranked Arena on any shop item, or exchange
them for ordinary credits. Every HP capsule, SP capsule and DigiMeat now has
both a credit price and a DigiRuby price. Your existing balances are ready to
use; no new character or wallet is required.

This release also removes the redundant **Struggle** action. **Attack still
costs zero SP**, including when a partner has no SP left.

## Buy with either currency

1. Open **Shop / B** outside combat.
2. Choose **Credits** or **DigiRubies** at the top. Both wallet balances remain
   visible, and each item shows its price in the selected currency.
3. Choose the item and quantity. Review the unit price and total, then use its
   **Buy** button. Only the selected currency is spent.
4. Wait for the server's purchase result. The item count and wallet update
   together when the purchase succeeds.

Purchases accept 1–99 of an item per transaction. The existing limit of **999
of each item** still applies. A purchase that would exceed the limit or your
balance is refused in full; it does not make a partial purchase or switch to
the other currency. Purchase availability follows the normal shop rules,
including story services where the shop is already available.

Credit prices are unchanged. The DigiRuby price is the credit price divided
by 200 and rounded **up**, with a minimum of one DigiRuby per item. The table
shows prices for **one item**; buying several multiplies that unit price.

| Item | Credits | DigiRubies |
|---|---:|---:|
| Small HP Capsule | 60 | 1 |
| Medium HP Capsule | 180 | 1 |
| Large HP Capsule | 420 | 3 |
| Small SP Capsule | 90 | 1 |
| Medium SP Capsule | 260 | 2 |
| Large SP Capsule | 600 | 3 |
| Friendship DigiMeat | 150 | 1 |
| Vitality DigiMeat +1 | 2,500 | 13 |
| Rare Vitality DigiMeat +5 | 25,000 | 125 |
| Spirit DigiMeat +1 | 2,500 | 13 |
| Rare Spirit DigiMeat +5 | 25,000 | 125 |
| Power DigiMeat +1 | 2,500 | 13 |
| Rare Power DigiMeat +5 | 25,000 | 125 |
| Guard DigiMeat +1 | 2,500 | 13 |
| Rare Guard DigiMeat +5 | 25,000 | 125 |
| Wisdom DigiMeat +1 | 2,500 | 13 |
| Rare Wisdom DigiMeat +5 | 25,000 | 125 |
| Swift DigiMeat +1 | 2,500 | 13 |
| Rare Swift DigiMeat +5 | 25,000 | 125 |

Capsules keep their existing recovery effects. Friendship DigiMeat grants CAM;
training DigiMeat permanently improves the named stat through the existing
DigiFarm feeding controls. Paying in DigiRubies does not change the item,
feeding requirements or training limits.

## Exchange DigiRubies for credits

Open **Ranked Arena / R** and choose the new **DigiRuby exchange** tab.
The published rate is **1 DigiRuby = 100 credits**.

1. Choose how many DigiRubies to spend with the amount controls or presets.
   **Max** selects the available amount within the transaction and credit limits.
2. Check the credits you will receive and both projected wallet balances.
3. Select **Review exchange**, then **Confirm exchange** to commit it. Choose
   **Back** to change the amount before confirming.
4. Read the server-confirmed result. Your DigiRuby balance decreases and your
   ordinary credits increase together.

| DigiRubies spent | Credits received |
|---:|---:|
| 1 | 100 |
| 10 | 1,000 |
| 50 | 5,000 |
| 100 | 10,000 |
| 1,000 | 100,000 |

The exchange is **one-way**; this screen does not buy DigiRubies with credits.
There is no additional fee. It accepts whole amounts from **1 to 100,000
DigiRubies per transaction**, limited by your available balance and remaining
credit capacity. Requests exceeding a limit are refused in full. The credit
cap remains 9,007,199,254,740,991.

Finish your current battle before exchanging. Return from Story Mode or Season
Mode to the shared world first. The shared DigiLab and DigiFarm can use the
exchange when no battle or private campaign is active. It does not spend arena
energy, start a match, or alter ranked points, grades or season records.

Shop DigiRuby prices and the credit exchange rate are different published
rates. The shop shows the exact direct price; the exchange preview shows the
exact credit amount. Choose the option you want before spending.

## Balances and reconnects

Your existing earned DigiRubies remain in the same persistent wallet. Credits
remain on your normal character and can be used through the existing game
systems. Normal ranked rewards and season eligibility continue unchanged.

Payment and the corresponding items or credits are committed together by the
server. An insufficient balance, full inventory, stale session or invalid
request cannot debit one wallet without granting its matching purchase. Retry
handling protects an already accepted transaction from charging twice. After
a disconnect, reconnect and check the refreshed balance and inventory before
making a new purchase.

The two story campaigns, Paradox scan bonus, partners, DigiFarm, Season career
and ranked progress remain part of the same saved account. No progress reset
is needed for this update.

## Attack when SP is empty

Choose **Attack**, or use its normal **Space** shortcut, for the free basic
attack. It works at zero SP. Skills still require their displayed SP cost.
Struggle is no longer a separate action or skill choice; normal attacks,
skills, item use, targeting and mode-specific fleeing rules remain available.

## Upgrade from v0.11.0

This is a **source release**, built on the complete v0.11.0 Paradox Chronicle
baseline. Rebuild **both the client and world server** using 64-bit Python 3.11
or newer with Tcl/Tk support on **Windows x64**. The first build needs internet
access for its Python dependencies. Keep matching client and server versions.

1. Run **STOP_SERVER.bat** in the working installation and wait for confirmed
   world and MySQL shutdown. Back up the entire stopped server folder and the
   client `config` folder. Do not back up a running database by copying its
   files.
2. Extract the complete v0.12.0 source into a separate writable source folder,
   or merge the source patch's `DigimonVenomNXT` directory into a copy of the
   complete **v0.11.0 source**, replacing the supplied files. The patch requires
   that baseline's existing assets and bundled MySQL runtime. Keep the live
   server installation outside the source's `dist` directory.
3. Run **BUILD_ALL.bat**. Use both generated packages:
   `dist/Windows_Client_x64.zip` and `dist/Windows_Server_x64.zip`.
4. Extract the new client into a new folder. Copy in the old client `config`,
   including `client.json` and the trusted `server-ca.pem`.
5. Work on a copy of the stopped server backup. Replace application components
   using the new server package: `VenomWorldServer.exe`, `_internal`, `admin`,
   `assets`, `data`, `docs`, `mysql/manager`, launchers, build metadata and
   readme files. Replace application directories in full.
6. Preserve the entire server `config` folder, **`mysql/data`**,
   `mysql/instance.json`, `mysql/game-login.json`, private MySQL configuration
   and bundled `mysql/runtime`. The top-level `data` directory contains game
   content; **`mysql/data` contains your accounts, balances and saved progress**.
   **Do not run fresh database setup or reset the database.**
7. Start MySQL, the updated world server and the updated client. Confirm your
   existing character, credits, DigiRuby balance, inventory, both story saves
   and Season career. Check both shop prices. If you choose to spend, verify a
   small purchase and a small exchange, then reconnect and confirm the saved
   balances and item count.

A native Windows build and interactive playtest on the intended PC are still
required. This guide does not claim they have already been completed. For a
new server only, follow the main README and
[../PORTABLE_SERVER_README.md](../PORTABLE_SERVER_README.md).

## v0.12.0 changes

- Added DigiRuby payment for all 19 existing shop items and visible currency
  selection, balances, unit prices and purchase totals.
- Added the Ranked Arena DigiRuby exchange with a fixed rate, balance preview
  and confirmation before spending.
- Added server-side payment validation and persistent transaction handling
  while retaining existing wallets, inventory limits and saves.
- Removed the redundant Struggle action; basic Attack remains free at zero SP.
- Updated the client, server, builder and setup version metadata and included
  this guide in both Windows distribution packages.

## Validation completed

The final automated suite passed **767 tests**, with **10 environment-dependent tests skipped** (nine graphical setup-wizard checks and one opt-in live MySQL check). All **21,806 asset/catalog SHA-256 records** verified, and Python compilation passed. Native shop, exchange and confirmation screens were checked at small and standard display sizes.

See `DIGIRUBY_VALIDATION_V0120.json` and `validation/digiruby_v0120/` for the recorded checks. These results do not replace the Windows build and target-PC playtest described above.
