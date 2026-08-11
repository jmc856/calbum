"""One-time interactive OAuth grant. Run this YOURSELF, in your own terminal —
not by asking an agent to run it for you — since the point is to keep the
refresh token out of any tool transcript.

Prereqs:
    - .env in the repo root (copy .env.example) with SPOTIFY_CLIENT_ID and
      SPOTIFY_CLIENT_SECRET filled in from the Spotify dashboard, and
      SPOTIFY_REDIRECT_URI matching the Redirect URI registered there exactly
      (http://127.0.0.1:8888/callback).

What it does:
    1. Opens your browser to Spotify's consent screen.
    2. Runs a local server on 127.0.0.1:8888 to catch the redirect.
    3. Exchanges the authorization code for an access + refresh token.
    4. Writes SPOTIFY_REFRESH_TOKEN into .env.

The refresh token is long-lived (~6 months, per Spotify's docs) — treat it like
a password. This is the only interactive auth step in the project
(see PLAN.md, Prereqs).
"""

import http.server
import os
import secrets
import sys
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv, set_key

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from models import TokenResponse  # noqa: E402
from token_auth import basic_auth_header  # noqa: E402

load_dotenv()

CLIENT_ID = os.environ["SPOTIFY_CLIENT_ID"]
CLIENT_SECRET = os.environ["SPOTIFY_CLIENT_SECRET"]
REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
SCOPES = "user-library-read playlist-read-private playlist-modify-private"
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

_state = secrets.token_urlsafe(16)
_auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
    {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": _state,
    }
)

_result: dict[str, str | None] = {}


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        _result["code"] = params.get("code", [None])[0]
        _result["state"] = params.get("state", [None])[0]
        _result["error"] = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>Done - you can close this tab.</body></html>")

    def log_message(self, format, *args):
        pass  # silence default request logging


def main() -> None:
    print(f"Opening your browser for Spotify consent...\n{_auth_url}\n")
    webbrowser.open(_auth_url)

    server = http.server.HTTPServer(("127.0.0.1", 8888), CallbackHandler)
    print("Waiting for the redirect on http://127.0.0.1:8888/callback ...")
    while "code" not in _result and "error" not in _result:
        server.handle_request()

    if _result.get("error"):
        raise SystemExit(f"Spotify returned an error: {_result['error']}")
    if _result.get("state") != _state:
        raise SystemExit("state mismatch on callback — possible CSRF, aborting")
    if not _result.get("code"):
        raise SystemExit("no authorization code received")

    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": basic_auth_header(CLIENT_ID, CLIENT_SECRET)},
        data={
            "grant_type": "authorization_code",
            "code": _result["code"],
            "redirect_uri": REDIRECT_URI,
        },
        timeout=10,
    )
    resp.raise_for_status()
    tokens = TokenResponse.model_validate(resp.json())
    if not tokens.refresh_token:
        raise SystemExit(
            "Spotify did not return a refresh_token — check that the "
            "authorization request actually prompted for consent."
        )

    set_key(ENV_PATH, "SPOTIFY_REFRESH_TOKEN", tokens.refresh_token)
    print(f"\nSaved SPOTIFY_REFRESH_TOKEN to {os.path.abspath(ENV_PATH)}")
    print(
        "Next: copy that same value into a GitHub Actions secret named "
        "SPOTIFY_REFRESH_TOKEN (repo Settings -> Secrets and variables -> Actions)."
    )


if __name__ == "__main__":
    main()
