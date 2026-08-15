"""Stage 1: enrich data/albums.json with genres via the Discogs cascade.

Cascade per PLAN.md Stage 1: Discogs-by-barcode -> Discogs-by-search ->
(MusicBrainz — not built; the UPC probe came back present and the coverage
report below is what decides whether a further source is worth adding, not
an assumption). `_overrides` (Stage 3, highest precedence) doesn't exist yet
either.

Only albums with `genres == []` are touched — an album that already has
genres, from any run, is left alone. Every write goes through
`Album.model_copy(update={...})`, never a fresh `Album(...)` construction,
so fields this module doesn't own (`added_at`, `removed_at`, everything
Stage 0 wrote) are byte-for-byte untouched — decision 12 froze `added_at`
inside poll.py's writer; this is the second writer to the same file and
needs the same discipline, just enforced structurally instead of by a guard.

Enrichment cache (data/raw/discogs/{album_id}.json) is write-once (constraint
4): an album that already has a cache file is re-normalized from it, never
re-queried. Deleting that file is the escape hatch that forces a re-query —
how a genre gets retroactively upgraded from a coarser source.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from calbum.models import Album, Genre, GenreSource
from calbum.paths import ALBUMS_PATH, DATA_DIR
from calbum.writer import read_albums, write_albums

load_dotenv()

RAW_DISCOGS_DIR = DATA_DIR / "raw" / "discogs"

USER_AGENT = "calbum/0.1 +https://github.com/jmc856/calbum"

logger = logging.getLogger(__name__)


class GenreLookup(Protocol):
    """The only capabilities enrich.py needs from a Discogs-shaped client.
    Defined here, by the consumer — same pattern as poll.py's AlbumSource."""

    def search_by_barcode(self, barcode: str) -> list[dict]: ...
    def search_by_artist_title_year(self, artist: str, title: str, year: int) -> list[dict]: ...
    def get_master(self, master_id: int) -> dict: ...


def cache_path(album_id: str) -> Path:
    return RAW_DISCOGS_DIR / f"{album_id}.json"


def load_cache(album_id: str) -> dict | None:
    path = cache_path(album_id)
    if path.exists():
        return json.loads(path.read_text())
    return None


def write_cache(album_id: str, data: dict) -> None:
    RAW_DISCOGS_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(album_id).write_text(json.dumps(data, indent=2) + "\n")


def strip_edition_suffix(title: str) -> str | None:
    """Strip a trailing parenthetical like "(Deluxe)", "(Remastered)",
    "(Expanded Edition)" — Discogs' own release_title search is close to
    exact-match and doesn't tolerate these even though Discogs lists the
    release itself (confirmed live: "good kid, m.A.A.d city (Deluxe)" finds
    0 results, "good kid, m.A.A.d city" finds 50, same master). Spotify
    appends these routinely; Discogs titles usually don't carry them. Returns
    None when there's nothing to strip, so the caller can skip a redundant
    identical retry."""
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
    return stripped if stripped and stripped != title else None


def choose_best_result(results: list[dict]) -> dict | None:
    """Deterministic tiebreak, not result[0] (PLAN.md Stage 1 step 2):
    prefer a result with master_id set (lowest master_id, for stability
    across re-runs after a cache delete); otherwise the lowest id."""
    if not results:
        return None
    with_master = [r for r in results if r.get("master_id") is not None]
    if with_master:
        return min(with_master, key=lambda r: r["master_id"])
    return min(results, key=lambda r: r["id"])


def _genres_from_fields(
    genre_names: list[str],
    style_names: list[str],
    genre_source: GenreSource,
    style_source: GenreSource,
) -> list[Genre]:
    return [Genre(name=n, kind="genre", source=genre_source) for n in genre_names] + [
        Genre(name=n, kind="style", source=style_source) for n in style_names
    ]


def enrich_album(client: GenreLookup, album: Album) -> Album:
    """Runs the cascade for one album already missing genres."""
    cached = load_cache(album.id)
    if cached is not None:
        genres = [Genre.model_validate(g) for g in cached["genres"]]
        return album.model_copy(
            update={"genres": genres, "discogs_release_id": cached.get("discogs_release_id")}
        )

    barcode_results: list[dict] = []
    if album.upc:
        barcode_results = client.search_by_barcode(album.upc)

    queried_title = album.title  # overwritten below only if the stripped-suffix retry is what hit

    if barcode_results:
        step = "barcode"
        results = barcode_results
        # Genre and style get distinct source values on a barcode hit
        # (constraint 6) — kind already says which tier, source additionally
        # says which cascade step, for both.
        genre_source, style_source = GenreSource.DISCOGS_GENRE, GenreSource.DISCOGS_STYLE
    else:
        step = "search"
        artist = album.artists[0] if album.artists else ""
        results = client.search_by_artist_title_year(artist, queried_title, album.release_year)
        if not results:
            # Retry once with a trailing "(Deluxe)"/"(Remastered)"/etc.
            # suffix stripped — see strip_edition_suffix. Only retried when
            # the full title actually found nothing, so an album that's
            # genuinely just missing from Discogs still costs one search,
            # not two.
            stripped_title = strip_edition_suffix(album.title)
            if stripped_title:
                results = client.search_by_artist_title_year(
                    artist, stripped_title, album.release_year
                )
                if results:
                    queried_title = stripped_title
        # A search hit doesn't distinguish further by tier — both genre and
        # style entries carry the same source value (constraint 6).
        genre_source = style_source = GenreSource.DISCOGS_SEARCH

    chosen = choose_best_result(results)
    discogs_release_id: int | None = None
    genres: list[Genre] = []

    if chosen is not None:
        master_id = chosen.get("master_id")
        if master_id is not None:
            # The master aggregates genre/style across pressings and was
            # confirmed (against live data) to be more complete than any
            # single pressing's own fields — worth the extra request.
            master = client.get_master(master_id)
            genres = _genres_from_fields(
                master.get("genres", []), master.get("styles", []), genre_source, style_source
            )
            discogs_release_id = master_id
        else:
            genres = _genres_from_fields(
                chosen.get("genre", []), chosen.get("style", []), genre_source, style_source
            )

    write_cache(
        album.id,
        {
            "step": step,
            "query": {
                "upc": album.upc,
                "artist": album.artists[0] if album.artists else None,
                "title": queried_title,
                "year": album.release_year,
            },
            "results": results,
            "discogs_release_id": discogs_release_id,
            "genres": [g.model_dump(mode="json") for g in genres],
        },
    )

    return album.model_copy(update={"genres": genres, "discogs_release_id": discogs_release_id})


def build_coverage_report(albums: list[Album]) -> dict:
    """PLAN.md Stage 1 step 8: counts by source, and how many albums still
    lack a sub-genre — decides whether a further source is worth adding, not
    an assumption."""
    total = len(albums)
    with_primary = 0
    with_sub = 0
    by_source: dict[str, int] = {}

    for album in albums:
        if album.genre_names:
            with_primary += 1
        if album.style_names:
            with_sub += 1
        if album.genres:
            primary = next((g for g in album.genres if g.kind == "genre"), album.genres[0])
            by_source[primary.source.value] = by_source.get(primary.source.value, 0) + 1

    return {
        "total": total,
        "with_primary_genre": with_primary,
        "with_sub_genre": with_sub,
        "missing_sub_genre": total - with_sub,
        "by_source": by_source,
    }


def print_coverage_report(report: dict) -> None:
    print("\n--- Coverage report ---")
    print(f"Total albums: {report['total']}")
    print(f"With primary genre: {report['with_primary_genre']}")
    print(f"With sub-genre: {report['with_sub_genre']}")
    print(f"Missing sub-genre: {report['missing_sub_genre']}")
    print("By source:")
    for source, count in sorted(report["by_source"].items()):
        print(f"  {source}: {count}")


def run() -> None:
    # Imported here, not at module level — same pattern as poll.py's run():
    # everything above this function depends only on the GenreLookup
    # protocol, not on DiscogsClient.
    from calbum.discogs.client import DiscogsClient

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    client = DiscogsClient(os.environ["DISCOGS_TOKEN"], USER_AGENT)

    albums = read_albums(ALBUMS_PATH)
    updated: list[Album] = []

    for album in albums:
        if album.genres:
            updated.append(album)
            continue
        try:
            updated.append(enrich_album(client, album))
        except Exception as exc:  # decision 2: one bad album degrades, never aborts
            logger.warning("Skipping enrichment for %s: %s", album.id, exc)
            updated.append(album)

    write_albums(ALBUMS_PATH, updated)

    report = build_coverage_report(updated)
    print_coverage_report(report)


if __name__ == "__main__":
    run()
