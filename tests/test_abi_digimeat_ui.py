"""ABI access without a de-digivolution route, plus native readable controls."""
import copy
from contextlib import ExitStack
from unittest.mock import patch, PropertyMock

import pytest

from tools.preview_abi_digimeat import abi_fixture, select_abi_view
from tools.preview_ui_screens import make_app
from venom.client import widgets
from venom.client import shop, partners, digifarm
import pygame


@pytest.fixture
def app():
    instance = abi_fixture(make_app('960x600'))
    yield instance
    pygame.quit()


def test_only_partner_uses_owned_meat_without_deposit_or_local_mutation(app):
    assert len(app.state['party']) == 1 and not app.state['storage']
    assert not any(route['devolve'] for route in app.state['evolution_options'][0])
    before = copy.deepcopy(app.state)
    with patch.object(app, 'send') as send:
        assert app.shop_screen.can_use_abi()
        app.shop_screen.use('digimeat_abi')
        send.assert_called_once_with('item', item='digimeat_abi', party_index=0,
                                     uid=app.state['party'][0]['uid'], quantity=1)
    assert app.state == before


@pytest.mark.parametrize('gate', ['cap', 'pending', 'community_busy', 'battle', 'field', 'unowned', 'missing_recipient'])
def test_party_abi_gates_prevent_consumption(app, gate):
    if gate == 'cap':
        app.state['party'][0]['abi'] = 200
    elif gate == 'pending':
        app.action_pending = True
    elif gate == 'community_busy':
        # Community exposes a computed busy property; exercise that exact gate.
        with patch.object(type(app.community), 'busy', new_callable=PropertyMock, return_value=True):
            with patch.object(app, 'send') as send:
                assert not app.shop_screen.can_use_abi()
                app.shop_screen.use('digimeat_abi')
                send.assert_not_called()
        return
    elif gate == 'battle':
        app.state['battle'] = {'active': [0]}
    elif gate == 'field':
        app.state.update(in_lab=False, in_farm=False)
    elif gate == 'unowned':
        app.state['inventory']['digimeat_abi'] = 0
    else:
        app.state['party'] = []
    with patch.object(app, 'send') as send:
        assert not app.shop_screen.can_use_abi()
        app.shop_screen.use('digimeat_abi')
        send.assert_not_called()


def test_party_uid_keeps_drawn_recipient_when_slots_change(app):
    original = app.state['party'][0]
    app.state['party'].insert(0, dict(original, uid='different-partner'))
    with patch.object(app, 'send') as send:
        app.shop_screen.use('digimeat_abi', uid=original['uid'])
        send.assert_called_once_with('item', item='digimeat_abi', party_index=1, uid=original['uid'], quantity=1)
        send.reset_mock()
        app.shop_screen.use('digimeat_abi', uid='removed-partner')
        send.assert_not_called()


def test_general_meat_choose_opens_visible_recipient_before_consuming(app):
    app.state['party'][0]['abi'] = 200
    app.state['party'].append(dict(app.state['party'][0], uid='eligible-partner', abi=0))
    app.shop_screen.filter('digimeat')
    original = app.ui.button
    choice = []

    def capture(rect, label, callback, **kwargs):
        if label == 'Choose':
            choice.append((pygame.Rect(rect), kwargs))
        return original(rect, label, callback, **kwargs)

    with patch.object(app.ui, 'button', side_effect=capture), patch.object(app, 'send') as send:
        app.draw()
        assert len(choice) == 1 and not choice[0][1]['disabled']
        assert app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                             pos=app.screen.to_physical_point(choice[0][0].center)))
        assert app.shop_screen.category == 'abi'
        send.assert_not_called()


def test_resident_abi_uses_own_cap_with_full_stat_pool(app):
    select_abi_view(app, 'farm')
    mon = app.state['storage'][0]
    mon['abi'] = 199
    assert sum(mon['farm_bonuses'].values()) == 300
    assert app.farm_screen.allowance(mon, app.shop_data()['digimeat_abi']) == 1
    before = copy.deepcopy(app.state)
    with patch.object(app, 'send') as send:
        app.farm_screen.feed()
        send.assert_called_once_with('digifarm', action='feed', uid=mon['uid'], item='digimeat_abi', quantity=1)
        assert app.state == before
        mon['abi'] = 200
        app.farm_screen.feed()
        assert send.call_count == 1


def test_both_prices_purchase_selected_currency_and_evolution_shop_path(app):
    item = app.shop_data()['digimeat_abi']
    with patch.object(app, 'send') as send:
        assert app.shop_screen.unit_price(item) == 6000
        app.shop_screen.buy('digimeat_abi')
        send.assert_called_with('shop', item='digimeat_abi', quantity=1)
        app.shop_screen.select_currency('digirubies')
        assert app.shop_screen.unit_price(item) == 30
        app.shop_screen.buy('digimeat_abi')
        assert send.call_args.args == ('shop',)
        assert send.call_args.kwargs['currency'] == 'digirubies'
        assert send.call_args.kwargs['item'] == 'digimeat_abi'
        assert len(send.call_args.kwargs['transaction_id']) == 32
    app.menu = 'party'
    app.partner_screen.open_abi_shop()
    assert app.menu == 'shop' and app.shop_screen.category == 'abi'


@pytest.mark.parametrize('size', ['960x600', '2047x1155'])
def test_native_abi_text_controls_and_six_recipient_roster_fit(size):
    app = make_app(size)
    original_text, original_button, original_card = widgets.text, app.ui.button, app.presentation.card
    labels, controls, cards = [], [], []

    def record_text(screen, assets, value, position, size=18, color=widgets.WHITE,
                    bold=False, max_width=None, center=False, **kwargs):
        rect = original_text(screen, assets, value, position, size, color, bold, max_width, center, **kwargs)
        labels.append((str(value), rect, size, bold, max_width))
        return rect

    def record_button(rect, label, callback, **kwargs):
        controls.append((str(label), pygame.Rect(rect), kwargs))
        return original_button(rect, label, callback, **kwargs)

    def record_card(rect, *args, **kwargs):
        cards.append(pygame.Rect(rect))
        return original_card(rect, *args, **kwargs)

    try:
        with ExitStack() as stack:
            for module in (widgets, shop, partners, digifarm):
                stack.enter_context(patch.object(module, 'text', side_effect=record_text))
            stack.enter_context(patch.object(app.ui, 'button', side_effect=record_button))
            stack.enter_context(patch.object(app.presentation, 'card', side_effect=record_card))
            for view in ('shop_credits', 'shop_rubies', 'evolution', 'evolution_no_devolve', 'evolution_cap', 'farm', 'shop_six'):
                select_abi_view(app, 'shop_credits' if view == 'shop_six' else view)
                if view == 'shop_six':
                    mon = app.state['party'][0]
                    app.state['party'] = [dict(mon, uid=f'slot-{i}') for i in range(6)]
                labels.clear(); controls.clear(); cards.clear()
                app.draw()
                bounds = app.screen.get_rect()
                for label, rect, options in controls:
                    assert bounds.contains(rect), (size, view, label, rect)
                    if label in ('ABI growth', 'ABI DigiMeat shop', 'Use +1 ABI', 'No ABI meat', 'Feed a farm resident', 'Feed one treat'):
                        font = app.assets.font(round(14*app.screen.scale), options.get('primary', False))
                        assert font.size(label)[0] <= (rect.width-14)*app.screen.scale, (size, view, label)
                relevant = [row for row in labels if 'ABI' in row[0] or row[0] == 'Paradox Fanglongmon']
                assert relevant
                for value, rect, font_size, bold, maximum in relevant:
                    font = app.assets.font(round(font_size*app.screen.scale), bold)
                    if maximum is not None:
                        assert font.size(value)[0] <= maximum*app.screen.scale, (size, view, value)
                    assert bounds.contains(rect), (size, view, value, rect)
                if view.startswith('evolution'):
                    protocol_text = [row for row in labels if row[0] == 'ABI DigiMeat also adds +1 permanently.']
                    for _, rect, *_ in protocol_text:
                        assert any(card.contains(rect) for card in cards), (size, view, rect)
                    assert any(value == 'No de-digivolution needed. Other route requirements still apply.' for value, *_ in labels)
                if view.startswith('shop'):
                    toolbar = [(label, rect) for label, rect, _ in controls if label in ('All supplies', 'HP recovery', 'SP recovery', 'DigiMeat', 'ABI growth') or label.startswith(('Credits ·', 'DigiRubies ·'))]
                    for i, (label, rect) in enumerate(toolbar):
                        assert not any(rect.colliderect(other) for _, other in toolbar[i+1:]), (size, label)
    finally:
        pygame.quit()
