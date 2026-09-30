"""Ghostline capability, progress, privacy and irreversible-finale boundaries.

Direct settlement isolates first-clear/retry rules; the separate acceptance suite
plays the production battle controls and collision-aware route through all maps.
"""
import copy
import json
from pathlib import Path

import pytest

from venom.common import story
from venom.common.game import GameEngine, GameError

ROOT = Path(__file__).resolve().parents[1]
XROS = 'xros_ghostline'


@pytest.fixture
def game():
    engine = GameEngine(ROOT, seed=821)
    state = engine.new_player('GhostlineTester', next(iter(engine.tamers)), 'agumon')
    return engine, state


def command(engine, state, action, **fields):
    return engine.handle(state, 'story', {'action': action, **fields})


def enter(engine, state, campaign=XROS):
    command(engine, state, 'enter', campaign_id=campaign)
    return state['story']


def choices(state):
    dialogue = state['story']['view']['dialogue']
    return {row['id'] for row in dialogue['choices']} if dialogue else set()


def choose(engine, state, choice):
    command(engine, state, 'dialogue', token=state['story']['view']['dialogue']['token'], choice=choice)


def meet(engine, state, npc):
    data = story.content(engine, state['story']['campaign_id'])
    region = next(row for row in data['regions'] if npc['map_id'] in row['maps'])
    command(engine, state, 'travel', chapter=region['index'], map_id=npc['map_id'])
    state.update(x=npc['x'], y=npc['y'])
    command(engine, state, 'talk', npc_id=npc['id'])
    while 'next' in choices(state):
        choose(engine, state, 'next')


def actors(engine, index):
    data = story.content(engine, XROS)
    return {data['npcs'][ident]['role']: data['npcs'][ident]
            for ident in data['regions'][index]['npc_ids']
            if data['npcs'][ident]['role'] in ('quest', 'trainer', 'final')}


def clear_field(engine, state, index):
    local = actors(engine, index)
    quest = local['quest']
    meet(engine, state, quest)
    choose(engine, state, 'accept_quest')
    if 'trainer' in local:
        meet(engine, state, local['trainer'])
        choose(engine, state, 'challenge')
        story.settle(engine, state, True)
        engine._refresh(state)
    meet(engine, state, quest)
    assert 'complete_quest' in choices(state)
    choose(engine, state, 'complete_quest')
    return local


def prepare_final(engine, state):
    """Settlement boundary fixture; played progression is covered separately."""
    data = story.content(engine, XROS)
    profile = state['story']
    final = data['npcs'][data['champion_id']]
    profile['completed'] = [row['id'] for row in data['npcs'].values() if row['role'] != 'final']
    profile['quest_accepted'] = [row['id'] for row in data['npcs'].values() if row['role'] == 'quest']
    profile['badges'] = story._badges(data)
    profile['revealed'] = True
    state['party'] = [engine._monster(ident, 99, abi=150, cam=100)
                      for ident in ('omnimon', 'wargreymon', 'metalgarurumon')]
    state.update(map_id=final['map_id'], x=final['x'], y=final['y'])
    engine._refresh(state)
    return data, final


def test_safe_hub_preserves_actual_owned_partners_and_all_services(game):
    engine, state = game
    state['party'] = [engine._monster('wargreymon_shiny', 63, abi=133, cam=79)]
    state['party'][0]['hp'] -= 3
    owned = copy.deepcopy({key: state[key] for key in ('party', 'storage', 'inventory', 'credits', 'scan')})
    enter(engine, state)
    assert {key: state[key] for key in owned} == owned
    view = state['story']['view']
    assert view['hub'] and not view['training_available']
    assert view['badge_name'] == 'Access Proof' and view['badge_total'] == 30
    assert len(view['chapters']) == 31
    assert {'shop', 'lab', 'farm', 'healer'} <= {row['role'] for row in view['npcs']}
    assert all(row['level'] == 0 for row in view['npcs'])
    with pytest.raises(GameError, match='peaceful'):
        command(engine, state, 'train')
    with pytest.raises(GameError):
        engine.handle(state, 'encounter', {})
    home = {key: state[key] for key in ('map_id', 'x', 'y')}
    command(engine, state, 'camp')
    assert state['in_story'] and state['in_lab']
    credits, capsules = state['credits'], state['inventory'].get('hp_s', 0)
    engine.handle(state, 'shop', {'item': 'hp_s', 'quantity': 1})
    assert state['credits'] < credits and state['inventory']['hp_s'] == capsules + 1
    command(engine, state, 'field')
    engine.handle(state, 'digifarm', {'action': 'enter'})
    assert state['in_farm'] and state['in_story']
    command(engine, state, 'field')
    assert {key: state[key] for key in home} == home
    assert state['party'][0]['uid'] == owned['party'][0]['uid']


def test_three_campaign_itineraries_survive_switching_and_serialization(game):
    engine, state = game
    original = {key: copy.deepcopy(state.get(key)) for key in story.LOCATION_FIELDS}
    profiles = {}
    for campaign in story.CAMPAIGN_IDS:
        profile = enter(engine, state, campaign)
        profiles[campaign] = profile['id']
        profile['met'].append('saved-' + campaign)
        if campaign != story.DAWN_CAMPAIGN:
            command(engine, state, 'travel', chapter=1)
        command(engine, state, 'return')
    assert len(set(profiles.values())) == 3
    state = json.loads(json.dumps(state))
    engine._refresh(state)
    for campaign in story.CAMPAIGN_IDS:
        profile = enter(engine, state, campaign)
        assert profile['id'] == profiles[campaign]
        assert 'saved-' + campaign in profile['met']
        assert profile['chapter'] == (0 if campaign == story.DAWN_CAMPAIGN else 1)
        command(engine, state, 'return')
    assert {key: state.get(key) for key in original} == original


def test_future_chapter_badge_and_final_identity_are_not_preloaded(game):
    engine, state = game
    profile = enter(engine, state)
    view = profile['view']
    assert not view['revealed']
    assert view['final_name'] is None and view['final_npc_id'] is None
    assert view['final_map_id'] is None and view['final_team'] == []
    assert profile['champion']['holder'] == 'Unidentified operator'
    assert profile['champion']['holder_id'] is None
    for chapter in view['chapters'][2:]:
        assert chapter['name'].startswith('Encrypted node')
        assert not chapter['synopsis']
        assert all(row['name'] == 'Encrypted destination' for row in chapter['maps'])
    for badge in view['badges'][1:]:
        assert badge['name'].startswith('Encrypted Access Proof')
    mara = [row for row in view['npcs'] if 'Mara' in row['name']]
    assert mara and all(row['role'] != 'final' for row in mara)


def test_exact_prefix_and_server_capabilities_reject_skips(game):
    engine, state = game
    profile = enter(engine, state)
    data = story.content(engine, XROS)
    profile['badges'] = [story._badges(data)[-1]] * 30
    with pytest.raises(GameError, match='preceding Access Proofs'):
        command(engine, state, 'travel', chapter=2)
    profile['badges'] = [story._badges(data)[0]]
    command(engine, state, 'travel', chapter=2)
    with pytest.raises(GameError):
        command(engine, state, 'travel', chapter=3)
    for action in ({'action': 'complete', 'badges': story._badges(data), 'winner': 'player'},
                   {'action': 'heal', 'campaign_id': story.DS_CAMPAIGN},
                   {'action': 'challenge', 'npc_id': data['champion_id'], 'token': 'forged'}):
        with pytest.raises(GameError):
            engine.handle(state, 'story', action)


def test_hack_occurs_only_on_first_real_tamer_win_and_quest_turnin_opens_gate(game):
    engine, state = game
    profile = enter(engine, state)
    local = actors(engine, 1)
    quest, trainer = local['quest'], local['trainer']
    assert trainer['hacked_after_victory']
    meet(engine, state, trainer)
    assert 'challenge' not in choices(state)
    meet(engine, state, quest)
    stale = profile['view']['dialogue']['token']
    choose(engine, state, 'accept_quest')
    with pytest.raises(GameError):
        command(engine, state, 'dialogue', token=stale, choice='accept_quest')
    meet(engine, state, trainer)
    choose(engine, state, 'challenge')
    story.settle(engine, state, False)
    engine._refresh(state)
    assert not profile['hacked'] and trainer['id'] not in profile['completed']
    meet(engine, state, quest)
    assert 'complete_quest' not in choices(state)
    meet(engine, state, trainer)
    choose(engine, state, 'challenge')
    scan_before = copy.deepcopy(state['scan'])
    story.settle(engine, state, True)
    engine._refresh(state)
    assert state['scan'] == scan_before
    assert profile['hacked'] == [trainer['id']] and not profile['badges']
    with pytest.raises(GameError):
        command(engine, state, 'travel', chapter=2)
    meet(engine, state, trainer)
    assert ' '.join(profile['dialogue']['lines']) == ' '.join(trainer['dialogue']['hacked_repeat'])
    assert 'challenge' not in choices(state)
    with pytest.raises(story.StoryError, match='already recorded'):
        story._begin(engine, state, trainer)
    assert profile['hacked'] == [trainer['id']]
    meet(engine, state, quest)
    stale = profile['view']['dialogue']['token']
    choose(engine, state, 'complete_quest')
    wallet, inventory = state['credits'], copy.deepcopy(state['inventory'])
    assert profile['badges'] == [quest['badge']]
    with pytest.raises(GameError):
        command(engine, state, 'dialogue', token=stale, choice='complete_quest')
    assert (state['credits'], state['inventory']) == (wallet, inventory)
    command(engine, state, 'travel', chapter=2)


def test_training_earns_combat_xp_without_artificial_level_floor(game, monkeypatch):
    engine, state = game
    enter(engine, state)
    command(engine, state, 'travel', chapter=1)
    def forbidden(*args):
        pytest.fail('Ghostline must not call the legacy level-floor reward shortcut')
    monkeypatch.setattr(story, '_training_xp', forbidden)
    before = copy.deepcopy(state['party'][0])
    story._grant_reward(engine, state, {'training_level': 99}, True)
    assert state['party'][0] == before
    command(engine, state, 'train')
    story.settle(engine, state, True)
    assert state['story']['hacked'] == [] and state['story']['badges'] == []
    assert state['party'][0]['level'] < 99
    assert state['party'][0]['xp'] != before['xp'] or state['party'][0]['level'] > before['level']


def test_mara_is_an_intel_contact_with_earned_context_then_disappears_on_reveal(game):
    engine, state = game
    profile = enter(engine, state)
    data = story.content(engine, XROS)
    mara = next(npc for npc in data['npcs'].values()
                if npc.get('character_id') == 'mara_vale' and npc['map_id'] == data['start_map'])
    meet(engine, state, mara)
    assert choices(state) == {'leave'}  # Intel never grants service/battle powers.
    opening = list(profile['dialogue']['lines'])
    clear_field(engine, state, 1)
    meet(engine, state, mara)
    first_report = next(row for row in mara['dialogue_variants']
                        if row.get('requires_completed') == ['ghost_01_quest'])
    assert profile['dialogue']['lines'] == first_report['lines']
    assert profile['dialogue']['lines'] != opening
    profile['revealed'] = True  # Isolate visibility migration for an active conversation.
    engine._refresh(state)
    assert profile['dialogue'] is None
    assert mara['id'] not in {npc['id'] for npc in profile['view']['npcs']}
    with pytest.raises(GameError):
        command(engine, state, 'talk', npc_id=mara['id'])


def test_campaign_progresses_all_30_fields_reveals_only_at_map27_and_final_is_irreversible(game):
    engine, state = game
    state['party'] = [engine._monster('wargreymon', 99, abi=150, cam=100)]
    profile = enter(engine, state)
    data = story.content(engine, XROS)
    for index in range(1, 31):
        if index == 26:
            assert profile['chapter'] == 26 and not profile['revealed']
            assert all(row['id'] != 'ghost_26_mara' for row in profile['view']['npcs'])
            assert 'Mara Vale is the Null Regent' not in profile['view']['synopsis']
        local = clear_field(engine, state, index)
        assert profile['badges'] == story._badges(data)[:index]
        assert bool(profile['revealed']) == (index >= 26)
        assert bool(profile['view']['final_name']) == (index >= 26)
        if index == 25:
            assert 'Mara Vale is the Null Regent' not in ' '.join(profile['dialogue']['lines'])
        if index == 26:
            assert 'Mara Vale is the Null Regent' in ' '.join(profile['dialogue']['lines'])
            assert any(row['id'] == 'ghost_26_mara' for row in profile['view']['npcs'])
        assert not state.get('permanent_rewards', {}).get('shiny_scan_mastery')
        if index < 30:
            exits = data['maps'][state['map_id']]['exits']
            gate = next(row for row in exits if row['to_map'] == data['regions'][index + 1]['maps'][0])
            state.update(x=gate['x'], y=gate['y'])
            command(engine, state, 'exit', exit_id=gate['id'])
            assert state['map_id'] == gate['to_map']
    final = data['npcs'][data['champion_id']]
    assert not profile['view']['chapters'][-1]['complete']
    final_gate = next(row for row in data['maps'][final['map_id']]['exits'] if row.get('requires_campaign_complete'))
    state.update(x=final_gate['x'], y=final_gate['y'])
    with pytest.raises(GameError, match='final opponent'):
        command(engine, state, 'exit', exit_id=final_gate['id'])
    meet(engine, state, final)
    choose(engine, state, 'challenge')
    story.settle(engine, state, False)
    engine._refresh(state)
    assert not profile['champion']['first_victory']
    assert any(row['id'] == final['id'] for row in profile['view']['npcs'])
    meet(engine, state, final)
    stale = profile['view']['dialogue']['token']
    choose(engine, state, 'challenge')
    story.settle(engine, state, True)
    engine._refresh(state)
    assert profile['champion']['first_victory'] and state['permanent_rewards']['shiny_scan_mastery']
    assert profile['view']['chapters'][-1]['complete']
    assert profile['view']['scan_bonus'] == 20
    assert profile['dialogue']['transmission'] and profile['view']['dialogue']['transmission']
    assert profile['dialogue']['npc_id'] == data['epilogue']['npc_id']
    while 'next' in choices(state):
        choose(engine, state, 'next')
    assert choices(state) == {'leave'}
    choose(engine, state, 'leave')
    assert profile['dialogue'] is None
    assert profile['view']['final_name'] is None and profile['view']['final_team'] == []
    with pytest.raises(GameError):
        command(engine, state, 'dialogue', token=stale, choice='challenge')
    with pytest.raises(story.StoryError):
        story._begin(engine, state, final)
    with pytest.raises(story.StoryError):
        story.settle(engine, state, True)
    state.update(x=final_gate['x'], y=final_gate['y'])
    command(engine, state, 'exit', exit_id=final_gate['id'])
    assert state['map_id'] == data['regions'][0]['maps'][0]
    state = json.loads(json.dumps(state))
    engine._refresh(state)
    wallet = state['credits']
    for region in data['regions']:
        command(engine, state, 'travel', chapter=region['index'])
        assert all(not npc['hacked'] for npc in state['story']['view']['npcs'])
        visible = {row['id'] for row in state['story']['view']['npcs']}
        for npc in data['npcs'].values():
            if npc.get('character_id') == 'mara_vale' and npc['map_id'] == state['map_id']:
                assert npc['id'] not in visible
                state.update(x=npc['x'], y=npc['y'])
                with pytest.raises(GameError):
                    command(engine, state, 'talk', npc_id=npc['id'])
    assert state['credits'] == wallet
    command(engine, state, 'return')
    enter(engine, state, story.DS_CAMPAIGN)
    assert state['permanent_rewards']['shiny_scan_mastery']
    assert state['story']['view']['shiny_scan_bonus'] == 20
    assert not state.get('permanent_rewards', {}).get('paradox_scan_mastery')


def test_final_checks_unique_proofs_and_cannot_settle_into_other_profile(game):
    engine, state = game
    enter(engine, state)
    data, final = prepare_final(engine, state)
    required = story._badges(data)
    state['story']['badges'] = required[:-1] + [required[0]]
    with pytest.raises(story.StoryError):
        story._begin(engine, state, final)
    state['story']['badges'] = required
    story._begin(engine, state, final)
    original = json.loads(json.dumps(state))
    for key, value in (('story_campaign_id', story.DS_CAMPAIGN), ('story_profile_id', 'foreign-profile')):
        changed = copy.deepcopy(original)
        changed['battle'][key] = value
        before = copy.deepcopy(changed)
        with pytest.raises(story.StoryError):
            story.settle(engine, changed, True)
        assert changed == before


def test_missing_permanent_flag_repairs_from_parked_completion(game):
    engine, state = game
    enter(engine, state)
    _, final = prepare_final(engine, state)
    story._begin(engine, state, final)
    story.settle(engine, state, True)
    command(engine, state, 'return')
    enter(engine, state, story.DAWN_CAMPAIGN)
    state['permanent_rewards'].pop('shiny_scan_mastery')
    state['story'] = None
    engine._refresh(state)
    assert state['permanent_rewards']['shiny_scan_mastery'] is True


def test_stale_mara_result_dialogue_is_purged_after_completed_reload(game):
    engine, state = game
    profile = enter(engine, state)
    _, final = prepare_final(engine, state)
    story._begin(engine, state, final)
    story.settle(engine, state, True)
    profile['dialogue'] = {'npc_id': final['id'], 'page': 0, 'lines': ['stale villain dialogue'],
                           'token': 'expired', 'result_only': True}
    engine._refresh(state)
    assert profile['dialogue'] is None and profile['view']['dialogue'] is None
