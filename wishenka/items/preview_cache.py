"""Bounded application-local cache for explicitly public preview metadata."""

import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from email.utils import parsedate_to_datetime

import httpx

from wishenka.items.models import ExtractedMetadata


@dataclass(frozen=True)
class CacheEntry:
    """Metadata and destinations retained only for the allowed freshness period."""

    metadata: ExtractedMetadata
    urls: tuple[str, ...]
    expires: float


class PreviewCache:
    """A loop-local TTL and LRU cache; no operations suspend."""

    def __init__(self, capacity: int = 256, ttl: float = 300) -> None:
        self.capacity = capacity
        self.ttl = ttl
        self.entries: OrderedDict[str, CacheEntry] = OrderedDict()

    def get(self, key: str) -> CacheEntry | None:
        entry = self.entries.get(key)
        if entry is None:
            return None
        if entry.expires <= time.monotonic():
            del self.entries[key]
            return None
        self.entries.move_to_end(key)
        return CacheEntry(replace(entry.metadata), entry.urls, entry.expires)

    def put(
        self, key: str, metadata: ExtractedMetadata, chain: tuple[tuple[str, httpx.Headers], ...]
    ) -> None:
        lifetime = self.ttl
        if not chain:
            return
        for url, headers in chain:
            parsed = httpx.URL(url)
            if parsed.query or parsed.username or parsed.password:
                return
            directives = [
                part.strip().lower() for part in headers.get("cache-control", "").split(",")
            ]
            if "public" not in directives or any(
                item.split("=", 1)[0] in {"private", "no-store", "no-cache"} for item in directives
            ):
                return
            if any(name in headers for name in ("set-cookie", "vary", "www-authenticate")):
                return
            age = headers.get("age", "0")
            try:
                age_seconds = max(0.0, float(int(age)))
                date_header = headers.get("date")
                date = parsedate_to_datetime(date_header) if date_header else None
                expires_header = headers.get("expires")
                expires = parsedate_to_datetime(expires_header) if expires_header else None
                if (date is not None and date.tzinfo is None) or (
                    expires is not None and expires.tzinfo is None
                ):
                    return
                now = time.time()
                if date is not None:
                    age_seconds = max(age_seconds, max(0.0, now - date.timestamp()))
                if expires is not None:
                    lifetime = min(
                        lifetime, expires.timestamp() - (date.timestamp() if date else now)
                    )
            except (ValueError, TypeError, OverflowError):
                return
            for directive in directives:
                if directive in {"max-age", "s-maxage"}:
                    return
                if directive.startswith(("max-age=", "s-maxage=")):
                    try:
                        lifetime = min(lifetime, int(directive.split("=", 1)[1].strip('"')))
                    except ValueError:
                        return
            lifetime -= age_seconds
        if lifetime <= 0 or self.capacity <= 0:
            return
        self.entries[key] = CacheEntry(
            replace(metadata), tuple(url for url, _ in chain), time.monotonic() + lifetime
        )
        self.entries.move_to_end(key)
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)

    def clear(self) -> None:
        self.entries.clear()
