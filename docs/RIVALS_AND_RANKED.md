# Tamer rivals and Battle Park — v0.2.0

The updated dedicated server runs the rival population and settles every battle.
The client displays server results, positions and records. Use **R** for Ranked
Arena (the Battle Park system), **V** for the Rivals Hub, **O** for Bot Activity,
or click a rival in a level.

## The 5,000 rival population

By default, the world creates 5,000 named AI tamers with stable identities and
saved progress. Initial placement is even across the 254 maps: each starts with
19 or 20 rivals. Their subsequent locations change as they travel and recover;
the population is not continuously teleported to maintain an exact per-map count.

Each fresh rival receives one ordinary Rookie at a level seeded for its starting
sector. That initial level is identified separately and is not recorded as earned
training XP. From then on, wild victories, defeated-Digimon scans, materialized
partners, levels, inventory and evolution changes use the game's actual rules.
Paradox scan progress remains slower and is not granted automatically.

Every rival repeatedly walks, fights a wild encounter, visits the DigiLab for
party care, considers a ranked attack, and returns to exploration. Wild turns
choose affordable skills, free attacks, useful items and party replacements.
Lab care heals, materializes when scan data reaches at least 100%, checks valid
evolution routes, rotates partners for training and buys supplies when affordable.
Materialization fills the six-member party and then storage. A scheduled activity
is a decision opportunity: it cannot create a partner below the scan threshold,
evolve without requirements, or buy items without credits.

Ranked energy applies to bots as well as players. When it is exhausted, a rival
continues its other activities and revisits Battle Park on later cycles. This
prevents ranked waiting from stopping wild training or walking.

Rivals normally spend **5–15 minutes** in a sector before considering travel.
Defeat can trigger an earlier move to a safer sector after recovery. Travel
prefers less populated destinations compatible with the party's strength. It
does not abruptly change a moving actor's position within a map: arrival in
another map is a deliberate zone transition.

Walking uses the imported tamer animation frames and validated navigation paths.
The server samples one authoritative population for each occupied map; clients
interpolate its snapshots for smooth display. Tamers stop while occupied with
other activities. Rivals are server-side actors, not 5,000 fake network clients.
Only the current field's actors are sent to its players.

Rival progress is saved to the server database. The default checkpoint writes up
to 100 changed rivals every three seconds; a fully changed 5,000-rival population
takes approximately 150 seconds to complete a save rotation, depending on load.
A clean shutdown saves all pending bot progress. An abrupt crash can lose wild
progress since each rival's last checkpoint. Ranked outcomes and season rewards
commit immediately; ranked counters reconcile from that ledger on restart.
Restart resumes stored rivals; it does not invent battles or training for time
spent offline. Database ownership checks prevent an expired server process from
overwriting the progress of its replacement.

## Rival interactions and activity

Click an AI tamer to inspect its party, location, current activity and progress.
Nearby available rivals can issue a friendly invitation. Open the Rivals Hub to
accept or decline it, search the directory, and review prior opponents. Direct
challenges require a nearby rival in the same sector; the server rechecks their
availability at the time you accept. A rival can finish an activity or leave
before an invitation is accepted. Invitations expire after three minutes and
are cleared on server restart; completed opponent records remain saved.

Friendly matches update your head-to-head history but do not change ranked
points, ranked wins/losses, rating, energy or season reward eligibility. Ranked
matches against rivals also contribute to the head-to-head history. The database
retains opponent totals; the hub exposes the 100 most recently fought opponents.

Bot Activity displays current phase counts and map distribution, along with
actual cumulative activity totals: wild and ranked wins/losses, starts, scan
events and percentage gained, materializations, Paradox materializations, earned
Battle XP and levels, evolution/de-evolution, party changes, healing, item use, purchases
and travel. The global detail feed keeps the **latest 100 events**, newest first.
Older event detail is pruned; aggregate counters remain. A zero counter means
that action has not yet completed under its required conditions. Battle XP sums
the base XP awards from wild victories; it does not multiply them by the number
of partners receiving a share.

## Battle Park format

Battle Park is asynchronous: you attack another competitor's saved defender
team, and the server resolves both sides automatically. An opponent does not
need to be logged in. Your team is refreshed from your actual party when you use
the community features. The first three partners start, with up to three reserves
entering when active partners fall. A one- or two-partner team uses its available
members.

Both sides fight using restored copies of their parties. The resolver uses real
stats, speed, skills, SP and type/attribute effectiveness. It selects affordable
skills and free attacks; results do not come from a random win/loss counter.
Field HP/SP, inventory and XP are unchanged by arena simulation. Configure your
party in Partners before entering; you do not issue manual commands during the
arena replay. Use **1× playback** to toggle double-speed playback, **Show result**
to skip the remainder, and **Return to hub** after the outcome.

The default turn limit is 240. If neither party is eliminated, the side with the
higher average remaining HP fraction wins; an exact tie is a successful defense.
This limit makes every match terminate. The same arena rules apply to humans
and bots.

The mode adapts ReArise's documented Battle Park structure. Its numerical rules,
weekly UTC schedule, three-active-partner SP combat, defensive records and career
ladder are **NXT rules**, not a claim of exact ReArise parity. The official sources
and remaining gaps are recorded in `REARISE_RULES_RESEARCH.md`.

## Published default ranking rules

| Rule | Default |
| --- | --- |
| Season | Seven days; Monday 00:00 UTC to the next Monday 00:00 UTC |
| Win | +20 season points |
| Loss | −5 season points, never below zero |
| Attack energy | Capacity 5; one energy spent per ranked attack |
| Recovery | One energy every 30 minutes, up to capacity |
| General match cooldown | Two seconds between initiated matches |
| Same ranked opponent | A 60-second rematch cooldown |
| Defensive results | Count toward both competitors' season and career records and points; no defensive energy charge |
| Career rating | Starts at 1,000; Elo update with K = 24 |
| Season ladder order | Points, then wins, then fewer losses, then stable competitor ID |
| Career ladder order | Rating, then wins, then fewer losses, then stable competitor ID |
| Reward eligibility | Start and complete at least one ranked attack during that season; passive defenses alone do not qualify |

Season points, wins/losses and earned grade start fresh each season. Career
wins/losses, rating, DigiRubies and closed-season records remain. The current,
career and archived-season screens show the top 100 competitors, including
humans and AI tamers. Archived seasons appear after the first season closes.

Crossing a grade threshold makes a promotion pending. Win a subsequent ranked
attack while still meeting the threshold to advance one grade. Defensive wins
can earn points but do not complete promotion battles. An earned grade is not
demoted by later point losses during that season.

| Grade | Points needed to open promotion | Season grade bonus |
| --- | ---: | ---: |
| Bronze | Starting grade | 10 DigiRubies |
| Silver | 100 | 20 DigiRubies |
| Gold | 300 | 40 DigiRubies |
| Platinum | 600 | 70 DigiRubies |
| Diamond | 1,000 | 100 DigiRubies |
| Master | 1,800 | 150 DigiRubies |

The final reward is the **placement bonus plus the earned-grade bonus**:

| Final placement | Placement bonus |
| --- | ---: |
| 1 | 300 DigiRubies |
| 2–10 | 200 DigiRubies |
| 11–25 | 150 DigiRubies |
| 26–50 | 100 DigiRubies |
| 51–100 | 75 DigiRubies |
| 101–500 | 40 DigiRubies |
| 501 and below | 20 DigiRubies |

For example, an eligible Gold competitor in place 40 receives 100 + 40 = 140
DigiRubies. Placement is the season ladder position; reward eligibility does not
turn an unplayed account into a participant. Rewards credit the persistent wallet
automatically after the season closes. Each competitor/season award has a unique
database record so retries cannot pay twice. If the server was stopped at reset,
its next startup closes the expired active season and awards it before continuing.
DigiRubies accumulate in this release; no DigiRuby shop is included.

The database retains compact match outcomes for history and duplicate protection.
Full animated replays are sent with the live result and are not stored in the
permanent ledger. Match history therefore grows with play; include the new
community tables in the normal database backup.

## Operator settings

The default population is enabled even when an existing `config/server.json`
does not yet have a `rivals` section. To adjust it, stop the world server, preserve
the existing configuration, and merge the following property into the top-level
JSON object. Do not replace the database, host or TLS properties.

```json
"rivals": {
  "enabled": true,
  "count": 5000,
  "dwell_min": 300,
  "dwell_max": 900
}
```

The snippet is one property inside the existing object; use commas between it and
other properties. `count` accepts whole numbers from 0 to 5,000. Setting
`enabled` to `false` disables roaming simulation. Saved rival data is retained.
Restart after changes. Keep a stable configuration during a competitive season.

The `ranked` configuration can override the timing/energy/point defaults in
`venom/server/ranked.py`. These are operator settings, not client controls. Each
season freezes the rules applied when it starts; changes to ordinary numerical
settings apply to the next season. Archived seasons retain their rules and reward
amounts. After the first season is created, changing `season_seconds` or
`season_anchor` is rejected: changing the season clock requires an explicit
migration, not a configuration edit. Prefer the shipped schedule and record any
planned rule change before opening a new world.

Use Bot Activity's distribution and activity counts to inspect progress. A
population of 5,000 is an actor count, not a promise of a particular FPS, network
capacity or number of simultaneous human connections. Follow `VALIDATION.md` for
measured checks, and verify sustained operation on the intended Windows/MySQL
host. Stop the console server cleanly before database backups or upgrades.
