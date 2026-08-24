"""Picking an image out of a Spotify `images` array.

Album covers (poll.py) and artist portraits (artists.py) face the same
choice, so the rule lives here once rather than in each caller. Selection is
by width rather than array order — Spotify documents the array as ordered
widest-first, but relying on that would break silently if it ever changed.
"""

from __future__ import annotations


def pick_image(images: list[dict] | None, min_width: int | None = None) -> str | None:
    """URL of the best image for the intended display size.

    With no `min_width`, the largest available — a consumer can always
    downscale a too-large image, never upscale a too-small one.

    With `min_width`, the *smallest* image at least that wide, falling back to
    the largest when nothing qualifies. That keeps a 44px avatar from shipping
    a 640px file while still degrading to whatever exists.
    """
    sized = [img for img in (images or []) if img.get("url")]
    if not sized:
        return None

    largest = max(sized, key=lambda img: img.get("width") or 0)
    if min_width is None:
        return largest.get("url")

    qualifying = [img for img in sized if (img.get("width") or 0) >= min_width]
    if not qualifying:
        return largest.get("url")
    return min(qualifying, key=lambda img: img.get("width") or 0).get("url")
