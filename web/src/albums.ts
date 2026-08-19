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

export function matches(album: Album, query: string, genre: string | null): boolean {
  if (genre && !album.genres.includes(genre)) return false;
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
