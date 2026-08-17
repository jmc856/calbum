"""Shared test scaffolding.

make_album: one factory used by every test module, replacing four
divergent copies that grew independently in test_poll.py, test_enrich.py,
test_sheets.py, and test_writer.py.

redirect_data_paths (autouse): repoints every module-level data-location
constant at tmp_path, replacing the ~14 per-test `monkeypatch.setattr(...,
"RAW_DISCOGS_DIR", tmp_path)` calls that were scattered across
test_enrich.py and test_poll.py. A test that wants the real constant back
can still monkeypatch it after the fact — this just sets a safe default so
forgetting the redirect can no longer write into the real data/ tree.

poll.py has no module-level path constants to redirect: Poller takes
data_dir explicitly (test_poll.py passes tmp_path straight to each Poller
it constructs), which is the seam PLAN.md's Poller recommendation intended.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

from calbum.models import Album, Genre


@pytest.fixture
def make_album() -> Callable[..., Album]:
    def _make_album(
        album_id: str = "a1",
        *,
        artists: list[str] | None = None,
        title: str = "Some Title",
        release_year: int = 2020,
        album_type: str = "album",
        upc: str | None = None,
        added_at: str | datetime = "2020-01-01T00:00:00Z",
        removed_at: str | datetime | None = None,
        genres: list[Genre] | None = None,
        discogs_release_id: int | None = None,
        source: str = "spotify",
    ) -> Album:
        return Album(
            id=album_id,
            artists=artists or ["Some Artist"],
            title=title,
            release_date=f"{release_year}-01-01",
            release_year=release_year,
            album_type=album_type,
            upc=upc,
            added_at=added_at,
            removed_at=removed_at,
            genres=genres or [],
            discogs_release_id=discogs_release_id,
            source=source,
        )

    return _make_album


@pytest.fixture(autouse=True)
def redirect_data_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import calbum.enrich as enrich_module
    import calbum.overrides as overrides_module
    import calbum.paths as paths_module
    import calbum.sheets as sheets_module

    albums_path = tmp_path / "albums.json"
    monkeypatch.setattr(paths_module, "ALBUMS_PATH", albums_path)
    monkeypatch.setattr(enrich_module, "ALBUMS_PATH", albums_path)
    monkeypatch.setattr(enrich_module, "RAW_DISCOGS_DIR", tmp_path / "raw" / "discogs")
    monkeypatch.setattr(sheets_module, "ALBUMS_PATH", albums_path)
    monkeypatch.setattr(overrides_module, "ALBUMS_PATH", albums_path)
    monkeypatch.setattr(overrides_module, "OVERRIDES_PATH", tmp_path / "overrides.toml")
