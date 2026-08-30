import { useCallback, useMemo, useRef, useState } from "react";
import { ALBUMS, matches, type View } from "./albums";
import { Nav } from "./components/Nav";
import type { CollapseApi } from "./views/props";
import { AlbumsView } from "./views/AlbumsView";
import { ArtistsView } from "./views/ArtistsView";
import { GenresView } from "./views/GenresView";

/**
 * Collapse state is bucketed per tab *module*, not per `View` — Albums and
 * Search are one mounted AlbumsView (see the slot comment below), so keying on
 * `View` would swap the bucket underneath a component that never remounted and
 * sections would pop open on a "tab switch" that isn't one.
 */
type Tab = "albums" | "genres" | "artists";
const tabOf = (view: View): Tab => (view === "search" ? "albums" : view);

/**
 * A section is collapsed iff `all` differs from an explicit exception for it.
 *
 * The XOR is what lets the section list change underneath the state, which it
 * does constantly: searching drops most year sections, the genre filter
 * re-groups them, and new years arrive as the catalogue grows. A key nobody
 * has touched inherits `all`; only keys the user actually toggled are stored.
 * An array of collapsed keys cannot do this — it goes stale the moment the
 * grouping changes.
 */
type Collapse = { all: boolean; except: Set<string> };
const isCollapsed = (c: Collapse, key: string) => c.all !== c.except.has(key);

/** Genres opens collapsed; the others open as grids. Mount-time only — never
 *  re-applied on tab change, which would clobber whatever the user chose. */
const INITIAL_COLLAPSE: Record<Tab, Collapse> = {
  albums: { all: false, except: new Set() },
  genres: { all: true, except: new Set() },
  artists: { all: false, except: new Set() },
};

/**
 * Shell and routing only. Everything a single tab knows about — its header,
 * its layout, its filter state — lives in that tab's view module, so adding
 * one is a new file plus a line here rather than another pair of
 * `view === "x"` branches threaded through this component.
 */
export default function App() {
  const [view, setView] = useState<View>("albums");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [collapse, setCollapse] = useState(INITIAL_COLLAPSE);

  const scrollRef = useRef<HTMLDivElement>(null);
  const tab = tabOf(view);

  // App owns the query filter because search is shell chrome, shared by every
  // tab. Any narrower filtering is the view's own business.
  const albums = useMemo(
    () => ALBUMS.filter((a) => matches(a, query.trim().toLowerCase(), null)),
    [query],
  );

  function changeView(next: View) {
    setView(next);
    if (next !== "search") setSearchOpen(false);
    scrollRef.current?.scrollTo({ top: 0 });
  }

  const toggleOne = useCallback(
    (key: string) =>
      setCollapse((prev) => {
        // Copy the Set — React bails out on an identical reference.
        const except = new Set(prev[tab].except);
        if (!except.delete(key)) except.add(key);
        return { ...prev, [tab]: { ...prev[tab], except } };
      }),
    [tab],
  );

  // A hard set, not a per-section pass: clearing the exceptions is what makes
  // "collapse all" unambiguous when some sections were toggled individually.
  // Collapsing removes most of the page height, so the browser would clamp
  // scroll somewhere arbitrary — go to the top, as changeView already does.
  // Expanding grows the page and leaves the current position valid, so it
  // deliberately does not scroll.
  const toggleAll = useCallback(() => {
    setCollapse((prev) => {
      const all = !prev[tab].all;
      if (all) scrollRef.current?.scrollTo({ top: 0 });
      return { ...prev, [tab]: { all, except: new Set() } };
    });
  }, [tab]);

  const collapseApi: CollapseApi = useMemo(
    () => ({
      for: (key) => ({
        collapsed: isCollapsed(collapse[tab], key),
        onToggle: () => toggleOne(key),
      }),
      allCollapsed: collapse[tab].all,
      onToggleAll: toggleAll,
    }),
    [collapse, tab, toggleOne, toggleAll],
  );

  const chrome = {
    albums,
    query,
    onQuery: setQuery,
    searchOpen: searchOpen || view === "search",
    onToggleSearch: () => setSearchOpen((o) => !o),
    collapse: collapseApi,
  };

  return (
    <div className="app">
      <div className="scroll" ref={scrollRef}>
        {/* One slot, not one per title: two sibling AlbumsViews would make
            React tear down and remount every card switching Albums<->Search,
            instead of reconciling the same grid in place. */}
        {(view === "albums" || view === "search") && (
          <AlbumsView title={view === "search" ? "Search" : "Albums"} {...chrome} />
        )}
        {view === "artists" && <ArtistsView {...chrome} />}
        {view === "genres" && <GenresView {...chrome} />}
      </div>

      <Nav view={view} onChange={changeView} />
    </div>
  );
}
