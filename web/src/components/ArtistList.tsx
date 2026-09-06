import type { ArtistEntry } from "../artists";
import { ArtistRow } from "./ArtistRow";

/**
 * The directory: every artist, with a strip of their covers. The strip's
 * length is the loyalty signal — five covers for someone you've followed,
 * one for someone you tried once — so the two halves of the tab reinforce
 * each other without extra chrome.
 */
export function ArtistList({
  entries,
  expanded,
  onToggle,
}: {
  entries: ArtistEntry[];
  expanded: string | null;
  onToggle: (id: string) => void;
}) {
  return (
    <div className="alist">
      {entries.map((entry) => (
        <ArtistRow
          key={entry.id}
          entry={entry}
          variant="row"
          expanded={expanded === entry.id}
          onToggle={() => onToggle(entry.id)}
        >
          <div className="arow-meta tnum">{meta(entry)}</div>
          <div className="astrip">
            {entry.albums.map((a) =>
              a.cover ? (
                <img key={a.id} src={a.cover} alt="" loading="lazy" />
              ) : (
                <span key={a.id} className="astrip-fb" />
              ),
            )}
          </div>
        </ArtistRow>
      ))}
    </div>
  );
}

function meta(entry: ArtistEntry): string {
  const n = entry.albums.length;
  if (n === 1) return `1 album · ${entry.from}`;
  // A single year for several albums shouldn't render as "2020–2020".
  const span = entry.from === entry.to ? `${entry.from}` : `${entry.from}–${entry.to}`;
  return `${n} albums · ${span}`;
}
