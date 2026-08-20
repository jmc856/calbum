# Music Consolidation — Build Plan

## Problem

Music tracking is scattered across three hand-maintained places (Spotify folders, a
Google Sheet, RateYourMusic). Every add is 3x work, drift is guaranteed, project
gets abandoned.

## Solution shape

One write path, N generated read-only projections.

- **Write surface:** a single Spotify playlist, `_selected`. Adding the whole album to it
  IS the capture action — the one and only commitment gesture. No custom capture UI, no
  mobile app, no share-sheet shortcut.
- **How you decide what goes into `_selected` is entirely your business and out of scope.**
  Hearting, a scratch playlist, memory — whatever workflow you use to narrow candidates
  down happens inside Spotify and the pipeline never sees it. Nothing downstream (the
  Sheet, the site) needs to know what you considered and passed on — only what you kept.
- **Canonical store:** JSON files in this git repo.
- **Read surfaces:** Google Sheet (share with friends), a React frontend (Stage 4).

Nothing except `data/overrides.toml` is ever hand-edited (see Stage 3).
Everything else is generated and can be deleted and rebuilt.

## Key decisions (do not relitigate)

- **`_selected` is the only write surface.** Spotify playlists can't hold albums (only
  tracks/episodes) or be organized into folders via the API — folders are invisible to any
  code we write, full stop. So capture means adding a whole album's tracks to one flat
  playlist. Everything Sheet/site needs is derivable from `_selected` playlist items plus
  one `GET /albums/{id}` per album for UPC — see Stage 0.
- **Candidates are explicitly out of scope.** Do not build a queue/inbox surface, do not
  poll any playlist except `_selected`, do not try to infer what was considered and
  rejected. This was tried twice this session and reversed both times — see cut list.
- **JSON over SQLite.** `albums.json` itself is ~200KB now, ~2MB at 5000 albums, and
  fits in memory with no query planner needed. (The per-album raw Spotify blobs from
  constraint 2 are on top of that and grow in git history on every re-fetch, but at
  the actual growth rate — no bulk backfill, ~5-10 albums added at a time, see Stage
  5 — that's kilobytes per poll run, not a practical concern.) Git diffs give free
  version history; a static file is directly fetchable by a browser with no host.
  JSON -> SQLite later is a 20-line script if ever needed.
- **GitHub Actions cron, not a self-hosted daemon.** The Action already has the
  checkout. **Repo is private.** Secrets are encrypted at rest and unreadable from a
  public repo either way — visibility was never what protected them — but private
  keeps the catalog and `GOOGLE_SA_JSON` out of public view for free. Cost tradeoff:
  private gets 2,000 Actions minutes/month (Free plan, shared across the whole
  account, billed rounded-up-per-job) vs. unlimited on public; cron cadence is set
  to every 4 hours (not hourly) to keep comfortable headroom — see Stage 0.
  `workflow_dispatch` is also enabled, so a run can be triggered on demand instead
  of waiting for the next scheduled tick. Private
  also means GitHub Pages needs a paid plan, so Stage 4 targets Netlify instead
  (already used for `house_planner/`, see root `CLAUDE.md`).
- **Genre cascade, not single-source.** The requirement is a primary genre plus at least
  one sub-genre per album. Only Discogs (`genre[]` + `style[]`) produces that shape;
  MusicBrainz is flat community tags and Spotify's artist-level genres are flat and
  deprecated. So the cascade is Discogs-by-barcode -> Discogs-by-search ->
  MusicBrainz -> `overrides.toml`, in that order, never skipping straight to MusicBrainz —
  see Stage 1.
- **Identity = Spotify album ID.** No fuzzy matching, no MBIDs as primary key,
  no review queue.

## Vet notes (2026-08-07, revised 2026-08-11)

This plan was reviewed against live Spotify/Discogs docs before build start. Verdict:
architecture is sound, build it. The write-surface design below was iterated three times
during implementation planning as real usage habits surfaced; this section reflects the
final design, not the history.

- **The write surface is `_selected` alone — no queue, no `keeper` field, no
  `/me/albums` involvement.** Earlier drafts of this plan considered `/me/albums`
  (heart-save) as the capture action, then a two-playlist `_inbox`/`_selected` model, then
  heart-as-queue with `_selected` as a separate promotion step. All were reversed once it
  became clear no deliverable depends on knowing what was considered and rejected — only
  what was kept. `_selected` is both the capture action and the keeper signal in one.
- **This removes the `year`/`keeper` circularity that existed in earlier drafts entirely**,
  rather than resolving it with a monotonic field. There is no `keeper` field anymore —
  every album in `albums.json` is in `_selected` by construction. `release_year` (from
  `release_date`) remains the only grouping key, used purely for read-surface grouping,
  never written back to Spotify.
- **`external_ids.upc` presence is unverified** — docs conflict (Feb 2026 changelog lists it
  as removed; live reference pages still show it, unflagged, while flagging other fields
  Deprecated). Resolve with one real API call: Chunk 5 (`scripts/probe.py`) fetches one
  album via `GET /albums/{id}` and checks for `external_ids.upc`. Gates Stage 1 only; does
  not block Stage 0.
- **The playlist-item album-ID JSON path is also unverified** and is the pipeline's critical
  path now that everything derives from `_selected`. Feb 2026 renamed
  `tracks.tracks.track -> items.items.item`, suggesting `item["item"]["album"]["id"]`, but
  this has not been confirmed against a real response. `scripts/probe.py` confirms this
  before `poll.py` is written against an assumption.
- **Dropping `keeper` removes a safety property, so a new one replaces it.** A monotonic
  `keeper` bit used to make a partial/failed playlist read inert. With `_selected` as the
  sole input, a transient failure mid-pagination would make every unreturned album look
  deleted. Stage 0 adds an explicit mass-removal guard for this — see below.

## Repo layout

Python is a real installable package, not a flat script directory — the previous flat
`src/*.py` layout only worked via a `sys.path` hack in `scripts/get_refresh_token.py`.

    src/calbum/
      models.py              # OUR canonical domain models (Album, Genre) — see constraint 6
      writer.py               # deterministic JSON writer — see constraint 1
      poll.py                 # Stage 0
      enrich.py                # Stage 1
      sheets.py                # Stage 2
      site.py                  # Stage 4 data export
      spotify/                 # all Spotify API code, isolated — see below
        auth.py                 # refresh token -> access token
        client.py                # HTTP session, pagination, 429/Retry-After handling
        schemas.py                # pydantic models for SPOTIFY's response shapes
    web/                      # React frontend (Vite + React + TS) — Stage 4
      public/data/albums.json   # emitted by site.py, served same-origin, no cross-origin fetch
    docker/                   # Dockerfile.pipeline, Dockerfile.web — local dev + self-host option
    docker-compose.yml
    data/
      raw/spotify/{album_id}.json    # raw Spotify blobs, one file per album
      raw/discogs/{album_id}.json    # enrichment cache, one file per album
      albums.json                    # canonical normalized records
      overrides.toml                 # hand-edited corrections + manual albums (Stage 3)
      unmatched.json                 # backfill rows that failed to resolve
    scripts/
      get_refresh_token.py     # one-time interactive OAuth grant
      probe.py                 # throwaway: confirms API assumptions before poll.py is built
    .github/workflows/sync.yml

**The module boundary that matters:** `spotify/schemas.py` models *Spotify's* response
shapes; `models.py` models *ours*. Nothing outside `spotify/` touches a raw Spotify dict.
The same pattern applies to `discogs/` and `musicbrainz/` once Stage 1 needs it.

**Docker is convenience, not load-bearing.** Neither the pipeline (runs in GitHub Actions)
nor the frontend (deploys as static files to Netlify) requires it in production. It exists
for reproducible local dev and to keep self-hosting open. CI runs `uv run` directly, not
through Docker, so a container problem can never break the sync job.

## Non-negotiable implementation constraints

1. **Deterministic serialization.** Sorted object keys, records sorted by album ID,
   2-space indent, trailing newline. Without this every run emits a giant noise diff
   and the git-as-audit-log property is destroyed. Implement this in stage 0, not later.
   Pydantic's `model_dump_json()` does **not** sort keys — models must go through
   `model_dump(mode="json")` and then `src/calbum/writer.py`.
2. **One file per album for raw blobs.** A run touching 3 albums must produce a
   3-file diff, not a whole-file rewrite.
3. **Store raw Spotify JSON verbatim** alongside normalized fields. Batch fetch
   endpoints were removed, so re-hydrating N albums costs N requests. This cache is also
   how the UPC gap gets filled — see Stage 0.
4. **Enrichment cache is write-once.** Never re-query Discogs for an album that
   already has a cached response. One escape hatch: deleting the cache file forces a
   re-query, which is how a genre gets retroactively upgraded from a coarser source.
5. **Single writer.** Only the scheduled Action writes. `git pull --rebase` before
   push. Never run two concurrently.
6. **Genre records carry provenance:** `{name, kind, source}` where source is one of
   `override | discogs_style | discogs_genre | discogs_search | musicbrainz`. This
   allows retroactive upgrades and keeps it honest about which cascade step supplied
   each genre.
7. **Mass-removal guard.** Since `_selected` is the sole source of album identity (no
   monotonic `keeper` field to fall back on), `poll.py` must abort before writing if the
   resolved album count drops more than ~10% (or at all, on a small catalog) versus the
   existing `albums.json`. A partial/failed playlist read must fail loudly, not silently
   commit a mass deletion.

## Spotify Web API gotchas (current as of 2026)

- Playlist endpoints use `/items`, not `/tracks`; the response field is `items`.
  Most tutorials and older client libraries are wrong about this. The exact per-item
  album path (`item["item"]["album"]["id"]` vs. the older `item["track"]["album"]["id"]`)
  is unconfirmed — see Chunk 5.
- Get Several Albums / Artists / Tracks batch endpoints were **removed**. One
  request per album. Pace accordingly.
- Search `limit` maxes at 10 (default 5). Matters for backfill matching.
- **Folders do not exist in the API** and never will. This is why `_selected` must be a
  single flat playlist, not a folder of per-year playlists.
- Playlist items carry a `SimplifiedAlbumObject`, which does **not** include
  `external_ids`. UPC requires a separate `GET /albums/{id}` per album — see Stage 0.
- Album `external_ids.upc` on the full album object is *probably* available but
  unverified against Feb 2026 changes (see Vet notes above). Confirmed via
  `scripts/probe.py` (Chunk 5) before Stage 1 is built on it.
- Dev mode requires the owner account to hold Premium. Fine here. Extended quota
  is not obtainable and is not needed.

## Prereqs

- Spotify app, dev mode. Scopes: `user-library-read`, `playlist-read-private`.
  (`playlist-modify-private` is not needed — the pipeline never writes to Spotify.)
- Run OAuth once locally to obtain a long-lived **refresh token**. This is the only
  interactive auth step in the project.
- Discogs personal access token.
- Google service account; share the target Sheet with its email as Editor.
- GitHub Actions secrets: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`,
  `SPOTIFY_REFRESH_TOKEN`, `DISCOGS_TOKEN`, `GOOGLE_SA_JSON`, `SHEET_ID`.
- A Spotify playlist named `_selected`, created by hand once, holding the whole albums you
  consider keepers.

---

# Stages

Build in order. Each stage is independently useful and independently shippable.
Do not start a stage before the previous one's "done when" is true.

## Stage 0 — Poller

Implemented as `poll.Poller` (`__init__(self, client: AlbumSource, data_dir:
Path)`): the client, data dir, and loaded `existing` albums live on `self`
rather than being re-passed through ~15 module functions by parameter.
`parse_release_date`, `earliest_added_at`, `simplified_album`,
`_below_threshold`, and `check_mass_removal_guard` stay free functions —
pure, don't touch `self`, and are exactly what the test suite exercises in
isolation.

1. `src/calbum/spotify/auth.py`: refresh token -> access token. Confirm the flow is
   authorization-code-with-client-secret, not PKCE (PKCE rotates the refresh token on
   every use; a static Actions secret would die on first refresh).
2. `GET /playlists/{_selected_id}/items`, paginated. Resolve the set of album IDs
   currently in `_selected` from each item's album object, skipping `is_local` items.
   `added_at` for each album = the earliest item `added_at` across its tracks in the
   playlist — this is the commitment timestamp.
3. For any resolved album ID without a cached raw blob in `data/raw/spotify/`, fetch
   `GET /albums/{id}` (full `AlbumObject`, has `external_ids.upc`; the playlist item's
   `SimplifiedAlbumObject` does not) and cache it. Write-once, same discipline as the
   Discogs cache (constraint 4).
4. **Mass-removal guard (constraint 7).** Compare the resolved album count against the
   existing `albums.json`. If it dropped more than the threshold, abort without writing
   and exit non-zero.
5. Normalize into `data/albums.json`:
   `id, artists[], title, release_date, release_year, album_type, upc, added_at, removed_at, genres, source`
   - `release_year` derives from `release_date`, NOT from `added_at`.
   - `album_type` (`album`/`single`/`compilation`) is captured but never filtered at
     ingest — read surfaces filter later if they want to.
   - There is no `keeper` field. Every record in `albums.json` is, by construction, an
     album that is (or was) in `_selected`.
   - `removed_at`: if a previously-recorded album is no longer resolvable from `_selected`
     (and the mass-removal guard didn't trip), set `removed_at` rather than deleting the
     record. This now means "you changed your mind about a favorite" — more consequential
     than the old inbox-rejection case, which no longer exists.
6. Implement the deterministic writer (`src/calbum/writer.py`).
7. `.github/workflows/sync.yml`, triggered by `schedule` (`0 */4 * * *` — every 4 hours,
   not hourly, to keep comfortable headroom against the private repo's 2,000
   Actions-minutes/month budget) and `workflow_dispatch` **only** (never a PR-shaped
   trigger — good hygiene for any repo holding `GOOGLE_SA_JSON` in secrets, private or
   not; `workflow_dispatch` also means a run can be triggered on demand rather than
   waiting for the next scheduled tick). Commit only when the diff is non-empty. Note:
   GitHub disables scheduled workflows after 60 days with no repo activity; the
   pipeline's own commits count as activity, so this only bites during an unusually
   quiet stretch.

**Known limitation, accepted:** adding an album to `_selected` and removing it again within
a single ~4h poll window means it's never recorded. This is a documented property, not a
bug — the interval is set for Actions-minutes headroom, not to catch every transient edit.

**Done when:** adding a whole album to `_selected` on your phone produces a commit within
a couple of hours.

## Stage 1 — Enrichment

Gated on the Stage 0 UPC probe (`scripts/probe.py`, Chunk 5). If `external_ids.upc` is
absent from the album object entirely, every album skips straight to step 2 (Discogs
search) — MusicBrainz is not a substitute fallback for a missing UPC, since it needs the
same barcode.

The cascade preserves the two-tier genre shape (`genre[]` primary + `style[]` sub) as long
as possible, since that shape is the actual requirement — MusicBrainz can only ever fill
the primary tier, so it's the last automated resort, not the first fallback.

1. **Discogs by barcode.** For albums with a `upc` and no genres:
   `GET https://api.discogs.com/database/search?barcode={upc}&type=release`. Normalize the
   barcode for UPC-12/EAN-13 leading-zero mismatches; Discogs' own search already compares
   digits-only and ignores spaces/dashes, so punctuation stripping is not needed on our end.
2. Do not take `result[0]` unconditionally — it's an arbitrary pressing and breaks
   consistency across re-runs. Prefer the result whose `master_id` is set; resolve to the
   master release where one exists. Record the resolved release/master ID on the album
   record so the choice is auditable. Cache the full response to
   `data/raw/discogs/{album_id}.json`.
3. **Discogs by artist + title + release_year search**, strict matching, on any album still
   missing genres after step 1 (whether because there was no UPC, or the barcode search
   missed — Discogs' barcode coverage skews physical media, so misses are expected on a
   Spotify-native, digital-heavy catalog). This is the real coverage recovery step and
   keeps the two-tier shape intact.
4. **MusicBrainz fallback**, primary-genre-only, for anything still missing after step 3:
   barcode -> release -> release-group with `inc=genres` (only when a UPC exists to look
   up; otherwise skip straight to `overrides.toml`, Stage 3).
5. Rate limits: Discogs 60/min authenticated, tracked via the `X-Discogs-Ratelimit-*`
   response headers. MusicBrainz 1 req/sec and requires a descriptive User-Agent with
   contact info.
6. Write `genres[]` with the provenance shape from constraint 6 — `source` records exactly
   which cascade step supplied each genre.
7. Cache is write-once in normal operation, with the escape hatch from constraint 4.
8. **Report coverage after the run**: counts by source, and the number of albums still
   lacking a sub-genre. This number — not an assumption — decides whether a fourth source
   (Last.fm `album.getTopTags`, free, no auth needed for reads, but noisy and needing
   tag-filtering) is worth adding.

**Done when:** the coverage report shows most albums have both a primary genre and a
sub-genre, and you can see which cascade step supplied each one.

## Stage 2 — Sheets writer

1. A flat `Albums` tab (one row per active album, `Year` as a column — not a
   tab-per-year split) plus a `by-genre` tab (one row per album x genre).
   Genre/Sub-genre on `Albums` are joined-string context columns, not the
   filter surface — Sheets' native filter/sort/pivot only works cleanly on
   atomic values, so `by-genre`'s one-row-per-genre shape is where filtering
   and grouping by an individual genre actually works. Confirmed live against
   the user's actual old hand-maintained tab: it used exactly one Genre + one
   Sub-genre column per album, not a list — but the user's stated priority is
   filterability in both Sheets and the eventual React frontend (Stage 4),
   not replicating that convention.
2. Clear-then-write. Never incremental.
3. Wrap the album cell in `HYPERLINK()` pointing at the Spotify album URL. This is
   what makes the shared sheet playable rather than merely readable — it is the
   whole point of the Sheet as a share surface.
4. Freeze the header row. Set protected ranges on all generated tabs so they can't
   be edited by accident. Protected ranges must include the writing service
   account's own email in `editor_users_emails` (with
   `requesting_user_can_edit=True`) — confirmed live that omitting this makes
   Google's API reject the request outright ("You can't remove yourself as an
   editor"), since an empty `editor_users_emails` is sent as an explicit
   "no editors," not "auto-add the owner" as gspread's docstring implies.
5. A real font and auto-resized columns on every generated tab (cosmetic,
   confirmed feasible via `gspread`). Must be applied before step 4's
   protection, not after, or the same class of permission failure recurs.

**Done when:** you can delete every generated tab and the next run rebuilds them.

**Future work (deferred, not built in the first pass):**
- An `Artists` tab (unique artist name + count of active albums,
  alphabetical). `Album.artists` is a list of Spotify display-name strings
  with no stable ID, so near-duplicate spellings across albums won't merge —
  accepted limitation.
- A `by-style` tab mirroring `by-genre`'s one-row-per-album pattern, applied
  to styles instead of genres, so sub-genre is independently
  filterable/groupable too.
- Mapping Discogs' vocabulary onto a personal/cleaner genre naming (e.g.
  Discogs' own category "Folk, World, & Country" isn't necessarily how
  anyone thinks about their music) — a data-layer concern for Stage 3's
  `overrides.toml` below, not a sheet-rendering one.

## Stage 3 — Overrides & manual albums

Implemented as `data/overrides.toml`, read by `overrides.py`, **not** the
`_overrides` Google Sheet tab this stage originally specced. Reasons for the
change: the Sheet is a generated output, rebuilt from scratch every run
(Stage 2 step 2) — making it *also* a hand-edited input is confusing; it
would put manual-album identity behind the Sheets API; and it gets no git
history, which this project already treats as its audit log (constraint 1).
A repo file solves all three, at zero new dependencies (`tomllib` is
stdlib on 3.13). It's edited via GitHub's mobile web UI on a phone, or
locally.

One file, one rule, keyed by album id:

- **Key matches an existing album** -> patches those fields (a correction).
  Any field may be overridden, not just genre/sub-genre.
- **Key matches no existing album** -> inserted as a new album with
  `source: "manual"` (an album that doesn't exist on Spotify at all).

Pipeline order: **poll -> overrides -> enrich -> sheets.** Running before
enrich means a manual album with empty `genres` gets filled in by the
Discogs cascade automatically (enrich only touches albums with
`genres == []`), and a corrected `title` is what enrich then sends to
Discogs' search.

`poll.py`'s tombstone logic and mass-removal-guard baseline both exclude
`source == "manual"` albums — they were never in `_selected`, so their
absence from a poll result says nothing about their status.

Genre overrides are reversible: deleting a row (or its `genres`/`styles`
keys) resets that album's genres to `[]` if they were override-sourced,
which is what makes enrich re-derive them from Discogs on the next run.
Scalar-field overrides (title, release_date, ...) are not reversible the
same way — nothing records the pre-override value, so undoing one means
editing the value back, not deleting the row. Deliberate: the common case
(a wrong genre) is fully reversible in a few lines; full undo history for
every field isn't worth the machinery.

**Done when:** a correction (or a manually-added album) typed on your phone
survives the next run.

## Stage 4 — React frontend

**Purpose, settled by scoping:** the Sheet already browses and filters, so the
frontend exists to be **a link you'd send to someone who won't open a
spreadsheet**. That single answer drives everything else — the visitor's goal
is to *listen*, so the Spotify link is the primary action; the OG link preview
is the real first impression; and filter depth matters far less than the Sheet's,
because a visitor scrolls rather than building a query.

Other scoping answers: fully public (no gate), auto-deploy on every data
commit, grouped by release year newest-first, album click opens Spotify
directly, and **artist grouping** is the one future feature given structural
room.

1. `src/calbum/site.py` emits `web/src/data/albums.json` — active albums only,
   UI fields only (`upc`, `discogs_release_id`, `added_at`, `removed_at` and
   genre provenance stay server-side). Reuses `writer.write_json_atomic`, so
   constraint 1's deterministic sorted-key contract holds here too.
2. `web/`: Vite + React + TS, **mobile-first**. Imports the payload at build
   time rather than fetching it — this satisfies the original "must ship as
   part of the deploy, not be pulled from raw.githubusercontent" requirement
   while removing the loading state, the error state, and a request from first
   paint (12KB today, ~125KB at 500 albums).
3. Navigation is one model in two placements: a **bottom tab bar** on phones,
   a wider grid on desktop. Destinations: Albums · Genres · Artists · Search.
4. **`groupBy(albums, keyFn)` in `src/albums.ts` is the extensibility seam** —
   Artists is the same function with a different `keyFn`, which is why that
   destination cost a line rather than a rewrite.
5. Deploy: **GitHub Pages on a public repo**, via a `deploy` job chained off
   `needs: sync` in the same workflow.

   Why a job and not a push-triggered workflow: every commit the sync
   workflow makes carries `[skip ci]` (needed so a data commit doesn't
   retrigger the whole sync), and **GitHub Actions honors that marker** — a
   push-triggered Pages workflow would never fire and the site would freeze
   while the data kept updating. Netlify ignored `[skip ci]`, which is why
   this only became a hazard on switching hosts. Chaining off `needs:`
   sidesteps it. The deploy job also checks out `ref: github.ref_name`
   rather than the triggering SHA, or it would build the pre-sync commit.

   Going public also removes two constraints this plan was written under:
   Pages is free (the earlier "needs a paid plan" note was purely about the
   repo being private), and Actions minutes become unlimited, so the 4-hour
   cadence is no longer budget-bound.

   No custom domain: the site serves as a GitHub Pages **project page**,
   `jmc856.github.io/calbum/`. `web/vite.config.ts` sets `base: "/calbum/"`
   so built asset URLs resolve under that path instead of 404ing at the
   origin root. OG/Twitter tags in `web/index.html` are hardcoded to
   `https://jmc856.github.io/calbum/` — relative OG URLs are not reliably
   resolved by iMessage, Slack, or Facebook, and the link preview is this
   stage's whole point.

   A custom subdomain was tried (`web/public/CNAME` + `VITE_SITE_URL` in
   `web/.env.production`, feeding the absolute OG URLs at build time) and
   reverted after the DNS check failed and the record was never added at the
   registrar. The mechanism still works if revisited: restore those two
   files and set `base: "/"` back in `vite.config.ts`.

**Not built, deliberately:** routing/album detail pages (click goes straight to
Spotify, so there's no second view), per-album notes, ratings, and
`docker/Dockerfile.web` (`npm run dev` needs no container and the deploy is
static output, so it would add a moving part serving nothing).

**Done when:** there is a public URL you'd actually send to someone.

**Remaining manual steps** (none scriptable):
1. Make the repo public. Audited safe — `.env` was never tracked or
   committed, no hardcoded IDs, everything env-driven; Actions secrets live
   in GitHub's store, not repo contents, so they stay private.
2. Settings → Pages → Source: **GitHub Actions** (not "deploy from branch").

## Stage 5 — Optional, whenever (RYM ratings import)

(Renumbered from the original Stage 6 — the playlist-reconciler stage that used to sit here
is deleted; see cut list. Also downgraded from a required "Backfill" stage — see below.)

**There is no playlist backfill.** `_selected` starts empty; there are no legacy
`{year} Best Of` playlists or old Sheet tabs predating it, and additions happen
~5-10 albums at a time through normal Stage 0 polling from day one. The
resolve-via-search-and-reconcile machinery this stage used to describe (limit-10
search, strict artist+title+year matching, `data/unmatched.json`) has no input to
run against and is not being built.

The only thing that could still live here: **optionally importing the RYM
ratings export**, if you ever want historical ratings/release-date data
alongside the catalog. Note the RYM export does NOT contain genre data, so it
would never substitute for Stage 1. This is speculative and not scoped — pick it
up only if it becomes a real want, not as planned work.

## Stage 6 — Optional, whenever

Browser extension (RYM chart annotation showing what's already in the catalog,
one-click capture, chart CSV export for RYM-grade genre seeding). PWA. Neither is
load-bearing; capture stays mobile-native through Spotify regardless.

## Stage 7 — Read-surface differentiation

Not renumbered ahead of Stages 5–6 despite being more likely to actually
happen — those numbers are cross-referenced elsewhere in this doc, and this
entry arrived later. Using Stage 4 surfaced a problem the build didn't
anticipate: **Albums, Genres, and Artists offer too similar an experience.**
All three bottom out in the same year-grouped cover grid — Genres adds a pill
rail that disappears once you pick one, Artists just swaps the group key.
Three tabs, one view. Three things worth fixing, none built yet:

1. **Desktop UX.** `.app` is hard-capped at `max-width: 480px`
   (`web/src/styles.css`), so anything wider than a phone renders as a
   480px column centered on a dark field — the only width media query
   (`min-width: 420px` → 3 grid columns) saturates immediately. There is
   currently zero desktop CSS, so a ~900px breakpoint (release the width
   cap, more grid columns, larger type, bottom tab bar becoming a left
   sidebar) is additive, not a rewrite. `Nav.tsx` already renders one
   destination list — the "one model, two placements" intent from Stage 4
   was designed but never actually built for desktop. One structural catch:
   `.app` is a fixed-height flex column with `.nav` absolutely positioned
   inside it, so a sidebar means flipping `.app`'s `flex-direction` at the
   breakpoint and re-anchoring `.nav`.

2. **Genres tab — a release-year timeline as the main focus**, not a
   secondary pill rail. Per-genre distribution across release years
   (2004→2026), answering *which eras of music I'm drawn to*; clicking a
   genre drives the existing filter, so the pill rail becomes chart-driven
   rather than a separate control. No backend change needed — `year` and
   `genres` are both already in the payload, and `groupBy`'s multi-key
   support (a `keyFn` returning an array, so a 3-genre album lands in 3
   buckets) is already the shape this needs. Caveat: 31 albums across ~20
   year buckets is sparse, so this likely needs 2–3 year binning to read as
   a trend rather than noise.

   An **added-at** axis (a true "how my taste shifted over time" chart) was
   considered and set aside, not forgotten. `added_at` exists on the model
   and is frozen at first write, but is deliberately not emitted to the
   frontend payload — adding it is one line. The blocker is data, not code:
   all 31 albums were added in the same 2026-08-13→16 cold-start backfill,
   so that chart is a single bar today. Worth revisiting after months of
   real polling history.

3. **Artists tab — artist-first, not album-first.** Today it's
   `groupBy(artist)` over the same cover grid, and with only 1 of 31 albums
   having multiple artists it's nearly 1:1 with Albums, which is exactly why
   it doesn't earn its own tab. Wants a grid of artists, click-through to
   that artist's albums. Portraits are a **backend feature, not a frontend
   one**: Spotify's cached album blobs carry each artist's `id`, `name`,
   `href`, and `external_urls`, but no `images` — real photos need a new
   `GET /v1/artists` fetch plus a cache and rate-limit handling. Ship a
   cover-collage / typographic tile fallback so the tab can be redesigned
   without blocking on that backend work; treat portraits as the fuller
   version to add later. Cheap intermediate step: `artist_ids` can be
   backfilled from the already-cached raw blobs at zero API cost, same
   pattern `poll.py` already uses for `cover_url` — a parallel field rather
   than changing `Album.artists` from `list[str]` to objects, which would
   ripple into `sheets.py`, `enrich.py`, `overrides.py`, the tests, and the
   stored shape of `data/albums.json`.

   Data-quality note worth recording while it's cheap: artists currently
   join by string equality only, so aliases or "The X" vs "X" would
   silently split into separate entries. Harmless while artists are just
   section headings; a real problem once they're first-class entities with
   portraits.

---

## Explicit cut list

Ratings. Ranking. Listen history. Multi-user. Any auth beyond a bearer token.
Real-time anything. A general non-Spotify ingestion path. MusicBrainz as a primary
source. Server-side RateYourMusic scraping (gets IPs banned; do not). **Any
candidate/inbox/queue surface** — tried three ways during design (`/me/albums`,
`_inbox` playlist, heart-as-queue) and reversed every time; no deliverable needs to know
what was considered and rejected. **A Spotify playlist reconciler** — there is no per-year
Spotify playlist to keep in sync anymore, since `_selected` is flat and `release_year` is
a pure data field used only for grouping in read surfaces.

## Stopping point

Stages 0-2 solve the original problem completely: after them you maintain exactly
one place (Spotify) and the Sheet regenerates itself. Everything from Stage 3
onward is improvement, not rescue. If momentum dies, dying after Stage 2 is a win.

## Technical debt (not scheduled)

Recorded, not applied — surfaced during code review, deliberately deferred.

None currently outstanding. (`poll.py`'s class-based refactor, previously
recorded here, was applied — see Stage 0.)
