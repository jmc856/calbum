"""Tests for sheets.py row-building: flat Albums tab, by-genre grouping,
HYPERLINK formula construction, and the removed_at / no-genre edge cases."""

from __future__ import annotations

from calbum.models import Genre, GenreSource
from calbum.sheets import (
    ALBUMS_TAB_HEADER,
    GENRE_TAB_HEADER,
    UNCATEGORIZED,
    build_albums_tab_rows,
    build_genre_tab_rows,
    hyperlink,
)


# --- hyperlink -----------------------------------------------------------------


def test_hyperlink_embeds_the_spotify_url_and_title(make_album) -> None:
    album = make_album(album_id="abc123", title="Punisher")
    formula = hyperlink(album)
    assert formula == '=HYPERLINK("https://open.spotify.com/album/abc123", "Punisher")'


def test_hyperlink_escapes_embedded_quotes_in_title(make_album) -> None:
    album = make_album(title='The "Great" Album')
    formula = hyperlink(album)
    assert '""Great""' in formula


# --- build_albums_tab_rows --------------------------------------------------------


def test_build_albums_tab_rows_includes_header_first(make_album) -> None:
    rows = build_albums_tab_rows([make_album()])
    assert rows[0] == list(ALBUMS_TAB_HEADER)


def test_build_albums_tab_rows_is_flat_not_grouped_by_year(make_album) -> None:
    albums = [make_album("a", release_year=2020), make_album("b", release_year=2021)]
    rows = build_albums_tab_rows(albums)
    assert len(rows) == 3  # header + both albums, one tab


def test_build_albums_tab_rows_includes_a_year_column(make_album) -> None:
    rows = build_albums_tab_rows([make_album(release_year=1999)])
    year_index = ALBUMS_TAB_HEADER.index("Year")
    assert rows[1][year_index] == 1999


def test_build_albums_tab_rows_takes_an_already_filtered_active_list(make_album) -> None:
    """Filtering to active albums is run()'s job (computed once, shared with
    build_genre_tab_rows) — this builder trusts what it's given."""
    all_albums = [make_album("kept"), make_album("gone", removed_at="2023-01-01T00:00:00Z")]
    active = [a for a in all_albums if a.is_active]

    rows = build_albums_tab_rows(active)

    assert len(rows) == 2  # header + only "kept"


def test_build_albums_tab_rows_sorts_by_title(make_album) -> None:
    albums = [make_album("a", title="Zebra"), make_album("b", title="Apple")]
    rows = build_albums_tab_rows(albums)
    titles_in_order = [row[0] for row in rows[1:]]
    assert "Apple" in titles_in_order[0]
    assert "Zebra" in titles_in_order[1]


def test_build_albums_tab_rows_joins_multiple_genres_and_styles(make_album) -> None:
    genres = [
        Genre(name="Rock", kind="genre", source=GenreSource.DISCOGS_SEARCH),
        Genre(name="Folk", kind="genre", source=GenreSource.DISCOGS_SEARCH),
        Genre(name="Indie Rock", kind="style", source=GenreSource.DISCOGS_SEARCH),
    ]
    rows = build_albums_tab_rows([make_album(genres=genres)])
    genre_index = ALBUMS_TAB_HEADER.index("Genre")
    style_index = ALBUMS_TAB_HEADER.index("Sub-genre")
    assert rows[1][genre_index] == "Rock; Folk"
    assert rows[1][style_index] == "Indie Rock"


def test_build_albums_tab_rows_uses_a_separator_that_survives_a_comma_in_a_genre_name(make_album) -> None:
    """A real Discogs genre is literally named "Folk, World, & Country" —
    joining with ", " would make ["Rock", "Folk, World, & Country"] render
    as an ambiguous "Rock, Folk, World, & Country". Confirmed against a live
    Sheet, not hypothetical."""
    genres = [
        Genre(name="Rock", kind="genre", source=GenreSource.DISCOGS_SEARCH),
        Genre(name="Folk, World, & Country", kind="genre", source=GenreSource.DISCOGS_SEARCH),
    ]
    rows = build_albums_tab_rows([make_album(genres=genres)])
    genre_index = ALBUMS_TAB_HEADER.index("Genre")
    assert rows[1][genre_index] == "Rock; Folk, World, & Country"
    assert rows[1][genre_index].count(";") == 1  # exactly one separator between two genres


def test_build_albums_tab_rows_empty_when_all_albums_removed(make_album) -> None:
    album = make_album(removed_at="2023-01-01T00:00:00Z")
    rows = build_albums_tab_rows([a for a in [album] if a.is_active])
    assert rows == [list(ALBUMS_TAB_HEADER)]


# --- build_genre_tab_rows --------------------------------------------------------


def test_build_genre_tab_rows_includes_header_first(make_album) -> None:
    rows = build_genre_tab_rows([make_album()])
    assert rows[0] == list(GENRE_TAB_HEADER)


def test_build_genre_tab_rows_repeats_album_once_per_primary_genre(make_album) -> None:
    genres = [
        Genre(name="Rock", kind="genre", source=GenreSource.DISCOGS_SEARCH),
        Genre(name="Folk", kind="genre", source=GenreSource.DISCOGS_SEARCH),
    ]
    rows = build_genre_tab_rows([make_album(genres=genres)])
    genre_column = [row[0] for row in rows[1:]]
    assert genre_column == ["Folk", "Rock"]  # sorted alphabetically


def test_build_genre_tab_rows_buckets_genreless_albums_as_uncategorized(make_album) -> None:
    rows = build_genre_tab_rows([make_album(genres=[])])
    assert rows[1][0] == UNCATEGORIZED


def test_build_genre_tab_rows_takes_an_already_filtered_active_list(make_album) -> None:
    album = make_album("gone", removed_at="2023-01-01T00:00:00Z")
    rows = build_genre_tab_rows([a for a in [album] if a.is_active])
    assert rows == [list(GENRE_TAB_HEADER)]


def test_build_genre_tab_rows_sorts_by_genre_then_title(make_album) -> None:
    rock = [Genre(name="Rock", kind="genre", source=GenreSource.DISCOGS_SEARCH)]
    albums = [
        make_album("a", title="Zebra", genres=rock),
        make_album("b", title="Apple", genres=rock),
    ]
    rows = build_genre_tab_rows(albums)
    titles = [row[2] for row in rows[1:]]
    assert "Apple" in titles[0]
    assert "Zebra" in titles[1]
