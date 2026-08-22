import raw from "./data/albums.json";

/** Shape emitted by src/calbum/site.py — keep the two in step. */
export interface Album {
  id: string;
  title: string;
  artists: string[];
  year: number;
  genres: string[];
  styles: string[];
  /** Spotify CDN URL, or null (manual albums have no Spotify art). */
  cover: string | null;
  /** null for a manual album — render it non-interactive, not as a dead link. */
  url: string | null;
}

export const ALBUMS = raw as Album[];

export type View = "albums" | "genres" | "artists" | "search";

/**
 * The extensibility seam: grouping is a parameter, not a hard-coded axis.
 * Artists is this same function with a different keyFn — which is why adding
 * that destination cost a line rather than a rewrite.
 *
 * keyFn may return several keys (an album with two artists appears under
 * both).
 */
export function groupBy<K>(
  items: Album[],
  keyFn: (a: Album) => K | K[],
  sortGroups: (a: [K, Album[]], b: [K, Album[]]) => number,
): [K, Album[]][] {
  const m = new Map<K, Album[]>();
  for (const item of items) {
    const keys = keyFn(item);
    for (const k of Array.isArray(keys) ? keys : [keys]) {
      const bucket = m.get(k);
      if (bucket) bucket.push(item);
      else m.set(k, [item]);
    }
  }
  return [...m.entries()].sort(sortGroups);
}

export const byYearDesc = (a: [number, Album[]], b: [number, Album[]]) => b[0] - a[0];
export const byNameAsc = (a: [string, Album[]], b: [string, Album[]]) =>
  a[0].localeCompare(b[0]);
export const byTitle = (a: Album, b: Album) => a.title.localeCompare(b.title);

export const UNCATEGORIZED = "Uncategorized";

/**
 * Release-year bins for the Genres chart.
 *
 * Sized to balance album counts rather than span equal time — the catalogue
 * is heavily weighted to recent releases, so uniform bins would leave the
 * early ones nearly empty. The axis is labelled to say so; it is NOT linear
 * time.
 *
 * First and last bins are deliberately open-ended: a 2027 release must land
 * somewhere, and a closed upper bound would silently drop it from the chart
 * while leaving it in the grid.
 */
export const ERAS: { label: string; from: number; to: number }[] = [
  { label: "–2014", from: -Infinity, to: 2014 },
  { label: "2015–18", from: 2015, to: 2018 },
  { label: "2019–21", from: 2019, to: 2021 },
  { label: "2022–23", from: 2022, to: 2023 },
  { label: "2024+", from: 2024, to: Infinity },
];

export function eraOf(year: number): string {
  // The open-ended outer bins make this total; the fallback is unreachable
  // and exists only to satisfy the return type.
  return ERAS.find((e) => year >= e.from && year <= e.to)?.label ?? ERAS[ERAS.length - 1].label;
}

/** A genre's stacked-bar data: one count per era, in ERAS order. */
export interface GenreRow {
  genre: string;
  counts: number[];
  total: number;
}

export interface GenreMatrix {
  rows: GenreRow[];
  /** Per-era sum across all genres — the bar heights. Tag counts, not album
   *  counts: an album with three genres contributes to three rows. */
  eraTotals: number[];
  max: number;
}

/**
 * Genre × era counts. Reuses groupBy's multi-key support (a keyFn returning
 * an array), which is what lets a multi-genre album land in several rows —
 * the same seam the Artists destination uses.
 */
export function genreEraMatrix(albums: Album[]): GenreMatrix {
  const idx = new Map(ERAS.map((e, i) => [e.label, i]));
  const groups = groupBy(
    albums,
    (a) => (a.genres.length ? a.genres : [UNCATEGORIZED]),
    byNameAsc,
  );

  const rows: GenreRow[] = groups.map(([genre, list]) => {
    const counts = ERAS.map(() => 0);
    for (const a of list) counts[idx.get(eraOf(a.year))!]++;
    return { genre, counts, total: list.length };
  });
  // Biggest genres first, so the legend's most useful entries lead and the
  // stack reads consistently across bars.
  rows.sort((a, b) => b.total - a.total || a.genre.localeCompare(b.genre));

  const eraTotals = ERAS.map((_, i) => rows.reduce((s, r) => s + r.counts[i], 0));
  return { rows, eraTotals, max: Math.max(1, ...eraTotals) };
}

/** Styles ranked by frequency across the albums carrying `genre`. */
export function stylesForGenre(albums: Album[], genre: string): [string, number][] {
  const counts = new Map<string, number>();
  for (const a of albums) {
    const has = genre === UNCATEGORIZED ? a.genres.length === 0 : a.genres.includes(genre);
    if (!has) continue;
    for (const s of a.styles) counts.set(s, (counts.get(s) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function matches(album: Album, query: string, genre: string | null): boolean {
  if (genre === UNCATEGORIZED) {
    // No album carries "Uncategorized" as a real genre — it's the bucket for
    // albums Discogs gave us nothing for, so match on the absence instead.
    if (album.genres.length) return false;
  } else if (genre && !album.genres.includes(genre)) {
    return false;
  }
  if (query) {
    const hay = `${album.title} ${album.artists.join(" ")}`.toLowerCase();
    if (!hay.includes(query)) return false;
  }
  return true;
}

/** First alphanumeric of a title, for the no-artwork fallback tile. */
export function initial(title: string): string {
  return (title.match(/[A-Za-z0-9]/)?.[0] ?? "?").toUpperCase();
}
