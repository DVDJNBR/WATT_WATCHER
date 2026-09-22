"""
In-memory TTL cache for API responses.

Reduces Supabase egress: DB is read at most once per TTL window per unique
param combination, instead of on every user request.
TTL = 15 min (matches pipeline refresh cadence).
"""

import time
import threading
from typing import Any, Optional

TTL_SECONDS = 900


class _TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.monotonic() - ts > TTL_SECONDS:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), value)

    def size(self) -> int:
        with self._lock:
            return len(self._store)


cache = _TTLCache()


def make_key(endpoint: str, params: dict) -> str:
    """Deterministic cache key: endpoint + sorted query params."""
    if not params:
        return endpoint
    kv = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return f"{endpoint}:{kv}"
