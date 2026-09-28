# Bot Activity v0.12.2 validation

This folder contains source validation evidence for the 12-hour global Bot
Activity update. The complete automated suite finished with **799 passed and
10 skipped** in **224.55 seconds**. The skips are one opt-in live-MySQL check
and nine graphical setup-wizard checks. See the [full log](full_suite.log) and
[JUnit XML results](full_suite.xml).

## Retention measurements

The [retention report](RETENTION_VALIDATION.md) and
[JSON results](retention_28_days.json) cover **40,320 minute batches across 28
simulated days**, with all 27 counters including fractional walking distance.
The maximum observed shared history was **720 minute buckets** and **100 feed
events**. Counter JSON stayed at **318,960 bytes** at days 1, 7 and 28, excluding
database overhead and all other gameplay data. The fixture's 720 receipt rows
reflect one save per minute; real receipt counts depend on save frequency
within the twelve-hour window.

## Client presentation

The native Pygame client was rendered with synthetic server responses at
1024×720, 2047×1149 and 3840×2160. The [UI report](ui/report.json) records 18
rendered variants, no action controls outside the display, and 12 passing
client tests. Included reviewed previews:

- [Activity at 1024×720](ui/activity_1024x720_normal.png)
- [Activity at 2047×1149](ui/activity_2047x1149_normal.png)
- [Initial empty activity window](ui/activity_1024x720_empty.png)
- [Separate rival career profile](ui/activity_1024x720_profile.png)

## Verification boundary

The simulated Windows package tests check package contents and metadata. They
do not execute native Windows applications. Native Windows executable building
and target-machine playtesting remain separate release checks. Retention
measurements used an isolated in-memory SQLite database, not the user's saved
world or a Windows/MySQL startup benchmark.
