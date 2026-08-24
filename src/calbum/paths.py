"""Shared filesystem layout. Owned once here rather than redefined per
stage module — see PLAN.md "Technical debt"/simplify pass notes: REPO_ROOT
was previously copy-pasted into poll.py, enrich.py, and sheets.py.

RAW_SPOTIFY_DIR / RAW_DISCOGS_DIR stay in their own modules (poll.py,
enrich.py) — they're genuinely per-module, not shared.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
ALBUMS_PATH = DATA_DIR / "albums.json"
OVERRIDES_PATH = DATA_DIR / "overrides.toml"
ENV_PATH = REPO_ROOT / ".env"

WEB_DIR = REPO_ROOT / "web"
SITE_DATA_PATH = WEB_DIR / "src" / "data" / "albums.json"
"""Frontend payload emitted by site.py. Under web/src/ rather than
web/public/ because the app imports it at build time instead of fetching it
— see site.py's module docstring for why."""

SITE_ARTISTS_PATH = WEB_DIR / "src" / "data" / "artists.json"
"""Artist portraits emitted by artists.py. A second file rather than
reshaping SITE_DATA_PATH's bare array, which the frontend consumes directly
as `ALBUMS = raw as Album[]` — a wrapper object would touch every consumer
for no gain."""
