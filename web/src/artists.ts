import rawArtists from "./data/artists.json";
import { groupBy, type Album } from "./albums";

/** Shape emitted by src/calbum/artists.py — keep the two in step. */
export interface Artist {
  id: string;
  name: string;
  /** Spotify CDN URL, or null when Spotify has no photo for them. */
  portrait: string | null;
}

const PORTRAITS = new Map((rawArtists as Artist[]).map((a) => [a.id, a.portrait]));

/**
 * One artist as the tab renders them: identity, their albums oldest-first,
 * and the span those albums cover.
 */
export interface ArtistEntry {
  id: string;
  name: string;
  portrait: string | null;
  albums: Album[];
  from: number;
  to: number;
}

/**
 * Primary artist only — the first name/ID on the album.
 *
 * Spotify lists group members alongside the group, so "Run The Jewels 2"
 * carries Run The Jewels, El-P, AND Killer Mike, and Madvillainy carries
 * Madvillain, Madlib, AND MF DOOM. Counting all of them invents artists with
 * one album each in a directory where one-offs already dominate.
 *
 * This is a presentation choice, which is why it lives here and not in the
 * payload: site.py emits the full parallel arrays and lets the frontend
 * decide.
 */
const primaryOf = (album: Album) => ({
  id: album.artistIds[0] ?? "",
  name: album.artists[0] ?? "",
});

export function artistEntries(albums: Album[]): ArtistEntry[] {
  // Keyed by ID, not display name: aliases and "The X" vs "X" would silently
  // split into separate entries otherwise. Albums with no artistIds (manual
  // ones, or any polled before the field existed) fall back to the name so
  // they still appear rather than collapsing into a single empty-ID bucket.
  const keyOf = (a: Album) => {
    const p = primaryOf(a);
    return p.id || p.name;
  };
  const groups = groupBy(albums, keyOf, () => 0);

  const entries = groups.map(([key, list]) => {
    const years = list.map((a) => a.year);
    return {
      id: key,
      name: primaryOf(list[0]).name,
      portrait: PORTRAITS.get(key) ?? null,
      albums: [...list].sort((a, b) => a.year - b.year),
      from: Math.min(...years),
      to: Math.max(...years),
    };
  });

  // Most-returned-to first, which is what the loyalty view is about; ties
  // alphabetical so the order is stable run to run.
  entries.sort((a, b) => b.albums.length - a.albums.length || a.name.localeCompare(b.name));
  return entries;
}

export const isRepeat = (entry: ArtistEntry) => entry.albums.length > 1;

/**
 * Linear year scale for the loyalty timeline, as a percentage across the
 * track.
 *
 * Deliberately not built on ERAS/eraIndexOf: those are bins sized to balance
 * album counts for the Genres chart, and a lane needs continuous position.
 * Same data, genuinely different question.
 */
export function yearScale(entries: ArtistEntry[]) {
  const years = entries.flatMap((e) => [e.from, e.to]);
  const min = years.length ? Math.min(...years) : 0;
  const max = years.length ? Math.max(...years) : 0;
  // A single-year span would divide by zero; pin it to the left instead.
  const span = max - min || 1;
  return { min, max, pct: (year: number) => ((year - min) / span) * 100 };
}
