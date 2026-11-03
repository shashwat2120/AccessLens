"""In-memory LRU cache and per-provider rate limiter for LLM calls (TRD §5)."""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from accesslens.llm.schemas import ItemResult


class LruCache:
    """Maps a content-derived key to an item result. Nothing is written to disk."""

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._data: OrderedDict[str, tuple[ItemResult, bool]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[ItemResult, bool] | None:
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: str, value: tuple[ItemResult, bool]) -> None:
        if self._maxsize <= 0:
            return
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


class RateLimiters:
    """Spaces calls to each provider evenly, ``60 / rpm`` seconds apart."""

    def __init__(
        self,
        rpm: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 60.0 / rpm
        self._clock = clock
        self._sleep = sleep
        self._next: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, provider: str) -> None:
        with self._lock:
            now = self._clock()
            start = max(now, self._next.get(provider, 0.0))
            self._next[provider] = start + self._interval
            delay = start - now
        if delay > 0:
            self._sleep(delay)
