"""Stage 0: resolve `_selected` -> data/albums.json.

`_selected` is the sole write surface and sole source of album identity —
see PLAN.md "Solution shape" and "Vet notes". This module:

1. Finds the `_selected` playlist and pages through its items, grouping by
   resolved album ID (skipping `is_local` items).
2. For each candidate album, fetches (write-once, constraint 3/4) and caches
   its full object to data/raw/spotify/{id}.json, then applies the
   partial-album-membership threshold (decision 11): an album only counts as
   kept if at least PARTIAL_ALBUM_THRESHOLD of its tracks are present in
   `_selected`. Below that, it's logged and skipped, not ingested.
3. Runs the mass-removal guard (constraint 7, decision 6) before writing
   anything.
4. Normalizes into Album records and writes data/albums.json via the
   deterministic, atomic writer.

added_at is frozen at first write and never recomputed on later polls
(decision 12). A previously-active album no longer resolvable gets
removed_at set, not deleted; a re-added album has removed_at cleared.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from calbum.models import Album
from calbum.paths import ALBUMS_PATH, DATA_DIR
from calbum.spotify.auth import get_access_token
from calbum.writer import read_albums, write_albums

RAW_SPOTIFY_DIR = DATA_DIR / "raw" / "spotify"


class AlbumSource(Protocol):
    """The only capabilities poll.py needs from a music-service client:
    resolve a playlist by name, page through its items, fetch one album.

    Defined here — by the consumer, not by spotify/client.py — so a
    different client (a different Spotify SDK, a mock, eventually a
    different service entirely) can satisfy this structurally without
    inheriting from anything Spotify-specific. `SpotifyClient` isn't
    imported by this module at all; `run()` imports it locally, right where
    the concrete choice is made."""

    def find_playlist_id(self, name: str) -> str | None: ...
    def playlist_items(self, playlist_id: str) -> Iterator[dict]: ...
    def get_album(self, album_id: str) -> dict: ...

PLAYLIST_NAME = "_selected"

# Decision 11: require most of an album's tracks present in _selected before
# counting it as kept, so a single stray track from a mix isn't captured.
PARTIAL_ALBUM_THRESHOLD = 0.90

# Decision 6 (constraint 7): below 50 albums any drop aborts; at/above 50, a
# drop of more than 10% aborts.
SMALL_CATALOG_SIZE = 50
MAX_DROP_FRACTION = 0.10

logger = logging.getLogger(__name__)


class MassRemovalAbort(SystemExit):
    """Raised (and left uncaught, for a non-zero exit) when the guard trips."""


def load_existing_albums() -> dict[str, Album]:
    """Cold start (no file at all) returns {}; a file that exists but parses
    to an empty list raises inside read_albums — see its docstring for why
    that's treated as data loss, not a fresh start. Not the same case:
    previous_active_count computing as 0 would let the mass-removal guard
    below never treat this run's result as a "drop"."""
    return {album.id: album for album in read_albums(ALBUMS_PATH)}


def parse_release_date(value: str) -> date:
    """Spotify's release_date can be year- or month-precision (see
    release_date_precision) as well as full YYYY-MM-DD. Pad missing
    components rather than failing the whole album — see decision 2,
    lenient-and-degrade at the boundary."""
    parts = value.split("-")
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else 1
    day = int(parts[2]) if len(parts) > 2 else 1
    return date(year, month, day)


def cache_path(album_id: str) -> Path:
    return RAW_SPOTIFY_DIR / f"{album_id}.json"


def fetch_and_cache_album(client: AlbumSource, album_id: str) -> dict:
    """Write-once (constraint 3/4): only hits the API if not already cached."""
    path = cache_path(album_id)
    if path.exists():
        return json.loads(path.read_text())
    album = client.get_album(album_id)
    RAW_SPOTIFY_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(album, indent=2) + "\n")
    return album


def resolve_playlist_items(client: AlbumSource, playlist_id: str) -> dict[str, list[dict]]:
    """Group playlist items by resolved album ID. See PLAN.md "gotchas": the
    per-item album path (item["item"]["album"]["id"] vs the older
    item["track"]["album"]["id"]) is confirmed by scripts/probe.py — this
    tries the new path first and falls back to the old one so poll.py keeps
    working across the rename either way."""
    by_album: dict[str, list[dict]] = {}
    for item in client.playlist_items(playlist_id):
        if item.get("is_local"):
            continue
        track_obj = item.get("item") or item.get("track")
        if not track_obj:
            continue
        album = track_obj.get("album") or {}
        album_id = album.get("id")
        if not album_id:
            continue
        by_album.setdefault(album_id, []).append(item)
    return by_album


def simplified_album(item: dict) -> dict:
    """The SimplifiedAlbumObject already embedded in a playlist item — no
    extra request needed. Used to apply the partial-album threshold before
    deciding whether an album is even worth fetching/caching."""
    track_obj = item.get("item") or item.get("track")
    return (track_obj or {}).get("album") or {}


def _below_threshold(present: int, total_tracks: int | None) -> bool:
    return bool(total_tracks) and present / total_tracks < PARTIAL_ALBUM_THRESHOLD


def resolve_candidates(
    client: AlbumSource, by_album: dict[str, list[dict]]
) -> dict[str, dict]:
    """Apply the partial-album threshold, then fetch/cache the full object
    for albums that pass. Returns {album_id: full_album_json}.

    The threshold is checked against the playlist item's already-present
    SimplifiedAlbumObject total_tracks first, so a stray track from a mix
    never triggers a fetch or a write-once cache write for an album that's
    then rejected (constraint 3/4: the raw cache is supposed to mirror only
    albums actually kept). SimplifiedAlbumObject's total_tracks is the same
    field name as on the full AlbumObject, but its presence there isn't
    documented, so this falls back to checking again after the full fetch —
    and deletes the cache file it just wrote if that late check rejects it."""
    resolved: dict[str, dict] = {}
    for album_id, items in by_album.items():
        present = len(items)

        pre_fetch_total = simplified_album(items[0]).get("total_tracks")
        if _below_threshold(present, pre_fetch_total):
            logger.warning(
                'Skipping %s: only %d/%d tracks present in "%s" (below %.0f%% '
                "threshold) — not counted as kept, never fetched.",
                album_id,
                present,
                pre_fetch_total,
                PLAYLIST_NAME,
                PARTIAL_ALBUM_THRESHOLD * 100,
            )
            continue

        full = fetch_and_cache_album(client, album_id)
        total_tracks = full.get("total_tracks", pre_fetch_total)
        if _below_threshold(present, total_tracks):
            cache_path(album_id).unlink(missing_ok=True)
            logger.warning(
                'Skipping %r (%s): only %d/%d tracks present in "%s" '
                "(below %.0f%% threshold, caught after fetch) — not counted "
                "as kept; cache write undone.",
                full.get("name", album_id),
                album_id,
                present,
                total_tracks,
                PLAYLIST_NAME,
                PARTIAL_ALBUM_THRESHOLD * 100,
            )
            continue

        resolved[album_id] = full
    return resolved


def earliest_added_at(items: list[dict]) -> datetime:
    timestamps = [
        datetime.fromisoformat(item["added_at"].replace("Z", "+00:00"))
        for item in items
        if item.get("added_at")
    ]
    return min(timestamps)


def check_mass_removal_guard(previous_active_count: int, new_active_count: int) -> None:
    """Abort before writing if the resolved album count dropped too much
    (constraint 7, decision 6). Cold start is handled by the caller never
    invoking this when there was no prior albums.json."""
    if new_active_count >= previous_active_count:
        return
    if previous_active_count < SMALL_CATALOG_SIZE:
        raise MassRemovalAbort(
            f"Mass-removal guard tripped: catalog has {previous_active_count} "
            f"active albums (< {SMALL_CATALOG_SIZE}), so any drop aborts. "
            f"This run resolved {new_active_count}. Aborting without writing — "
            "investigate before re-running."
        )
    drop_fraction = (previous_active_count - new_active_count) / previous_active_count
    if drop_fraction > MAX_DROP_FRACTION:
        raise MassRemovalAbort(
            f"Mass-removal guard tripped: {previous_active_count} -> "
            f"{new_active_count} active albums is a {drop_fraction:.0%} drop "
            f"(> {MAX_DROP_FRACTION:.0%} threshold). Aborting without writing — "
            "investigate before re-running."
        )


def build_albums(
    existing: dict[str, Album],
    resolved: dict[str, dict],
    by_album: dict[str, list[dict]],
    now: datetime,
) -> list[Album]:
    result: dict[str, Album] = dict(existing)

    for album_id, full in resolved.items():
        if album_id in existing:
            # Known album: added_at is frozen (decision 12), never
            # recomputed from playlist state. Clear removed_at if it was
            # previously removed and has now reappeared.
            album = existing[album_id]
            if not album.is_active:
                result[album_id] = album.model_copy(update={"removed_at": None})
            continue

        # Decision 2: lenient at the boundary. One malformed album must
        # degrade, not abort the whole run — its raw blob is already cached
        # (resolve_candidates ran first), so it can be re-normalized later
        # with no re-fetch once whatever's wrong is fixed.
        try:
            release_date = parse_release_date(full["release_date"])
            new_album = Album(
                id=album_id,
                artists=[a["name"] for a in full.get("artists", [])],
                title=full["name"],
                release_date=release_date,
                release_year=release_date.year,
                album_type=full["album_type"],
                upc=full.get("external_ids", {}).get("upc"),
                added_at=earliest_added_at(by_album[album_id]),
                removed_at=None,
                genres=[],
                source="spotify",
            )
        except (KeyError, ValueError) as exc:
            logger.warning(
                "Skipping %s: failed to normalize (%s: %s). Raw blob is "
                "still cached; will retry on the next run once fixed.",
                album_id,
                type(exc).__name__,
                exc,
            )
            continue

        result[album_id] = new_album

    # Previously active but not resolved this run -> removed_at, not deleted.
    for album_id, album in existing.items():
        if album_id not in resolved and album.is_active:
            result[album_id] = album.model_copy(update={"removed_at": now})

    return list(result.values())


def run() -> None:
    # Imported here, not at module level: this is the one place the concrete
    # client is chosen. Everything above this function depends only on the
    # AlbumSource protocol, not on SpotifyClient.
    from calbum.spotify.client import SpotifyClient

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    existing = load_existing_albums()
    previous_active_count = sum(1 for a in existing.values() if a.is_active)

    access_token = get_access_token()
    client: AlbumSource = SpotifyClient(access_token)

    playlist_id = client.find_playlist_id(PLAYLIST_NAME)
    if playlist_id is None:
        raise SystemExit(
            f'No playlist named "{PLAYLIST_NAME}" found. Create it by hand '
            "first (see PLAN.md Prereqs)."
        )

    by_album = resolve_playlist_items(client, playlist_id)
    resolved = resolve_candidates(client, by_album)

    # Cold start (no albums.json at all) skips the guard; an existing-but-
    # empty file already raised inside read_albums(), via load_existing_albums.
    if existing:
        check_mass_removal_guard(previous_active_count, len(resolved))

    now = datetime.now(UTC)
    albums = build_albums(existing, resolved, by_album, now)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_albums(ALBUMS_PATH, albums)

    active = sum(1 for a in albums if a.is_active)
    logger.info("Wrote %d albums (%d active) to %s", len(albums), active, ALBUMS_PATH)


if __name__ == "__main__":
    run()
