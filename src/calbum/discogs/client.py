"""HTTP client for the Discogs API: proactive rate limiting and the barcode
normalization PLAN.md Stage 1 calls for.

Discogs is 60 req/min *authenticated*, and every response carries
X-Discogs-Ratelimit-Remaining — unlike Spotify's occasional 429, this limit
is expected to be approached routinely during a real enrichment run, so this
throttles proactively between requests rather than retrying after a 429
(see PLAN.md decision 7's contrast: Spotify's client is a good template for
its own problem, not for this one). A Retry adapter still sits underneath,
matching spotify/client.py's resilience pattern, for the 429/5xx cases the
proactive throttle doesn't fully prevent.
"""

from __future__ import annotations

import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from calbum.discogs.schemas import DiscogsMaster, DiscogsSearchResult

API_BASE = "https://api.discogs.com"

# 60/min authenticated -> a request roughly every second keeps remaining from
# ever hitting zero under steady load. Below LOW_REMAINING_THRESHOLD, slow
# down further in proportion to what's left, rather than blindly continuing
# at the steady-state pace until a 429 actually happens.
STEADY_STATE_INTERVAL = 1.0
LOW_REMAINING_THRESHOLD = 5

_RETRY = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    respect_retry_after_header=True,
)


class DiscogsAuthError(Exception):
    """A 401/403 from Discogs — an expired/invalid DISCOGS_TOKEN, not a
    per-album data problem. Distinct from data-shaped failures so run() can
    let this propagate and fail loudly instead of degrading album-by-album
    (an expired token would otherwise 401 every request, log N warnings, and
    still exit 0)."""


def _build_session() -> requests.Session:
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=_RETRY))
    return session


class DiscogsClient:
    def __init__(self, token: str, user_agent: str):
        self._session = _build_session()
        self._headers = {
            "Authorization": f"Discogs token={token}",
            "User-Agent": user_agent,
        }
        self._last_request_at: float | None = None
        self._remaining: int | None = None

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        if self._remaining is not None and self._remaining <= LOW_REMAINING_THRESHOLD:
            # Spread whatever's left across the rest of the minute window
            # rather than burning through it at the steady-state pace.
            min_gap = 60.0 / max(self._remaining, 1)
            if elapsed < min_gap:
                time.sleep(min_gap - elapsed)
        # Above the low-remaining threshold, don't sleep at all — the header
        # already says there's ample budget; STEADY_STATE_INTERVAL is a
        # ceiling for the low-remaining case, not a floor on every request.

    def _get(self, url: str, params: dict) -> dict:
        self._throttle()
        # Stamped before the request, not after: the gap between requests is
        # meant to be measured request-start to request-start. Stamping
        # after resp returns would silently fold each response's RTT into
        # the gap on top of the intended interval, under-using the allowed
        # rate.
        self._last_request_at = time.monotonic()
        resp = self._session.get(url, headers=self._headers, params=params, timeout=10)
        remaining_header = resp.headers.get("X-Discogs-Ratelimit-Remaining")
        if remaining_header is not None:
            self._remaining = int(remaining_header)
        if resp.status_code in (401, 403):
            raise DiscogsAuthError(
                f"Discogs returned {resp.status_code} for {url} — DISCOGS_TOKEN "
                "is likely missing, expired, or invalid."
            )
        resp.raise_for_status()
        return resp.json()

    def search_by_barcode(self, barcode: str) -> list[DiscogsSearchResult]:
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

    def _search(self, **params: str) -> list[DiscogsSearchResult]:
        data = self._get(f"{API_BASE}/database/search", params={**params, "type": "release"})
        return [DiscogsSearchResult.model_validate(r) for r in data.get("results", [])]

    def search_by_artist_title_year(self, artist: str, title: str, year: int) -> list[DiscogsSearchResult]:
        return self._search(artist=artist, release_title=title, year=str(year))

    def get_master(self, master_id: int) -> DiscogsMaster:
        data = self._get(f"{API_BASE}/masters/{master_id}", params={})
        return DiscogsMaster.model_validate(data)
