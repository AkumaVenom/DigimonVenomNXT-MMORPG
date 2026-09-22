# ReArise reference and NXT ranked rules

Research date: 22 September 2026.

Digimon Venom NXT's ranked mode is an adaptation for its existing battle engine.
It is not a verified, exact reproduction of every rule from a particular regional
release of Digimon ReArise. Historical source access is incomplete, and the
original game changed during its service life. The implementation and its shipped
configuration, rather than unsourced recollections of ReArise, define NXT's rules.

## Verified original features

The following facts are paraphrased from Bandai Namco's archived Japanese website.
Confidence refers to what the cited source explicitly supports, not to parity
between Japanese and worldwide releases.

| Feature | Evidence | Confidence |
| --- | --- | --- |
| Battle Park uses players' trained Digimon teams. | Official Battle Park guide. | High |
| Winning and accumulating BP points advances rank at thresholds. | Official Battle Park guide. | High |
| Season rewards depend on both rank grade and leaderboard placement. | Official Battle Park guide. | High |
| Season rewards can include DigiRubies and BP Medals. | Official Battle Park guide. | High |
| At least one battle during the season is required for a season reward. | Explicit participation requirement in the Battle Park guide. | High |
| Players can issue skill commands in Battle Park. | Official Battle Park guide. | High |

Source: [Bandai Namco, Jijimon's Adventure Guide 4: Battle Park tips](https://web.archive.org/web/20210731124904/https://digi-rearise.bn-ent.net/information/?p=473).
The page displays 27 December 2018, but this is a July 2021 archive capture and
its contents may reflect later edits.

Bandai Namco's anniversary announcement describes a July 2019 Battle Park
revision that retained auto battles, added manual control, and introduced
promotion battles required to advance rank. It also associated promotion with
additional Battle Park story content. This establishes that there were distinct
versions of the rules; it does not establish numerical promotion thresholds.

Source: [Bandai Namco, ReArise newsletter volume 11](https://web.archive.org/web/20210820165431/https://digi-rearise.bn-ent.net/information/?p=545),
displayed date 21 June 2019, archived 20 August 2021. Confidence: high.

The original battle guide describes automatic normal attacks and player-issued
main, sub, and EX skills, with cooldowns after skill use. An Auto option also
handles skills. That is a different combat model from NXT's existing
turn-based SP combat; reusing NXT combat must not be described as an exact copy.

Source: [Bandai Namco, Jijimon's Adventure Guide 1: battles](https://web.archive.org/web/20210731114904/https://digi-rearise.bn-ent.net/information/?p=386),
displayed date 23 August 2018, archived 31 July 2021. Confidence: high.

## Details not established by the recovered sources

Do not label any of these as verified ReArise values without further evidence:

- An exact weekly reset weekday, hour, time zone, or maintenance interval.
- The complete grade sequence, grade thresholds, or promotion opponent tables.
- Points gained or lost, matchmaking formula, and streak bonuses.
- Complete DigiRuby or BP Medal reward amounts and placement brackets.
- Battle stamina capacity, regeneration, or refill prices.
- The effects of asynchronous defensive victories and defeats on either record.
- A regional version's precise roster limits and battle timeout behavior.
- Lifetime win/loss tracking, an overall historical ladder, and rivalry tracking.

No numerical original reward table is supplied here: none was recovered with
adequate supporting evidence. Naming an NXT currency DigiRubies follows the
user's request and the official currency terminology; it does not establish
parity of the economy.

## NXT implementation boundary

NXT's 5,000 persistent roaming rivals, visible overworld activity, scan-based
collection, map travel, activity history, career records, and season archives are
requested NXT features. They should be documented and tested on their own terms.

Any selected season schedule, points formula, reward table, team format,
promotion behavior, stamina policy, or defensive-record policy is an NXT rule
unless additional evidence establishes otherwise. Show the active schedule and
rewards to players, retain the applied rules with a closed season, and award
each eligible competitor once when that season closes. Bot and human competitors
should use the same published ranked rules.

The minimum-one-battle participation requirement can be adopted directly from
the verified guide. Automatic season closing, durable results, career totals,
and restart-safe reward delivery are implementation requirements for this
dedicated server; they are not claims about how the original service was built.

## Access notes

The current official game site, several community guides, and some archived
screenshots could not be read during this research. Search results frequently
failed to return relevant historical pages. Official text was recovered by
following the archived site linked from [Wikimon's ReArise reference](https://wikimon.net/Digimon_ReArise).
The secondary reference is used to locate the primary material, not as evidence
for unverified numerical rules.
