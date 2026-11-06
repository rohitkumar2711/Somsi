"""Tiny TTL + LRU cache.

Every shared sheet link in a WhatsApp group hits the same enckey, so the cache
is what makes a 1000-user spike cheap: second and later visitors of the same
link cost zero upstream requests.
"""

from __future__ import annotations

import os
import re
import time
import urllib.parse
from collections import OrderedDict

TTL = int(os.getenv("CACHE_TTL", "1800"))
MAXSIZE = int(os.getenv("CACHE_SIZE", "5000"))


_ENCKEY_RE = re.compile(r"enc?key=([^&#]+)", re.I)


def key_for(url: str) -> str:
    """Cache on the enckey, whatever it is spelled like.

    The same candidate sheet is reachable as ViewCandResponse.aspx?enckey=...,
    ViewCandResponse4.aspx?EncKey=... etc. and all of those are the same data,
    so they share one cache entry.
    """
    m = _ENCKEY_RE.search(urllib.parse.urlsplit(url).query)
    if m:
        return "enckey:" + m.group(1).strip().upper()
    return url.lower()


class TTLCache:
    def __init__(self, ttl: int = TTL, maxsize: int = MAXSIZE):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        item = self._data.get(key)
        if not item:
            self.misses += 1
            return None
        ts, value = item
        if time.time() - ts > self.ttl:
            self._data.pop(key, None)
            self.misses += 1
            return None
        self._data.move_to_end(key)
        self.hits += 1
        return value

    def set(self, key: str, value) -> None:
        self._data[key] = (time.time(), value)
        self._data.move_to_end(key)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "size": len(self._data),
            "maxsize": self.maxsize,
            "ttl": self.ttl,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total * 100, 1) if total else 0.0,
        }
