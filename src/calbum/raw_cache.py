"""Write-once raw-response cache: {dir}/{key}.json. Shared by poll.py's
Spotify cache and enrich.py's Discogs cache, which previously hand-rolled
the same exists-then-read / mkdir-then-write pattern independently.

Load/store only — no policy (write-once, threshold checks, rollback) lives
here; that stays owned by each caller.
"""

from __future__ import annotations

import json
from pathlib import Path


class RawCache:
    def __init__(self, directory: Path):
        self._dir = directory

    def path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def load(self, key: str) -> dict | None:
        path = self.path(key)
        if path.exists():
            return json.loads(path.read_text())
        return None

    def store(self, key: str, data: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self.path(key).write_text(json.dumps(data, indent=2) + "\n")
