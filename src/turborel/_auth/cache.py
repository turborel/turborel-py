"""The SCRAM key cache [CLIENT The SCRAM key cache].

A SCRAM login derives its keys from the password by PBKDF2, made slow on
purpose. A server sends a user the same salt and iterations at each
login, so the cache keeps the keys a password derived, and a later login
of the same salt and iterations skips the derivation. An entry is found
by the salt, the iterations and a tag of the password, an HMAC under a
random secret of the cache's own, so a wrong password finds nothing and
the cache holds nothing a password could be guessed from offline. It
holds at most 64 entries, the oldest dropped first; an entry is dropped
when a login that used it fails; it lives in the process's memory alone.
As turborel-client's `scram/cache.rs`, shared safely by threads.
"""

from __future__ import annotations

import hmac
import secrets
import threading
from collections import OrderedDict
from typing import Final

from turborel._auth.scram import Derived

KEY_CACHE_ENTRIES: Final = 64
"""The most entries a cache holds."""

_SECRET_BYTES: Final = 32


class KeyCache:
    """Keys SCRAM logins derived, found by salt, iterations and password."""

    def __init__(self) -> None:
        """An empty cache, with a random secret of its own."""
        self._secret = secrets.token_bytes(_SECRET_BYTES)
        self._held: OrderedDict[tuple[bytes, bytes, int], Derived] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def __repr__(self) -> str:
        """Its size alone, never a key or a tag."""
        return f"KeyCache({len(self)} entries)"

    def _index(
        self, password: str, salt: bytes, iterations: int
    ) -> tuple[bytes, bytes, int]:
        tag = hmac.digest(self._secret, password.encode(), "sha256")
        return tag, bytes(salt), iterations

    def derived(self, password: str, salt: bytes, iterations: int) -> Derived:
        """The keys of `password` under `salt` and `iterations`, kept or derived."""
        index = self._index(password, salt, iterations)
        with self._lock:
            found = self._held.get(index)
            if found is not None:
                self._hits += 1
                return found
            self._misses += 1
        keys = Derived.of(password, salt, iterations)
        with self._lock:
            if index not in self._held:
                if len(self._held) >= KEY_CACHE_ENTRIES:
                    self._held.popitem(last=False)
                self._held[index] = keys
        return keys

    def forget(self, password: str, salt: bytes, iterations: int) -> None:
        """Drop the entry of `password`, `salt` and `iterations`: its login failed."""
        with self._lock:
            self._held.pop(self._index(password, salt, iterations), None)

    def __len__(self) -> int:
        """The entries held."""
        with self._lock:
            return len(self._held)

    def lookups(self) -> tuple[int, int]:
        """Its hits and its misses."""
        with self._lock:
            return self._hits, self._misses

    def clear(self) -> None:
        """Drop every entry."""
        with self._lock:
            self._held.clear()
