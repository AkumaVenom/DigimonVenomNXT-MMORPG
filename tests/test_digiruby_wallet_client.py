"""A ranked wallet refresh must not replay character events or replace the party."""
import os
import queue
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
from tools.preview_ui_screens import make_app, game_fixture


def test_ranked_wallet_refresh_preserves_live_character_and_pending_gameplay():
    app = make_app('1280x800')
    try:
        app.state = game_fixture(app)
        character, party = app.state, app.state['party']
        app.state['events'] = [{'kind': 'message', 'text': 'An earlier reward.'}]
        app.state['digirubies'] = 5
        app.action_pending = True
        app.connection = SimpleNamespace(connected=True, incoming=queue.Queue())
        app.requests[77] = 'community'
        app.community.pending['ranked'] = (77, app.now)
        app.community.request_ids[77] = 'ranked'
        economy = {'enabled': True, 'credits_per_ruby': 100, 'max_exchange_rubies': 100000}
        app.connection.incoming.put({
            'op': 'result', 'rid': 77, 'ok': True,
            'wallet': {'digirubies': 450}, 'economy': economy,
            'community': {'action': 'ranked', 'data': {'own': {'digirubies': 450}}},
        })
        with patch.object(app, 'consume_events') as events:
            app.poll()
            events.assert_not_called()
        assert app.state is character
        assert app.state['party'] is party
        assert app.state['digirubies'] == 450
        assert app.state['economy'] == economy
        assert app.action_pending
        assert not app.community.pending
    finally:
        pygame.quit()
