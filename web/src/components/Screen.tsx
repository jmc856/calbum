import { useEffect, useRef, type ReactNode } from "react";

/**
 * The chrome every tab shares: accent header, title, a subtitle slot, and the
 * search field.
 *
 * Views compose this rather than App branching on `view` to assemble each
 * one's header. That's what keeps a new tab to a single new file — the
 * alternative was a second set of `view === "x"` conditionals in App, one for
 * the header and one for the body, that had to be kept in sync by eye.
 *
 * `subtitle` is a closed choice, not an open slot: every current tab needs
 * one of exactly two shapes — the album-shaped tabs a three-column stat row,
 * the chart-shaped ones a line of text — so the type says that instead of
 * leaving it to convention. Screen owns rendering both; a view only supplies
 * the data.
 */
type Subtitle = { kind: "stats"; albums: StatsAlbum[] } | { kind: "text"; text: ReactNode };

export function Screen({
  title,
  subtitle,
  query,
  onQuery,
  searchOpen,
  onToggleSearch,
  children,
}: {
  title: string;
  subtitle: Subtitle;
  query: string;
  onQuery: (q: string) => void;
  searchOpen: boolean;
  onToggleSearch: () => void;
  children: ReactNode;
}) {
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (searchOpen) searchRef.current?.focus();
  }, [searchOpen]);

  return (
    <>
      <header className="hdr">
        <div className="hdr-top">
          <h1 className="hdr-title">{title}</h1>
          <button
            className="icon-btn"
            onClick={onToggleSearch}
            aria-label="Search albums"
            aria-expanded={searchOpen}
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

        {subtitle.kind === "stats" ? <Stats albums={subtitle.albums} /> : <p className="hdr-sub tnum">{subtitle.text}</p>}

        {searchOpen && (
          <div className="search-wrap">
            <input
              ref={searchRef}
              type="text"
              value={query}
              onChange={(e) => onQuery(e.target.value)}
              placeholder="Search albums or artists…"
              autoComplete="off"
              aria-label="Search albums or artists"
            />
          </div>
        )}
      </header>

      {children}
    </>
  );
}

type StatsAlbum = { genres: string[]; artists: string[] };

/** The three-column count row. Internal to Screen — a view supplies albums
 *  via `subtitle={{kind: "stats", albums}}` rather than rendering this
 *  itself. */
function Stats({ albums }: { albums: StatsAlbum[] }) {
  const rows = [
    { n: albums.length, l: "Albums", lead: true },
    { n: new Set(albums.flatMap((a) => a.genres)).size, l: "Genres", lead: false },
    { n: new Set(albums.flatMap((a) => a.artists)).size, l: "Artists", lead: false },
  ];
  return (
    <div className="stats">
      {rows.map((s) => (
        <div key={s.l} className={s.lead ? "stat lead" : "stat"}>
          <div className="n tnum">{s.n}</div>
          <div className="l">{s.l}</div>
          <div className="tick" />
        </div>
      ))}
    </div>
  );
}

export function Empty() {
  return <p className="empty">Nothing matches that.</p>;
}
