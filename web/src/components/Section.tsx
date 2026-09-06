import type { Album } from "../albums";
import { byTitle, byYearDesc, groupBy } from "../albums";
import type { CollapseApi } from "../views/props";
import { AlbumCard } from "./AlbumCard";
import { Empty } from "./Screen";

/**
 * The year-grouped body shared by Albums and Genres: a collapse-all control
 * sitting at the top of the list, then one Section per year.
 *
 * The control lives here rather than in Screen's header because it acts on
 * this list and nothing else — in the header it read as global app chrome,
 * which it never was.
 */
export function SectionList({
  albums,
  collapse,
}: {
  albums: Album[];
  collapse: CollapseApi;
}) {
  const sections = groupBy(albums, (a) => a.year, byYearDesc);

  if (sections.length === 0) return <Empty />;

  return (
    <>
      {/* Same class as a section heading's button, so it is the same
          full-width tap target and the same glyph without a second set of
          rules; .all-btn only restates the type the <h2> would have given. */}
      <button
        className="sec-btn all-btn"
        onClick={collapse.onToggleAll}
        aria-pressed={collapse.allCollapsed}
      >
        {collapse.allCollapsed ? "Expand all" : "Collapse all"}
        <Glyph collapsed={collapse.allCollapsed} />
      </button>

      {sections.map(([year, list]) => (
        <Section
          key={`year-${year}`}
          label={String(year)}
          albums={list}
          {...collapse.for(String(year))}
        />
      ))}
    </>
  );
}

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
          <Glyph collapsed={collapsed} />
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

/** Shows what clicking gets you, not what you have: a grid when collapsed, a
 *  list when expanded. Deliberately not a chevron — nothing is being hidden. */
function Glyph({ collapsed }: { collapsed: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      {collapsed ? (
        <>
          <rect x="3" y="3" width="7" height="7" />
          <rect x="14" y="3" width="7" height="7" />
          <rect x="3" y="14" width="7" height="7" />
          <rect x="14" y="14" width="7" height="7" />
        </>
      ) : (
        <>
          <path d="M8 6h13M8 12h13M8 18h13" />
          <path d="M3 6h.01M3 12h.01M3 18h.01" />
        </>
      )}
    </svg>
  );
}
