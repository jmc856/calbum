# Music Consolidation — Build Plan

## Problem

Music tracking is scattered across three hand-maintained places (Spotify folders, a
Google Sheet, RateYourMusic). Every add is 3x work, drift is guaranteed, project
gets abandoned.

## Solution shape

One write path, N generated read-only projections.

- **Write surface:** Spotify. Saving an album in the Spotify app IS the capture
  action. No custom capture UI, no mobile app, no share-sheet shortcut.
- **Canonical store:** JSON files in this git repo.
- **Read surfaces:** Google Sheet (share with friends), static site (future-proofing),
  Spotify year playlists (existing habit preserved).

Nothing except the Sheet's `_overrides` tab is ever hand-edited. Everything else is
generated and can be deleted and rebuilt.

## Key decisions (do not relitigate)

- **Spotify-only.** Albums Spotify lacks are handled by hand-adding a JSON record
  with `source: "manual"`. Do not build a general non-Spotify path.
- **JSON over SQLite.** Data is ~200KB now, ~2MB at 5000 albums. Fits in memory,
  no query planner needed. Git diffs give free version history; a static file is
  directly fetchable by a browser with no host. JSON -> SQLite later is a 20-line
  script if ever needed.
- **GitHub Actions cron, not a self-hosted daemon.** The Action already has the
  checkout. **Repo is private.** Secrets are encrypted at rest and unreadable from a
  public repo either way — visibility was never what protected them — but private
  keeps the catalog and `GOOGLE_SA_JSON` out of public view for free. Cost tradeoff:
  private gets 2,000 Actions minutes/month (Free plan, shared across the whole
  account, billed rounded-up-per-job) vs. unlimited on public; cron cadence is set
  to every 2 hours (not hourly) to keep comfortable headroom — see Stage 0. Private
  also means GitHub Pages needs a paid plan, so Stage 4 targets Netlify instead
  (already used for `house_planner/`, see root `CLAUDE.md`).
- **Discogs primary for genre, MusicBrainz fallback.** Discogs `style[]` is the
  granular sub-genre field we actually want. MusicBrainz genres are community tags:
  sparser and coarser. Both support exact barcode/UPC lookup.
- **Identity = Spotify album ID.** No fuzzy matching, no MBIDs as primary key,
  no review queue.

## Vet notes (2026-08-07)

This plan was reviewed against live Spotify/Discogs docs before build start. Verdict:
architecture is sound, build it. Two structural fixes are folded into the stages below:

- **`year` was circular** (derived from playlists in Stage 0, written back to playlists in
  Stage 5). Resolved: `year` is dropped as a field. `release_year` (from `release_date`) is
  the only grouping key. A separate sticky `keeper` boolean (from `^\d{4}$` playlist
  membership) tracks curation status independently. Stage 5 may only *relocate* an already-
  known keeper to its correct `release_year` playlist — it may never add a non-keeper or
  remove a keeper. `keeper` is monotonic; demotion only via `_overrides`.
- **`external_ids.upc` presence is unverified** — docs conflict (Feb 2026 changelog lists it
  as removed; live reference pages still show it, unflagged, while flagging other fields
  Deprecated). Resolve with one real API call, not more doc reading: Stage 0 step 0 fetches
  one saved album and asserts `external_ids.upc` is present. Gates Stage 1 only; does not
  block Stage 0. If absent, MusicBrainz barcode lookup is *not* a fallback (same dependency)
  — fall back to artist+title+release-year search instead.

## Repo layout

    data/
      raw/spotify/{album_id}.json    # raw Spotify blobs, one file per album
      raw/discogs/{album_id}.json    # enrichment cache, one file per album
      albums.json                    # canonical normalized records
      overrides.json                 # snapshot of the Sheet's _overrides tab
      unmatched.json                 # backfill rows that failed to resolve
    site/
      data/albums.json               # generated, denormalized, minimal
      index.html
    src/
      auth.py poll.py enrich.py sheets.py site.py playlists.py
    .github/workflows/sync.yml

## Non-negotiable implementation constraints

1. **Deterministic serialization.** Sorted object keys, records sorted by album ID,
   2-space indent, trailing newline. Without this every run emits a giant noise diff
   and the git-as-audit-log property is destroyed. Implement this in stage 0, not later.
2. **One file per album for raw blobs.** A run touching 3 albums must produce a
   3-file diff, not a whole-file rewrite.
3. **Store raw Spotify JSON verbatim** alongside normalized fields. Batch fetch
   endpoints were removed, so re-hydrating N albums costs N requests.
4. **Enrichment cache is write-once.** Never re-query Discogs for an album that
   already has a cached response.
5. **Single writer.** Only the scheduled Action writes. `git pull --rebase` before
   push. Never run two concurrently.
6. **Genre records carry provenance:** `{name, kind, source}` where source is one of
   `override | discogs_style | discogs_genre | musicbrainz`. This allows retroactive
   upgrades.

## Spotify Web API gotchas (current as of 2026)

- Playlist endpoints use `/items`, not `/tracks`; the response field is `items`.
  Most tutorials and older client libraries are wrong about this.
- Get Several Albums / Artists / Tracks batch endpoints were **removed**. One
  request per album. Pace accordingly.
- Search `limit` maxes at 10 (default 5). Matters for backfill matching.
- **Folders do not exist in the API** and never will. Year playlists are flat;
  they get dragged into a folder once, by hand, in the client.
- Album `external_ids.upc` is *probably* available and is the intended join key to
  Discogs/MusicBrainz — but this is unverified against Feb 2026 changes (see Vet notes
  above). Confirm with a live call before building Stage 1 on it.
- Dev mode requires the owner account to hold Premium. Fine here. Extended quota
  is not obtainable and is not needed.

## Prereqs

- Spotify app, dev mode. Scopes: `user-library-read`, `playlist-read-private`,
  `playlist-modify-private`.
- Run OAuth once locally to obtain a long-lived **refresh token**. This is the only
  interactive auth step in the project.
- Discogs personal access token.
- Google service account; share the target Sheet with its email as Editor.
- GitHub Actions secrets: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`,
  `SPOTIFY_REFRESH_TOKEN`, `DISCOGS_TOKEN`, `GOOGLE_SA_JSON`, `SHEET_ID`.

---

# Stages

Build in order. Each stage is independently useful and independently shippable.
Do not start a stage before the previous one's "done when" is true.

## Stage 0 — Poller

0. **UPC probe.** Fetch one saved album via `GET /me/albums` and assert
   `external_ids.upc` is present in the response. Record the result — it gates Stage 1,
   not this stage.
1. `src/auth.py`: refresh token -> access token. Confirm the flow is authorization-code-
   with-client-secret, not PKCE (PKCE rotates the refresh token on every use; a static
   Actions secret would die on first refresh).
2. `GET /me/albums`, paginated at limit 50. Write each album to
   `data/raw/spotify/{id}.json`. Preserve `added_at`. If an album previously written is no
   longer present in the response, do NOT delete its file or drop it from `albums.json` —
   set `removed_at` on the normalized record instead. Silent deletion undermines the
   audit-log property that is the point of this system.
3. `GET /me/playlists`. Filter names matching `^\d{4}$`. Fetch their items via
   `/playlists/{id}/items` (not `/tracks`). Map `item.album.id` -> `keeper = true`
   (NOT `track.album.id` — the track object now sits under `.item`, per the gotchas above).
4. Normalize into `data/albums.json`:
   `id, artists[], title, release_date, release_year, upc, added_at, removed_at, keeper, source`
   - `release_year` derives from `release_date`, NOT from `added_at`. There is no `year`
     field — `release_year` is the only grouping key, and playlist membership carries only
     the `keeper` bit, never a year. This avoids a circular dependency with Stage 5 (see
     Vet notes above).
   - `keeper` is monotonic: once observed `true` it never reverts to `false` except via an
     explicit `_overrides` entry (Stage 3). A transient playlist-read failure must not
     demote a keeper.
5. Implement the deterministic writer.
6. `.github/workflows/sync.yml`, triggered by `schedule` (`0 */2 * * *` — every 2 hours,
   not hourly, to keep comfortable headroom against the private repo's 2,000
   Actions-minutes/month budget) and `workflow_dispatch` **only** (never a PR-shaped
   trigger — good hygiene for any repo holding `GOOGLE_SA_JSON` in secrets, private or
   not). Commit only when the diff is non-empty. Note: GitHub disables scheduled
   workflows after 60 days with no repo activity; the pipeline's own commits count as
   activity, so this only bites during an unusually quiet stretch.

**Done when:** saving an album on your phone produces a commit within a couple of hours.

## Stage 1 — Enrichment

Gated on the Stage 0 UPC probe. If `external_ids.upc` was absent, skip to the search-based
fallback in step 3b below for all albums (MusicBrainz barcode lookup shares the same
missing-UPC dependency, so it is not a usable fallback in that case).

1. For albums with a `upc` and no genres:
   `GET https://api.discogs.com/database/search?barcode={upc}&type=release`. Normalize the
   barcode first (strip spaces/dashes, handle UPC-12 vs EAN-13 leading-zero mismatch) —
   Discogs' barcode field is free text and a raw compare silently misses matches.
2. Do not take `result[0]` unconditionally — it's an arbitrary pressing and breaks
   consistency across re-runs. Prefer the result whose `master_id` is set; resolve to the
   master release where one exists. Record the resolved release/master ID on the album
   record so the choice is auditable. Cache the full response to
   `data/raw/discogs/{album_id}.json`.
3. MusicBrainz fallback on miss (only when UPC exists but Discogs has no match): barcode ->
   release -> release-group with `inc=genres`.
   3b. No-UPC fallback: Discogs search by artist + title + release year, strict matching,
   flagged for manual review rather than auto-accepted.
4. Rate limits: Discogs 60/min authenticated, tracked via the `X-Discogs-Ratelimit-*`
   response headers. MusicBrainz 1 req/sec and requires a descriptive User-Agent with
   contact info.
5. Write `genres[]` with the provenance shape above.
6. Cache is write-once in normal operation, with one escape hatch: deleting
   `data/raw/discogs/{album_id}.json` forces a re-query, which is how a genre gets
   retroactively upgraded from a coarser source.

**Done when:** most albums have a sub-genre and you can see which source supplied it.

## Stage 2 — Sheets writer

1. One tab per release year, plus a `by-genre` tab.
2. Clear-then-write. Never incremental.
3. Wrap the album cell in `HYPERLINK()` pointing at the Spotify album URL. This is
   what makes the shared sheet playable rather than merely readable — it is the
   whole point of the Sheet as a share surface.
4. Freeze the header row. Set protected ranges on all generated tabs so they can't
   be edited by accident.

**Done when:** you can delete every generated tab and the next run rebuilds them.

## Stage 3 — Overrides

1. Create an `_overrides` tab: `spotify_album_id | genre | sub_genre | keeper | note`. The
   `keeper` column is the only way to demote a keeper back to non-keeper (see Stage 0 —
   `keeper` is otherwise monotonic).
2. Read it as the FIRST step of the pipeline. Snapshot to `data/overrides.json`.
3. Apply at highest precedence, above Discogs and MusicBrainz.

This tab is the only hand-editable surface in the system. It is editable from the
Sheets mobile app, which is the intended correction workflow.

**Done when:** a correction typed on your phone survives the next run.

## Stage 4 — Static site

1. `src/site.py` emits `site/data/albums.json` — denormalized, minimal fields only.
2. `site/index.html`: single file. `fetch()` the JSON, filter client-side by year /
   genre / artist. No build step, no framework, no bundler.
3. Deploy `/site` to Netlify (already used for `house_planner/`; GitHub Pages needs a
   paid plan on this private repo). Because the repo is private, `data/albums.json` is
   not fetchable straight off GitHub — `site/data/albums.json` must ship as part of the
   Netlify deploy, not be fetched cross-origin from the repo. Once automated, that's a
   Netlify CLI/build-hook step in the Action, not drag-and-drop.

**Done when:** there is a public URL you'd actually send to someone.

## Stage 5 — Playlist reconciler

1. Compute desired `YYYY` playlist membership from `albums.json`, scoped to records where
   `keeper == true`, grouped by `release_year`. Diff against actual playlists.
2. **Authority is scoped, not general sync.** This stage may only *relocate* an
   already-known keeper into its correct `release_year` playlist. It must never add an
   album that isn't a keeper, and must never remove an album that is one — `keeper` is the
   upstream source of truth (Stage 0), not something this stage gets to revise.
3. **Ship dry-run first.** Log the intended diff, write nothing, and eyeball it for
   about a week. This is the only stage that writes to Spotify and a bug here
   silently mangles playlists that are not easily recoverable.
4. Then enable add/remove, still within the scoped authority above.

## Stage 6 — Backfill

1. Import existing Sheet tabs. Resolve each to Spotify via search (limit 10 — match
   on artist + title + release year, and be strict).
2. Anything unmatched goes to `data/unmatched.json` to be worked through by hand.
3. Optional: import the RYM ratings export for release dates and RYM IDs. Note that
   the RYM export does NOT contain genre data.

## Stage 7 — Optional, whenever

Browser extension (RYM chart annotation showing what's already in the catalog,
one-click capture, chart CSV export for RYM-grade genre seeding). PWA. Neither is
load-bearing; capture stays mobile-native through Spotify regardless.

---

## Explicit cut list

Ratings. Ranking. Listen history. Multi-user. Any auth beyond a bearer token.
Real-time anything. A general non-Spotify ingestion path. MusicBrainz as a primary
source. Server-side RateYourMusic scraping (gets IPs banned; do not).

## Stopping point

Stages 0-2 solve the original problem completely: after them you maintain exactly
one place (Spotify) and the Sheet regenerates itself. Everything from Stage 3
onward is improvement, not rescue. If momentum dies, dying after Stage 2 is a win.
