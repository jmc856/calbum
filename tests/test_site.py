"""Tests for site.py's frontend payload: active-only filtering, field
trimming, ordering, and the manual-album (no Spotify link) case."""

from __future__ import annotations

from calbum.models import Genre, GenreSource
from calbum.site import build_site_payload


def test_emits_only_the_fields_the_ui_renders(make_album) -> None:
    album = make_album(
        "a1",
        genres=[
            Genre(name="Rock", kind="genre", source=GenreSource.DISCOGS_SEARCH),
            Genre(name="Indie Rock", kind="style", source=GenreSource.DISCOGS_SEARCH),
        ],
        upc="123456789012",
        discogs_release_id=42,
        cover_url="https://i.scdn.co/image/abc",
    )

    [row] = build_site_payload([album])

    assert set(row) == {
        "id", "title", "artists", "artistIds", "year", "genres", "styles", "cover", "url",
    }
    assert row["genres"] == ["Rock"]
    assert row["styles"] == ["Indie Rock"]
    assert row["cover"] == "https://i.scdn.co/image/abc"


def test_drops_server_side_fields(make_album) -> None:
    """upc / discogs_release_id / added_at / removed_at and genre provenance
    are auditing detail, not UI data."""
    [row] = build_site_payload([make_album("a1", upc="123456789012", discogs_release_id=7)])

    for field in ("upc", "discogs_release_id", "added_at", "removed_at", "source"):
        assert field not in row


def test_spotify_album_gets_a_url(make_album) -> None:
    [row] = build_site_payload([make_album("abc123")])
    assert row["url"] == "https://open.spotify.com/album/abc123"


def test_manual_album_url_is_none_not_a_fabricated_link(make_album) -> None:
    [row] = build_site_payload([make_album("manual:x", source="manual")])
    assert row["url"] is None


def test_album_without_cover_art_emits_none(make_album) -> None:
    [row] = build_site_payload([make_album("a1", cover_url=None)])
    assert row["cover"] is None


def test_sorted_by_year_descending_then_title(make_album) -> None:
    albums = [
        make_album("a", title="Zebra", release_year=2020),
        make_album("b", title="Apple", release_year=2024),
        make_album("c", title="Apple", release_year=2020),
    ]

    rows = build_site_payload(albums)

    assert [(r["year"], r["title"]) for r in rows] == [
        (2024, "Apple"),
        (2020, "Apple"),
        (2020, "Zebra"),
    ]


def test_empty_input_yields_empty_payload() -> None:
    assert build_site_payload([]) == []


def test_artist_ids_ride_parallel_to_artist_names(make_album) -> None:
    """Joined positionally by the frontend, so the two lists must stay in
    step — this is what lets artists.json be joined on a stable ID rather
    than a display name."""
    album = make_album("a1", artists=["Clipse", "Pusha T"], artist_ids=["c1", "p1"])

    [row] = build_site_payload([album])

    assert row["artists"] == ["Clipse", "Pusha T"]
    assert row["artistIds"] == ["c1", "p1"]


def test_manual_album_has_no_artist_ids(make_album) -> None:
    """A manual album has no Spotify identity; the frontend renders it
    without a portrait rather than joining on a fabricated ID."""
    [row] = build_site_payload([make_album("m1", source="manual")])

    assert row["artistIds"] == []
