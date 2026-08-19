import { useEffect, useMemo, useRef, useState } from "react";
import {
  ALBUMS,
  UNCATEGORIZED,
  byNameAsc,
  byYearDesc,
  groupBy,
  matches,
  type View,
} from "./albums";
import { Nav } from "./components/Nav";
import { Section } from "./components/Section";

const TITLES: Record<View, string> = {
  albums: "Albums",
  genres: "Genres",
  artists: "Artists",
  search: "Search",
};

export default function App() {
  const [view, setView] = useState<View>("albums");
  const [query, setQuery] = useState("");
  const [genre, setGenre] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const visible = useMemo(
    () => ALBUMS.filter((a) => matches(a, query.trim().toLowerCase(), genre)),
    [query, genre],
  );

  // Genre counts come from the whole catalog, not the filtered set — a count
  // that changed as you filtered would be telling you about your own filter
  // rather than about the collection.
  const genreGroups = useMemo(
    () => groupBy(ALBUMS, (a) => (a.genres.length ? a.genres : [UNCATEGORIZED]), byNameAsc),
    [],
  );

  const sections = useMemo(() => {
    if (view === "artists") {
      return groupBy(visible, (a) => a.artists, byNameAsc).map(([artist, albums]) => ({
        key: `artist-${artist}`,
        label: `${artist} · ${albums.length}`,
        albums,
      }));
    }
    return groupBy(visible, (a) => a.year, byYearDesc).map(([year, albums]) => ({
      key: `year-${year}`,
      label: String(year),
      albums,
    }));
  }, [view, visible]);

  const showSearch = searchOpen || view === "search";

  useEffect(() => {
    if (showSearch) searchRef.current?.focus();
  }, [showSearch]);

  function changeView(next: View) {
    setView(next);
    setGenre(null);
    if (next !== "search") setSearchOpen(false);
    scrollRef.current?.scrollTo({ top: 0 });
  }

  const stats = [
    { n: visible.length, l: "Albums", lead: true },
    { n: new Set(visible.flatMap((a) => a.genres)).size, l: "Genres", lead: false },
    { n: new Set(visible.flatMap((a) => a.artists)).size, l: "Artists", lead: false },
  ];

  return (
    <div className="app">
      <div className="scroll" ref={scrollRef}>
        <header className="hdr">
          <div className="hdr-top">
            <h1 className="hdr-title">{genre ?? TITLES[view]}</h1>
            <button
              className="icon-btn"
              onClick={() => setSearchOpen((o) => !o)}
              aria-label="Search albums"
              aria-expanded={showSearch}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="M20 20l-3.5-3.5" />
              </svg>
            </button>
          </div>

          <div className="stats">
            {stats.map((s) => (
              <div key={s.l} className={s.lead ? "stat lead" : "stat"}>
                <div className="n tnum">{s.n}</div>
                <div className="l">{s.l}</div>
                <div className="tick" />
              </div>
            ))}
          </div>

          {showSearch && (
            <div className="search-wrap">
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search albums or artists…"
                autoComplete="off"
                aria-label="Search albums or artists"
              />
            </div>
          )}
        </header>

        {view === "genres" && !genre && (
          <div className="pills">
            {genreGroups.map(([name, list]) => (
              <button
                key={name}
                className="pill"
                aria-pressed={genre === name}
                onClick={() => setGenre(name)}
              >
                {name}
                <span className="c">{list.length}</span>
              </button>
            ))}
          </div>
        )}

        {sections.map((s) => (
          <Section key={s.key} label={s.label} albums={s.albums} />
        ))}

        {visible.length === 0 && <p className="empty">Nothing matches that.</p>}
      </div>

      <Nav view={view} onChange={changeView} />
    </div>
  );
}
