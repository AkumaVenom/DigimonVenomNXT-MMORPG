"""Additive MySQL/SQLite persistence for rivals, rankings and the bot population.

The account/save schema is deliberately untouched. Every community write shares
Database.lock and a transaction with related balances/counters. Match identifiers
and season reward keys are unique, so a retry cannot award a second result.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import hashlib
import math
import time
import uuid

from venom.common.game import GameError
from venom.common.population import retired_bot_ids
from venom.server.activity_window import BUCKET_SECONDS, EVENT_LIMIT, WINDOW_SECONDS
from venom.server.database import DatabaseError


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


class CommunityStore:
    ACTIVITY_WINDOW_SECONDS = WINDOW_SECONDS
    ACTIVITY_PRECISION_SECONDS = BUCKET_SECONDS
    ACTIVITY_RECEIPT_PRUNE_BATCH = 1000
    RETIREMENT_BATCH = 100
    RETIREMENT_PLAN = "population_retirement_pending"

    def __init__(self, database):
        self.database = database
        self.lock = database.lock
        self._sql = database._sql
        self.owner_token = None
        self.lease_seconds = 90

    @contextmanager
    def transaction(self, require_lease=True):
        with self.lock:
            db = self.database._connect()
            cursor = db.cursor()
            lease = None
            try:
                # A single writer owns the population; SQLite also serializes a
                # second process before it reads a balance it intends to update.
                if self.database.driver == "sqlite":
                    cursor.execute("BEGIN IMMEDIATE")
                if require_lease and self.owner_token is not None:
                    query = "SELECT value_json FROM venom_community_meta WHERE name='world_lease'"
                    if self.database.driver == "mysql":
                        query += " FOR UPDATE"
                    cursor.execute(query)
                    found = cursor.fetchone()
                    lease = json.loads(found[0]) if found else {}
                    if lease.get("token") != self.owner_token or lease.get("until", 0) <= time.time():
                        raise DatabaseError("The rival population lease expired or belongs to another world server.")
                    # The same transaction holds the lease row until its writes
                    # commit. A paused former owner cannot overwrite a successor
                    # between a separate ownership check and the actual save.
                yield cursor
                if lease is not None and lease.get("until", 0) - time.time() < self.lease_seconds / 3:
                    # The ownership row stayed locked for this entire valid
                    # transaction. Refresh before releasing it: a slow query or
                    # checkpoint may have blocked the heartbeat for >90s, but
                    # no successor could acquire ownership while this lock was
                    # held. An already-expired lease still fails at entry.
                    cursor.execute(self._sql("UPDATE venom_community_meta SET value_json=? WHERE name='world_lease'"),
                                   (_json({"token": lease["token"], "until": time.time() + self.lease_seconds}),))
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                cursor.close()

    def initialize(self):
        tables = [
            """CREATE TABLE IF NOT EXISTS venom_community_meta (
                name VARCHAR(64) PRIMARY KEY, value_json LONGTEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS venom_competitors (
                id VARCHAR(64) PRIMARY KEY, kind VARCHAR(12) NOT NULL,
                name VARCHAR(64) NOT NULL, tamer VARCHAR(128) NOT NULL,
                profile_json LONGTEXT NOT NULL, career_wins INTEGER NOT NULL DEFAULT 0,
                career_losses INTEGER NOT NULL DEFAULT 0, career_rating INTEGER NOT NULL DEFAULT 1000,
                digirubies BIGINT NOT NULL DEFAULT 0, energy INTEGER NOT NULL DEFAULT 5,
                energy_at DOUBLE NOT NULL, last_attack DOUBLE NOT NULL DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS venom_ranked_seasons (
                id BIGINT PRIMARY KEY, starts_at DOUBLE NOT NULL,
                ends_at DOUBLE NOT NULL, status VARCHAR(16) NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS venom_ranked_records (
                season_id BIGINT NOT NULL, participant_id VARCHAR(64) NOT NULL,
                points INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0, grade INTEGER NOT NULL DEFAULT 0,
                promotion_pending INTEGER NOT NULL DEFAULT 0, final_rank INTEGER NULL,
                PRIMARY KEY(season_id, participant_id))""",
            """CREATE TABLE IF NOT EXISTS venom_ranked_matches (
                id VARCHAR(64) PRIMARY KEY, season_id BIGINT NOT NULL,
                attacker_id VARCHAR(64) NOT NULL, defender_id VARCHAR(64) NOT NULL,
                winner_id VARCHAR(64) NOT NULL, ranked INTEGER NOT NULL,
                played_at DOUBLE NOT NULL, result_json LONGTEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS venom_ranked_rewards (
                season_id BIGINT NOT NULL, participant_id VARCHAR(64) NOT NULL,
                amount INTEGER NOT NULL, final_rank INTEGER NOT NULL, awarded_at DOUBLE NOT NULL,
                PRIMARY KEY(season_id, participant_id))""",
            """CREATE TABLE IF NOT EXISTS venom_bot_state (
                id VARCHAR(64) PRIMARY KEY, state_json LONGTEXT NOT NULL, updated_at DOUBLE NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS venom_activity (
                id VARCHAR(64) PRIMARY KEY, bot_id VARCHAR(64) NOT NULL,
                kind VARCHAR(48) NOT NULL, happened_at DOUBLE NOT NULL, event_json LONGTEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS venom_activity_counters (
                name VARCHAR(64) PRIMARY KEY, value BIGINT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS venom_activity_batches (
                id VARCHAR(64) PRIMARY KEY, happened_at DOUBLE NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS venom_activity_windows (
                bucket_at BIGINT PRIMARY KEY, counters_json LONGTEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS venom_rival_matches (
                player_id VARCHAR(64) NOT NULL, match_id VARCHAR(64) NOT NULL,
                PRIMARY KEY(player_id, match_id))""",
            """CREATE TABLE IF NOT EXISTS venom_rival_history (
                player_id VARCHAR(64) NOT NULL, rival_id VARCHAR(64) NOT NULL,
                wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0,
                last_at DOUBLE NOT NULL, last_match VARCHAR(64) NOT NULL,
                PRIMARY KEY(player_id, rival_id))""",
        ]
        suffix = " ENGINE=InnoDB" if self.database.driver == "mysql" else ""
        with self.transaction() as cursor:
            for table in tables:
                cursor.execute(table + suffix)
            # SQLite IF NOT EXISTS and MySQL's information_schema both let us
            # repair a missing index without changing existing accounts/saves.
            indexes = {
                "venom_match_season_attacker": ("venom_ranked_matches", "season_id, attacker_id"),
                "venom_match_attacker_at": ("venom_ranked_matches", "attacker_id, played_at"),
                "venom_match_defender_at": ("venom_ranked_matches", "defender_id, played_at"),
                # Restart reconciliation uses only these compact columns. The
                # covering indexes avoid reading every historical result JSON
                # row from disk as a server's match history grows.
                "venom_match_attacker_totals": ("venom_ranked_matches", "attacker_id, ranked, winner_id"),
                "venom_match_defender_totals": ("venom_ranked_matches", "defender_id, ranked, winner_id"),
                "venom_activity_time": ("venom_activity", "happened_at"),
                "venom_activity_batch_time": ("venom_activity_batches", "happened_at, id"),
                "venom_ranking_order": ("venom_ranked_records", "season_id, points, wins, losses"),
            }
            for name, (table, columns) in indexes.items():
                if self.database.driver == "mysql":
                    cursor.execute(self._sql("SELECT COUNT(*) FROM information_schema.statistics "
                                              "WHERE table_schema=DATABASE() AND table_name=? AND index_name=?"),
                                   (table, name))
                    exists = cursor.fetchone()[0]
                    if not exists:
                        cursor.execute(f"CREATE INDEX {name} ON {table} ({columns})")
                else:
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")
            cursor.execute("SELECT value_json FROM venom_community_meta WHERE name='activity_window_v1'")
            if cursor.fetchone() is None:
                # Old aggregate totals have no event times. They cannot honestly
                # become a last-12-hours total. Only this obsolete telemetry is
                # reset; bot progression and ranked/career records are untouched.
                cursor.execute("DELETE FROM venom_activity_counters")
                cursor.execute(self._sql("INSERT INTO venom_community_meta(name,value_json) "
                                         "VALUES ('activity_window_v1',?)"),
                               (_json({"version": 1, "tracking_since": time.time()}),))
        # Old builds kept a receipt for every telemetry flush indefinitely.
        # Drain that backlog with indexed pages and release the database lock
        # between commits. Never load the historical receipt list into memory.
        self.maintain_activity(drain=True)

    def acquire_world(self, token, lease_seconds=120, now=None):
        with self.transaction(require_lease=False) as cursor:
            query = "SELECT value_json FROM venom_community_meta WHERE name='world_lease'"
            if self.database.driver == "mysql":
                query += " FOR UPDATE"
            cursor.execute(query)
            found = cursor.fetchone()
            # A long transaction can keep this call queued on either the
            # Python connection lock or the SQL ownership row. Its new lease
            # starts when ownership is actually read, never before that wait.
            now = time.time() if now is None else float(now)
            lease = json.loads(found[0]) if found else {}
            if lease.get("token") != token and lease.get("until", 0) > now:
                return False
            value = _json({"token": token, "until": now + lease_seconds})
            if found:
                cursor.execute(self._sql("UPDATE venom_community_meta SET value_json=? WHERE name='world_lease'"), (value,))
            else:
                cursor.execute(self._sql("INSERT INTO venom_community_meta(name,value_json) VALUES ('world_lease',?)"), (value,))
            return True

    def renew_world(self, token, lease_seconds=120, now=None):
        with self.transaction(require_lease=False) as cursor:
            query = "SELECT value_json FROM venom_community_meta WHERE name='world_lease'"
            if self.database.driver == "mysql":
                query += " FOR UPDATE"
            cursor.execute(query)
            found = cursor.fetchone()
            now = time.time() if now is None else float(now)
            lease = json.loads(found[0]) if found else {}
            if lease.get("token") != token or lease.get("until", 0) <= now:
                return False
            cursor.execute(self._sql("UPDATE venom_community_meta SET value_json=? WHERE name='world_lease'"),
                           (_json({"token": token, "until": now + lease_seconds}),))
            return True

    def release_world(self, token):
        with self.transaction(require_lease=False) as cursor:
            query = "SELECT value_json FROM venom_community_meta WHERE name='world_lease'"
            if self.database.driver == "mysql":
                query += " FOR UPDATE"
            cursor.execute(query)
            row = cursor.fetchone()
            if row and json.loads(row[0]).get("token") == token:
                cursor.execute("DELETE FROM venom_community_meta WHERE name='world_lease'")
                return True
            return False

    def retire_legacy_bots(self):
        """Remove the retired population before loading defender teams.

        Only canonical legacy bots 03001--05000 are eligible. Each small batch
        commits under the world lease, so an interrupted upgrade can resume by
        running this method again without touching retained rivals or players.
        Historical match/reward ledgers and already-expired season standings
        remain intact. A small durable plan lets an interrupted current-season
        roster change finish consistently even if that season expires offline.
        """
        if not self.owner_token:
            raise DatabaseError("Acquire the world population lease before retiring rivals.")
        retired = tuple(retired_bot_ids())
        counts = {"bot_states": 0, "competitors": 0, "activity_events": 0, "season_records": 0}
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT value_json FROM venom_community_meta WHERE name=?"),
                           (self.RETIREMENT_PLAN,))
            found = cursor.fetchone()
            try:
                plan = json.loads(found[0]) if found else {"pending_season_ids": []}
                planned = plan["pending_season_ids"]
                if not isinstance(planned, list) or any(type(ident) is not int for ident in planned):
                    raise ValueError("Invalid pending season identifiers.")
            except (KeyError, TypeError, ValueError) as exc:
                raise DatabaseError("The saved rival retirement plan is invalid; no rivals were removed.") from exc
            cursor.execute(self._sql("SELECT id FROM venom_ranked_seasons WHERE status='active' AND ends_at>?"),
                           (time.time(),))
            planned = sorted(set(planned).union(int(row[0]) for row in cursor.fetchall()))
            value = _json({"pending_season_ids": planned})
            if found:
                cursor.execute(self._sql("UPDATE venom_community_meta SET value_json=? WHERE name=?"),
                               (value, self.RETIREMENT_PLAN))
            else:
                cursor.execute(self._sql("INSERT INTO venom_community_meta(name,value_json) VALUES (?,?)"),
                               (self.RETIREMENT_PLAN, value))
        season_placeholders = ",".join("?" for _ in planned)
        for offset in range(0, len(retired), self.RETIREMENT_BATCH):
            batch = retired[offset:offset + self.RETIREMENT_BATCH]
            placeholders = ",".join("?" for _ in batch)
            with self.transaction() as cursor:
                # Use the durable selection, not a moving time cutoff. A crash
                # across a season boundary must not leave a partial old roster
                # behind for the automatic reward settlement that follows.
                if planned:
                    cursor.execute(self._sql(
                        "DELETE FROM venom_ranked_records WHERE participant_id IN (" + placeholders + ") "
                        "AND season_id IN (" + season_placeholders + ")"), (*batch, *planned))
                    counts["season_records"] += cursor.rowcount
                for table, column, key in (
                    ("venom_bot_state", "id", "bot_states"),
                    ("venom_competitors", "id", "competitors"),
                    ("venom_activity", "bot_id", "activity_events"),
                ):
                    cursor.execute(self._sql("DELETE FROM " + table + " WHERE " + column +
                                             " IN (" + placeholders + ")"), batch)
                    counts[key] += cursor.rowcount
        # Keep one fixed checkpoint row, not an ever-growing completed history.
        # Clearing only after every page commits also makes a last-page crash
        # safely replayable without changing the planned season membership.
        with self.transaction() as cursor:
            cursor.execute(self._sql("UPDATE venom_community_meta SET value_json=? WHERE name=?"),
                           (_json({"pending_season_ids": []}), self.RETIREMENT_PLAN))
        return counts

    def register_many(self, profiles, now, capacity=5):
        rows = list(profiles)
        if not rows:
            return
        with self.transaction() as cursor:
            sql = "INSERT INTO venom_competitors(id,kind,name,tamer,profile_json,energy,energy_at) VALUES (?,?,?,?,?,?,?)"
            if self.database.driver == "mysql":
                sql += " ON DUPLICATE KEY UPDATE kind=VALUES(kind),name=VALUES(name),tamer=VALUES(tamer),profile_json=VALUES(profile_json)"
            else:
                sql += " ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,name=excluded.name,tamer=excluded.tamer,profile_json=excluded.profile_json"
            cursor.executemany(self._sql(sql), [(p["id"], p.get("kind", "bot"), p.get("name", p["id"]),
                                               p.get("tamer", ""), _json(p), capacity, now) for p in rows])

    def profiles(self):
        rows, after = [], ""
        while True:
            batch = self.profiles_batch(after)
            if not batch:
                return rows
            rows.extend(batch)
            after = batch[-1]["id"]

    def _json_batch(self, table, column, after_id, limit):
        if not isinstance(after_id, str) or len(after_id) > 64:
            raise ValueError("Choose a valid saved-record cursor.")
        limit = max(1, min(200, int(limit)))
        # Table and column are fixed private-call constants, never client input.
        with self.transaction() as cursor:
            cursor.execute(self._sql(f"SELECT id,{column} FROM {table} WHERE id>? ORDER BY id LIMIT ?"), (after_id, limit))
            raw = cursor.fetchall()
        # Parsing a large JSON page must not hold the SQL connection/lease row
        # lock and prevent the independent startup heartbeat from renewing.
        rows = []
        for ident, value in raw:
            try:
                decoded = json.loads(value)
                if not isinstance(decoded, dict):
                    raise ValueError("Saved record must be an object.")
            except (ValueError, TypeError) as exc:
                raise DatabaseError(f"Saved record {ident} in {table} is invalid; no saved progress was changed.") from exc
            decoded["id"] = ident
            rows.append(decoded)
        return rows

    def profiles_batch(self, after_id="", limit=200):
        return self._json_batch("venom_competitors", "profile_json", after_id, limit)

    def competitor(self, participant_id, cursor=None):
        if cursor is None:
            with self.transaction() as owned:
                return self.competitor(participant_id, owned)
        cursor.execute(self._sql("SELECT id,kind,name,tamer,career_wins,career_losses,career_rating,"
                                 "digirubies,energy,energy_at,last_attack FROM venom_competitors WHERE id=?"), (participant_id,))
        row = cursor.fetchone()
        if not row:
            raise GameError("That competitor is not registered.")
        keys = ("id", "kind", "name", "tamer", "career_wins", "career_losses", "career_rating",
                "digirubies", "energy", "energy_at", "last_attack")
        return dict(zip(keys, row))

    @staticmethod
    def energy(record, now, capacity, refill_seconds):
        current = min(capacity, max(0, int(record["energy"])))
        elapsed = max(0, now - record["energy_at"])
        gained = int(elapsed // refill_seconds)
        current = min(capacity, current + gained)
        stamp = now if current == capacity else record["energy_at"] + gained * refill_seconds
        return current, stamp

    def configure_ranked_schedule(self, season_seconds, season_anchor):
        schedule = {"season_seconds": season_seconds, "season_anchor": season_anchor}
        with self.transaction() as cursor:
            cursor.execute("SELECT value_json FROM venom_community_meta WHERE name='ranked_schedule'")
            old = cursor.fetchone()
            if old and json.loads(old[0]) != schedule:
                raise GameError("The saved Battle Park season clock differs from this server configuration. "
                                "Restore season_seconds and season_anchor; changing an existing season clock requires an explicit migration.")
            if not old:
                cursor.execute(self._sql("INSERT INTO venom_community_meta(name,value_json) VALUES ('ranked_schedule',?)"), (_json(schedule),))

    def _season_rules(self, cursor, season_id):
        cursor.execute(self._sql("SELECT value_json FROM venom_community_meta WHERE name=?"), (f"season_rules:{season_id}",))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else {}

    def season(self, season_id, starts_at, ends_at, now, reward_for, rules=None):
        """Close all unfinished past seasons and award wallets in one transaction."""
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT id FROM venom_ranked_seasons WHERE status='active' AND ends_at<=? ORDER BY id"), (now,))
            expired = [int(row[0]) for row in cursor.fetchall()]
            for old_id in expired:
                frozen = self._season_rules(cursor, old_id)
                cursor.execute(self._sql("SELECT participant_id,points,wins,losses,grade FROM venom_ranked_records "
                                         "WHERE season_id=? AND wins+losses>0 ORDER BY points DESC,wins DESC,losses ASC,participant_id ASC"), (old_id,))
                standings = cursor.fetchall()
                cursor.execute(self._sql("SELECT DISTINCT attacker_id FROM venom_ranked_matches WHERE season_id=? AND ranked=1"), (old_id,))
                eligible = {row[0] for row in cursor.fetchall()}
                for rank, row in enumerate(standings, 1):
                    participant_id, points, wins, losses, grade = row
                    cursor.execute(self._sql("UPDATE venom_ranked_records SET final_rank=? WHERE season_id=? AND participant_id=?"),
                                   (rank, old_id, participant_id))
                    if participant_id not in eligible:
                        continue
                    cursor.execute(self._sql("SELECT amount FROM venom_ranked_rewards WHERE season_id=? AND participant_id=?"),
                                   (old_id, participant_id))
                    if cursor.fetchone():
                        continue
                    if frozen.get("grades") and frozen.get("placement_rewards"):
                        placements = frozen["placement_rewards"]
                        placement = next((r["digirubies"] for r in placements if rank <= r["rank_max"]), placements[-1]["digirubies"])
                        earned_grade = frozen["grades"][max(0, min(len(frozen["grades"]) - 1, grade))]
                        amount = max(0, int(placement + earned_grade["digirubies"]))
                    else:
                        amount = max(0, int(reward_for(rank, points, grade)))
                    cursor.execute(self._sql("INSERT INTO venom_ranked_rewards(season_id,participant_id,amount,final_rank,awarded_at) VALUES (?,?,?,?,?)"),
                                   (old_id, participant_id, amount, rank, now))
                    cursor.execute(self._sql("UPDATE venom_competitors SET digirubies=digirubies+? WHERE id=?"), (amount, participant_id))
                cursor.execute(self._sql("UPDATE venom_ranked_seasons SET status='closed' WHERE id=?"), (old_id,))
            cursor.execute(self._sql("SELECT id,starts_at,ends_at,status FROM venom_ranked_seasons WHERE id=?"), (season_id,))
            found = cursor.fetchone()
            if not found:
                cursor.execute(self._sql("INSERT INTO venom_ranked_seasons(id,starts_at,ends_at,status) VALUES (?,?,?,'active')"),
                               (season_id, starts_at, ends_at))
                found = (season_id, starts_at, ends_at, "active")
            saved_rules = self._season_rules(cursor, season_id)
            if not saved_rules and rules is not None:
                saved_rules = rules
                cursor.execute(self._sql("INSERT INTO venom_community_meta(name,value_json) VALUES (?,?)"),
                               (f"season_rules:{season_id}", _json(saved_rules)))
            return dict(zip(("id", "starts_at", "ends_at", "status"), found), rules=saved_rules)

    def seasons(self, limit=20):
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT s.id,s.starts_at,s.ends_at,s.status,COUNT(r.participant_id) "
                                     "FROM venom_ranked_seasons s LEFT JOIN venom_ranked_records r ON r.season_id=s.id "
                                     "GROUP BY s.id,s.starts_at,s.ends_at,s.status ORDER BY s.id DESC LIMIT ?"), (max(1, min(100, int(limit))),))
            return [dict(zip(("id", "starts_at", "ends_at", "status", "competitors"), row)) for row in cursor.fetchall()]

    def standings(self, season_id=None, career=False):
        with self.transaction() as cursor:
            if career:
                cursor.execute("SELECT id,name,kind,tamer,career_rating,career_wins,career_losses,career_rating,0,0,NULL "
                               "FROM venom_competitors WHERE career_wins+career_losses>0 "
                               "ORDER BY career_rating DESC,career_wins DESC,career_losses ASC,id ASC")
            else:
                cursor.execute(self._sql("SELECT c.id,c.name,c.kind,c.tamer,r.points,r.wins,r.losses,c.career_rating,r.grade,r.promotion_pending,r.final_rank "
                                         "FROM venom_ranked_records r JOIN venom_competitors c ON c.id=r.participant_id "
                                         "WHERE r.season_id=? AND r.wins+r.losses>0 "
                                         "ORDER BY r.points DESC,r.wins DESC,r.losses ASC,c.id ASC"), (season_id,))
            keys = ("id", "name", "kind", "tamer", "points", "wins", "losses", "career_rating", "grade_index", "promotion_pending")
            # Final placements describe the competitors present at settlement.
            # Removing a retired profile must not promote historical opponents
            # on screen or misrepresent the placement used for their reward.
            return [dict(zip(keys, row), rank=int(row[10]) if row[10] is not None else rank)
                    for rank, row in enumerate(cursor.fetchall(), 1)]

    def candidate_records(self, participant_ids, season_id):
        ids = list(participant_ids)
        if not ids:
            return {}
        with self.transaction() as cursor:
            placeholders = ",".join("?" for _ in ids)
            cursor.execute(self._sql("SELECT c.id,c.career_rating,COALESCE(r.points,0),COALESCE(r.wins,0),"
                                     "COALESCE(r.losses,0),COALESCE(r.grade,0),COALESCE(r.promotion_pending,0) "
                                     "FROM venom_competitors c LEFT JOIN venom_ranked_records r ON r.participant_id=c.id AND r.season_id=? "
                                     "WHERE c.id IN (" + placeholders + ")"), (season_id, *ids))
            keys = ("id", "career_rating", "points", "wins", "losses", "grade_index", "promotion_pending")
            return {row[0]: dict(zip(keys, row)) for row in cursor.fetchall()}

    def entry_counts(self, participant_id, season_id):
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT COUNT(*) FROM venom_ranked_matches WHERE season_id=? AND attacker_id=? AND ranked=1"),
                           (season_id, participant_id))
            attacks = int(cursor.fetchone()[0])
            cursor.execute(self._sql("SELECT COUNT(*) FROM venom_ranked_matches WHERE season_id=? AND defender_id=? AND ranked=1"),
                           (season_id, participant_id))
            return {"attacks": attacks, "defenses": int(cursor.fetchone()[0]), "reward_eligible": attacks > 0}

    def record(self, participant_id, season_id, cursor=None):
        if cursor is None:
            with self.transaction() as owned:
                return self.record(participant_id, season_id, owned)
        cursor.execute(self._sql("SELECT points,wins,losses,final_rank,grade,promotion_pending FROM venom_ranked_records WHERE season_id=? AND participant_id=?"),
                       (season_id, participant_id))
        row = cursor.fetchone()
        return dict(zip(("points", "wins", "losses", "final_rank", "grade_index", "promotion_pending"), row or (0, 0, 0, None, 0, 0)))

    def match(self, match_id, cursor=None):
        if cursor is None:
            with self.transaction() as owned:
                return self.match(match_id, owned)
        cursor.execute(self._sql("SELECT result_json FROM venom_ranked_matches WHERE id=?"), (match_id,))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None

    def commit_match(self, result, now, capacity, refill_seconds, cooldown, win_points, loss_points, grades, opponent_cooldown=60):
        """Authoritative outcome, two rankings, stamina and rival history commit together."""
        with self.transaction() as cursor:
            previous = self.match(result["id"], cursor)
            if previous:
                return {**previous, "duplicate": True}
            attacker = self.competitor(result["attacker_id"], cursor)
            defender = self.competitor(result["defender_id"], cursor)
            if now - attacker["last_attack"] < cooldown:
                raise GameError("Please wait a moment before starting another arena battle.")
            if result["ranked"]:
                cursor.execute(self._sql("SELECT status,ends_at FROM venom_ranked_seasons WHERE id=?"), (result["season_id"],))
                season = cursor.fetchone()
                if not season or season[0] != "active" or now >= season[1]:
                    raise GameError("The season has ended. Refresh the Battle Park.")
                cursor.execute(self._sql("SELECT MAX(played_at) FROM venom_ranked_matches WHERE attacker_id=? AND defender_id=? AND ranked=1"),
                               (attacker["id"], defender["id"]))
                last_pair = cursor.fetchone()[0]
                if last_pair is not None and now - last_pair < opponent_cooldown:
                    raise GameError("That opponent is on a short rematch cooldown. Choose another rival.")
                energy, energy_at = self.energy(attacker, now, capacity, refill_seconds)
                if energy < 1:
                    raise GameError("Battle Park energy is recovering. Rival challenges remain available.")
                cursor.execute(self._sql("UPDATE venom_competitors SET energy=?,energy_at=? WHERE id=?"),
                               (energy - 1, energy_at, attacker["id"]))
                expected = 1 / (1 + 10 ** ((defender["career_rating"] - attacker["career_rating"]) / 400))
                delta = round(24 * ((1 if result["attacker_won"] else 0) - expected))
                result["rating_delta"] = {"attacker": delta, "defender": -delta}
                result["points"] = {}
                for side, competitor, rating_delta in (("attacker", attacker, delta), ("defender", defender, -delta)):
                    won = competitor["id"] == result["winner_id"]
                    record = self.record(competitor["id"], result["season_id"], cursor)
                    after = max(0, record["points"] + (win_points if won else -loss_points))
                    result["points"][side] = {"before": record["points"], "after": after, "delta": after - record["points"]}
                    grade = record["grade_index"]
                    pending = bool(record["promotion_pending"])
                    promoted = side == "attacker" and won and pending and grade + 1 < len(grades) and after >= grades[grade + 1]["points"]
                    if promoted:
                        grade += 1
                    pending = grade + 1 < len(grades) and after >= grades[grade + 1]["points"]
                    if side == "attacker":
                        result["promotion"] = {"was_pending": bool(record["promotion_pending"]), "promoted": promoted,
                                               "grade": grades[grade]["name"], "pending": pending}
                    sql = "INSERT INTO venom_ranked_records(season_id,participant_id,points,wins,losses,grade,promotion_pending) VALUES (?,?,?,?,?,?,?)"
                    if self.database.driver == "mysql":
                        sql += " ON DUPLICATE KEY UPDATE points=VALUES(points),wins=VALUES(wins),losses=VALUES(losses),grade=VALUES(grade),promotion_pending=VALUES(promotion_pending)"
                    else:
                        sql += " ON CONFLICT(season_id,participant_id) DO UPDATE SET points=excluded.points,wins=excluded.wins,losses=excluded.losses,grade=excluded.grade,promotion_pending=excluded.promotion_pending"
                    cursor.execute(self._sql(sql), (result["season_id"], competitor["id"], after,
                                                   record["wins"] + int(won), record["losses"] + int(not won), grade, int(pending)))
                    cursor.execute(self._sql("UPDATE venom_competitors SET career_wins=career_wins+?,career_losses=career_losses+?,"
                                             "career_rating=? WHERE id=?"),
                                   (int(won), int(not won), max(0, competitor["career_rating"] + rating_delta), competitor["id"]))
            cursor.execute(self._sql("UPDATE venom_competitors SET last_attack=? WHERE id=?"), (now, attacker["id"]))
            for left, right in ((attacker, defender), (defender, attacker)):
                if left["kind"] == "player":
                    self._rival_record(cursor, left["id"], right["id"], result, now)
            # Full animation frames travel only in the response. The permanent
            # idempotency ledger keeps the authoritative compact outcome.
            summary = {key: value for key, value in result.items() if key not in ("replay", "own")}
            cursor.execute(self._sql("INSERT INTO venom_ranked_matches(id,season_id,attacker_id,defender_id,winner_id,ranked,played_at,result_json) "
                                     "VALUES (?,?,?,?,?,?,?,?)"),
                           (result["id"], result["season_id"], attacker["id"], defender["id"], result["winner_id"],
                            int(result["ranked"]), now, _json(summary)))
            return result

    def _rival_record(self, cursor, player_id, rival_id, result, now):
        cursor.execute(self._sql("SELECT match_id FROM venom_rival_matches WHERE player_id=? AND match_id=?"), (player_id, result["id"]))
        if cursor.fetchone():
            return False
        cursor.execute(self._sql("INSERT INTO venom_rival_matches(player_id,match_id) VALUES (?,?)"), (player_id, result["id"]))
        cursor.execute(self._sql("SELECT wins,losses,last_match FROM venom_rival_history WHERE player_id=? AND rival_id=?"), (player_id, rival_id))
        old = cursor.fetchone()
        if old and old[2] == result["id"]:
            return
        won = result["winner_id"] == player_id
        if old:
            cursor.execute(self._sql("UPDATE venom_rival_history SET wins=?,losses=?,last_at=?,last_match=? WHERE player_id=? AND rival_id=?"),
                           (old[0] + int(won), old[1] + int(not won), now, result["id"], player_id, rival_id))
        else:
            cursor.execute(self._sql("INSERT INTO venom_rival_history(player_id,rival_id,wins,losses,last_at,last_match) VALUES (?,?,?,?,?,?)"),
                           (player_id, rival_id, int(won), int(not won), now, result["id"]))

    def rival_record(self, player_id, bot_id, result):
        # commit_match already records player opponents. A permanent match key
        # also makes a delayed/reordered integration callback exactly once.
        with self.transaction() as cursor:
            return self._rival_record(cursor, player_id, bot_id, result, result.get("played_at", time.time()))

    def rival_history(self, player_id, limit=100):
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT h.rival_id,c.name,c.kind,c.tamer,h.wins,h.losses,h.last_at,h.last_match "
                                     "FROM venom_rival_history h JOIN venom_competitors c ON c.id=h.rival_id "
                                     "WHERE h.player_id=? ORDER BY h.last_at DESC,h.rival_id ASC LIMIT ?"),
                           (player_id, max(1, min(100, int(limit)))))
            keys = ("id", "name", "kind", "tamer", "wins", "losses", "last_at", "last_match")
            return [dict(zip(keys, row)) for row in cursor.fetchall()]

    def recent_matches(self, participant_id, limit=20):
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT result_json FROM venom_ranked_matches WHERE attacker_id=? OR defender_id=? "
                                     "ORDER BY played_at DESC,id DESC LIMIT ?"), (participant_id, participant_id, max(1, min(100, int(limit)))))
            return [json.loads(row[0]) for row in cursor.fetchall()]

    def ranked_totals(self):
        """Reconcile bot checkpoints with matches committed before a crash."""
        result = {}
        with self.transaction() as cursor:
            for side in ("attacker", "defender"):
                column = side + "_id"
                cursor.execute("SELECT " + column + ","
                               "SUM(CASE WHEN ranked=1 AND winner_id=" + column + " THEN 1 ELSE 0 END),"
                               "SUM(CASE WHEN ranked=1 AND winner_id<>" + column + " THEN 1 ELSE 0 END),"
                               "SUM(CASE WHEN ranked=1 THEN 1 ELSE 0 END),"
                               "SUM(CASE WHEN ranked=0 AND winner_id=" + column + " THEN 1 ELSE 0 END),"
                               "SUM(CASE WHEN ranked=0 AND winner_id<>" + column + " THEN 1 ELSE 0 END) "
                               "FROM venom_ranked_matches WHERE " + column + " LIKE 'bot:%' GROUP BY " + column)
                for ident, wins, losses, entries, friendly_wins, friendly_losses in cursor.fetchall():
                    row = result.setdefault(ident, {"ranked_wins": 0, "ranked_losses": 0, "ranked_started": 0,
                                                    "rival_wins": 0, "rival_losses": 0})
                    row["ranked_wins"] += int(wins)
                    row["ranked_losses"] += int(losses)
                    if side == "attacker":
                        row["ranked_started"] += int(entries)
                    row["rival_wins"] += int(friendly_wins)
                    row["rival_losses"] += int(friendly_losses)
        return result

    bot_match_counters = ranked_totals

    def season_info(self, season_id):
        with self.transaction() as cursor:
            cursor.execute(self._sql("SELECT id,starts_at,ends_at,status FROM venom_ranked_seasons WHERE id=?"), (season_id,))
            row = cursor.fetchone()
            return dict(zip(("id", "starts_at", "ends_at", "status"), row), rules=self._season_rules(cursor, season_id)) if row else None

    def bot_load_all(self):
        rows, after = [], ""
        while True:
            batch = self.bot_load_batch(after)
            if not batch:
                return rows
            rows.extend(batch)
            after = batch[-1]["id"]

    def bot_load_batch(self, after_id="", limit=200):
        """Read one bounded durable page without deleting or rewriting history."""
        return self._json_batch("venom_bot_state", "state_json", after_id, limit)

    def bot_save_batch(self, rows):
        rows = list(rows)
        if not rows:
            return
        now = time.time()
        sql = "INSERT INTO venom_bot_state(id,state_json,updated_at) VALUES (?,?,?)"
        if self.database.driver == "mysql":
            sql += " ON DUPLICATE KEY UPDATE state_json=VALUES(state_json),updated_at=VALUES(updated_at)"
        else:
            sql += " ON CONFLICT(id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at"
        with self.transaction() as cursor:
            cursor.executemany(self._sql(sql), [(row["id"], _json(row), now) for row in rows])

    @staticmethod
    def _activity_time(now):
        now = time.time() if now is None else float(now)
        if not math.isfinite(now):
            raise ValueError("Choose a finite activity timestamp.")
        return now

    @staticmethod
    def _activity_value(value):
        # Walking distance is deliberately fractional. Integer-only telemetry
        # would silently lose part of every movement increment.
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Choose a finite numeric activity increment.")
        return max(0, value)

    def _prune_activity(self, cursor, now):
        cutoff = now - self.ACTIVITY_WINDOW_SECONDS
        # Counter buckets expire conservatively at their start time: telemetry
        # never includes an event older than 12 hours. Minute precision can
        # retire the rest of that minute less than one minute early.
        cursor.execute(self._sql("DELETE FROM venom_activity_windows WHERE bucket_at<=?"), (cutoff,))
        cursor.execute(self._sql("DELETE FROM venom_activity WHERE happened_at<=?"), (cutoff,))
        cursor.execute(self._sql("SELECT id FROM venom_activity_batches WHERE happened_at<=? "
                                 "ORDER BY happened_at,id LIMIT ?"),
                       (cutoff, self.ACTIVITY_RECEIPT_PRUNE_BATCH))
        expired = [row[0] for row in cursor.fetchall()]
        if expired:
            cursor.execute(self._sql("DELETE FROM venom_activity_batches WHERE id IN (" +
                                     ",".join("?" for _ in expired) + ")"), tuple(expired))
        return len(expired)

    def maintain_activity(self, now=None, drain=False):
        """Expire telemetry even when idle, in bounded receipt transactions."""
        now = self._activity_time(now)
        removed = 0
        while True:
            with self.transaction() as cursor:
                count = self._prune_activity(cursor, now)
            removed += count
            if not drain or count < self.ACTIVITY_RECEIPT_PRUNE_BATCH:
                return removed

    def add_activity_batch(self, events, buckets, batch_id, batch_at, now=None):
        """Commit timestamped rolling telemetry once, without permanent receipts.

        A retry must retain its original batch ID, creation time and payload.
        Once that time expires the whole retry is ignored, including after its
        receipt has been pruned. Activity is independent of gameplay saves.
        """
        now = self._activity_time(now)
        batch_at = self._activity_time(batch_at)
        if not isinstance(batch_id, str) or not batch_id or len(batch_id) > 64:
            raise ValueError("Choose a valid activity batch ID.")
        cutoff = now - self.ACTIVITY_WINDOW_SECONDS
        normalized = {}
        for bucket in buckets:
            at = int(self._activity_time(bucket["at"]))
            at -= at % self.ACTIVITY_PRECISION_SECONDS
            if not cutoff < at <= now:
                continue
            counts = normalized.setdefault(at, {})
            for key, value in bucket.get("counters", {}).items():
                if not isinstance(key, str) or not key or len(key) > 64:
                    raise ValueError("Choose a valid activity counter name.")
                value = self._activity_value(value)
                if value:
                    counts[key] = counts.get(key, 0) + value
        events = [dict(event) for event in events]
        with self.transaction() as cursor:
            self._prune_activity(cursor, now)
            if not cutoff < batch_at <= now:
                return False
            cursor.execute(self._sql("SELECT id FROM venom_activity_batches WHERE id=?"), (batch_id,))
            if cursor.fetchone():
                return False
            fresh_events = {}
            for event in events:
                event.setdefault("id", uuid.uuid4().hex)
                event.setdefault("at", batch_at)
                at = self._activity_time(event["at"])
                if not cutoff < at <= now:
                    continue
                cursor.execute(self._sql("SELECT id FROM venom_activity WHERE id=?"), (event["id"],))
                if not cursor.fetchone():
                    fresh_events[event["id"]] = (event, at)
            if not fresh_events and not any(normalized.values()):
                return False
            cursor.execute(self._sql("INSERT INTO venom_activity_batches(id,happened_at) VALUES (?,?)"),
                           (batch_id, batch_at))
            for event, at in fresh_events.values():
                cursor.execute(self._sql("INSERT INTO venom_activity(id,bot_id,kind,happened_at,event_json) VALUES (?,?,?,?,?)"),
                               (event["id"], event.get("bot_id", ""), event.get("kind", "activity"), at, _json(event)))
            for at, counts in sorted(normalized.items()):
                if not counts:
                    continue
                cursor.execute(self._sql("SELECT counters_json FROM venom_activity_windows WHERE bucket_at=?"), (at,))
                existing = cursor.fetchone()
                combined = json.loads(existing[0]) if existing else {}
                for key, value in counts.items():
                    combined[key] = self._activity_value(combined.get(key, 0)) + value
                if existing:
                    cursor.execute(self._sql("UPDATE venom_activity_windows SET counters_json=? WHERE bucket_at=?"),
                                   (_json(combined), at))
                else:
                    cursor.execute(self._sql("INSERT INTO venom_activity_windows(bucket_at,counters_json) VALUES (?,?)"),
                                   (at, _json(combined)))
            cursor.execute(self._sql("SELECT id FROM venom_activity ORDER BY happened_at DESC,id DESC LIMIT ?"),
                           (EVENT_LIMIT,))
            keep = [row[0] for row in cursor.fetchall()]
            if keep:
                cursor.execute(self._sql("DELETE FROM venom_activity WHERE id NOT IN (" + ",".join("?" for _ in keep) + ")"), tuple(keep))
            return True

    def add_events(self, events, counters=None):
        """Compatibility adapter; new writers supply timestamped counter buckets."""
        events = [dict(event) for event in events]
        now = self._activity_time(None)
        ids = [str(event["id"]) for event in events if event.get("id")]
        batch_id = hashlib.sha256(_json([sorted(ids), sorted((counters or {}).items())]).encode()).hexdigest() if ids else uuid.uuid4().hex
        batch_at = max((self._activity_time(event.get("at", now)) for event in events), default=now)
        return self.add_activity_batch(events, [{"at": batch_at, "counters": counters or {}}],
                                       batch_id, batch_at, now=now)

    def activity_snapshot(self, now=None, limit=100):
        now = self._activity_time(now)
        cutoff = now - self.ACTIVITY_WINDOW_SECONDS
        with self.transaction() as cursor:
            self._prune_activity(cursor, now)
            cursor.execute(self._sql("SELECT event_json FROM venom_activity WHERE happened_at>? AND happened_at<=? "
                                     "ORDER BY happened_at DESC,id DESC LIMIT ?"),
                           (cutoff, now, max(1, min(EVENT_LIMIT, int(limit)))))
            events = [json.loads(row[0]) for row in cursor.fetchall()]
            cursor.execute(self._sql("SELECT bucket_at,counters_json FROM venom_activity_windows "
                                     "WHERE bucket_at>? AND bucket_at<=? ORDER BY bucket_at"), (cutoff, now))
            buckets = [{"at": int(at), "counters": json.loads(raw)} for at, raw in cursor.fetchall()]
            counters = {}
            for bucket in buckets:
                for key, value in bucket["counters"].items():
                    counters[key] = counters.get(key, 0) + self._activity_value(value)
            cursor.execute("SELECT value_json FROM venom_community_meta WHERE name='activity_window_v1'")
            marker = cursor.fetchone()
            tracking_since = json.loads(marker[0])["tracking_since"] if marker else now
            return {"events": events, "counters": counters, "buckets": buckets,
                    "window_seconds": self.ACTIVITY_WINDOW_SECONDS, "window_start": cutoff,
                    "as_of": now, "tracking_since": tracking_since,
                    "precision_seconds": self.ACTIVITY_PRECISION_SECONDS}

    def activity(self, limit=100):
        snapshot = self.activity_snapshot(limit=limit)
        return {"events": snapshot["events"], "counters": snapshot["counters"]}
