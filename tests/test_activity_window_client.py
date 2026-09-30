"""The native activity window distinguishes recent totals from durable careers."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import pygame

import test_community_client as community_harness
from tools.preview_ui_screens import ROOT, make_app
from venom.client import community
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas


@unittest.skipUnless((ROOT/'data/catalog.json').exists(), 'Imported assets required')
class ActivityWindowClientTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app('1280x800')
        self.addCleanup(pygame.quit)
        self.app.community.data = community_harness.fixture(self.app)
        self.app.menu = 'community'
        self.app.community.tab, self.app.community.mode = 'activity', 'feed'
        self.labels, self.buttons = [], []
        original_text, original_button = community.text, self.app.community.button

        def capture_text(screen, assets, value, *args, **kwargs):
            area = original_text(screen, assets, value, *args, **kwargs)
            self.labels.append((str(value), area))
            return area

        def capture_button(rect, label, callback, *args, **kwargs):
            self.buttons.append((label, pygame.Rect(rect)))
            return original_button(rect, label, callback, *args, **kwargs)

        self.enterContext(patch.object(community, 'text', side_effect=capture_text))
        self.enterContext(patch.object(self.app.community, 'button', side_effect=capture_button))

    def draw(self):
        self.labels.clear()
        self.buttons.clear()
        self.app.draw()
        return [label for label, _ in self.labels]

    def click(self, label):
        area = next(rect for name, rect in self.buttons if name == label)
        self.assertTrue(self.app.ui.event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=self.app.screen.to_physical_point(area.center))))

    def test_recent_counter_pages_fit_native_sizes_and_actions_stay_usable(self):
        self.app.community.data['activity']['counters']['firewall_materialized'] = 8472
        before = copy.deepcopy(self.app.community.data)
        counters = self.app.community.COUNTERS
        pages = (len(counters)+11)//12
        self.assertIn(('firewall_materialized', 'FireWall created'), counters)
        self.assertGreaterEqual(pages, 3)
        for size in ((1024, 720), (1180, 800), (2047, 1149), (3840, 2160)):
            self.app.screen = NativeCanvas(pygame.display.set_mode(size), effective_ui_scale(size))
            self.app.ui.screen = self.app.screen
            self.app.community.stats_page = 0
            seen = set()
            for page in range(pages):
                with self.subTest(size=size, page=page):
                    self.assertEqual(self.app.community.stats_page, page)
                    labels = self.draw()
                    self.assertIn('LAST 12 HOURS', labels)
                    self.assertIn('Latest 100 events within the last 12 hours.', labels)
                    self.assertNotIn('WORLD TOTALS', labels)
                    self.assertTrue(all('New tracking:' not in label for label in labels))
                    bounds = self.app.screen.get_rect()
                    for label, area in self.labels:
                        self.assertTrue(bounds.contains(area), (label, area, bounds))
                    for area, _ in self.app.ui.actions:
                        self.assertTrue(bounds.contains(area), (area, bounds))
                    expected = {label.upper() for _, label in counters[page*12:(page+1)*12]}
                    actual = {label for label in labels if label in {name.upper() for _, name in counters}}
                    self.assertEqual(actual, expected)
                    seen.update(actual)
                    if 'FIREWALL CREATED' in actual:
                        position = labels.index('FIREWALL CREATED')
                        self.assertEqual(labels[position+1], '8,472')
                    for label in ('All', 'Wild', 'Ranked', 'Progress', 'Travel'):
                        self.assertIn(label, [name for name, _ in self.buttons])
                    self.click(f'Counters {page+1} / {pages}  ·  Next')
                    self.assertEqual(self.app.community.stats_page, (page+1)%pages)
            self.assertEqual(seen, {label.upper() for _, label in counters})
            self.assertEqual(self.app.community.stats_page, 0)
        self.assertEqual(self.app.community.data, before)
        self.assertFalse(self.app.assets.errors, self.app.assets.errors)

    def test_first_window_and_empty_filter_explain_missing_history_without_mutation(self):
        activity = self.app.community.data['activity']
        activity['tracking_since'] = activity['as_of']-300
        before = copy.deepcopy(activity)
        labels = self.draw()
        self.assertIn('New tracking: 00h 05m captured. Earlier totals are not included.', labels)
        self.click('Travel')
        labels = self.draw()
        self.assertIn('No matching events in the recent feed.', labels)
        self.assertEqual(activity, before)
        self.click('All')
        activity['events'] = []
        activity['counters'] = {}
        labels = self.draw()
        self.assertIn('No activity in the last 12 hours. New adventures will appear here.', labels)

    def test_legacy_server_totals_are_not_mislabeled_as_a_twelve_hour_window(self):
        activity = self.app.community.data['activity']
        for key in ('window_seconds', 'window_start', 'as_of', 'tracking_since'):
            activity.pop(key)
        labels = self.draw()
        self.assertNotIn('LAST 12 HOURS', labels)
        self.assertIn('ACTIVITY TOTALS', labels)
        self.assertIn('Update the server to enable the rolling 12-hour activity window.', labels)

    def test_current_population_and_career_record_are_distinct_from_recent_activity(self):
        self.app.community.mode = 'maps'
        labels = self.draw()
        self.assertIn('CURRENT MAP POPULATION', labels)
        self.app.community.tab, self.app.community.mode = 'rivals', 'profile'
        self.app.community.profile_id = 'bot:00001'
        labels = self.draw()
        self.assertIn('CAREER RECORD  /  Current collection shown alongside career counters', labels)
        self.assertNotIn('LAST 12 HOURS', labels)
