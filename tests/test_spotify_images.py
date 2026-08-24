"""Tests for pick_image — the size-selection rule shared by album covers
(poll.py) and artist portraits (artists.py)."""

from __future__ import annotations

from calbum.spotify.images import pick_image

IMAGES = [
    {"url": "small", "width": 64},
    {"url": "large", "width": 640},
    {"url": "medium", "width": 300},
]


def test_no_min_width_picks_the_largest() -> None:
    """A consumer can downscale a too-large image, never upscale a too-small
    one — so unconstrained means widest."""
    assert pick_image(IMAGES) == "large"


def test_picks_by_width_not_array_order() -> None:
    """Spotify documents images as widest-first, but relying on that would
    break silently if it changed."""
    assert pick_image([{"url": "a", "width": 1}, {"url": "b", "width": 99}]) == "b"


def test_min_width_picks_the_smallest_qualifying_image() -> None:
    """Smallest that still clears the bar: a 44px avatar shouldn't ship a
    640px file."""
    assert pick_image(IMAGES, 200) == "medium"


def test_min_width_falls_back_to_largest_when_nothing_qualifies() -> None:
    assert pick_image(IMAGES, 5000) == "large"


def test_min_width_is_inclusive() -> None:
    assert pick_image(IMAGES, 300) == "medium"


def test_empty_and_missing() -> None:
    assert pick_image([]) is None
    assert pick_image(None) is None


def test_entries_without_a_url_are_ignored() -> None:
    assert pick_image([{"width": 640}, {"url": "ok", "width": 64}]) == "ok"


def test_missing_width_does_not_crash() -> None:
    assert pick_image([{"url": "a"}, {"url": "b", "width": 100}]) == "b"
