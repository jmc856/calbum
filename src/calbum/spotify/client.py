"""HTTP session for Spotify's Web API: retry/backoff and pagination.

See PLAN.md decision 7: requests.Session + HTTPAdapter/urllib3.Retry, 429 in
status_forcelist, honors Retry-After natively. A 429 is retried transparently
inside this client and never surfaces to callers as a partial read — it does
not trip poll.py's mass-removal guard.
"""

from __future__ import annotations

from collections.abc import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_BASE = "https://api.spotify.com/v1"

_RETRY = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    respect_retry_after_header=True,
)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=_RETRY))
    return session


class SpotifyClient:
    """One retrying Session, bearer auth, and pagination helpers over the
    handful of endpoints Stage 0 needs."""

    def __init__(self, access_token: str):
        self._session = _build_session()
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def get(self, url: str, params: dict | None = None) -> dict:
        resp = self._session.get(url, headers=self._headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def paginate(self, url: str, params: dict | None = None) -> Iterator[dict]:
        """Yield every item across a Spotify cursor-paginated `items` response."""
        while url:
            page = self.get(url, params=params)
            yield from page.get("items", [])
            url = page.get("next")
            params = None  # `next` already encodes the query params

    def find_playlist_id(self, name: str) -> str | None:
        for playlist in self.paginate(f"{API_BASE}/me/playlists", {"limit": 50}):
            if playlist["name"] == name:
                return playlist["id"]
        return None

    def playlist_items(self, playlist_id: str) -> Iterator[dict]:
        # /items, not /tracks — see PLAN.md "Spotify Web API gotchas".
        yield from self.paginate(
            f"{API_BASE}/playlists/{playlist_id}/items", {"limit": 50}
        )

    def get_album(self, album_id: str) -> dict:
        return self.get(f"{API_BASE}/albums/{album_id}")

    def get_artist(self, artist_id: str) -> dict:
        # One at a time, deliberately: the batched /v1/artists?ids= endpoint
        # returns 403 for this app, while the single-artist form works. That
        # also keeps the artist cache 1:1 fetch->blob, like the album cache.
        return self.get(f"{API_BASE}/artists/{artist_id}")
