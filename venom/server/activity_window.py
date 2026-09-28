"""Small global activity aggregates; gameplay and career records live elsewhere."""
from collections import Counter
import math
import time

WINDOW_SECONDS = 12 * 60 * 60
BUCKET_SECONDS = 60
EVENT_LIMIT = 100


class RollingActivity:
    """At most 720 shared minute buckets, independent of the rival population.

    Expiry uses the start of each minute. Nothing older than twelve hours is
    counted; the oldest partial minute can expire less than one minute early.
    """

    def __init__(self, keys, tracking_since=None):
        self.keys = tuple(keys)
        self.buckets = {}
        self.counters = Counter({key: 0 for key in self.keys})
        self.tracking_since = time.time() if tracking_since is None else float(tracking_since)
        self.next_expiry = math.inf
        self.last_at = None

    def _recount(self):
        self.counters.clear()
        self.counters.update({key: 0 for key in self.keys})
        for values in self.buckets.values():
            self.counters.update(values)
        self.next_expiry = min(self.buckets, default=math.inf) + WINDOW_SECONDS

    def advance(self, now):
        now = float(now)
        if now >= self.next_expiry or (self.last_at is not None and now < self.last_at):
            self.buckets = {at: values for at, values in self.buckets.items()
                            if now - WINDOW_SECONDS < at <= now}
            self._recount()
        self.last_at = now

    def restore(self, snapshot, now):
        self.buckets.clear()
        self.tracking_since = float(snapshot.get('tracking_since', now))
        for row in snapshot.get('buckets', []):
            at = int(row['at'])
            if now - WINDOW_SECONDS < at <= now:
                self.buckets[at] = Counter({key: value for key, value in row['counters'].items()
                                            if key in self.keys and value > 0})
        # Timeless legacy totals cannot be assigned a twelve-hour timestamp.
        self._recount()
        self.last_at = float(now)

    def record(self, key, value, at):
        if key not in self.keys or not math.isfinite(value) or value < 0:
            raise ValueError('Activity increments must be known, finite and nonnegative.')
        self.advance(at)
        stamp = int(at // BUCKET_SECONDS) * BUCKET_SECONDS
        self.buckets.setdefault(stamp, Counter())[key] += value
        self.counters[key] += value
        self.next_expiry = min(self.next_expiry, stamp + WINDOW_SECONDS)
        return stamp

    def metadata(self, now):
        self.advance(now)
        return {'window_seconds': WINDOW_SECONDS, 'window_start': now - WINDOW_SECONDS,
                'as_of': now, 'tracking_since': self.tracking_since,
                'precision_seconds': BUCKET_SECONDS}
