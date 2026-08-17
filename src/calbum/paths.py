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
