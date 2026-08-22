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
const SLOT = IW / ERAS.length;
const BAR_W = SLOT * 0.58;

const barX = (i: number) => PAD_X + SLOT * (i + 0.5);

export function GenreChart({
  albums,
  selected,
  onSelect,
}: {
  albums: Album[];
  selected: string | null;
  onSelect: (genre: string | null) => void;
}) {
  const { rows, eraTotals, max } = useMemo(() => genreEraMatrix(albums), [albums]);

  // Genre → CSS colour. Hue is assigned by position among the REAL genres:
  // Uncategorized isn't a genre but the absence of one, so it takes a fixed
  // neutral rather than consuming a slot. Without that it sat mid-list, shunted
  // every genre after it down one, and wrapped the 9th back onto --g0 — Blues
  // rendering in Rock's orange.
  const hue = useMemo(() => {
    let n = 0;
    return new Map(
      rows.map((r) => [
        r.genre,
        r.genre === UNCATEGORIZED ? "var(--g-none)" : `var(--g${n++ % 8})`,
      ]),
    );
  }, [rows]);

  const toggle = (genre: string) => onSelect(selected === genre ? null : genre);
  const dimmed = (genre: string) => selected !== null && selected !== genre;

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
          const x = barX(e);
          let acc = 0;

          return (
            <g key={era.label}>
              {rows.map((row) => {
                const v = row.counts[e];
                if (!v || !total) return null;
                const h = (v / total) * barH;
                const y = PAD_TOP + IH - acc - h;
                acc += h;
                return (
                  <rect
                    key={row.genre}
                    className={dimmed(row.genre) ? "gseg dim" : "gseg"}
                    x={x - BAR_W / 2}
                    y={y}
                    width={BAR_W}
                    height={h}
                    fill={hue.get(row.genre)}
                    onClick={() => toggle(row.genre)}
                  >
                    <title>{`${row.genre} · ${v} in ${era.label}`}</title>
                  </rect>
                );
              })}
              <text className="gnum tnum" x={x} y={PAD_TOP + IH - barH - 5} textAnchor="middle">
                {total}
              </text>
              <text className="glab" x={x} y={H - 7} textAnchor="middle">
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
            className={dimmed(row.genre) ? "gpill dim" : "gpill"}
            aria-pressed={selected === row.genre}
            style={{ color: hue.get(row.genre) }}
            onClick={() => toggle(row.genre)}
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
