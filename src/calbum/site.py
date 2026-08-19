"""Stage 4: emit the frontend payload from data/albums.json.

Runs last in the pipeline (poll -> overrides -> enrich -> sheets -> site),
writing web/src/data/albums.json for the React app to import.

**Build-time import, not a runtime fetch.** PLAN.md Stage 4 step 1 originally
said emit to web/public/ and fetch it same-origin. The stated reason was that
the data must ship as part of the deploy rather than be pulled from
raw.githubusercontent — which a build-time import satisfies equally, while
also removing the loading state, the fetch-error state, and one request from
first paint. At ~250 bytes/album the payload is ~8KB today and ~125KB at 500
albums, so inlining stays comfortable well past any realistic catalog size.
Revisit only if that stops being true.

Only active albums are emitted, and only the fields the UI actually renders —
`upc`, `discogs_release_id`, `added_at`, `removed_at`, and genre provenance
all stay server-side. Genre `source` in particular is an auditing detail
(constraint 6); the frontend just needs the names.
"""

from __future__ import annotations

import logging

from calbum.models import Album
from calbum.paths import ALBUMS_PATH, SITE_DATA_PATH
from calbum.writer import read_albums, write_json_atomic

logger = logging.getLogger(__name__)


def build_site_payload(active: list[Album]) -> list[dict]:
    """Pure function — no I/O — so it's what tests exercise directly, same
    pattern as sheets.build_albums_tab_rows.

    Sorted by year descending then title, matching the frontend's default
    view, so the emitted file is stable and the UI needs no initial sort.
    """
    ordered = sorted(active, key=lambda a: (-a.release_year, a.title.lower()))
    return [
        {
            "id": album.id,
            "title": album.title,
            "artists": album.artists,
            "year": album.release_year,
            "genres": album.genre_names,
            "styles": album.style_names,
            "cover": album.cover_url,
            # None for a manual album — the UI renders those non-interactive
            # rather than as a dead link.
            "url": album.spotify_url,
        }
        for album in ordered
    ]


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    albums = read_albums(ALBUMS_PATH)
    active = [a for a in albums if a.is_active]
    payload = build_site_payload(active)

    SITE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Reuses the deterministic atomic writer (constraint 1) so this file
    # produces no noise diffs either.
    write_json_atomic(SITE_DATA_PATH, payload)

    missing_art = sum(1 for a in payload if not a["cover"])
    logger.info(
        "Wrote %d albums to %s%s",
        len(payload),
        SITE_DATA_PATH,
        f" ({missing_art} without cover art)" if missing_art else "",
    )


if __name__ == "__main__":
    run()
