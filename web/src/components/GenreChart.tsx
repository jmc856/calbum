import { useMemo } from "react";
import { ERAS, UNCATEGORIZED, genreEraMatrix, type Album } from "../albums";

/* Chart geometry. A viewBox rather than pixel sizing so the SVG scales with
   the column it sits in — the same drawing serves phone and desktop. */
const W = 342;
const H = 132;
const PAD_X = 8;
const PAD_TOP = 16;
const PAD_BOTTOM = 22;
const IW = W - PAD_X * 2;
const IH = H - PAD_TOP - PAD_BOTTOM;
const BAR_W = (IW / ERAS.length) * 0.58;

const barX = (i: number) => PAD_X + (IW / ERAS.length) * (i + 0.5);

/**
 * Genre → colour. Defined as CSS custom properties so both themes get their
 * own values — see styles.css.
 *
 * Uncategorized takes a fixed neutral rather than a slot in the cycle: it
 * isn't a genre, it's the absence of one, and grey says that. It also frees
 * all eight hues for the eight real genres — without this, the 9th row wrapped
 * to --g0 and Blues rendered in Rock's orange.
 */
const colorOf = (genre: string, i: number) =>
  genre === UNCATEGORIZED ? "var(--g-none)" : `var(--g${i % 8})`;

export function GenreChart({
  albums,
  selected,
  onSelect,
}: {
  albums: Album[];
  selected: string | null;
  onSelect: (genre: string | null) => void;
}) {
  // Built from the whole catalogue, never the filtered set: a chart that
  // reshaped itself as you filtered would describe your filter rather than
  // the collection.
  const { rows, eraTotals, max } = useMemo(() => genreEraMatrix(albums), [albums]);

  // Hue is assigned by position among the REAL genres, so Uncategorized
  // sitting mid-list doesn't shunt everything after it down a slot and wrap
  // the last genre back onto the first one's colour.
  const hue = useMemo(() => {
    const m = new Map<string, string>();
    let n = 0;
    for (const r of rows) m.set(r.genre, colorOf(r.genre, r.genre === UNCATEGORIZED ? -1 : n++));
    return m;
  }, [rows]);

  return (
    <div className="gchart">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="gsvg"
        role="img"
        aria-label="Albums by genre and release era"
      >
        {ERAS.map((era, e) => {
          const total = eraTotals[e];
          const barH = (total / max) * IH;
          let acc = 0;

          return (
            <g key={era.label}>
              {rows.map((row) => {
                const v = row.counts[e];
                if (!v || !total) return null;
                const h = (v / total) * barH;
                const y = PAD_TOP + IH - acc - h;
                acc += h;
                const dim = selected !== null && selected !== row.genre;
                return (
                  <rect
                    key={row.genre}
                    className={dim ? "gseg dim" : "gseg"}
                    x={barX(e) - BAR_W / 2}
                    y={y}
                    width={BAR_W}
                    height={h}
                    fill={hue.get(row.genre)}
                    onClick={() => onSelect(selected === row.genre ? null : row.genre)}
                  >
                    <title>{`${row.genre} · ${v} in ${era.label}`}</title>
                  </rect>
                );
              })}
              <text className="gnum tnum" x={barX(e)} y={PAD_TOP + IH - barH - 5} textAnchor="middle">
                {total}
              </text>
              <text className="glab" x={barX(e)} y={H - 7} textAnchor="middle">
                {era.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* The legend is the accessible path to every genre: bar segments for
          the smallest genres are only a pixel or two tall, and these chips
          are the ≥44px targets that make them reachable. */}
      <div className="glegend">
        {rows.map((row) => (
          <button
            key={row.genre}
            className={selected !== null && selected !== row.genre ? "gpill dim" : "gpill"}
            aria-pressed={selected === row.genre}
            style={{ color: hue.get(row.genre) }}
            onClick={() => onSelect(selected === row.genre ? null : row.genre)}
          >
            <span className="gsw" style={{ background: hue.get(row.genre) }} />
            <span className="gnm">{row.genre}</span>
            <span className="gct tnum">{row.total}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
