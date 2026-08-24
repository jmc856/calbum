"""Tests for RawCache.store_if_absent — the write-once rule poll.py and
artists.py both depend on."""

from __future__ import annotations

from pathlib import Path

from calbum.raw_cache import RawCache


def test_store_if_absent_writes_when_nothing_is_cached(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)

    assert cache.store_if_absent("k", {"v": 1}) is True
    assert cache.load("k") == {"v": 1}


def test_store_if_absent_leaves_an_existing_blob_untouched(tmp_path: Path) -> None:
    """Write-once: a second call must neither overwrite nor report a write,
    or every run would churn the cached blobs."""
    cache = RawCache(tmp_path)
    cache.store_if_absent("k", {"v": "original"})

    assert cache.store_if_absent("k", {"v": "replacement"}) is False
    assert cache.load("k") == {"v": "original"}


def test_store_still_overwrites(tmp_path: Path) -> None:
    """The unconditional path stays available for callers wanting other
    policy — store_if_absent is the opt-in, not a behaviour change."""
    cache = RawCache(tmp_path)
    cache.store("k", {"v": "original"})
    cache.store("k", {"v": "replacement"})

    assert cache.load("k") == {"v": "replacement"}


def test_creates_the_directory_on_first_write(tmp_path: Path) -> None:
    cache = RawCache(tmp_path / "nested" / "dir")

    assert cache.store_if_absent("k", {"v": 1}) is True
    assert cache.load("k") == {"v": 1}
