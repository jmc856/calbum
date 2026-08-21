# calbum

Tracks my favorite albums by year, genre, and artist. Adding an album to a
Spotify playlist called `_selected` is the only manual step — genres, a
Google Sheet, and a web page all get generated from that automatically.

**Live:** https://jmc856.github.io/calbum/

## How it works

```
Spotify (_selected playlist)
  -> poll        pulls new albums into data/albums.json
  -> overrides   applies manual fixes / albums added outside Spotify
  -> enrich      looks up genres on Discogs
  -> sheets      updates the Google Sheet
  -> site        builds the JSON the frontend uses
```

Runs on a schedule via `.github/workflows/sync.yml`. To add an album, add it
to `_selected` in Spotify — that's it. The only file edited by hand is
`data/overrides.toml`.

## Local dev

```bash
uv sync
cp .env.example .env   # fill in your own credentials
uv run pytest
uv run python -m calbum.poll   # etc. — see .github/workflows/sync.yml for the full sequence

cd web && npm install && npm run dev
```
