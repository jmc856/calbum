import { useEffect, useMemo, useRef, useState } from "react";
import {
  ALBUMS,
  byNameAsc,
  byYearDesc,
  groupBy,
  matches,
  stylesForGenre,
  type View,
} from "./albums";
import { GenreChart } from "./components/GenreChart";
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

  // Ranked styles for the selected genre. This is the drill-down that finally
  // renders `styles` — 55 values that ship in the payload and, until now,
  // appeared nowhere in the UI.
  // Capped: Rock alone has 24 styles, and the count-1 tail is noise that
  // pushed the album grid entirely below the fold. The top slice carries the
  // signal; the grid is still the point of the screen.
  const styles = useMemo(
    () => (genre ? stylesForGenre(ALBUMS, genre).slice(0, 12) : []),
    [genre],
  );

  const genreCount = useMemo(
    () => new Set(ALBUMS.flatMap((a) => a.genres)).size,
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

          {/* The Genres tab trades the stat row for the chart, which says
              more about the collection's shape than three static numbers
              did. The count survives as a subtitle. */}
          {view === "genres" ? (
            <p className="hdr-sub tnum">
              {genre
                ? `${visible.length} album${visible.length === 1 ? "" : "s"} · ${genre}`
                : `${ALBUMS.length} albums · ${genreCount} genres`}
            </p>
          ) : (
            <div className="stats">
              {stats.map((s) => (
                <div key={s.l} className={s.lead ? "stat lead" : "stat"}>
                  <div className="n tnum">{s.n}</div>
                  <div className="l">{s.l}</div>
                  <div className="tick" />
                </div>
              ))}
            </div>
          )}

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

        {/* The chart stays mounted once a genre is picked — unlike the pill
            rail it replaced, which vanished on selection and left no way to
            see or change the active filter. */}
        {view === "genres" && (
          <>
            <GenreChart albums={ALBUMS} selected={genre} onSelect={setGenre} />
            {genre && styles.length > 0 && (
              <div className="gstyles">
                <p className="gstyles-lab">{genre} → styles</p>
                <div className="gchips">
                  {styles.map(([name, n]) => (
                    <span className="gchip" key={name}>
                      {name}
                      <span className="gchip-n tnum">{n}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
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
