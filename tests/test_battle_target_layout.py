"""Battle highlights contain the actual rendered names and metadata at native DPI."""
from __future__ import annotations

import math
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
import pytest

from tools.preview_battle_targets import CASES, audit_render, target_fixture, use_display
from tools.preview_ui_screens import make_app
from venom.client.widgets import GOLD, MUTED, RED


@pytest.fixture(scope='module')
def app():
    value = make_app('1280x800')
    yield value
    pygame.quit()


def squashed(value):
    return ''.join(str(value).split())


def assert_complete_layout(app, report):
    enemies = app.state['battle']['enemies']
    cards = [pygame.Rect(value) for value in report['targets']]
    assert len(cards) == len(enemies)
    view = pygame.Rect(report['viewport'])
    padding = max(1, math.floor(4*app.screen.scale))
    assert report['outlines'] == [list(cards[app.target])], 'Visible gold box must match clickable target'
    centers = [app.screen.to_physical_point(app.battle_positions('enemy', i, len(enemies)))[0]
               for i in range(len(enemies))]
    labels = [[] for _ in enemies]
    metadata = [[] for _ in enemies]
    seen_enemy = False
    for row in report['text']:
        color = tuple(row['color'])
        if seen_enemy and color == (231, 241, 249) and row['bold'] and row['size'] in (14, 15):
            break  # The following metadata belongs to the player's party.
        seen_enemy = seen_enemy or color == RED
        if color != RED and color != MUTED:
            continue
        rect = pygame.Rect(row['rect'])
        index = min(range(len(centers)), key=lambda i: abs(rect.centerx-centers[i]))
        (labels if color == RED else metadata)[index].append(row)
    for index, (mon, card) in enumerate(zip(enemies, cards)):
        assert view.contains(card), (view, card)
        assert all(not card.colliderect(other) for other in cards[index+1:]), cards
        assert squashed(''.join(row['rendered'] for row in labels[index])) == squashed(mon['name'])
        expected = f"Lv.{mon['level']} · {mon['type']} / {mon['attribute']}"
        assert squashed(''.join(row['rendered'] for row in metadata[index])) == squashed(expected)
        previous = None
        for row in labels[index]+metadata[index]:
            assert row['requested'] == row['rendered'], f'Truncated text: {row}'
            assert '…' not in row['rendered']
            rect = pygame.Rect(row['rect'])
            assert card.inflate(-padding*2, -padding*2).contains(rect), (mon['name'], card, row)
            if previous is not None:
                assert not previous.colliderect(rect), (mon['name'], previous, rect)
            previous = rect
    badges = [row for row in report['text'] if row['requested'] == 'TARGET']
    assert len(badges) == 1
    badge = pygame.Rect(badges[0]['rect'])
    assert cards[app.target].inflate(-padding*2, -padding*2).contains(badge)
    assert all(not badge.colliderect(pygame.Rect(row['rect']))
               for row in labels[app.target]+metadata[app.target])


@pytest.mark.parametrize('size,scale', CASES)
@pytest.mark.parametrize('longest', (False, True), ids=('fanglongmon', 'longest-catalog-names'))
def test_complete_names_details_and_badge_fit_actual_gold_highlight(app, size, scale, longest):
    use_display(app, size, scale)
    target_fixture(app, longest=longest)
    report = audit_render(app)
    assert_complete_layout(app, report)
    # A non-selected card must remain clickable; the next frame's gold outline
    # must move to that same card, preserving the server's enemy indices.
    for index in (1, 2, 0):
        point = pygame.Rect(report['targets'][index]).center
        assert app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
        assert app.target == index
        report = audit_render(app)
        assert_complete_layout(app, report)


def test_long_unspaced_species_token_wraps_without_losing_characters(app):
    use_display(app, '960x600', .75)
    target_fixture(app, longest=True)
    report = audit_render(app)
    assert_complete_layout(app, report)
    longest = app.state['battle']['enemies'][0]['name']
    assert longest == 'Paradox ImperialdramonDragonModeBlack'
    # Checking the real native output makes a future word-only wrap regression
    # fail even when a layout helper reports that its rectangle fits.
    names = [row for row in report['text'] if tuple(row['color']) == RED]
    assert len(names) > 3
    assert any(row['rendered'] in longest and 'Imperialdramon' in row['rendered'] for row in names)


@pytest.mark.parametrize('count', (1, 2))
@pytest.mark.parametrize('size,scale', (('960x600', .75), ('2047x1155', 1.0625)))
def test_one_and_two_enemy_rows_size_the_highlight_to_complete_long_names(app, count, size, scale):
    use_display(app, size, scale)
    target_fixture(app, longest=True)
    app.state['battle']['enemies'] = app.state['battle']['enemies'][:count]
    report = audit_render(app)
    assert_complete_layout(app, report)
    for index in range(count):
        point = pygame.Rect(report['targets'][index]).center
        assert app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
        assert app.target == index


def test_lunges_recoils_and_effects_use_card_anchors_with_swapped_active_slots(app):
    """Animation moves sprites, while labels/hit areas and effect slot mapping stay correct."""
    from unittest.mock import patch
    import venom.client.app as app_module

    use_display(app, '960x600', .75)
    target_fixture(app, longest=True)
    engine = app._qa_engine
    app.state['party'] = [engine._monster(sid, 99) for sid in
                          ('agumon', 'omnimon', 'gabumon', 'fanglongmon', 'patamon', 'fanglongmon_paradox')]
    app.state['battle'].update(active=[3, 1, 5], actor=3)
    sprite_positions = []
    original_blit = app.screen.blit

    def record_sprite(source, dest, *args, **kwargs):
        sprite_positions.append(pygame.Rect(dest).midbottom)
        return original_blit(source, dest, *args, **kwargs)

    with patch.object(app.screen, 'blit', side_effect=record_sprite):
        before = audit_render(app)
        assert len(sprite_positions) == 6
        anchors = tuple(sprite_positions)
        sprite_positions.clear()
        age = .21  # Peak lunge; the recipient is also in its recoil interval.
        app.animations = [
            {'start': app.now-age, 'attacker_side': 'enemy', 'attacker_index': 0,
             'side': 'player', 'index': 3, 'amount': 71, 'kind': 'damage', 'attribute': 'electric'},
            {'start': app.now-age, 'attacker_side': 'player', 'attacker_index': 5,
             'side': 'enemy', 'index': 1, 'amount': 83, 'kind': 'damage', 'attribute': 'light'},
        ]
        try:
            with patch.object(app_module, 'outlined_text', wraps=app_module.outlined_text) as effect_text:
                during = audit_render(app)
        finally:
            app.animations = []

    assert_complete_layout(app, during)
    assert during['targets'] == before['targets']
    assert during['outlines'] == before['outlines']

    def fixed_text(report):
        return [(row['rendered'], row['rect'], row['glyphs']) for row in report['text']
                if (tuple(row['color']) == RED or tuple(row['color']) == MUTED and row['size'] == 11
                    or row['rendered'] == 'TARGET')]
    assert fixed_text(during) == fixed_text(before)
    assert len(sprite_positions) == 6
    # Actual party index 3 is the first active slot, not the third; index 5 is
    # the third slot. A callback using raw party indices sends these elsewhere.
    for attacker, recipient in ((0, 3), (5, 1)):
        start, end = pygame.Vector2(anchors[attacker]), pygame.Vector2(anchors[recipient])
        expected = start+(end-start)*.55
        assert sprite_positions[attacker] == pytest.approx(expected, abs=1)
        assert sprite_positions[attacker] != anchors[attacker]
    for recipient in (1, 3):
        assert sprite_positions[recipient][0] != anchors[recipient][0]
        assert sprite_positions[recipient][1] == anchors[recipient][1]
    for unchanged in (2, 4):
        assert sprite_positions[unchanged] == anchors[unchanged]

    amounts = {call.args[2]: call.args[3] for call in effect_text.call_args_list
               if call.args[2] in ('71', '83')}
    assert set(amounts) == {'71', '83'}
    for value, recipient in (('71', 3), ('83', 1)):
        expected = (anchors[recipient][0]-app.viewport.x,
                    anchors[recipient][1]-app.viewport.y-65-age*50)
        assert amounts[value] == pytest.approx(expected)
