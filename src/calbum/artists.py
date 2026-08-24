"""Stage 7: emit artist portraits for the frontend's Artists tab.

Runs after site.py (poll -> overrides -> enrich -> sheets -> site -> artists),
writing web/src/data/artists.json alongside albums.json.

Spotify's cached album blobs carry each artist's id and name but no `images`,
so portraits are the one thing here that needs a network call. Artist blobs
are cached write-once under data/raw/spotify/artists/ exactly like album
blobs, which makes a re-run a no-op costing zero requests.

The payload carries only what the frontend cannot derive: id, name, portrait.
Album counts and year spans are computable from albums.json, and duplicating
them here would create a second source of truth that drifts.
"""

from __future__ import annotations

import logging
from typing import Protocol

from calbum.models import Album
from calbum.paths import DATA_DIR, ALBUMS_PATH, SITE_ARTISTS_PATH
from calbum.raw_cache import RawCache
from calbum.spotify.auth import get_access_token
from calbum.spotify.images import pick_image
from calbum.writer import read_albums, write_json_atomic

logger = logging.getLogger(__name__)

# Rendered at 44px (and 34px in the loyalty lanes), so the 320px asset is the
# right trade: crisp on a 3x display without shipping Spotify's 640px file.
PORTRAIT_MIN_WIDTH = 320


def _cache() -> RawCache:
    """The artist blob cache — a sibling directory to poll.py's album cache
    rather than the same one, since data/raw/spotify/ is a flat {id}.json
    namespace with no type discriminator and an ID collision there would hand
    back an artist where an album was expected.

    Built per call rather than once at import, matching enrich.py: tests
    monkeypatch this module's DATA_DIR (see tests/conftest.py), and a
    module-level instance would capture the real path before that lands."""
    return RawCache(DATA_DIR / "raw" / "spotify" / "artists")


class ArtistSource(Protocol):
    """The one capability this stage needs from a music-service client.

    Declared by the consumer, mirroring poll.py's AlbumSource, so a mock or a
    different client satisfies it structurally without importing anything
    Spotify-specific."""

    def get_artist(self, artist_id: str) -> dict: ...


def artist_ids_in(albums: list[Album]) -> list[str]:
    """Every distinct Spotify artist ID across active albums, in first-seen
    order so the emitted file stays stable run to run.

    All artists, not just each album's primary: which one is "primary" is a
    frontend presentation choice, and fetching the rest costs nothing after
    the first run."""
    seen: dict[str, None] = {}
    for album in albums:
        for artist_id in album.artist_ids:
            seen.setdefault(artist_id, None)
    return list(seen)


def build_artists_payload(blobs: list[dict]) -> list[dict]:
    """Pure — no I/O — so tests exercise it directly, same pattern as
    site.build_site_payload. Sorted by name so the file is deterministic."""
    return [
        {
            "id": blob["id"],
            "name": blob["name"],
            "portrait": pick_image(blob.get("images"), PORTRAIT_MIN_WIDTH),
        }
        for blob in sorted(blobs, key=lambda b: b["name"].lower())
    ]


def fetch_blobs(client: ArtistSource, cache: RawCache, artist_ids: list[str]) -> list[dict]:
    """Cached blob per ID, fetching only what's missing. Returns blobs in the
    order the IDs were given; a fetch that fails is logged and skipped rather
    than aborting — one dead artist shouldn't cost the whole file."""
    blobs = []
    fetched = 0
    for artist_id in artist_ids:
        blob = cache.load(artist_id)
        if blob is None:
            try:
                blob = client.get_artist(artist_id)
            except Exception as exc:  # noqa: BLE001 — degrade, don't abort
                logger.warning("Skipping artist %s: %s", artist_id, exc)
                continue
            cache.store_if_absent(artist_id, blob)
            fetched += 1
        blobs.append(blob)
    logger.info("%d artists (%d fetched, %d cached)", len(blobs), fetched, len(blobs) - fetched)
    return blobs


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from calbum.spotify.client import SpotifyClient

    albums = [a for a in read_albums(ALBUMS_PATH) if a.is_active]
    artist_ids = artist_ids_in(albums)
    if artist_ids:
        client = SpotifyClient(get_access_token())
        payload = build_artists_payload(fetch_blobs(client, _cache(), artist_ids))
    else:
        # Skip the OAuth round-trip and client construction — there is
        # nothing to fetch. Still writes an empty file below rather than
        # leaving a stale one, so the frontend payload reflects reality.
        logger.warning(
            "No artist_ids on any album — run poll.py first to backfill them "
            "from the cached blobs (no API calls needed)."
        )
        payload = []

    SITE_ARTISTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(SITE_ARTISTS_PATH, payload)

    missing = sum(1 for a in payload if not a["portrait"])
    logger.info(
        "Wrote %d artists to %s%s",
        len(payload),
        SITE_ARTISTS_PATH,
        f" ({missing} without a portrait)" if missing else "",
    )


if __name__ == "__main__":
    run()
