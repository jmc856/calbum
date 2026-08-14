"""Tests for the Discogs enrichment cascade: deterministic result selection,
genre/style -> kind/source mapping (constraint 6), write-once caching, and
that enrichment never touches fields it doesn't own."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from calbum.enrich import (
    build_coverage_report,
    cache_path,
    choose_best_result,
    enrich_album,
)
from calbum.models import Album, Genre, GenreSource


def make_album(album_id: str = "a1", upc: str | None = "656605144269", genres: list[Genre] | None = None) -> Album:
    return Album(
        id=album_id,
        artists=["Phoebe Bridgers"],
        title="Stranger in the Alps",
        release_date="2017-09-22",
        release_year=2017,
        album_type="album",
        upc=upc,
        added_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        genres=genres or [],
    )


# --- choose_best_result -------------------------------------------------------


def test_choose_best_result_empty_returns_none() -> None:
    assert choose_best_result([]) is None


def test_choose_best_result_prefers_lowest_master_id() -> None:
    results = [
        {"id": 1, "master_id": 500},
        {"id": 2, "master_id": 100},
        {"id": 3, "master_id": None},
    ]
    chosen = choose_best_result(results)
    assert chosen["id"] == 2


def test_choose_best_result_falls_back_to_lowest_id_when_no_master() -> None:
    results = [{"id": 30, "master_id": None}, {"id": 10, "master_id": None}]
    chosen = choose_best_result(results)
    assert chosen["id"] == 10


def test_choose_best_result_is_deterministic_regardless_of_input_order() -> None:
    results_a = [{"id": 1, "master_id": 500}, {"id": 2, "master_id": 100}]
    results_b = list(reversed(results_a))
    assert choose_best_result(results_a) == choose_best_result(results_b)


# --- enrich_album --------------------------------------------------------------


class FakeGenreLookup:
    def __init__(self, barcode_results=None, search_results=None, masters=None):
        self._barcode_results = barcode_results or []
        self._search_results = search_results or []
        self._masters = masters or {}
        self.barcode_calls: list[str] = []
        self.search_calls: list[tuple] = []
        self.master_calls: list[int] = []

    def search_by_barcode(self, barcode: str) -> list[dict]:
        self.barcode_calls.append(barcode)
        return self._barcode_results

    def search_by_artist_title_year(self, artist: str, title: str, year: int) -> list[dict]:
        self.search_calls.append((artist, title, year))
        return self._search_results

    def get_master(self, master_id: int) -> dict:
        self.master_calls.append(master_id)
        return self._masters[master_id]


def test_enrich_album_barcode_hit_with_master_uses_master_genres(monkeypatch, tmp_path) -> None:
    import calbum.enrich as enrich_module

    monkeypatch.setattr(enrich_module, "RAW_DISCOGS_DIR", tmp_path)
    client = FakeGenreLookup(
        barcode_results=[{"id": 1, "master_id": 42}],
        masters={42: {"id": 42, "genres": ["Rock"], "styles": ["Indie Rock", "Folk"]}},
    )
    album = make_album()

    result = enrich_album(client, album)

    assert client.master_calls == [42]
    assert client.search_calls == []  # barcode hit, never falls through to search
    assert result.discogs_release_id == 42
    genre_entries = [g for g in result.genres if g.kind == "genre"]
    style_entries = [g for g in result.genres if g.kind == "style"]
    assert [g.name for g in genre_entries] == ["Rock"]
    assert {g.name for g in style_entries} == {"Indie Rock", "Folk"}
    assert all(g.source == GenreSource.DISCOGS_GENRE for g in genre_entries)
    assert all(g.source == GenreSource.DISCOGS_STYLE for g in style_entries)


def test_enrich_album_barcode_hit_without_master_uses_result_fields_directly(monkeypatch, tmp_path) -> None:
    import calbum.enrich as enrich_module

    monkeypatch.setattr(enrich_module, "RAW_DISCOGS_DIR", tmp_path)
    client = FakeGenreLookup(barcode_results=[{"id": 1, "master_id": None, "genre": ["Rock"], "style": ["Emo"]}])
    album = make_album()

    result = enrich_album(client, album)

    assert client.master_calls == []  # no master_id -> no extra fetch
    assert result.discogs_release_id is None
    assert {g.name for g in result.genres if g.kind == "genre"} == {"Rock"}
    assert {g.name for g in result.genres if g.kind == "style"} == {"Emo"}


def test_enrich_album_falls_through_to_search_when_no_upc(monkeypatch, tmp_path) -> None:
    import calbum.enrich as enrich_module

    monkeypatch.setattr(enrich_module, "RAW_DISCOGS_DIR", tmp_path)
    client = FakeGenreLookup(search_results=[{"id": 1, "master_id": None, "genre": ["Rock"], "style": ["Emo"]}])
    album = make_album(upc=None)

    result = enrich_album(client, album)

    assert client.barcode_calls == []
    assert len(client.search_calls) == 1
    # A search hit uses one source for both tiers (constraint 6) — not
    # DISCOGS_GENRE/DISCOGS_STYLE, which are barcode-only.
    assert all(g.source == GenreSource.DISCOGS_SEARCH for g in result.genres)


def test_enrich_album_falls_through_to_search_when_barcode_finds_nothing(monkeypatch, tmp_path) -> None:
    import calbum.enrich as enrich_module

    monkeypatch.setattr(enrich_module, "RAW_DISCOGS_DIR", tmp_path)
    client = FakeGenreLookup(barcode_results=[], search_results=[{"id": 1, "master_id": None, "genre": ["Rock"], "style": []}])
    album = make_album()

    result = enrich_album(client, album)

    assert client.barcode_calls == [album.upc]
    assert len(client.search_calls) == 1
    assert result.genres[0].source == GenreSource.DISCOGS_SEARCH


def test_enrich_album_no_results_anywhere_yields_empty_genres_and_still_caches(monkeypatch, tmp_path) -> None:
    import calbum.enrich as enrich_module

    monkeypatch.setattr(enrich_module, "RAW_DISCOGS_DIR", tmp_path)
    client = FakeGenreLookup()
    album = make_album()

    result = enrich_album(client, album)

    assert result.genres == []
    assert cache_path(album.id).exists()  # write-once cache still recorded, even for a miss


def test_enrich_album_is_write_once_second_call_never_hits_client(monkeypatch, tmp_path) -> None:
    import calbum.enrich as enrich_module

    monkeypatch.setattr(enrich_module, "RAW_DISCOGS_DIR", tmp_path)
    client = FakeGenreLookup(barcode_results=[{"id": 1, "master_id": None, "genre": ["Rock"], "style": []}])
    album = make_album()

    first = enrich_album(client, album)
    calls_after_first = len(client.barcode_calls)
    second = enrich_album(client, album)

    assert len(client.barcode_calls) == calls_after_first  # no new call
    assert first.genres == second.genres


def test_enrich_album_never_touches_fields_it_does_not_own(monkeypatch, tmp_path) -> None:
    """The whole point of model_copy over reconstruction: added_at (frozen,
    decision 12) and every other Stage-0-owned field survive untouched."""
    import calbum.enrich as enrich_module

    monkeypatch.setattr(enrich_module, "RAW_DISCOGS_DIR", tmp_path)
    client = FakeGenreLookup(barcode_results=[{"id": 1, "master_id": None, "genre": ["Rock"], "style": []}])
    album = make_album()

    result = enrich_album(client, album)

    assert result.id == album.id
    assert result.artists == album.artists
    assert result.title == album.title
    assert result.release_date == album.release_date
    assert result.release_year == album.release_year
    assert result.album_type == album.album_type
    assert result.upc == album.upc
    assert result.added_at == album.added_at
    assert result.removed_at == album.removed_at
    assert result.source == album.source


# --- build_coverage_report ------------------------------------------------------


def test_build_coverage_report_counts_by_source_and_missing_sub_genre() -> None:
    albums = [
        make_album("a", genres=[Genre(name="Rock", kind="genre", source=GenreSource.DISCOGS_GENRE),
                                  Genre(name="Indie Rock", kind="style", source=GenreSource.DISCOGS_STYLE)]),
        make_album("b", genres=[Genre(name="Electronic", kind="genre", source=GenreSource.DISCOGS_SEARCH)]),
        make_album("c", genres=[]),
    ]

    report = build_coverage_report(albums)

    assert report["total"] == 3
    assert report["with_primary_genre"] == 2
    assert report["with_sub_genre"] == 1
    assert report["missing_sub_genre"] == 2
    assert report["by_source"] == {"discogs_genre": 1, "discogs_search": 1}
