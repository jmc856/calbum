# Stage 0, step 1: exchange a long-lived Spotify refresh token for a short-lived
# access token. Authorization-code-with-client-secret flow (NOT PKCE) — PKCE
# rotates the refresh token on every use, which a static Actions secret can't track.
#
# Note: even in this flow Spotify may occasionally return a *new* refresh_token
# in the response, and the original expires after ~6 months regardless. Locally
# we persist a rotated token back to .env. In CI we can't write GitHub secrets
# without extra permissions we've deliberately not granted (see PLAN.md prereqs
# — the OAuth run is meant to stay the one interactive step) — if the token
# expires or gets rotated out from under a CI run, re-run
# scripts/get_refresh_token.py locally and update the SPOTIFY_REFRESH_TOKEN
# GitHub Actions secret by hand.

import base64
import os

import requests
from dotenv import load_dotenv, set_key

from calbum.spotify.schemas import TokenResponse

load_dotenv()

TOKEN_URL = "https://accounts.spotify.com/api/token"
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")


def basic_auth_header(client_id: str, client_secret: str) -> str:
    """Shared helper for Spotify's client-credentials Basic auth header. Used
    here (refresh -> access token) and by scripts/get_refresh_token.py (the
    one-time authorization-code grant)."""
    raw = f"{client_id}:{client_secret}".encode()
    return f"Basic {base64.b64encode(raw).decode()}"


def get_access_token() -> str:
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
    refresh_token = os.environ["SPOTIFY_REFRESH_TOKEN"]

    resp = requests.post(
        TOKEN_URL,
        headers={"Authorization": basic_auth_header(client_id, client_secret)},
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=10,
    )
    resp.raise_for_status()
    tokens = TokenResponse.model_validate(resp.json())

    if tokens.refresh_token and tokens.refresh_token != refresh_token:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            # Don't print the token into CI logs — Actions only masks secrets it
            # already knows about, and this one is new to it.
            print(
                "::warning::Spotify rotated the refresh token. Local .env is not "
                "updated from CI. Re-run scripts/get_refresh_token.py locally and "
                "update the SPOTIFY_REFRESH_TOKEN GitHub secret before the next run."
            )
        else:
            set_key(ENV_PATH, "SPOTIFY_REFRESH_TOKEN", tokens.refresh_token)
            print("Spotify issued a new refresh token; updated .env.")

    return tokens.access_token


if __name__ == "__main__":
    token = get_access_token()
    print(f"OK — got access token ({token[:8]}...{token[-4:]}, {len(token)} chars)")
