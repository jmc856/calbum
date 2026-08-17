"""Stage 3: apply data/overrides.toml to data/albums.json.

Runs between poll and enrich (poll -> overrides -> enrich -> sheets). One
hand-edited file, one rule: each entry is keyed by album id.

  - Key matches an existing album  -> patches that album's fields (a
    correction).
  - Key matches no existing album  -> inserted as a new album with
    source="manual" (an album that doesn't exist on Spotify at all).

Running before enrich means a manual album with no genres yet gets filled in
by the Discogs cascade automatically (enrich.run() only touches albums with
`genres == []`), and a corrected `title` is what enrich then sends to
Discogs' search — fixing bad title matches at the source.

Genre reversibility: deleting an override row (or its genres/styles keys)
resets that album's genres back to `[]` if they were override-sourced,
which is exactly what makes enrich.run() re-derive them from Discogs on the
next run. Scalar-field overrides (title, release_date, ...) are NOT
reversible this way — nothing records the pre-override value, so undoing
one means editing the TOML back to the old value, not deleting the row.
This is a deliberate simplification: the common case (a wrong genre) is
fully reversible in a few lines; full undo history for every field is not
worth the machinery.

This file replaced the `_overrides` Google Sheet tab from the original
Stage 3 design (see PLAN.md): a Sheet that's both a generated output and a
hand-edited input is confusing, it would put manual-album identity behind
the Sheets API, and it gets no git history — a repo file does, for free,
matching how this project already treats albums.json as its audit log.
"""

from __future__ import annotations

import logging
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

from calbum.models import Album, Genre, GenreSource
from calbum.paths import ALBUMS_PATH, OVERRIDES_PATH
from calbum.poll import parse_release_date
from calbum.writer import read_albums, write_albums

logger = logging.getLogger(__name__)

# Album fields an override entry may patch directly (verbatim, no special
# handling). genres/styles are handled separately (they build Genre records,
# tagged with provenance); "note" is TOML-only documentation, never stored.
# cover_url matters most for a manual album (no Spotify art to backfill from)
# but is patchable on any album, same as every other scalar field.
_SCALAR_FIELDS = {"artists", "title", "release_date", "album_type", "upc", "added_at", "cover_url"}
_KNOWN_FIELDS = _SCALAR_FIELDS | {"genres", "styles", "note"}

# A manual album (id not already in the catalog) needs at least these to be
# constructible at all.
_REQUIRED_FOR_MANUAL = {"artists", "title", "release_date"}


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, dict]:
    """The file is optional — a fresh clone with no overrides.toml must work
    identically to one with an empty file."""
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _override_genres(entry: dict) -> list[Genre]:
    return [
        Genre(name=name, kind="genre", source=GenreSource.OVERRIDE) for name in entry.get("genres", [])
    ] + [
        Genre(name=name, kind="style", source=GenreSource.OVERRIDE) for name in entry.get("styles", [])
    ]


def _has_override_genres(album: Album) -> bool:
    return any(g.source == GenreSource.OVERRIDE for g in album.genres)


def _as_date(value: object) -> date:
    # TOML's native date literal (2002-02-18) already parses to datetime.date
    # via tomllib; a quoted string falls back to the same lenient,
    # partial-precision parser poll.py uses for Spotify's release_date.
    return value if isinstance(value, date) else parse_release_date(str(value))


def _as_added_at(value: object, default: datetime) -> datetime:
    if value is None:
        return default
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _patch_album(album: Album, entry: dict) -> Album:
    unknown = set(entry) - _KNOWN_FIELDS
    if unknown:
        logger.warning("Override for %s has unrecognized field(s), ignored: %s", album.id, sorted(unknown))

    update: dict = {k: entry[k] for k in _SCALAR_FIELDS if k in entry}
    if "release_date" in update:
        update["release_date"] = _as_date(update["release_date"])
        update["release_year"] = update["release_date"].year
    if "added_at" in update:
        update["added_at"] = _as_added_at(update["added_at"], album.added_at)

    if "genres" in entry or "styles" in entry:
        update["genres"] = _override_genres(entry)
        update["discogs_release_id"] = None
    elif _has_override_genres(album):
        # The row no longer specifies genres/styles (or was removed
        # entirely — see apply_overrides) but this album still carries
        # override-sourced genres from a previous run. Reset to [] so
        # enrich.run() re-derives them from Discogs on the next run.
        update["genres"] = []
        update["discogs_release_id"] = None

    return album.model_copy(update=update)


def _new_manual_album(album_id: str, entry: dict, now: datetime) -> Album | None:
    unknown = set(entry) - _KNOWN_FIELDS
    if unknown:
        logger.warning("Override for %s has unrecognized field(s), ignored: %s", album_id, sorted(unknown))

    missing = _REQUIRED_FOR_MANUAL - set(entry)
    if missing:
        logger.warning(
            "Skipping override %r: not an existing album id, and missing required "
            "field(s) to add it as a manual album: %s",
            album_id,
            sorted(missing),
        )
        return None

    release_date = _as_date(entry["release_date"])
    return Album(
        id=album_id,
        artists=entry["artists"],
        title=entry["title"],
        release_date=release_date,
        release_year=release_date.year,
        album_type=entry.get("album_type", "album"),
        upc=entry.get("upc"),
        added_at=_as_added_at(entry.get("added_at"), now),
        removed_at=None,
        genres=_override_genres(entry),
        source="manual",
        cover_url=entry.get("cover_url"),
    )


def apply_overrides(albums: list[Album], overrides: dict[str, dict], now: datetime) -> list[Album]:
    """Pure function — no I/O — so it's what tests exercise directly."""
    result: dict[str, Album] = {a.id: a for a in albums}

    # Un-override anything whose row is gone but still carries
    # override-sourced genres from a previous run (see _patch_album's
    # docstring note on reversibility).
    for album_id, album in list(result.items()):
        if album_id not in overrides and _has_override_genres(album):
            result[album_id] = album.model_copy(update={"genres": [], "discogs_release_id": None})

    for album_id, entry in overrides.items():
        try:
            if album_id in result:
                result[album_id] = _patch_album(result[album_id], entry)
            else:
                new_album = _new_manual_album(album_id, entry, now)
                if new_album is not None:
                    result[album_id] = new_album
        except Exception as exc:  # decision 2: one bad row degrades, never aborts
            logger.warning("Skipping override %r: %s: %s", album_id, type(exc).__name__, exc)

    return list(result.values())


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    albums = read_albums(ALBUMS_PATH)
    overrides = load_overrides(OVERRIDES_PATH)
    updated = apply_overrides(albums, overrides, datetime.now(UTC))
    write_albums(ALBUMS_PATH, updated)

    logger.info("Applied %d override row(s) from %s to %s", len(overrides), OVERRIDES_PATH, ALBUMS_PATH)


if __name__ == "__main__":
    run()
