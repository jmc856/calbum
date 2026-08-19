import type { ReactNode } from "react";
import type { View } from "../albums";

const ICONS: Record<View, ReactNode> = {
  albums: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="2.6" />
    </>
  ),
  genres: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.6" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.6" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.6" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.6" />
    </>
  ),
  artists: (
    <>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" />
    </>
  ),
};

const LABELS: Record<View, string> = {
  albums: "Albums",
  genres: "Genres",
  artists: "Artists",
  search: "Search",
};

const ORDER: View[] = ["albums", "genres", "artists", "search"];

export function Nav({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  return (
    <nav className="nav" role="tablist" aria-label="Browse">
      {ORDER.map((v) => (
        <button
          key={v}
          className="tab"
          role="tab"
          aria-selected={view === v}
          onClick={() => onChange(v)}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {ICONS[v]}
          </svg>
          <span className="tl">{LABELS[v]}</span>
        </button>
      ))}
    </nav>
  );
}
