# Season Mode v0.7.0 validation

Validation host: Linux, Python 3.12, pygame-ce 2.5.8, websockets 16.0.
Source baseline: supplied Digimon Venom NXT v0.6.2 High Ping Disconnect Fix.

## Automated results

- Full suite: **486 passed, 10 skipped**, completed in 72.90 seconds.
- After final visual polish, focused client/build/audio regression checks: **22 passed**.
- Content/build preflight: **21,360 asset and catalog integrity records passed**,
  covering 506.3 MiB. Original art/audio bytes remain intact; the manifest records
  the updated screen-audio configuration.
- Python compilation and whitespace checks passed.
- No Windows executables were built on this Linux host.

## Season coverage

The new tests use the actual catalog and gameplay engine. Protocol tests run the
real WebSocket server against an on-disk development SQLite database.

- Gregorian month boundaries, leap centuries and 2,000 sampled reference dates;
  integer date arithmetic beyond Year 10,000, including Year 10^30.
- A 1,000-week simulation with preserved lifetime totals, at most 120 roster
  pair rivalries, 12 recent reigns and 12 headlines, and bounded active career
  state. Completed snapshots are handed off for immutable history archival.
- Annual transition into Year 10,001 without resetting champion, career ID,
  rivalries or records.
- Live player battle actions through a terminal result; no client-submitted
  winner or player autoplay. Attack, skills, items, guard and swap use existing
  engine turn rules. Flee and activity/forfeit bypasses are rejected.
- Stale card tokens, old battle identifiers and repeated turn commands rejected.
- Victory, defeat, championship defense and title transfer recorded once.
- Private ownership, pagination, numeric ordering of large week counters,
  account lease/revision failures, and injected archive-write rollback.
- Full server/database restart preserves battle queue, calendar and fixture.
  A three-year real-clock jump causes no fictional advancement.
- Existing shared Ranked tables remain unchanged through private career play.
- Client buttons send authoritative requests without locally applying outcomes;
  reconnect and return transitions, match history paging, muted audio routing,
  and native layout bounds at 960x600, 1180x800 and 1920x1080.

Independent read-only review also compared 20,000 calendar samples with standard
Gregorian dates and checked distant integer-calendar boundaries.

## Visual review

Native pygame screenshots were rendered using an isolated engine fixture and
labelled **SYNTHETIC QA PREVIEW**. The review covered the ready card, completed
card, roster/rankings, rivalries, championship, archive/detail, live battle,
skills and items, the minimum layout and a five-digit year. Screens use the
shipped artwork and screen/battle soundtrack families. Visual fixtures are not
production accounts and do not imply a completed player career.

The review corrected header date/signal overlap, latest-headline ordering,
pending-save feedback, and the availability of shared chat during a private
league match.

## Retained regression checks

The supplied baseline had six existing test failures, reproduced in an isolated
copy of its original code. Ranked tests assumed a five-energy/30-minute fixture
while the supplied defaults were 30 energy/five minutes. Their explicit test
configuration now matches the fixtures they assert. The old DigiFarm snapshot
test now awaits the per-client queued senders introduced by the supplied high-
ping fix. These corrections change tests only; shared Ranked balance and the
queued-send implementation remain intact.

## Unverified host-specific behavior

The 10 skipped checks are one opt-in live MySQL-runtime test and nine graphical
Tk setup-wizard tests requiring a desktop/Xvfb. SQLite exercises transactional
save behavior; the new MySQL-compatible additive table and SQL paths still need
a live target-host smoke test. This run does not establish Windows packaging,
hardware performance, production load capacity, or an interactive audio
listening/playtest. Build both Windows applications with BUILD_ALL.bat and test
the updated installation on a copy of the stopped server before rollout.
