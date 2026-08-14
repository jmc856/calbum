"""Pydantic models for the canonical album record and the API payloads that
feed it. Validates shape at the boundary — external API responses (Spotify,
Discogs, MusicBrainz) come in here first; nothing downstream touches a raw
dict.

Note: pydantic's model_dump_json() does NOT sort keys or guarantee our
deterministic-serialization contract (see PLAN.md "Non-negotiable
implementation constraints" #1). Models give us validation and type safety;
the deterministic writer still pipes model_dump(mode="json") through
json.dumps(..., sort_keys=True, indent=2) itself.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class GenreSource(StrEnum):
    OVERRIDE = "override"
    DISCOGS_STYLE = "discogs_style"
    DISCOGS_GENRE = "discogs_genre"
    DISCOGS_SEARCH = "discogs_search"
    MUSICBRAINZ = "musicbrainz"


class Genre(BaseModel):
    """See PLAN.md #6: genre records carry provenance so a coarser source can
    be retroactively upgraded to a more granular one."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: Literal["genre", "style"]
    source: GenreSource


class Album(BaseModel):
    """The canonical normalized record stored in data/albums.json.

    `_selected` is the sole write surface and the sole source of album
    identity — every record here is (or was) in `_selected` by construction.
    There is no `keeper` field: that bit was retired along with the old
    two-playlist design (see PLAN.md "Vet notes"). release_year is the only
    stored year — it derives from release_date, never from added_at or
    playlist membership. `added_at` is frozen at first write and never
    recomputed on later polls (see PLAN.md decisions), so it stays a stable
    commitment timestamp even if the earliest-added track is later removed
    from the playlist. A previously-recorded album no longer resolvable from
    `_selected` gets `removed_at` set rather than being deleted.
    """

    id: str
    artists: list[str]
    title: str
    release_date: date
    release_year: int
    album_type: Literal["album", "single", "compilation"]
    upc: str | None = None
    added_at: datetime
    removed_at: datetime | None = None
    genres: list[Genre] = []
    discogs_release_id: int | None = None
    """Resolved Discogs release/master ID, when a genre came from the Discogs
    cascade (constraint 6). Records which pressing/master was chosen so a
    re-run's choice is auditable, per PLAN.md Stage 1 step 2."""
    source: Literal["spotify", "manual"] = "spotify"
