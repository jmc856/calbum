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
 * `subtitle` is a slot, not a string, because the tabs genuinely differ: the
 * album-shaped tabs render a three-column stat row, the chart-shaped ones a
 * line of text.
 */
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
  subtitle: ReactNode;
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

        {subtitle}

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

/** The three-column count row. Used by the tabs that show a cover grid. */
export function Stats({ albums }: { albums: { genres: string[]; artists: string[] }[] }) {
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

/** Single line of text, for the tabs whose header carries a chart instead. */
export function Subtitle({ children }: { children: ReactNode }) {
  return <p className="hdr-sub tnum">{children}</p>;
}

export function Empty() {
  return <p className="empty">Nothing matches that.</p>;
}
