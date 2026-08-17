"""Tests for overrides.py: patching an existing album, inserting a manual
album, genre-override reversibility, and the malformed-row degrade path."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from calbum.models import GenreSource
from calbum.overrides import apply_overrides, load_overrides


NOW = datetime(2024, 1, 1, tzinfo=UTC)


# --- load_overrides --------------------------------------------------------


def test_load_overrides_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    assert load_overrides(tmp_path / "does-not-exist.toml") == {}


def test_load_overrides_parses_a_real_file(tmp_path: Path) -> None:
    path = tmp_path / "overrides.toml"
    path.write_text('["abc123"]\ngenres = ["Rock"]\n')
    assert load_overrides(path) == {"abc123": {"genres": ["Rock"]}}


# --- apply_overrides: patching an existing album ----------------------------


def test_patches_genres_on_an_existing_album_and_tags_source(make_album) -> None:
    album = make_album("a1")
    overrides = {"a1": {"genres": ["Hip Hop"], "styles": ["West Coast"]}}

    [result] = apply_overrides([album], overrides, NOW)

    assert {g.name for g in result.genres} == {"Hip Hop", "West Coast"}
    assert all(g.source == GenreSource.OVERRIDE for g in result.genres)
    assert result.discogs_release_id is None


def test_genre_override_replaces_prior_discogs_genres(make_album) -> None:
    from calbum.models import Genre

    discogs_genre = Genre(name="Conscious", kind="genre", source=GenreSource.DISCOGS_SEARCH)
    album = make_album("a1", genres=[discogs_genre], discogs_release_id=42)
    overrides = {"a1": {"genres": ["Hip Hop"]}}

    [result] = apply_overrides([album], overrides, NOW)

    assert [g.name for g in result.genres] == ["Hip Hop"]
    assert result.discogs_release_id is None


def test_patches_arbitrary_scalar_fields(make_album) -> None:
    album = make_album("a1", title="ARIZONA BABY")
    overrides = {"a1": {"title": "Arizona Baby"}}

    [result] = apply_overrides([album], overrides, NOW)

    assert result.title == "Arizona Baby"


def test_release_date_patch_keeps_release_year_in_sync(make_album) -> None:
    import datetime as dt

    album = make_album("a1", release_year=2019)
    overrides = {"a1": {"release_date": dt.date(2020, 3, 15)}}

    [result] = apply_overrides([album], overrides, NOW)

    assert result.release_date == dt.date(2020, 3, 15)
    assert result.release_year == 2020


def test_unrecognized_field_is_ignored_not_fatal(make_album, caplog) -> None:
    album = make_album("a1")
    overrides = {"a1": {"favorite_color": "blue"}}

    [result] = apply_overrides([album], overrides, NOW)

    assert result.id == "a1"  # nothing crashed


def test_note_field_is_never_stored(make_album) -> None:
    album = make_album("a1")
    overrides = {"a1": {"genres": ["Rock"], "note": "just a comment"}}

    [result] = apply_overrides([album], overrides, NOW)

    assert not hasattr(result, "note")


def test_unaffected_album_passes_through_untouched(make_album) -> None:
    album = make_album("a1", title="Untouched")
    result = apply_overrides([album], overrides={}, now=NOW)

    assert result == [album]


# --- apply_overrides: reversibility -----------------------------------------


def test_deleting_the_override_row_resets_override_genres_to_empty(make_album) -> None:
    """Deleting a genre override must clear it back to [] so enrich.run()
    (which only touches albums with genres == []) re-derives it from
    Discogs on the next run."""
    from calbum.models import Genre

    overridden = make_album(
        "a1", genres=[Genre(name="Hip Hop", kind="genre", source=GenreSource.OVERRIDE)], discogs_release_id=None
    )

    result = apply_overrides([overridden], overrides={}, now=NOW)  # row deleted

    assert result[0].genres == []
    assert result[0].discogs_release_id is None


def test_removing_only_the_genres_key_from_the_row_also_resets(make_album) -> None:
    """The row can stay (e.g. keeping a `note`) with genres/styles removed
    from it — same reset behavior as deleting the row outright."""
    from calbum.models import Genre

    overridden = make_album("a1", genres=[Genre(name="Hip Hop", kind="genre", source=GenreSource.OVERRIDE)])
    overrides = {"a1": {"note": "used to override the genre, not anymore"}}

    result = apply_overrides([overridden], overrides, NOW)

    assert result[0].genres == []


def test_discogs_sourced_genres_are_not_reset_when_no_override_present(make_album) -> None:
    from calbum.models import Genre

    album = make_album("a1", genres=[Genre(name="Rock", kind="genre", source=GenreSource.DISCOGS_SEARCH)])

    result = apply_overrides([album], overrides={}, now=NOW)

    assert result[0].genres == album.genres  # untouched, not an override target


# --- apply_overrides: manual albums -----------------------------------------


def test_inserts_a_manual_album_when_key_matches_nothing() -> None:
    overrides = {
        "manual:boc-geogaddi": {
            "artists": ["Boards of Canada"],
            "title": "Geogaddi",
            "release_date": "2002-02-18",
            "genres": ["Electronic"],
        }
    }

    result = apply_overrides([], overrides, NOW)

    [album] = result
    assert album.id == "manual:boc-geogaddi"
    assert album.source == "manual"
    assert album.artists == ["Boards of Canada"]
    assert album.release_year == 2002
    assert album.genres[0].name == "Electronic"
    assert album.genres[0].source == GenreSource.OVERRIDE


def test_manual_album_without_genres_is_left_empty_for_enrich_to_fill(make_album) -> None:
    overrides = {
        "manual:x": {"artists": ["A"], "title": "T", "release_date": "2020-01-01"},
    }

    [album] = apply_overrides([], overrides, NOW)

    assert album.genres == []


def test_manual_album_defaults_added_at_to_now_when_not_specified() -> None:
    overrides = {"manual:x": {"artists": ["A"], "title": "T", "release_date": "2020-01-01"}}

    [album] = apply_overrides([], overrides, NOW)

    assert album.added_at == NOW


def test_manual_album_uses_explicit_added_at_when_given() -> None:
    overrides = {
        "manual:x": {
            "artists": ["A"],
            "title": "T",
            "release_date": "2020-01-01",
            "added_at": "2019-06-01T00:00:00Z",
        }
    }

    [album] = apply_overrides([], overrides, NOW)

    assert album.added_at == datetime(2019, 6, 1, tzinfo=UTC)


def test_manual_album_missing_required_field_is_skipped_not_fatal() -> None:
    overrides = {"manual:x": {"title": "T"}}  # missing artists, release_date

    result = apply_overrides([], overrides, NOW)

    assert result == []


def test_a_second_run_patches_the_manual_album_instead_of_reinserting(make_album) -> None:
    """Once a manual album exists in albums.json, its id is now a known
    key — the next overrides run patches it rather than treating it as a
    fresh manual insertion."""
    manual = make_album("manual:x", title="Old Title", source="manual")
    overrides = {"manual:x": {"title": "New Title"}}

    [result] = apply_overrides([manual], overrides, NOW)

    assert result.title == "New Title"
    assert result.added_at == manual.added_at  # untouched: not in this override entry


# --- apply_overrides: malformed rows degrade, never abort -------------------


def test_a_malformed_row_is_skipped_and_does_not_affect_other_rows(make_album) -> None:
    good = make_album("good")
    overrides = {
        "good": {"genres": ["Rock"]},
        "bad": {"artists": ["A"], "title": "T", "release_date": "not-a-real-date-xyz"},
    }

    result = apply_overrides([good], overrides, NOW)

    ids = {a.id for a in result}
    assert "good" in ids
    assert "bad" not in ids
