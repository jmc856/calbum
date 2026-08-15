"""Writer determinism: constraint 1 (sorted keys, records sorted by album ID,
2-space indent, trailing newline) and decision 10 (atomic write)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from calbum.writer import dump_albums, read_albums, write_albums, write_json_atomic


def test_dump_albums_sorts_by_id(make_album) -> None:
    albums = [make_album("b"), make_album("a"), make_album("c")]
    dumped = dump_albums(albums)
    assert [a["id"] for a in dumped] == ["a", "b", "c"]


def test_write_albums_is_byte_identical_across_runs(make_album, tmp_path: Path) -> None:
    albums = [make_album("b"), make_album("a")]
    path = tmp_path / "albums.json"

    write_albums(path, albums)
    first = path.read_text()

    write_albums(path, list(reversed(albums)))  # input order shouldn't matter
    second = path.read_text()

    assert first == second


def test_read_albums_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert read_albums(tmp_path / "does-not-exist.json") == []


def test_read_albums_round_trips_write_albums(make_album, tmp_path: Path) -> None:
    path = tmp_path / "albums.json"
    albums = [make_album("b"), make_album("a")]

    write_albums(path, albums)

    assert [a.id for a in read_albums(path)] == ["a", "b"]


def test_read_albums_rejects_a_file_that_exists_but_is_empty(tmp_path: Path) -> None:
    """An existing-but-empty albums.json is data loss, not a fresh start —
    see poll.py's mass-removal guard, which relies on this to never silently
    read a truncated store as a cold start."""
    path = tmp_path / "albums.json"
    path.write_text("[]\n")

    with pytest.raises(SystemExit):
        read_albums(path)


def test_write_json_atomic_sorts_keys_and_indents(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    write_json_atomic(path, {"z": 1, "a": 2, "nested": {"y": 1, "b": 2}})
    text = path.read_text()

    # Round-trips to the same data...
    assert json.loads(text) == {"z": 1, "a": 2, "nested": {"y": 1, "b": 2}}
    # ...but the top-level and nested keys are written in sorted order.
    assert text.index('"a"') < text.index('"z"')
    assert text.index('"b"') < text.index('"y"')
    # 2-space indent.
    assert '\n  "a"' in text


def test_write_json_atomic_ends_with_single_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    write_json_atomic(path, {"a": 1})
    text = path.read_text()
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_write_json_atomic_leaves_no_tmp_file_behind(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    write_json_atomic(path, {"a": 1})
    assert not (tmp_path / "out.json.tmp").exists()
    assert path.exists()


def test_write_json_atomic_survives_a_previous_partial_tmp_file(tmp_path: Path) -> None:
    """A leftover .tmp from a prior crashed run must not stop or corrupt the
    next write."""
    path = tmp_path / "out.json"
    (tmp_path / "out.json.tmp").write_text("garbage, not valid json")

    write_json_atomic(path, {"a": 1})

    assert json.loads(path.read_text()) == {"a": 1}
