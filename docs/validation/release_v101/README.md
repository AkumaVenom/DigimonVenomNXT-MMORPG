# v1.0.1 validation evidence

This folder records development verification of ABI DigiMeat on the corrected
v1.0.0 source baseline. ABI DigiMeat costs **6,000 credits or 30 DigiRubies** and
permanently grants **+1 ABI**, capped at 200, without resetting a partner's
level. The current upgrade guide is [ABI_DIGIMEAT_V101.md](../../ABI_DIGIMEAT_V101.md).

## Current results

The complete automated suite finished with **938 passed and 10 skipped** in
**236.43 seconds**, with zero failures and zero errors. The skips are one
opt-in live-MySQL check and nine graphical setup-wizard checks; they are not
passes. Results are recorded in [full_suite.log](full_suite.log) and
[full_suite.xml](full_suite.xml). Focused selections overlap with this suite and
must not be added to its pass count.

The ABI regression checks exercise credit and DigiRuby purchases, exact
inventory consumption, party and stored-resident feeding, stat recalculation,
the 200 ABI cap, rejected requests, evolution requirements and saved progress.
Existing campaign, economy, restart, rival population, activity-retention and
battle-layout regressions remain in the complete suite.

## Native interface captures

The focused UI selection completed with **34 passed**, comprising 14 ABI UI
checks and 20 retained shop/partner layout checks. Twelve native captures cover
credit and DigiRuby checkout, party/evolution feeding, a species without a
backward route, the ABI cap and stored-resident feeding. Each scene is captured
at **960×600** with UI scale **0.75** and **2047×1155** with UI scale **1.25**.
The [UI report](abi_ui_report.json) records no actions outside either display.

- [ABI shop and selected recipient at 2047×1155](abi_shop_credits_2047x1155.png)
- [DigiRuby checkout at 960×600](abi_shop_rubies_960x600.png)
- [Evolution controls at 960×600](abi_evolution_960x600.png)
- [No de-digivolution route at 960×600](abi_evolution_no_devolve_960x600.png)
- [ABI cap at 960×600](abi_evolution_cap_960x600.png)
- [Stored-resident feeding at 960×600](abi_farm_960x600.png)

These are native client captures using unsaved QA state. The primary
[ABI preview](abi_preview.png) is the 2047×1155 credit-shop capture.

## Release and packaging

Client, server, setup and Windows build metadata share `venom/version.py`.
The Windows packaging checks simulate external build tools with dummy
executables. They verify that both packages contain the current ABI guide and
validation evidence, retain the v1.0.0 history, and exclude live database state
and credentials. These checks do not compile or execute native Windows
applications.

The focused packaging, setup-diagnostics and source-package selection completed
with **23 passed** in **0.87 seconds**. Its [log](package_tests.log) and
[JUnit report](package_tests.xml) are retained here.

The release changes no original sprite assets and requires no database reset.
Historical reports in `release_v100` and earlier folders retain their original
versions and measurement scope; they are not new v1.0.1 performance results.

These are development checks. Build both Windows applications, preserve the
existing database and private configuration, and validate the intended host
using the current upgrade guide.
