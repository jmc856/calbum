"""Pydantic models for DISCOGS' response shapes. Nothing outside discogs/
touches a raw Discogs dict — see PLAN.md "The module boundary that matters"
(the same pattern spotify/schemas.py follows).

Field names are verified against live responses, not the docs alone — Discogs
has a real, documented-nowhere-obviously quirk: the search endpoint uses
singular `genre`/`style` (both still arrays), while the release/master detail
endpoints use plural `genres`/`styles`. Mixing these up silently drops every
genre.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DiscogsSearchResult(BaseModel):
    """One item from GET /database/search?type=release. Genre/style come
    straight off the search result — no extra request needed for a
    non-master-linked pressing."""

    model_config = ConfigDict(extra="allow")  # decision 2: lenient at the boundary

    id: int
    title: str = ""
    master_id: int | None = None
    genre: list[str] = []
    style: list[str] = []


class DiscogsMaster(BaseModel):
    """GET /masters/{id}. Plural field names — see module docstring."""

    model_config = ConfigDict(extra="allow")

    id: int
    genres: list[str] = []
    styles: list[str] = []
