from __future__ import annotations

import collections
import threading
import time


class SlidingWindowRateLimiter:
    """Simple sliding-window limiter for API calls.

    Polygon basic plan is capped at 5 requests per minute. This limiter blocks
    until a request slot is available.
    """

    def __init__(self, max_calls: int = 5, period_seconds: int = 60) -> None:
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._calls = collections.deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and (now - self._calls[0]) >= self.period_seconds:
                    self._calls.popleft()

                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return

                wait_for = self.period_seconds - (now - self._calls[0])

            if wait_for > 0:
                time.sleep(wait_for)