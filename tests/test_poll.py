"""Mass-removal guard (constraint 7, decision 6) and the other pure functions
in poll.py: parse_release_date, resolve_playlist_items, build_albums."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from calbum.poll import (
    MassRemovalAbort,
    build_albums,
    cache_path,
    check_mass_removal_guard,
    earliest_added_at,
    load_existing_albums,
    parse_release_date,
    resolve_candidates,
    resolve_playlist_items,
)


class FakeClient:
    def __init__(self, items: list[dict]):
        self._items = items

    def playlist_items(self, playlist_id: str):
        return iter(self._items)


# --- parse_release_date -----------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1965", date(1965, 1, 1)),
        ("1965-03", date(1965, 3, 1)),
        ("1965-03-12", date(1965, 3, 12)),
    ],
)
def test_parse_release_date_handles_all_precisions(value: str, expected: date) -> None:
    assert parse_release_date(value) == expected


# --- resolve_playlist_items --------------------------------------------------


def test_resolve_playlist_items_groups_by_album_and_skips_local() -> None:
    items = [
        {"added_at": "2020-01-01T00:00:00Z", "item": {"album": {"id": "a1"}}},
        {"added_at": "2020-01-02T00:00:00Z", "item": {"album": {"id": "a1"}}},
        {"added_at": "2020-01-03T00:00:00Z", "track": {"album": {"id": "a2"}}},
        {"added_at": "2020-01-04T00:00:00Z", "is_local": True, "item": {"album": {"id": "a3"}}},
    ]
    by_album = resolve_playlist_items(FakeClient(items), "playlist-id")

    assert set(by_album.keys()) == {"a1", "a2"}
    assert len(by_album["a1"]) == 2
    assert len(by_album["a2"]) == 1


def test_resolve_playlist_items_prefers_new_item_path_over_old_track_path() -> None:
    """When both shapes are somehow present, the newer item["item"] path wins."""
    items = [
        {
            "added_at": "2020-01-01T00:00:00Z",
            "item": {"album": {"id": "new-path"}},
            "track": {"album": {"id": "old-path"}},
        },
    ]
    by_album = resolve_playlist_items(FakeClient(items), "playlist-id")
    assert set(by_album.keys()) == {"new-path"}


# --- earliest_added_at -------------------------------------------------------


def test_earliest_added_at_picks_the_minimum() -> None:
    items = [
        {"added_at": "2020-06-01T00:00:00Z"},
        {"added_at": "2020-01-01T00:00:00Z"},
        {"added_at": "2020-03-01T00:00:00Z"},
    ]
    result = earliest_added_at(items)
    assert result == datetime(2020, 1, 1, tzinfo=timezone.utc)


# --- check_mass_removal_guard -------------------------------------------------


def test_guard_passes_when_count_does_not_drop() -> None:
    check_mass_removal_guard(previous_active_count=10, new_active_count=10)
    check_mass_removal_guard(previous_active_count=10, new_active_count=15)


def test_guard_aborts_on_any_drop_below_small_catalog_threshold() -> None:
    with pytest.raises(MassRemovalAbort):
        check_mass_removal_guard(previous_active_count=12, new_active_count=11)


def test_guard_passes_small_drop_at_or_above_threshold_size() -> None:
    check_mass_removal_guard(previous_active_count=200, new_active_count=199)


def test_guard_aborts_on_large_drop_at_or_above_threshold_size() -> None:
    with pytest.raises(MassRemovalAbort):
        check_mass_removal_guard(previous_active_count=200, new_active_count=150)


def test_guard_boundary_exactly_ten_percent_drop_passes() -> None:
    # 200 -> 180 is exactly 10%, and the guard trips only when drop > 10%.
    check_mass_removal_guard(previous_active_count=200, new_active_count=180)


def test_guard_boundary_just_over_ten_percent_drop_aborts() -> None:
    with pytest.raises(MassRemovalAbort):
        check_mass_removal_guard(previous_active_count=200, new_active_count=179)


def test_guard_boundary_exactly_fifty_uses_percentage_rule() -> None:
    # previous_active_count == 50 is "at or above" SMALL_CATALOG_SIZE, so the
    # percentage rule applies, not the any-drop rule: a 1-album drop (2%) passes.
    check_mass_removal_guard(previous_active_count=50, new_active_count=49)


# --- build_albums -------------------------------------------------------------


def test_build_albums_freezes_added_at_for_existing_albums(make_album) -> None:
    existing = {"a1": make_album("a1", added_at="2019-01-01T00:00:00+00:00")}
    resolved = {"a1": {"name": "T", "artists": [{"name": "A"}], "release_date": "2020-01-01",
                        "album_type": "album", "external_ids": {}}}
    by_album = {"a1": [{"added_at": "2024-06-01T00:00:00Z"}]}  # would be later if recomputed

    result = {a.id: a for a in build_albums(existing, resolved, by_album, datetime.now(timezone.utc))}

    assert result["a1"].added_at == datetime(2019, 1, 1, tzinfo=timezone.utc)


def test_build_albums_clears_removed_at_when_album_reappears(make_album) -> None:
    existing = {
        "a1": make_album("a1", added_at="2019-01-01T00:00:00+00:00", removed_at="2023-01-01T00:00:00+00:00")
    }
    resolved = {"a1": {"name": "T", "artists": [{"name": "A"}], "release_date": "2020-01-01",
                        "album_type": "album", "external_ids": {}}}
    by_album = {"a1": [{"added_at": "2024-06-01T00:00:00Z"}]}

    result = {a.id: a for a in build_albums(existing, resolved, by_album, datetime.now(timezone.utc))}

    assert result["a1"].removed_at is None


def test_build_albums_sets_removed_at_for_albums_no_longer_resolved(make_album) -> None:
    existing = {"a1": make_album("a1", added_at="2019-01-01T00:00:00+00:00")}
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    result = {a.id: a for a in build_albums(existing, resolved={}, by_album={}, now=now)}

    assert result["a1"].removed_at == now


def test_build_albums_creates_new_album_with_computed_fields() -> None:
    resolved = {
        "a1": {
            "name": "New Album",
            "artists": [{"name": "New Artist"}],
            "release_date": "1999-06",
            "album_type": "single",
            "external_ids": {"upc": "012345678905"},
        }
    }
    by_album = {"a1": [{"added_at": "2024-01-01T00:00:00Z"}, {"added_at": "2024-01-02T00:00:00Z"}]}

    result = {a.id: a for a in build_albums({}, resolved, by_album, datetime.now(timezone.utc))}

    album = result["a1"]
    assert album.title == "New Album"
    assert album.artists == ["New Artist"]
    assert album.release_year == 1999
    assert album.album_type == "single"
    assert album.upc == "012345678905"
    assert album.added_at == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert album.removed_at is None


def test_build_albums_degrades_a_single_malformed_album_instead_of_aborting() -> None:
    """Decision 2: lenient at the boundary. One bad album is logged and
    skipped; the rest of the run still produces output."""
    resolved = {
        "good": {"name": "Good Album", "artists": [{"name": "A"}], "release_date": "2020-01-01",
                  "album_type": "album", "external_ids": {}},
        "bad": {"name": "Bad Album", "artists": [{"name": "A"}],  # missing release_date
                 "album_type": "album", "external_ids": {}},
    }
    by_album = {
        "good": [{"added_at": "2024-01-01T00:00:00Z"}],
        "bad": [{"added_at": "2024-01-01T00:00:00Z"}],
    }

    result = {a.id: a for a in build_albums({}, resolved, by_album, datetime.now(timezone.utc))}

    assert "good" in result
    assert "bad" not in result


# --- load_existing_albums ----------------------------------------------------
# ALBUMS_PATH is already redirected to tmp_path/albums.json by conftest.py's
# autouse redirect_data_paths fixture.


def test_load_existing_albums_true_cold_start_returns_empty() -> None:
    assert load_existing_albums() == {}


def test_load_existing_albums_rejects_a_file_that_exists_but_is_empty() -> None:
    """An existing-but-empty albums.json is data loss, not a fresh start, and
    must not be silently treated as a cold start (which would bypass the
    mass-removal guard entirely, since previous_active_count would read 0)."""
    import calbum.poll as poll_module

    poll_module.ALBUMS_PATH.write_text("[]\n")

    with pytest.raises(SystemExit):
        load_existing_albums()


# --- resolve_candidates -------------------------------------------------------
# RAW_SPOTIFY_DIR is already redirected to tmp_path by conftest.py's autouse
# redirect_data_paths fixture.


class FakeAlbumClient:
    """Tracks get_album calls so tests can assert a rejected album was never
    fetched (pre-fetch threshold) or that a cache write was undone
    (post-fetch fallback threshold)."""

    def __init__(self, albums: dict[str, dict]):
        self._albums = albums
        self.fetched: list[str] = []

    def get_album(self, album_id: str) -> dict:
        self.fetched.append(album_id)
        return self._albums[album_id]


def test_resolve_candidates_rejects_without_fetching_when_simplified_total_known() -> None:
    client = FakeAlbumClient({})  # would KeyError if fetched — proves it wasn't
    by_album = {
        "stray": [
            {"added_at": "2024-01-01T00:00:00Z", "item": {"album": {"id": "stray", "total_tracks": 12}}}
        ]
    }

    resolved = resolve_candidates(client, by_album)

    assert resolved == {}
    assert client.fetched == []
    assert not cache_path("stray").exists()


def test_resolve_candidates_keeps_album_at_or_above_threshold() -> None:
    full = {"name": "Kept Album", "total_tracks": 10, "artists": [{"name": "A"}],
            "release_date": "2020-01-01", "album_type": "album", "external_ids": {}}
    client = FakeAlbumClient({"kept": full})
    items = [
        {"added_at": "2024-01-01T00:00:00Z", "item": {"album": {"id": "kept", "total_tracks": 10}}}
        for _ in range(9)  # 9/10 = 90%, at the threshold
    ]
    by_album = {"kept": items}

    resolved = resolve_candidates(client, by_album)

    assert resolved == {"kept": full}
    assert client.fetched == ["kept"]
    assert cache_path("kept").exists()


def test_resolve_candidates_undoes_cache_write_when_only_post_fetch_total_available() -> None:
    """SimplifiedAlbumObject's total_tracks presence isn't guaranteed — when
    it's absent, the album is fetched (and cached) first, then rejected by
    the full object's total_tracks. The cache write must be undone."""
    full = {"name": "Stray", "total_tracks": 12, "artists": [{"name": "A"}],
            "release_date": "2020-01-01", "album_type": "album", "external_ids": {}}
    client = FakeAlbumClient({"stray": full})
    # No total_tracks on the simplified object -> pre-fetch check can't reject it.
    by_album = {"stray": [{"added_at": "2024-01-01T00:00:00Z", "item": {"album": {"id": "stray"}}}]}

    resolved = resolve_candidates(client, by_album)

    assert resolved == {}
    assert client.fetched == ["stray"]  # had to fetch to find out
    assert not cache_path("stray").exists()  # but the write was undone
