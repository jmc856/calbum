"""Tests for the Discogs enrichment cascade: deterministic result selection,
genre/style -> kind/source mapping (constraint 6), write-once caching, and
that enrichment never touches fields it doesn't own."""

from __future__ import annotations

import pytest

from calbum.enrich import (
    build_coverage_report,
    cache_path,
    choose_best_result,
    enrich_album,
    strip_edition_suffix,
)
from calbum.models import Genre, GenreSource


@pytest.fixture
def make_album(make_album):
    """This module's albums default to a real Phoebe Bridgers release (with
    a UPC, so most enrich_album tests exercise the barcode-first path by
    default) — everything else defers to the shared conftest.py fixture."""

    def _make_album(
        album_id="a1",
        *,
        artists=None,
        title="Stranger in the Alps",
        release_year=2017,
        upc="656605144269",
        **kwargs,
    ):
        return make_album(
            album_id,
            artists=artists or ["Phoebe Bridgers"],
            title=title,
            release_year=release_year,
            upc=upc,
            **kwargs,
        )

    return _make_album


# --- strip_edition_suffix -------------------------------------------------------


def test_strip_edition_suffix_removes_trailing_parenthetical() -> None:
    assert strip_edition_suffix("good kid, m.A.A.d city (Deluxe)") == "good kid, m.A.A.d city"


def test_strip_edition_suffix_handles_multi_word_suffix() -> None:
    assert strip_edition_suffix("Some Album (Expanded Edition)") == "Some Album"


def test_strip_edition_suffix_returns_none_when_nothing_to_strip() -> None:
    assert strip_edition_suffix("Punisher") is None


def test_strip_edition_suffix_returns_none_for_parenthetical_only_title() -> None:
    """An edge case worth pinning down: stripping must never produce an
    empty string."""
    assert strip_edition_suffix("(Deluxe)") is None


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
    def __init__(self, barcode_results=None, search_results=None, masters=None, search_results_by_title=None):
        self._barcode_results = barcode_results or []
        self._search_results = search_results or []
        self._search_results_by_title = search_results_by_title  # optional, overrides _search_results
        self._masters = masters or {}
        self.barcode_calls: list[str] = []
        self.search_calls: list[tuple] = []
        self.master_calls: list[int] = []

    def search_by_barcode(self, barcode: str) -> list[dict]:
        self.barcode_calls.append(barcode)
        return self._barcode_results

    def search_by_artist_title_year(self, artist: str, title: str, year: int) -> list[dict]:
        self.search_calls.append((artist, title, year))
        if self._search_results_by_title is not None:
            return self._search_results_by_title.get(title, [])
        return self._search_results

    def get_master(self, master_id: int) -> dict:
        self.master_calls.append(master_id)
        return self._masters[master_id]


def test_enrich_album_barcode_hit_with_master_uses_master_genres(make_album) -> None:
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


def test_enrich_album_barcode_hit_without_master_uses_result_fields_directly(make_album) -> None:
    client = FakeGenreLookup(barcode_results=[{"id": 1, "master_id": None, "genre": ["Rock"], "style": ["Emo"]}])
    album = make_album()

    result = enrich_album(client, album)

    assert client.master_calls == []  # no master_id -> no extra fetch
    assert result.discogs_release_id is None
    assert {g.name for g in result.genres if g.kind == "genre"} == {"Rock"}
    assert {g.name for g in result.genres if g.kind == "style"} == {"Emo"}


def test_enrich_album_falls_through_to_search_when_no_upc(make_album) -> None:
    client = FakeGenreLookup(search_results=[{"id": 1, "master_id": None, "genre": ["Rock"], "style": ["Emo"]}])
    album = make_album(upc=None)

    result = enrich_album(client, album)

    assert client.barcode_calls == []
    assert len(client.search_calls) == 1
    # A search hit uses one source for both tiers (constraint 6) — not
    # DISCOGS_GENRE/DISCOGS_STYLE, which are barcode-only.
    assert all(g.source == GenreSource.DISCOGS_SEARCH for g in result.genres)


def test_enrich_album_falls_through_to_search_when_barcode_finds_nothing(make_album) -> None:
    client = FakeGenreLookup(barcode_results=[], search_results=[{"id": 1, "master_id": None, "genre": ["Rock"], "style": []}])
    album = make_album()

    result = enrich_album(client, album)

    assert client.barcode_calls == [album.upc]
    assert len(client.search_calls) == 1
    assert result.genres[0].source == GenreSource.DISCOGS_SEARCH


def test_enrich_album_retries_search_with_edition_suffix_stripped(make_album) -> None:
    """Confirmed live: Discogs' release_title search finds 0 results for
    "good kid, m.A.A.d city (Deluxe)" but 50 for the same title without the
    suffix, same master. This is the regression test for that."""
    full_title = "good kid, m.A.A.d city (Deluxe)"
    stripped_title = "good kid, m.A.A.d city"
    client = FakeGenreLookup(
        barcode_results=[],
        search_results_by_title={
            full_title: [],
            stripped_title: [{"id": 1, "master_id": None, "genre": ["Hip Hop"], "style": ["Conscious"]}],
        },
    )
    album = make_album(upc=None, title=full_title)

    result = enrich_album(client, album)

    assert client.search_calls == [
        ("Phoebe Bridgers", full_title, 2017),
        ("Phoebe Bridgers", stripped_title, 2017),
    ]
    assert {g.name for g in result.genres} == {"Hip Hop", "Conscious"}


def test_enrich_album_does_not_retry_when_title_has_no_suffix_to_strip(make_album) -> None:
    """An album with no parenthetical suffix and no results anywhere should
    cost exactly one search call, not a redundant identical retry."""
    client = FakeGenreLookup(barcode_results=[], search_results=[])
    album = make_album(upc=None, title="Punisher")

    enrich_album(client, album)

    assert len(client.search_calls) == 1


def test_enrich_album_no_results_anywhere_yields_empty_genres_and_still_caches(make_album) -> None:
    client = FakeGenreLookup()
    album = make_album()

    result = enrich_album(client, album)

    assert result.genres == []
    assert cache_path(album.id).exists()  # write-once cache still recorded, even for a miss


def test_enrich_album_is_write_once_second_call_never_hits_client(make_album) -> None:
    client = FakeGenreLookup(barcode_results=[{"id": 1, "master_id": None, "genre": ["Rock"], "style": []}])
    album = make_album()

    first = enrich_album(client, album)
    calls_after_first = len(client.barcode_calls)
    second = enrich_album(client, album)

    assert len(client.barcode_calls) == calls_after_first  # no new call
    assert first.genres == second.genres


def test_enrich_album_never_touches_fields_it_does_not_own(make_album) -> None:
    """The whole point of model_copy over reconstruction: added_at (frozen,
    decision 12) and every other Stage-0-owned field survive untouched."""
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


def test_build_coverage_report_counts_by_source_and_missing_sub_genre(make_album) -> None:
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
