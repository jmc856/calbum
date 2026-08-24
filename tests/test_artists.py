"""Tests for artists.py: ID collection, the portrait payload, and the
write-once fetch/cache loop that makes a re-run cost zero requests."""

from __future__ import annotations

from pathlib import Path

import pytest

from calbum.artists import (
    PORTRAIT_MIN_WIDTH,
    artist_ids_in,
    build_artists_payload,
    fetch_blobs,
)
from calbum.raw_cache import RawCache


def blob(artist_id: str, name: str, widths: list[int] | None = None) -> dict:
    images = [{"url": f"https://i.scdn.co/{artist_id}/{w}", "width": w} for w in widths or []]
    return {"id": artist_id, "name": name, "images": images}


class FakeClient:
    """Records what it was asked for, so tests can assert on call count —
    the property that matters is that a cached artist is never refetched."""

    def __init__(self, blobs: dict[str, dict] | None = None):
        self.blobs = blobs or {}
        self.calls: list[str] = []

    def get_artist(self, artist_id: str) -> dict:
        self.calls.append(artist_id)
        if artist_id not in self.blobs:
            raise RuntimeError(f"no such artist {artist_id}")
        return self.blobs[artist_id]


# ---------- artist_ids_in ----------

def test_collects_distinct_ids_in_first_seen_order(make_album) -> None:
    """First-seen order, not sorted: the emitted file must be stable across
    runs, and re-sorting happens later in build_artists_payload."""
    albums = [
        make_album("a1", artist_ids=["x", "y"]),
        make_album("a2", artist_ids=["y", "z"]),
    ]

    assert artist_ids_in(albums) == ["x", "y", "z"]


def test_album_with_no_artist_ids_contributes_nothing(make_album) -> None:
    """A manual album has no Spotify identity, and an album polled before
    artist_ids existed hasn't been backfilled yet. Neither may crash."""
    albums = [make_album("a1", source="manual"), make_album("a2", artist_ids=["x"])]

    assert artist_ids_in(albums) == ["x"]


# ---------- build_artists_payload ----------

def test_payload_carries_only_what_the_frontend_cannot_derive() -> None:
    """Album counts and year spans are computable from albums.json; putting
    them here too would create a second source of truth."""
    [row] = build_artists_payload([blob("x", "Kendrick Lamar", [640, 320, 160])])

    assert set(row) == {"id", "name", "portrait"}


def test_payload_prefers_the_smallest_image_at_least_min_width() -> None:
    [row] = build_artists_payload([blob("x", "A", [160, 320, 640])])

    assert row["portrait"] == f"https://i.scdn.co/x/{PORTRAIT_MIN_WIDTH}"


def test_payload_is_sorted_by_name() -> None:
    rows = build_artists_payload([blob("2", "Zach Bryan"), blob("1", "alvvays")])

    assert [r["name"] for r in rows] == ["alvvays", "Zach Bryan"]


def test_artist_with_no_images_gets_a_null_portrait() -> None:
    [row] = build_artists_payload([blob("x", "A", [])])

    assert row["portrait"] is None


# ---------- fetch_blobs ----------

def test_fetches_only_uncached_artists(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)
    cache.store("cached", blob("cached", "Cached"))
    client = FakeClient({"fresh": blob("fresh", "Fresh")})

    blobs = fetch_blobs(client, cache, ["cached", "fresh"])

    assert client.calls == ["fresh"]
    assert [b["name"] for b in blobs] == ["Cached", "Fresh"]


def test_rerun_costs_zero_requests(tmp_path: Path) -> None:
    """The property the whole cache exists for."""
    cache = RawCache(tmp_path)
    client = FakeClient({"x": blob("x", "X")})

    fetch_blobs(client, cache, ["x"])
    fetch_blobs(client, cache, ["x"])

    assert client.calls == ["x"]


def test_a_failing_artist_is_skipped_not_fatal(tmp_path: Path, caplog) -> None:
    """One dead artist must not cost the whole file — same degrade-at-the-
    boundary rule poll.py applies to a malformed album."""
    client = FakeClient({"ok": blob("ok", "OK")})

    blobs = fetch_blobs(client, RawCache(tmp_path), ["missing", "ok"])

    assert [b["name"] for b in blobs] == ["OK"]


def test_a_failing_artist_is_not_cached(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)
    fetch_blobs(FakeClient(), cache, ["missing"])

    assert cache.load("missing") is None


def test_cache_lives_beside_the_album_cache_not_in_it(tmp_path: Path, monkeypatch) -> None:
    """data/raw/spotify/ is a flat {id}.json namespace shared by albums; an
    artist blob written there could be handed back where an album was
    expected. The artists/ subdirectory keeps the two namespaces apart."""
    import calbum.artists as artists_module

    monkeypatch.setattr(artists_module, "DATA_DIR", tmp_path)
    cache = artists_module._cache()
    cache.store("abc", {"id": "abc"})

    assert (tmp_path / "raw" / "spotify" / "artists" / "abc.json").exists()
    assert not (tmp_path / "raw" / "spotify" / "abc.json").exists()


def test_cache_is_rebuilt_per_call_so_path_patches_take_effect(tmp_path: Path, monkeypatch) -> None:
    """The reason _cache() is a function and not a module-level constant: a
    constant would capture the real data/ path at import and write into the
    repo during a test run."""
    import calbum.artists as artists_module

    monkeypatch.setattr(artists_module, "DATA_DIR", tmp_path / "first")
    first = artists_module._cache().path("k")
    monkeypatch.setattr(artists_module, "DATA_DIR", tmp_path / "second")
    second = artists_module._cache().path("k")

    assert first != second
