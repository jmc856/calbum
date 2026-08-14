"""Pydantic models for SPOTIFY's response shapes. Nothing outside spotify/
touches a raw Spotify dict — code elsewhere works with calbum.models.Album
and friends instead. See PLAN.md, "The module boundary that matters."
"""

from __future__ import annotations

from pydantic import BaseModel


class TokenResponse(BaseModel):
    """Response shape from POST https://accounts.spotify.com/api/token."""

    access_token: str
    token_type: str
    expires_in: int
    scope: str | None = None
    refresh_token: str | None = None
