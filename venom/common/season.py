"""Private, action-driven Solo Season careers.

This module never reads a real clock, Ranked Arena state, or another player.
Only NPC-only fixtures are simulated. The human result is supplied internally by
GameEngine after its ordinary authoritative battle reaches a terminal state.
Current state is bounded; completed cards are handed to the save transaction for
per-player archival. Gregorian arithmetic uses arbitrary-precision integer days.
"""
from __future__ import annotations

import copy
import hashlib
import random
import uuid

PLAYER_ID = "player"
TITLE = "Solo Season World Champion"
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")
NAMES = ("Rei Voltage", "Mika Cipher", "Kai Nightfall", "Sora Pulse", "Ren Aegis",
         "Yuna Arc", "Kira Flux", "Toma Zenith", "Aoi Vortex", "Riku Chrome",
         "Nia Eclipse", "Haru Nova", "Akira Zero", "Mei Prism", "Jin Overdrive")


class SeasonError(ValueError):
    """A safe rejection translated by GameEngine into GameError."""


def leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_before_year(year: int) -> int:
    if isinstance(year, bool) or not isinstance(year, int) or year < 1:
        raise ValueError("A fictional year must be a positive integer.")
    previous = year - 1
    return previous * 365 + previous // 4 - previous // 100 + previous // 400


def elapsed_for_date(year: int, month: int, day: int) -> int:
    lengths = (31, 29 if leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if not 1 <= month <= 12 or not 1 <= day <= lengths[month - 1]:
        raise ValueError("Invalid fictional calendar date.")
    return days_before_year(year) + sum(lengths[:month - 1]) + day - 1


def calendar_date(elapsed_days: int) -> dict:
    """Proleptic Gregorian date, with no datetime/platform maximum year."""
    if isinstance(elapsed_days, bool) or not isinstance(elapsed_days, int) or elapsed_days < 0:
        raise ValueError("Fictional elapsed days must be a non-negative integer.")
    cycles, remaining = divmod(elapsed_days, 146097)
    centuries = min(3, remaining // 36524)
    remaining -= centuries * 36524
    quads, remaining = divmod(remaining, 1461)
    singles = min(3, remaining // 365)
    remaining -= singles * 365
    year = 1 + cycles * 400 + centuries * 100 + quads * 4 + singles
    lengths = (31, 29 if leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    month = 1
    for length in lengths:
        if remaining < length:
            break
        remaining -= length
        month += 1
    day = remaining + 1
    weekday = WEEKDAYS[elapsed_days % 7]
    return {"weekday": weekday, "day": day, "month": month, "month_name": MONTHS[month - 1],
            "year": year, "label": f"{weekday}, {day} {MONTHS[month - 1]}, Year {year}"}


def _rng(season: dict, purpose: str) -> random.Random:
    value = f"{season['seed']}:{season['week']}:{purpose}".encode()
    return random.Random(int.from_bytes(hashlib.sha256(value).digest(), "big"))


def member(season: dict, ident: str) -> dict:
    return next(row for row in season["roster"] if row["id"] == ident)


def human_match(season: dict) -> dict:
    return next(match for match in season["card"]["matches"] if match["is_player"])


def validate_token(season: dict, token: object) -> None:
    if not isinstance(token, str) or token != season["card"]["token"]:
        raise SeasonError("This match card has changed. Use the current Season card and try again.")


def update_views(season: dict, state: dict | None = None) -> None:
    """Derived display data only: no booking, simulation, or time advancement."""
    if state:
        human = member(season, PLAYER_ID)
        human.update(name=state["username"], tamer=state["tamer"],
                     species_id=state["party"][0]["species_id"], level=state["party"][0]["level"])
        human["team"] = [{"species_id": m["species_id"], "level": m["level"]} for m in state["party"][:3]]
    season["calendar"] = calendar_date(season["elapsed_days"])
    ordered = sorted(season["roster"], key=lambda r: (-r["rating"], -r["wins"], r["losses"], r["id"]))
    season["standings"] = [r["id"] for r in ordered]
    for rank, row in enumerate(ordered, 1):
        row["rank"] = rank
    champion = season["champion"]
    champion["holder_name"] = member(season, champion["holder_id"])["name"]
    player = member(season, PLAYER_ID)
    season["career"] = {key: player[key] for key in ("wins", "losses", "streak", "titles", "defenses", "matches")}
    season["career"].update(rank=player["rank"], rating=player["rating"],
                            champion=champion["holder_id"] == PLAYER_ID)


def create_career(state: dict, species: dict, tamers: dict, starters: list[str]) -> dict:
    career_id = uuid.uuid4().hex
    season = {"version": 1, "id": career_id, "seed": uuid.uuid4().hex,
              "elapsed_days": 0, "week": 1, "phase": "ready", "roster": [],
              "rivalries": [], "recent_news": ["Your private World Circuit begins. Every match is part of your career."],
              "recent_reigns": [], "title_events": []}
    rng = _rng(season, "roster")
    tamer_ids = sorted(tamers)
    partner_ids = sorted(sid for sid in starters if not species[sid].get("paradox")
                         and not species[sid].get("shiny") and not species[sid].get("firewall"))
    human_level = max(1, sum(m["level"] for m in state["party"][:3]) // len(state["party"][:3]))
    for index, name in enumerate((state["username"],) + NAMES):
        is_player = index == 0
        level = max(1, min(99, human_level + (0 if is_player else (index % 5) - 2)))
        team = [{"species_id": rng.choice(partner_ids), "level": level} for _ in range(3)]
        row = {"id": PLAYER_ID if is_player else f"tamer_{index:02d}", "name": name,
               "tamer": state["tamer"] if is_player else rng.choice(tamer_ids),
               "is_player": is_player, "species_id": team[0]["species_id"], "level": level,
               "team": team, "rating": 1200 if is_player else 1110 + index * 15,
               "wins": 0, "losses": 0, "matches": 0, "streak": 0, "titles": 0, "defenses": 0,
               "last_opponent": None, "development": 0}
        season["roster"].append(row)
    champion = season["roster"][-1]
    champion["titles"] = 1
    season["champion"] = {"title": TITLE, "holder_id": champion["id"], "holder_name": champion["name"],
                          "since_week": 1, "reign": 1, "defenses": 0}
    season["recent_reigns"].append({"holder_id": champion["id"], "holder_name": champion["name"],
                                   "start_week": 1, "end_week": None, "defenses": 0})
    update_views(season, state)
    book_week(season)
    return season


def book_week(season: dict) -> None:
    """One fixture per tamer; dates are real calendar days within this booking week."""
    start = (season["week"] - 1) * 7
    date = calendar_date(start)
    end = calendar_date(start + 6)
    annual = start <= days_before_year(date["year"] + 1) - 1 <= start + 6
    monthly = date["month"] != end["month"] or annual
    title_week = season["week"] % 4 == 0 or monthly
    event_kind = "annual" if annual else "championship" if title_week else "league"
    title = (f"World Circuit Grand Championship · Year {date['year']}" if annual else
             "World Circuit Championship" if title_week else "Venom Circuit · Weekly Clash")
    rng = _rng(season, "booking")
    remaining = {row["id"] for row in season["roster"]}
    pairs = []
    if title_week:
        holder = season["champion"]["holder_id"]
        challenger = next(ident for ident in season["standings"] if ident != holder)
        pairs.append((holder, challenger, True))
        remaining.difference_update((holder, challenger))
    if PLAYER_ID in remaining:
        human = member(season, PLAYER_ID)
        candidates = [ident for ident in sorted(remaining) if ident != PLAYER_ID]
        fresh = [ident for ident in candidates if ident != human["last_opponent"]]
        candidates = fresh or candidates
        rival_ids = []
        for rivalry in sorted(season["rivalries"], key=lambda r: -r["heat"]):
            if PLAYER_ID in (rivalry["a"], rivalry["b"]) and rivalry["heat"] >= 15:
                rival_ids.extend(ident for ident in (rivalry["a"], rivalry["b"]) if ident in candidates)
        if rival_ids and season["week"] % 3 == 0:
            opponent = rival_ids[0]
        else:
            candidates.sort(key=lambda ident: abs(member(season, ident)["rating"] - human["rating"]))
            opponent = rng.choice(candidates[:4])
        pairs.append((PLAYER_ID, opponent, False))
        remaining.difference_update((PLAYER_ID, opponent))
    rest = sorted(remaining)
    rng.shuffle(rest)
    pairs.extend((rest[i], rest[i + 1], False) for i in range(0, len(rest), 2))
    # Human match on Tuesday; title NPC main event closes the card on Sunday.
    pairs.sort(key=lambda p: (PLAYER_ID not in p[:2], p[2]))
    matches = []
    for index, (home_id, away_id, title_match) in enumerate(pairs):
        home, away = member(season, home_id), member(season, away_id)
        day = start + (1 if PLAYER_ID in (home_id, away_id) else min(6, 2 + (index - 1) * 5 // 7))
        if title_match and PLAYER_ID not in (home_id, away_id):
            day = start + 6
        fixture_date = calendar_date(day)
        matches.append({"id": uuid.uuid4().hex, "home_id": home_id, "away_id": away_id,
                        "home_name": home["name"], "away_name": away["name"],
                        "home_species_id": home["species_id"], "away_species_id": away["species_id"],
                        "day": day, "weekday": fixture_date["weekday"], "date_label": fixture_date["label"],
                        "is_player": PLAYER_ID in (home_id, away_id), "title_match": title_match,
                        "status": "scheduled", "winner_id": None, "result": "Awaiting match"})
    season["card"] = {"token": uuid.uuid4().hex, "week": season["week"], "title": title,
                      "event_kind": event_kind, "start_day": start, "matches": matches}
    season["phase"] = "ready"
    season["title_events"] = []
    season["elapsed_days"] = start
    update_views(season)


def begin_match(season: dict, token: object) -> dict:
    validate_token(season, token)
    if season["phase"] != "ready":
        raise SeasonError("This week's player match is already underway or complete.")
    fixture = human_match(season)
    fixture["status"] = "in_progress"
    season["phase"] = "battle"
    season["elapsed_days"] = fixture["day"]
    update_views(season)
    return fixture


def _develop(row: dict, species: dict, rng: random.Random, news: list[str]) -> None:
    if row["is_player"]:
        return
    row["development"] += 1
    if row["development"] % 3:
        return
    for index, partner in enumerate(row["team"]):
        partner["level"] = min(99, partner["level"] + 1)
        source = species[partner["species_id"]]
        routes = [r for r in source.get("evolutions", []) if r.get("to") in species
                  and not species[r["to"]].get("paradox")
                  and not species[r["to"]].get("shiny")
                  and not species[r["to"]].get("firewall")
                  and int(r.get("level", 15)) <= partner["level"]]
        # NPC training is persistent; a partner can advance form at most once a quarter.
        if routes and row["development"] % 12 == 0:
            target = rng.choice(routes)["to"]
            partner["species_id"] = target
            if index == 0:
                news.append(f"{row['name']}'s partner digivolved into {species[target]['name']}.")
    row["species_id"] = row["team"][0]["species_id"]
    row["level"] = row["team"][0]["level"]


def _record_match(season: dict, fixture: dict, winner_id: str, species: dict,
                  rng: random.Random, news: list[str]) -> None:
    if fixture["status"] == "complete":
        raise SeasonError("This match has already been recorded.")
    home, away = member(season, fixture["home_id"]), member(season, fixture["away_id"])
    winner = home if winner_id == home["id"] else away
    loser = away if winner is home else home
    expected = 1 / (1 + 10 ** ((loser["rating"] - winner["rating"]) / 400))
    change = max(4, round(32 * (1 - expected)))
    winner["rating"] = min(2400, winner["rating"] + change)
    loser["rating"] = max(600, loser["rating"] - change)
    winner["wins"] += 1
    loser["losses"] += 1
    winner["streak"] = max(0, winner["streak"]) + 1
    loser["streak"] = min(0, loser["streak"]) - 1
    for row, other in ((winner, loser), (loser, winner)):
        row["matches"] += 1
        row["last_opponent"] = other["id"]
        _develop(row, species, rng, news)
    fixture.update(status="complete", winner_id=winner_id, winner_name=winner["name"],
                   result=f"{winner['name']} defeated {loser['name']}")
    a, b = sorted((home["id"], away["id"]))
    rivalry = next((r for r in season["rivalries"] if r["a"] == a and r["b"] == b), None)
    if rivalry is None:
        rivalry = {"a": a, "b": b, "a_name": member(season, a)["name"],
                   "b_name": member(season, b)["name"], "heat": 0, "matches": 0,
                   "a_wins": 0, "b_wins": 0, "last_week": season["week"], "leader_id": None}
        season["rivalries"].append(rivalry)
    rivalry["matches"] += 1
    rivalry["a_wins" if winner_id == a else "b_wins"] += 1
    rivalry["heat"] = min(100, rivalry["heat"] + (24 if fixture["title_match"] else 12))
    rivalry["last_week"] = season["week"]
    rivalry["leader_id"] = (a if rivalry["a_wins"] > rivalry["b_wins"] else
                             b if rivalry["b_wins"] > rivalry["a_wins"] else None)
    if fixture["is_player"]:
        news.append(fixture["result"] + (" in a World Championship match!" if fixture["title_match"] else "."))
    if fixture["title_match"]:
        champion = season["champion"]
        old_holder = champion["holder_id"]
        if old_holder == winner_id:
            champion["defenses"] += 1
            winner["defenses"] += 1
            season["recent_reigns"][-1]["defenses"] = champion["defenses"]
            kind = "defense"
            news.append(f"{winner['name']} retained the Solo Season World Championship.")
        else:
            season["recent_reigns"][-1]["end_week"] = season["week"]
            winner["titles"] += 1
            champion.update(holder_id=winner_id, holder_name=winner["name"],
                            since_week=season["week"], reign=champion["reign"] + 1, defenses=0)
            season["recent_reigns"].append({"holder_id": winner_id, "holder_name": winner["name"],
                                           "start_week": season["week"], "end_week": None, "defenses": 0})
            season["recent_reigns"] = season["recent_reigns"][-12:]
            kind = "title_change"
            news.append(f"NEW CHAMPION: {winner['name']} won the Solo Season World Championship!")
        season["title_events"].append({"kind": kind, "week": season["week"], "day": fixture["day"],
                                       "previous_holder_id": old_holder, "holder_id": winner_id,
                                       "holder_name": winner["name"], "reign": champion["reign"],
                                       "defenses": champion["defenses"]})


def finish_human(season: dict, won: bool, species: dict) -> None:
    if season["phase"] != "battle":
        raise SeasonError("No scheduled Season battle is awaiting a result.")
    fixture = human_match(season)
    if fixture["status"] != "in_progress":
        raise SeasonError("This match is not in progress.")
    rng = _rng(season, "results")
    news: list[str] = []
    opponent_id = fixture["away_id"] if fixture["home_id"] == PLAYER_ID else fixture["home_id"]
    _record_match(season, fixture, PLAYER_ID if won else opponent_id, species, rng, news)
    for other in season["card"]["matches"]:
        if other["is_player"]:
            continue
        home, away = member(season, other["home_id"]), member(season, other["away_id"])
        rating_gap = home["rating"] - away["rating"] + (home["level"] - away["level"]) * 4
        chance = 1 / (1 + 10 ** (-max(-1200, min(1200, rating_gap)) / 400))
        winner_id = home["id"] if rng.random() < chance else away["id"]
        _record_match(season, other, winner_id, species, rng, news)
    if season["card"]["event_kind"] == "annual":
        year = calendar_date(season["card"]["start_day"])["year"]
        news.append(f"Year {year} closes. All records, rivalries and the World Champion carry into the next year.")
    season["phase"] = "results"
    season["elapsed_days"] = season["card"]["start_day"] + 6
    season["recent_news"] = (news + season["recent_news"])[:12]
    update_views(season)


def next_week(state: dict, token: object) -> None:
    season = state["season"]
    validate_token(season, token)
    if season["phase"] != "results" or any(m["status"] != "complete" for m in season["card"]["matches"]):
        raise SeasonError("Play your scheduled match before continuing to the next week.")
    snapshot = {"week": season["week"], "career_id": season["id"],
                "start_date": calendar_date(season["card"]["start_day"]),
                "end_date": calendar_date(season["card"]["start_day"] + 6),
                "card": copy.deepcopy(season["card"]), "champion": copy.deepcopy(season["champion"]),
                "title_events": copy.deepcopy(season["title_events"]),
                "standings": [{key: row[key] for key in ("id", "name", "rating", "wins", "losses", "level", "species_id")}
                              for row in sorted(season["roster"], key=lambda r: r["rank"])],
                "news": list(season["recent_news"])}
    state.setdefault("_season_archive_pending", []).append(snapshot)
    season["week"] += 1
    for rivalry in season["rivalries"]:
        rivalry["heat"] = max(0, rivalry["heat"] - 2)
    book_week(season)
