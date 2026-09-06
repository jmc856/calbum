import type { ArtistEntry } from "../artists";
import { yearScale } from "../artists";
import { ArtistRow } from "./ArtistRow";

/**
 * The loyalty view: one lane per artist you've returned to, positioned on a
 * shared year axis so span is comparable across lanes. Four albums over
 * eleven years reads differently from five over six.
 *
 * CSS percentage positioning rather than SVG — GenreChart uses a viewBox
 * because stacked bars need coordinate math, but a rail and some dots don't,
 * and staying in the DOM keeps the rows focusable and the layout fluid.
 */
export function ArtistLanes({
  entries,
  expanded,
  onToggle,
}: {
  entries: ArtistEntry[];
  expanded: string | null;
  onToggle: (id: string) => void;
}) {
  const scale = yearScale(entries);

  return (
    <div className="alanes">
      {entries.map((entry) => (
        <ArtistRow
          key={entry.id}
          entry={entry}
          variant="lane"
          expanded={expanded === entry.id}
          onToggle={() => onToggle(entry.id)}
        >
          <Track entry={entry} scale={scale} />
        </ArtistRow>
      ))}
      <div className="aaxis tnum">
        <span>{scale.min}</span>
        <span>{scale.max}</span>
      </div>
    </div>
  );
}

function Track({
  entry,
  scale,
}: {
  entry: ArtistEntry;
  scale: ReturnType<typeof yearScale>;
}) {
  // Two albums in the same year land on the same coordinate; nudge each
  // duplicate so both stay visible instead of one hiding the other.
  const seen = new Map<number, number>();

  return (
    <div className="atrack">
      <span
        className="arail"
        style={{ left: `${scale.pct(entry.from)}%`, right: `${100 - scale.pct(entry.to)}%` }}
      />
      {entry.albums.map((album) => {
        const n = seen.get(album.year) ?? 0;
        seen.set(album.year, n + 1);
        return (
          <span
            key={album.id}
            className="adot"
            style={{ left: `${scale.pct(album.year) + n * 3.4}%` }}
            title={`${album.title} · ${album.year}`}
          />
        );
      })}
    </div>
  );
}
