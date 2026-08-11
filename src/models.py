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

    release_year is the only stored year — it derives from release_date, never
    from added_at or playlist membership. `keeper` is a separate, sticky bit
    observed from ^\\d{4}$ playlist membership; it is monotonic (true stays
    true) except via an explicit _overrides demotion. See PLAN.md "Vet notes"
    for why year and keeper were split out of a single overloaded field.
    """

    id: str
    artists: list[str]
    title: str
    release_date: date
    release_year: int
    upc: str | None = None
    added_at: datetime
    removed_at: datetime | None = None
    keeper: bool = False
    genres: list[Genre] = []
    source: Literal["spotify", "manual"] = "spotify"


class TokenResponse(BaseModel):
    """Response shape from POST https://accounts.spotify.com/api/token."""

    access_token: str
    token_type: str
    expires_in: int
    scope: str | None = None
    refresh_token: str | None = None
