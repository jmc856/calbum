import type { ReactNode } from "react";
import { initial } from "../albums";
import type { ArtistEntry } from "../artists";
import { AlbumCard } from "./AlbumCard";

/**
 * One artist, in either section of the Artists tab.
 *
 * The loyalty lane and the directory row are the same structure — portrait,
 * name, a varying body, and the expansion below — so they share this rather
 * than being two components that drift. Callers supply the body as children
 * and a class for the size differences; the toggle contract and
 * `aria-expanded` live here so neither re-implements them.
 */
export function ArtistRow({
  entry,
  variant,
  expanded,
  onToggle,
  children,
}: {
  entry: ArtistEntry;
  variant: "lane" | "row";
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <>
      <button
        className={`arow arow-${variant}`}
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <Portrait entry={entry} />
        <div className="arow-body">
          <div className="arow-nm">{entry.name}</div>
          {children}
        </div>
      </button>
      {expanded && (
        <div className="aexp">
          <div className="aexp-in">
            {entry.albums.map((a) => (
              <AlbumCard key={a.id} album={a} sub={String(a.year)} />
            ))}
          </div>
        </div>
      )}
    </>
  );
}

/** Portrait, or the artist's initial when Spotify has no photo for them. */
function Portrait({ entry }: { entry: ArtistEntry }) {
  if (!entry.portrait) {
    return (
      <div className="aportrait aportrait-fb" aria-hidden="true">
        {initial(entry.name)}
      </div>
    );
  }
  return <img className="aportrait" src={entry.portrait} alt="" loading="lazy" />;
}
