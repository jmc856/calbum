"""HTTP client for the Discogs API: proactive rate limiting and the barcode
normalization PLAN.md Stage 1 calls for.

Discogs is 60 req/min *authenticated*, and every response carries
X-Discogs-Ratelimit-Remaining — unlike Spotify's occasional 429, this limit
is expected to be approached routinely during a real enrichment run, so this
throttles proactively between requests rather than retrying after a 429
(see PLAN.md decision 7's contrast: Spotify's client is a good template for
its own problem, not for this one).
"""

from __future__ import annotations

import time

import requests

API_BASE = "https://api.discogs.com"

# 60/min authenticated -> a request roughly every second keeps remaining from
# ever hitting zero under steady load. Below LOW_REMAINING_THRESHOLD, slow
# down further in proportion to what's left, rather than blindly continuing
# at the steady-state pace until a 429 actually happens.
STEADY_STATE_INTERVAL = 1.0
LOW_REMAINING_THRESHOLD = 5


class DiscogsClient:
    def __init__(self, token: str, user_agent: str):
        self._session = requests.Session()
        self._headers = {
            "Authorization": f"Discogs token={token}",
            "User-Agent": user_agent,
        }
        self._last_request_at: float | None = None
        self._remaining: int | None = None

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        min_gap = STEADY_STATE_INTERVAL
        if self._remaining is not None and self._remaining <= LOW_REMAINING_THRESHOLD:
            # Spread whatever's left across the rest of the minute window
            # rather than burning through it at the steady-state pace.
            min_gap = 60.0 / max(self._remaining, 1)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)

    def _get(self, url: str, params: dict) -> dict:
        self._throttle()
        resp = self._session.get(url, headers=self._headers, params=params, timeout=10)
        self._last_request_at = time.monotonic()
        remaining_header = resp.headers.get("X-Discogs-Ratelimit-Remaining")
        if remaining_header is not None:
            self._remaining = int(remaining_header)
        resp.raise_for_status()
        return resp.json()

    def search_by_barcode(self, barcode: str) -> list[dict]:
        """Tries the barcode as given, then a UPC-12/EAN-13 leading-zero
        variant if the first search comes back empty (PLAN.md Stage 1 step 1).
        Digits-only/whitespace/dash differences are already handled by
        Discogs' own search — no punctuation stripping needed here."""
        results = self._search(barcode=barcode)
        if results:
            return results

        variant = self._zero_pad_variant(barcode)
        if variant is None:
            return []
        return self._search(barcode=variant)

    @staticmethod
    def _zero_pad_variant(barcode: str) -> str | None:
        digits = barcode.strip()
        if len(digits) == 12:
            return "0" + digits  # UPC-12 -> EAN-13
        if len(digits) == 13 and digits.startswith("0"):
            return digits[1:]  # EAN-13 -> UPC-12
        return None

    def _search(self, **params: str) -> list[dict]:
        data = self._get(f"{API_BASE}/database/search", params={**params, "type": "release"})
        return data.get("results", [])

    def search_by_artist_title_year(self, artist: str, title: str, year: int) -> list[dict]:
        return self._search(artist=artist, release_title=title, year=str(year))

    def get_master(self, master_id: int) -> dict:
        return self._get(f"{API_BASE}/masters/{master_id}", params={})
