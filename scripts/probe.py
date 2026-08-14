"""Throwaway: confirms two live-API assumptions before poll.py is built
against them (see PLAN.md "Vet notes" and Stage 0, Chunk 5):

1. Does external_ids.upc exist on the full album object (GET /albums/{id})?
   Docs conflict — Feb 2026 changelog lists it removed, live reference pages
   still show it unflagged. Gates whether Stage 1's Discogs-by-barcode step
   has anything to key off of.
2. What is the actual playlist-item album path? Feb 2026 renamed
   tracks.tracks.track -> items.items.item, suggesting
   item["item"]["album"]["id"], but this has never been confirmed against a
   real response.

Also saves the real responses to tests/fixtures/ — per PLAN.md decision
"pytest + committed API fixtures": fixtures are captured from real API
output, never hand-invented.

Uses plain `requests` directly rather than a future spotify/client.py — this
script is meant to be deleted or ignored once poll.py exists; it isn't part
of the pipeline's steady-state code path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from calbum.spotify.auth import get_access_token  # noqa: E402

API_BASE = "https://api.spotify.com/v1"
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
PLAYLIST_NAME = "_selected"


def find_selected_playlist_id(headers: dict) -> str:
    url = f"{API_BASE}/me/playlists"
    params = {"limit": 50}
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        page = resp.json()
        for playlist in page["items"]:
            if playlist["name"] == PLAYLIST_NAME:
                return playlist["id"]
        url = page.get("next")
        params = None  # `next` already encodes params
    raise SystemExit(
        f'No playlist named "{PLAYLIST_NAME}" found among your playlists. '
        "Create it by hand first (see PLAN.md Prereqs)."
    )


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    playlist_id = find_selected_playlist_id(headers)
    print(f'Found "{PLAYLIST_NAME}" playlist: {playlist_id}')

    items_resp = requests.get(
        f"{API_BASE}/playlists/{playlist_id}/items",
        headers=headers,
        params={"limit": 5},
        timeout=10,
    )
    items_resp.raise_for_status()
    items_payload = items_resp.json()

    items_fixture = FIXTURES_DIR / "spotify_playlist_items.json"
    items_fixture.write_text(json.dumps(items_payload, indent=2) + "\n")
    print(f"Saved raw playlist items response -> {items_fixture}")

    items = items_payload.get("items", [])
    if not items:
        raise SystemExit(
            f'"{PLAYLIST_NAME}" is empty — add at least one album to probe '
            "the item shape."
        )

    first_item = items[0]
    print("\n--- Probe 2: playlist-item album path ---")
    new_path = first_item.get("item", {}).get("album", {}).get("id")
    old_path = first_item.get("track", {}).get("album", {}).get("id")
    print(f'  item["item"]["album"]["id"]  = {new_path!r}')
    print(f'  item["track"]["album"]["id"] = {old_path!r}')
    if new_path:
        print('  CONFIRMED: use item["item"]["album"]["id"]')
        album_id = new_path
    elif old_path:
        print('  CONFIRMED: use item["track"]["album"]["id"] (old path still live)')
        album_id = old_path
    else:
        raise SystemExit(
            "Neither known path resolved an album ID — inspect the saved "
            "fixture by hand."
        )

    album_resp = requests.get(f"{API_BASE}/albums/{album_id}", headers=headers, timeout=10)
    album_resp.raise_for_status()
    album_payload = album_resp.json()

    album_fixture = FIXTURES_DIR / "spotify_album.json"
    album_fixture.write_text(json.dumps(album_payload, indent=2) + "\n")
    print(f"Saved raw album response -> {album_fixture}")

    print("\n--- Probe 1: external_ids.upc presence ---")
    upc = album_payload.get("external_ids", {}).get("upc")
    if upc is not None:
        print(f"  CONFIRMED: external_ids.upc is present ({upc!r})")
    else:
        print(
            "  CONFIRMED ABSENT: external_ids.upc is missing from the full "
            "album object. Stage 1 must skip straight to Discogs-by-search "
            "for every album — see PLAN.md Stage 1 gating note."
        )


if __name__ == "__main__":
    main()
