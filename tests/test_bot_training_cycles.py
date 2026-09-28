"""Earned-team rotation and persisted-world regressions for tamer rivals.

Mature saves are explicit fixtures. Any scan/capture in the principal migration
case is earned through real GameEngine battles, and the continuous-loop test
uses the real scheduler with shortened exploration/action timers only.
"""
from __future__ import annotations

import copy
from pathlib import Path

from venom.common.game import GameEngine, GameError
from venom.server.bots import BotManager
from test_bots import MemoryStore


ROOT = Path(__file__).resolve().parents[1]


class RankedRecorder:
    """Observe scheduler participation; the independent SQL benchmark tests ranked combat."""
    def __init__(self):
        self.profiles = {}
        self.matches = []

    def register_many(self, profiles):
        self.profiles.update({profile["id"]: copy.deepcopy(profile) for profile in profiles})

    def register_participant(self, ident, profile):
        self.profiles[ident] = copy.deepcopy(profile)

    def start_match(self, ident):
        opponent = next(key for key in self.profiles if key != ident)
        result = {"id": f"cycle-match-{len(self.matches)}", "attacker_id": ident,
                  "defender_id": opponent, "winner_id": ident, "ranked": True}
        self.matches.append(result)
        return result


def make_manager(count=2, levels=(1, 1), store=None, now=0):
    engine = GameEngine(ROOT, seed=501)
    engine.maps = dict(list(engine.maps.items())[:len(levels)])
    engine.starters = ["agumon"]
    for area, level in zip(engine.maps.values(), levels):
        area["level"] = level
        engine._pools[area["id"]] = (["agumon"], [])
    manager = BotManager(engine, store or MemoryStore(), RankedRecorder(),
                         {"count": count, "seed": 842, "action_interval": .1,
                          "explore_seconds": 2, "min_dwell": 30, "max_dwell": 60,
                          "save_interval": 10000, "tick_budget_ms": 100})
    manager.initialize(now)
    return manager


def owned(bot):
    return {member["uid"]: member for member in bot["state"]["party"] + bot["state"]["storage"]}


def move_to(manager, bot, map_id):
    old = bot["state"]["map_id"]
    manager._execute(bot, "travel", {"map_id": map_id})
    manager.by_map[old].discard(bot["id"])
    manager.by_map[map_id].add(bot["id"])


def earn_full_scan(manager, bot, species="agumon"):
    for _ in range(12):
        if bot["state"]["scan"].get(species, 0) >= 100:
            return
        manager._execute(bot, "encounter", {})
        for _ in range(500):
            if not bot["state"].get("battle"):
                break
            manager._execute(bot, "battle", manager._battle_action(bot))
        assert not bot["state"].get("battle"), "Controlled real battle did not terminate"
        assert not bot["state"]["in_lab"], "Mature fixture unexpectedly lost its low-level scan battle"
    raise AssertionError("Expected real low-level victories to earn 100% scan data")


def test_mature_full_party_banks_veterans_and_trains_a_genuinely_earned_recruit():
    manager = make_manager()
    bot = manager.bots["bot:00001"]
    bot["state"]["party"] = [manager.engine._monster("agumon", level=60, abi=30, cam=75)
                               for _ in range(6)]
    manager.engine._refresh(bot["state"])
    earn_full_scan(manager, bot)
    assert bot["stats"]["wild_wins"] > 0 and bot["stats"]["scans"] >= 5
    veterans = copy.deepcopy(owned(bot))
    manager._execute(bot, "digilab", {"action": "enter"})
    manager._materialize(bot)
    manager._manage_party(bot)
    assert bot["stats"]["materialized"] >= 1
    assert bot["state"]["scan"]["agumon"] == 0
    active = {member["uid"] for member in bot["state"]["party"]}
    assert active and active.isdisjoint(veterans)
    assert max(member["level"] for member in bot["state"]["party"]) == 1
    banked = {member["uid"]: member for member in bot["state"]["storage"]}
    assert set(veterans) <= set(banked)
    for uid, veteran in veterans.items():
        # Healing may restore HP/SP, but identity and earned development survive.
        for key in ("species_id", "level", "xp", "abi", "cam", "history"):
            assert banked[uid][key] == veteran[key]
    assert set(bot["runtime"]["training_uids"]) == active


def test_duplicate_recruit_still_requires_complete_scan_data():
    manager = make_manager()
    bot = manager.bots["bot:00001"]
    bot["state"]["party"] = [manager.engine._monster("agumon", level=60) for _ in range(6)]
    manager._execute(bot, "digilab", {"action": "enter"})
    bot["state"]["scan"]["agumon"] = 99
    before = set(owned(bot))
    manager._materialize(bot)
    assert set(owned(bot)) == before
    assert bot["stats"]["materialized"] == 0
    assert bot["state"]["scan"]["agumon"] == 99
    bot["state"]["scan"]["agumon"] = 100
    manager._materialize(bot)
    assert len(set(owned(bot)) - before) == 1
    assert bot["state"]["scan"]["agumon"] == 0


def test_mature_rivals_can_repopulate_undercrowded_low_level_maps():
    manager = make_manager(count=12, levels=(1, 20, 50, 60))
    high_map = max(manager.engine.maps, key=lambda mid: manager.engine.maps[mid]["level"])
    for bot in manager.bots.values():
        bot["state"]["party"] = [manager.engine._monster("agumon", level=60)]
        move_to(manager, bot, high_map)
    assert len(manager.by_map[high_map]) == 12
    for bot in manager.bots.values():
        manager._relocate(bot, 100)
    low = min(manager.engine.maps, key=lambda mid: manager.engine.maps[mid]["level"])
    assert manager.by_map[low], "Level-based filtering abandoned every low-level field"
    assert len(manager.by_map[high_map]) < 12
    for bot in manager.bots.values():
        assert bot["runtime"]["leave_at"] >= 130


def test_coverage_retains_a_solo_veteran_and_banks_the_earned_young_recruit():
    manager = make_manager(count=12, levels=(1, 20, 50, 60))
    high_map = next(mid for mid, area in manager.engine.maps.items() if area["level"] == 50)
    residents = sorted(manager.by_map[high_map])
    bot = manager.bots[residents[0]]
    # Existing high-sector save: the other residents have started young teams.
    # This resident is the last one capable of maintaining that sector's cover.
    for ident in residents[1:]:
        manager.bots[ident]["state"]["party"] = [manager.engine._monster("agumon", level=1)]
    bot["state"]["party"] = [manager.engine._monster("agumon", level=52)]
    veteran_uid = bot["state"]["party"][0]["uid"]
    # The same battle/scan rules produce a recruit; a weak second field slot
    # must not make the viable solo veteran fail the coverage selection.
    low_map = next(mid for mid, area in manager.engine.maps.items() if area["level"] == 1)
    move_to(manager, bot, low_map)
    earn_full_scan(manager, bot)
    move_to(manager, bot, high_map)
    manager._execute(bot, "digilab", {"action": "enter"})
    manager._materialize(bot)
    before = copy.deepcopy(owned(bot))
    recruits = set(before) - {veteran_uid}
    assert recruits and manager._coverage_guard(bot)
    manager._manage_party(bot)
    assert [member["uid"] for member in bot["state"]["party"]] == [veteran_uid]
    assert recruits <= {member["uid"] for member in bot["state"]["storage"]}
    assert owned(bot) == before
    assert bot["runtime"]["coverage_duty"]
    assert not bot["runtime"]["relocate"]


def test_training_plan_and_retained_partner_development_survive_restart():
    store = MemoryStore()
    manager = make_manager(store=store)
    bot = manager.bots["bot:00001"]
    bot["state"]["party"] = [manager.engine._monster("agumon", level=60) for _ in range(3)]
    earn_full_scan(manager, bot)
    manager._execute(bot, "digilab", {"action": "enter"})
    manager._materialize(bot)
    manager._manage_party(bot)
    manager.flush(force=True, now=10)
    saved = copy.deepcopy(store.rows)
    restored = make_manager(store=store, now=1000)
    for ident, rival in restored.bots.items():
        assert owned(rival) == {member["uid"]: member for member in
                                saved[ident]["state"]["party"] + saved[ident]["state"]["storage"]}
        assert rival["stats"] == saved[ident]["stats"]
        for key in ("training_uids", "training_round", "training_goal",
                    "training_started_cycle", "training_start_wins"):
            assert rival["runtime"].get(key) == saved[ident]["runtime"].get(key)
    assert dict(restored.counters) == dict(manager.counters)


def test_full_soft_bank_retrains_through_eligible_evolution_without_deleting_partners(monkeypatch):
    manager = make_manager()
    bot = manager.bots["bot:00001"]
    state = bot["state"]
    state["party"] = [manager.engine._monster("agumon", level=60, abi=200, cam=100)
                      for _ in range(6)]
    state["storage"] = [manager.engine._monster("greymon", level=60, abi=200, cam=100)
                        for _ in range(48)]
    manager.engine._refresh(state)
    original_uids = set(owned(bot))
    evolved = []
    original_handle = manager.engine.handle
    def observe_handle(player, op, payload):
        if op == "evolve":
            member = player["party"][payload["party_index"]]
            assert any(route["eligible"] and route["to"] == payload["to"]
                       for route in manager.engine.evolution_options(member))
            evolved.append(member["uid"])
        return original_handle(player, op, payload)
    monkeypatch.setattr(manager.engine, "handle", observe_handle)
    bot["runtime"].update(phase="lab", phase_step=0, training_goal=12,
                          training_uids=[member["uid"] for member in state["party"]])
    for step in range(6):
        manager._lab_step(bot, 100 + step)
    assert evolved, "A full collection must still have a legal path to renewed training"
    assert set(owned(bot)) == original_uids
    assert any(owned(bot)[uid]["level"] == 1 for uid in evolved)
    assert len(owned(bot)) <= 54 and 1 <= len(state["party"]) <= 6
    assert bot["stats"]["materialized"] == 0


def test_full_bank_terminal_forms_can_use_canonical_devolution_without_prior_history():
    manager = make_manager()
    bot = manager.bots["bot:00001"]
    state = bot["state"]
    # Captured final forms have no evolution history. Their eligible engine
    # devolution routes must remain usable when the earned collection is full.
    state["party"] = [manager.engine._monster("beelzemonblastmode", level=60, abi=200, cam=100)
                      for _ in range(6)]
    state["storage"] = [manager.engine._monster("beelzemonblastmode", level=60, abi=200, cam=100)
                        for _ in range(48)]
    manager.engine._refresh(state)
    manager._execute(bot, "digilab", {"action": "enter"})
    original_uids = set(owned(bot))
    original_species = {uid: member["species_id"] for uid, member in owned(bot).items()}
    routes = manager.engine.evolution_options(state["party"][0])
    assert all(not member["history"] for member in owned(bot).values())
    assert any(route["eligible"] and route.get("devolve") for route in routes)
    assert not any(route["eligible"] and not route.get("devolve") for route in routes)
    bot["runtime"].update(training_uids=[member["uid"] for member in state["party"]],
                          training_goal=60, training_peak=60, training_start_wins=0)
    manager._evolve(bot)
    manager._manage_party(bot)
    assert set(owned(bot)) == original_uids
    changed = [member for uid, member in owned(bot).items()
               if member["species_id"] != original_species[uid]]
    assert len(changed) == 1 and changed[0]["level"] == 1
    assert changed[0]["species_id"] in {route["to"] for route in routes
                                        if route["eligible"] and route.get("devolve")}
    assert bot["stats"]["devolutions"] == 1
    assert bot["stats"]["materialized"] == 0


def test_repeated_real_training_keeps_ranked_scanning_care_and_shop_active():
    manager = make_manager(count=4)
    initial = {ident: set(owned(bot)) for ident, bot in manager.bots.items()}
    for bot in manager.bots.values():
        bot["state"]["inventory"]["hp_s"] = 0
        bot["state"]["inventory"]["sp_s"] = 0
    # 90 minutes of simulated time, with shortened action/exploration timers.
    # No XP, levels, scan data, results, or counters are injected by the test.
    for tick in range(1, 54001):
        manager.tick(tick / 10, .1, budget=1000)
    for ident, bot in manager.bots.items():
        assert initial[ident] <= set(owned(bot))
        stats = bot["stats"]
        assert stats["training_rotations"] >= 2
        assert stats["teams_trained"] >= 2
        for key in ("wild_wins", "ranked_started", "scans", "materialized", "level_ups",
                    "heals", "purchases", "party_swaps", "travels", "exploration_steps"):
            assert stats[key] > 0, (ident, key)
        assert stats["errors"] == 0
        assert len(owned(bot)) <= 54
        assert len(bot["state"]["party"]) <= 6
    assert manager.counters["evolutions"] + manager.counters["devolutions"] > 0
    assert len(manager.events) <= 100
    assert len(manager.heap) <= len(manager.bots) * 2


def test_mid_lab_checkpoint_persists_plan_and_peak_when_roster_does_not_change():
    store = MemoryStore()
    manager = make_manager(store=store)
    bot = manager.bots["bot:00001"]
    manager._execute(bot, "digilab", {"action": "enter"})
    manager.flush(force=True, now=1)
    original_party = copy.deepcopy(bot["state"]["party"])
    # These real Lab phases make only runtime changes for a sole Rookie: first
    # assign a training plan, then observe its peak while evolution is deferred.
    for phase_step in (2, 3):
        bot["runtime"].update(phase="lab", phase_step=phase_step)
        manager._lab_step(bot, 10 + phase_step)
        expected = {key: copy.deepcopy(value) for key, value in bot["runtime"].items()
                    if key.startswith("training_") or key.startswith("coverage_")}
        manager.flush(force=True, now=10 + phase_step)
        restored = make_manager(store=store, now=100)
        rival = restored.bots[bot["id"]]
        assert rival["state"]["party"] == original_party
        assert {key: rival["runtime"].get(key) for key in expected} == expected
    assert expected["training_peak"] == original_party[0]["level"]


def test_ranked_energy_wait_persists_cycle_without_a_match_or_party_change(monkeypatch):
    store = MemoryStore()
    manager = make_manager(store=store)
    bot = manager.bots["bot:00001"]
    manager.flush(force=True, now=1)
    old_stats, old_party = copy.deepcopy(bot["stats"]), copy.deepcopy(bot["state"]["party"])
    def exhausted(_ident):
        raise GameError("Battle stamina is recharging.")
    monkeypatch.setattr(manager.ranked, "start_match", exhausted)
    manager._ranked_step(bot, 10)
    manager.flush(force=True, now=10)
    restored = make_manager(store=store, now=100)
    rival = restored.bots[bot["id"]]
    assert rival["runtime"]["cycle"] == 1
    assert rival["runtime"]["phase"] == "explore"
    assert rival["runtime"]["walk_pending"]
    assert rival["runtime"]["ranked_wait_reason"] == "Battle stamina is recharging."
    assert rival["stats"] == old_stats and rival["state"]["party"] == old_party


def coverage_world():
    manager = make_manager(count=12, levels=(1, 20, 50, 60))
    low_map = next(mid for mid, area in manager.engine.maps.items() if area["level"] == 1)
    for bot in manager.bots.values():
        move_to(manager, bot, low_map)
    return manager, low_map


def prepare_banked_veteran(manager, bot):
    # Mature-save fixture, followed by genuinely earned scan and conversion.
    bot["state"]["party"] = [manager.engine._monster("agumon", level=62)]
    veteran_uid = bot["state"]["party"][0]["uid"]
    earn_full_scan(manager, bot)
    manager._execute(bot, "digilab", {"action": "enter"})
    manager._materialize(bot)
    recruit_uid = next(uid for uid in owned(bot) if uid != veteran_uid)
    manager._equip_party(bot, [recruit_uid])
    bot["runtime"].update(training_uids=[recruit_uid], training_round=1,
                          training_goal=20, training_peak=1,
                          training_start_wins=bot["stats"]["wild_wins"],
                          training_started_cycle=bot["runtime"]["cycle"])
    return veteran_uid, recruit_uid


def test_banked_veterans_reserve_distinct_underfilled_sectors_and_consume_arrival_reservations():
    manager, low_map = coverage_world()
    first, second = [manager.bots[ident] for ident in ("bot:00001", "bot:00002")]
    first_veteran, _ = prepare_banked_veteran(manager, first)
    second_veteran, _ = prepare_banked_veteran(manager, second)
    before = {bot["id"]: copy.deepcopy(owned(bot)) for bot in (first, second)}
    for bot, veteran in ((first, first_veteran), (second, second_veteran)):
        manager._manage_party(bot)
        assert bot["runtime"]["coverage_duty"]
        assert bot["runtime"]["relocate"]
        assert [member["uid"] for member in bot["state"]["party"]] == [veteran]
        assert bot["state"]["map_id"] == low_map, "Lab maintenance must not teleport the field actor"
        assert owned(bot) == before[bot["id"]]
    first_target = first["runtime"]["coverage_target"]
    second_target = second["runtime"]["coverage_target"]
    assert first_target != second_target
    assert manager.coverage_reservations[first_target] == {first["id"]}
    assert manager.coverage_reservations[second_target] == {second["id"]}
    manager._execute(first, "digilab", {"action": "return"})
    manager._relocate(first, 100, easier=True)
    assert first["state"]["map_id"] == first_target
    assert first["id"] in manager.by_map[first_target]
    assert not manager.coverage_reservations[first_target]
    assert "coverage_target" not in first["runtime"]
    assert manager.coverage_reservations[second_target] == {second["id"]}


def test_coverage_duty_deadline_restores_training_and_guarantees_a_rest_period():
    manager, _ = coverage_world()
    bot = manager.bots["bot:00001"]
    veteran_uid, recruit_uid = prepare_banked_veteran(manager, bot)
    manager._manage_party(bot)
    manager._execute(bot, "digilab", {"action": "return"})
    manager._relocate(bot, 100, easier=True)
    manager._execute(bot, "digilab", {"action": "enter"})
    assert manager._coverage_guard(bot)
    # Simulate restoring an overdue duty visit with no further victories. The
    # activity-cycle deadline must release it even when its map still needs help.
    bot["runtime"]["cycle"] = bot["runtime"]["coverage_started_cycle"] + 16
    before = copy.deepcopy(owned(bot))
    manager._manage_party(bot)
    assert not bot["runtime"]["coverage_duty"]
    assert [member["uid"] for member in bot["state"]["party"]] == [recruit_uid]
    assert veteran_uid in {member["uid"] for member in bot["state"]["storage"]}
    assert owned(bot) == before
    rest_until = bot["runtime"]["coverage_rest_until_cycle"]
    assert rest_until >= bot["runtime"]["cycle"] + 12
    bot["runtime"]["cycle"] = rest_until - 1
    manager._manage_party(bot)
    assert not bot["runtime"]["coverage_duty"]
    assert [member["uid"] for member in bot["state"]["party"]] == [recruit_uid]
    assert not any(bot["id"] in reserved for reserved in manager.coverage_reservations.values())


def test_reserved_veteran_visit_survives_restart_and_repeated_lab_maintenance():
    manager, _ = coverage_world()
    assigned = {}
    for ident in ("bot:00001", "bot:00002", "bot:00003"):
        bot = manager.bots[ident]
        prepare_banked_veteran(manager, bot)
        manager._manage_party(bot)
        assigned[ident] = bot["runtime"]["coverage_target"]
    assert len(set(assigned.values())) == 3
    before = {ident: copy.deepcopy(owned(manager.bots[ident])) for ident in assigned}
    manager.flush(force=True, now=10)
    restored = make_manager(count=12, levels=(1, 20, 50, 60), store=manager.store, now=1000)
    for ident, target in assigned.items():
        assert restored.coverage_reservations[target] == {ident}
        assert restored.bots[ident]["runtime"]["coverage_target"] == target
    bot = restored.bots["bot:00001"]
    for step in range(6):
        restored._lab_step(bot, 1000 + step)
    target = assigned[bot["id"]]
    assert bot["runtime"].get("coverage_target") == target
    assert restored.coverage_reservations[target] == {bot["id"]}
    assert owned(bot) == before[bot["id"]]
    restored._ranked_step(bot, 1010)
    restored._explore(bot, 1011)
    assert bot["state"]["map_id"] == target
    assert not restored.coverage_reservations[target]
    assert "coverage_target" not in bot["runtime"]
