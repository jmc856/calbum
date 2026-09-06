import { useEffect, useRef, type ReactNode } from "react";

/**
 * The chrome every tab shares: accent header, title, a line of subtitle text,
 * and the search field.
 *
 * Views compose this rather than App branching on `view` to assemble each
 * one's header. That's what keeps a new tab to a single new file — the
 * alternative was a second set of `view === "x"` conditionals in App, one for
 * the header and one for the body, that had to be kept in sync by eye.
 *
 * Every tab's subtitle is one line of counts, so `subtitle` is that line. The
 * Albums tab used to get a three-column stat block instead; one header shape
 * for the whole app is both simpler here and less to read on the way to the
 * albums themselves.
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

        <p className="hdr-sub tnum">{subtitle}</p>

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

export function Empty() {
  return <p className="empty">Nothing matches that.</p>;
}
