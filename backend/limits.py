from threading import Lock
from time import monotonic


class RateLimiter:
    def __init__(self) -> None:
        self._values: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def allow(self, key: str, limit: int, window: float) -> bool:
        current = monotonic()
        with self._lock:
            started, count = self._values.get(key, (current, 0))
            if current - started >= window:
                started, count = current, 0
            if count >= limit:
                self._values[key] = (started, count)
                return False
            self._values[key] = (started, count + 1)
            return True
