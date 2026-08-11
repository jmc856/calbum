"""Shared helper for Spotify's client-credentials Basic auth header. Used by
both auth.py (refresh -> access token) and scripts/get_refresh_token.py
(the one-time authorization-code grant)."""

import base64


def basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return f"Basic {base64.b64encode(raw).decode()}"
