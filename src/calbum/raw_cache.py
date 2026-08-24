"""Raw-response cache: {dir}/{key}.json, one file per fetched thing.

Holds unmodified API responses so a stage never re-requests something it has
already fetched. This is the ONLY cache implementation in the codebase; all
three consumers construct one of these rather than rolling their own:

    poll.py      data/raw/spotify/{album_id}.json
    artists.py   data/raw/spotify/artists/{artist_id}.json
    enrich.py    data/raw/discogs/{album_id}.json

Not to be confused with the two other JSON files in the tree, neither of
which is a cache: data/albums.json is the canonical store (source of truth),
and web/src/data/*.json are derived read surfaces, regenerated every run.

Every entry is written once and never updated. Callers express that rule in
one of two shapes, and the difference is deliberate:

  - `store_if_absent` — check at the write. poll.py and artists.py fetch
    first and decide afterwards, so the guard belongs where the write is.
  - `store` after an early return — enrich.py checks for a cached blob at the
    TOP of its cascade and bails there, because the guard has to skip the
    Discogs requests too, not just the write. Guarding only the write would
    spend the API calls and throw the result away.
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

    def store_if_absent(self, key: str, data: dict) -> bool:
        """Store only if nothing is cached under `key` yet; True if written.

        The write-site spelling of write-once — see the module docstring for
        why enrich.py uses the other one."""
        if self.path(key).exists():
            return False
        self.store(key, data)
        return True
