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

    Frozen (like Genre): the only way to produce a modified Album is
    `model_copy(update={...})`, structurally enforcing the field-ownership
    discipline enrich.py's docstring otherwise only argues for in prose.
    """

    model_config = ConfigDict(frozen=True)

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
    artist_ids: list[str] = []
    """Spotify artist IDs, positionally parallel to `artists`. A separate
    field rather than making `artists` a list of objects: that would ripple
    into sheets.py, enrich.py, overrides.py's _SCALAR_FIELDS, the tests, and
    the stored shape of albums.json, for no gain. Backfilled from the
    already-cached raw blobs at zero API cost — see poll.py's
    Poller.build_albums. Empty for a manual album, which has no Spotify
    identity."""
    cover_url: str | None = None
    """The largest available cover image from Spotify's AlbumObject.images,
    set once at first write like added_at — see poll.py's Poller.build_albums
    for how an album polled before this field existed gets it backfilled
    from its already-cached raw blob, at no extra API cost. A manual album
    (source="manual") has no Spotify art; set this via an override entry."""

    @property
    def is_active(self) -> bool:
        """The single owning definition of "active" — still resolvable from
        `_selected`, not removed. Every consumer (the mass-removal guard,
        both Sheet tabs) reads this instead of re-deriving `removed_at is
        None` independently."""
        return self.removed_at is None

    @property
    def genre_names(self) -> list[str]:
        return [g.name for g in self.genres if g.kind == "genre"]

    @property
    def style_names(self) -> list[str]:
        return [g.name for g in self.genres if g.kind == "style"]

    @property
    def spotify_url(self) -> str | None:
        """None for a manual album (source != "spotify") — its id isn't a
        real Spotify id, so there's no URL to fabricate."""
        if self.source != "spotify":
            return None
        return f"https://open.spotify.com/album/{self.id}"
