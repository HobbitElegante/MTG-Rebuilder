import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from mtg_rebuilder.config import SCRYFALL_API_BASE, SCRYFALL_RATE_LIMIT_SECONDS

# Cards per /cards/search page (fixed by Scryfall).
SEARCH_PAGE_SIZE = 175
PING_TIMEOUT_SECONDS = 5.0
# /cards/search answers 429 above ~2 requests per second, below the general
# API limit, so search pages get their own slower pace.
SEARCH_MIN_INTERVAL_SECONDS = 0.5
# Waits before re-asking a search page after a reset or a 429.
SEARCH_RETRY_DELAYS = (2.0, 5.0)


class ScryfallQueryError(ValueError):
    """Scryfall rejected the query (HTTP 400). ``str()`` is Scryfall's detail."""


class _SearchStopped(Exception):
    """``should_stop`` fired while waiting to retry a page."""


@dataclass(frozen=True)
class SearchResult:
    """Oracle ids that matched, plus whether the walk stopped before the end."""

    oracle_ids: set[str]
    total_cards: int
    cancelled: bool = False


class ScryfallClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=SCRYFALL_API_BASE,
            headers={"User-Agent": "MTG-Rebuilder/0.10"},
            timeout=30.0,
        )
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < SCRYFALL_RATE_LIMIT_SECONDS:
            time.sleep(SCRYFALL_RATE_LIMIT_SECONDS - elapsed)
        self._last_request_at = time.monotonic()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._throttle()
        response = self._client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Scryfall response shape")
        return payload

    def fetch_card_by_name(self, name: str) -> dict[str, Any]:
        return self._get("/cards/named", params={"exact": name})

    def fetch_card_fuzzy(self, name: str) -> dict[str, Any]:
        return self._get("/cards/named", params={"fuzzy": name})

    def fetch_cards_collection(
        self, identifiers: list[dict[str, str]]
    ) -> dict[str, Any]:
        """POST /cards/collection (max 75 identifiers per Scryfall request)."""
        self._throttle()
        response = self._client.post("/cards/collection", json={"identifiers": identifiers})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Scryfall collection response shape")
        return payload

    def fetch_card_prints(self, oracle_id: str) -> list[dict[str, Any]]:
        """Every printing of one card (the oracle bulk pack keeps only one)."""
        prints: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._get(
                "/cards/search",
                params={
                    "q": f"oracleid:{oracle_id}",
                    "unique": "prints",
                    "order": "released",
                    "page": page,
                },
            )
            data = payload.get("data")
            if isinstance(data, list):
                prints.extend(entry for entry in data if isinstance(entry, dict))
            if not payload.get("has_more"):
                return prints
            page += 1

    def _get_with_retry(
        self,
        path: str,
        params: dict[str, Any],
        *,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Paced GET that rides out resets and 429s (long searches hit both)."""
        for delay in (*SEARCH_RETRY_DELAYS, None):
            wait = SEARCH_MIN_INTERVAL_SECONDS - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            try:
                return self._get(path, params=params)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 or delay is None:
                    raise
                delay = max(delay, _retry_after(exc.response))
            except httpx.TransportError:
                if delay is None:
                    raise
            if should_stop is not None and should_stop():
                raise _SearchStopped
            time.sleep(delay)
        raise AssertionError("unreachable")

    def ping(self) -> bool:
        """True when the Scryfall API answers (cheap reachability probe)."""
        try:
            self._throttle()
            response = self._client.get("/bulk-data", timeout=PING_TIMEOUT_SECONDS)
        except httpx.HTTPError:
            return False
        return response.status_code < 500

    def search_oracle_ids(self, query: str) -> set[str]:
        """Return every oracle_id matching a Scryfall search query."""
        return self.search_oracle_ids_in(query, None).oracle_ids

    def search_oracle_ids_in(
        self,
        query: str,
        inventory_ids: set[str] | None,
        *,
        on_page: Callable[[int, int], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> SearchResult:
        """Walk every result page of ``query`` and collect oracle_ids.

        The query goes to Scryfall verbatim, so the full syntax (tags
        included) works. With ``inventory_ids`` only those ids are kept, and
        the walk ends early once all of them have matched. ``on_page`` gets
        ``(page, total_pages)`` after each page. ``should_stop`` is checked
        before each request and yields a partial result marked ``cancelled``.
        """
        trimmed = query.strip()
        if not trimmed:
            return SearchResult(set(), 0)
        if inventory_ids is not None and not inventory_ids:
            return SearchResult(set(), 0)
        found: set[str] = set()
        total_cards = 0
        page = 1
        while True:
            if should_stop is not None and should_stop():
                return SearchResult(found, total_cards, cancelled=True)
            try:
                payload = self._get_with_retry(
                    "/cards/search",
                    {"q": trimmed, "unique": "cards", "page": page},
                    should_stop=should_stop,
                )
            except _SearchStopped:
                return SearchResult(found, total_cards, cancelled=True)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # Scryfall returns 404 when the query matches nothing.
                if status == 404:
                    return SearchResult(found, total_cards)
                if status == 400:
                    raise ScryfallQueryError(_error_details(exc.response)) from exc
                raise
            reported = payload.get("total_cards")
            if isinstance(reported, int):
                total_cards = reported
            data = payload.get("data")
            if isinstance(data, list):
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    oracle_id = entry.get("oracle_id")
                    if not isinstance(oracle_id, str) or not oracle_id:
                        continue
                    if inventory_ids is None or oracle_id in inventory_ids:
                        found.add(oracle_id)
            if on_page is not None:
                total_pages = max(page, math.ceil(total_cards / SEARCH_PAGE_SIZE))
                on_page(page, total_pages)
            if inventory_ids is not None and len(found) >= len(inventory_ids):
                break
            if not payload.get("has_more"):
                break
            page += 1
        return SearchResult(found, total_cards)

    def fetch_bulk_data(self) -> list[dict[str, Any]]:
        payload = self._get("/bulk-data")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("Unexpected Scryfall bulk-data response shape")
        return data

    def download_file(self, url: str, destination: Path) -> None:
        """Download any URL (API or absolute CDN) to disk with rate limiting."""
        self._throttle()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._client.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)

    def download_bulk_file(self, download_uri: str, destination: Path) -> None:
        self.download_file(download_uri, destination)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ScryfallClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _retry_after(response: httpx.Response) -> float:
    try:
        return max(0.0, float(response.headers.get("Retry-After", "0")))
    except ValueError:
        return 0.0


def _error_details(response: httpx.Response) -> str:
    """Scryfall's human-readable reason for a rejected query."""
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        details = payload.get("details")
        if isinstance(details, str) and details:
            return details
    return f"HTTP {response.status_code}"
