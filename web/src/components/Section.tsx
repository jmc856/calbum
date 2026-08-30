import type { Album } from "../albums";
import { byTitle } from "../albums";
import { AlbumCard } from "./AlbumCard";

/**
 * One grouped block — a year, a genre, an artist. Heading plus either the
 * cover grid or, collapsed, the same albums as text rows.
 *
 * Controlled, like ArtistRow: the caller owns `collapsed`. Section holding its
 * own state would look tidier and would silently lose it, because sections
 * unmount whenever the grouping changes — every tab switch, every keystroke in
 * search, every genre filter.
 *
 * The heading stays an <h2> with a button inside rather than becoming a button
 * itself: the year headings are the document outline for these tabs, and
 * `.sec-head` is shared with the Artists tab's non-interactive headings.
 *
 * `aria-pressed`, not `aria-expanded` — nothing is hidden when collapsed, the
 * same albums are all still listed. Claiming a region isn't rendered would be
 * a lie to a screen reader.
 */
export function Section({
  label,
  albums,
  collapsed,
  onToggle,
}: {
  label: string;
  albums: Album[];
  collapsed: boolean;
  onToggle: () => void;
}) {
  // Sorted once, for both branches — sorting in only one would silently
  // reorder the albums as you toggle.
  const sorted = [...albums].sort(byTitle);

  return (
    <section>
      <h2 className="sec-head sec-head-btn">
        <button
          className="sec-btn"
          onClick={onToggle}
          aria-pressed={collapsed}
          aria-label={collapsed ? `${label} — show covers` : `${label} — hide covers`}
        >
          {label}
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
          >
            {collapsed ? (
              // grid: what clicking gets you back
              <>
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
              </>
            ) : (
              // list: what clicking collapses to
              <>
                <path d="M8 6h13M8 12h13M8 18h13" />
                <path d="M3 6h.01M3 12h.01M3 18h.01" />
              </>
            )}
          </svg>
        </button>
      </h2>

      {collapsed ? (
        <ul className="rows">
          {sorted.map((a) => (
            <li key={a.id}>
              <AlbumCard album={a} variant="row" />
            </li>
          ))}
        </ul>
      ) : (
        <div className="grid">
          {sorted.map((a) => (
            <AlbumCard key={a.id} album={a} />
          ))}
        </div>
      )}
    </section>
  );
}
