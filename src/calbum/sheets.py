"""Stage 2: regenerate the shared Google Sheet from data/albums.json.

Clear-then-write, never incremental (PLAN.md Stage 2 step 2): every
generated tab is deleted and recreated from scratch each run, both because
that's simpler than diffing and because it's what makes "delete a tab by
hand, next run rebuilds it" (the stage's own done-when) true for free —
there's no separate "did this tab drift from source" logic to get right.

A flat Albums tab (Year as a column, not a tab-per-year split) plus a
by-genre tab. Only active albums (Album.is_active) are shown — the Sheet
reflects your current keepers, not the full history of everything ever added
to _selected (that history still lives in albums.json/git either way).

Genre/Sub-genre on the Albums tab are joined-string context columns, not the
filter surface — by-genre (one row per album x genre) is where filtering and
grouping by an individual genre actually works in Sheets. See PLAN.md Stage 2
"Future work" for the deferred Artists and by-style tabs.
"""

from __future__ import annotations

import base64
import os
from typing import Protocol

from dotenv import load_dotenv

from calbum.models import Album
from calbum.paths import ALBUMS_PATH
from calbum.writer import read_albums

load_dotenv()

ALBUMS_TAB_HEADER = ["Album", "Artist(s)", "Year", "Release Date", "Genre", "Sub-genre"]
GENRE_TAB_HEADER = ["Genre", "Sub-genre", "Album", "Artist(s)", "Year"]
UNCATEGORIZED = "(Uncategorized)"

# NOT ", " — some Discogs genre names contain a literal comma themselves
# (e.g. "Folk, World, & Country"), confirmed live: joining with ", " makes
# ["Rock", "Folk, World, & Country"] unreadable as "how many genres is
# that?". Artist names have the same risk ("Earth, Wind & Fire"), so this is
# used everywhere multiple values get joined into one cell, not just genres.
MULTI_VALUE_SEP = "; "


class SheetBackend(Protocol):
    """The only capability sheets.py needs: replace a tab's entire contents
    (create-if-missing, clear-if-present, write, freeze header, protect).
    Defined here, by the consumer — same pattern as poll.py's AlbumSource
    and enrich.py's GenreLookup."""

    def replace_tab(self, title: str, rows: list[list[object]]) -> None: ...


def hyperlink(album: Album) -> str:
    title = album.title.replace('"', '""')
    return f'=HYPERLINK("{album.spotify_url}", "{title}")'


def build_albums_tab_rows(albums: list[Album]) -> list[list[object]]:
    """One row per active album, flat (no per-year split — Year is a column).
    Sorted by title."""
    active = [a for a in albums if a.is_active]

    rows: list[list[object]] = [list(ALBUMS_TAB_HEADER)]
    for album in sorted(active, key=lambda a: a.title.lower()):
        rows.append(
            [
                hyperlink(album),
                MULTI_VALUE_SEP.join(album.artists),
                album.release_year,
                album.release_date.isoformat(),
                MULTI_VALUE_SEP.join(album.genre_names),
                MULTI_VALUE_SEP.join(album.style_names),
            ]
        )
    return rows


def build_genre_tab_rows(albums: list[Album]) -> list[list[object]]:
    """One row per (album, primary genre) pair — an album with more than one
    primary genre appears once per genre, which is the point of a
    browse-by-genre tab. Albums with no genre yet are grouped under
    "(Uncategorized)" rather than silently omitted, so an un-enriched album
    stays visible instead of just vanishing from this tab."""
    active = [a for a in albums if a.is_active]

    entries: list[tuple[str, Album]] = []
    for album in active:
        genre_names = album.genre_names
        if genre_names:
            entries.extend((name, album) for name in genre_names)
        else:
            entries.append((UNCATEGORIZED, album))

    entries.sort(key=lambda pair: (pair[0].lower(), pair[1].title.lower()))

    rows: list[list[object]] = [list(GENRE_TAB_HEADER)]
    for genre_name, album in entries:
        rows.append(
            [
                genre_name,
                MULTI_VALUE_SEP.join(album.style_names),
                hyperlink(album),
                MULTI_VALUE_SEP.join(album.artists),
                album.release_year,
            ]
        )
    return rows


def load_sa_json() -> str:
    """GOOGLE_SA_JSON_B64 is the service-account key JSON, base64-encoded —
    not stored as raw JSON. The key's private_key field embeds literal `\\n`
    sequences, and both python-dotenv (loading .env locally) and shells
    unescape those into real newlines depending on quoting, which corrupts
    the JSON (a raw newline inside a JSON string is invalid). Base64 has no
    quotes, backslashes, or newlines to mis-parse, so it survives any
    .env/shell/GitHub-Actions-secret round trip intact."""
    encoded = os.environ["GOOGLE_SA_JSON_B64"]
    return base64.b64decode(encoded).decode("utf-8")


def run() -> None:
    # Imported here, not at module level — same pattern as poll.py/enrich.py:
    # everything above this function depends only on the SheetBackend
    # protocol, not on gspread.
    from calbum.gsheets.backend import GspreadSheetBackend

    albums = read_albums(ALBUMS_PATH)
    backend: SheetBackend = GspreadSheetBackend(
        sa_json=load_sa_json(), sheet_id=os.environ["SHEET_ID"]
    )

    backend.replace_tab("Albums", build_albums_tab_rows(albums))
    backend.replace_tab("by-genre", build_genre_tab_rows(albums))


if __name__ == "__main__":
    run()
