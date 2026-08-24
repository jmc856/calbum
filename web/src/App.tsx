import { useMemo, useRef, useState } from "react";
import { ALBUMS, matches, type View } from "./albums";
import { Nav } from "./components/Nav";
import { AlbumsView } from "./views/AlbumsView";
import { GenresView } from "./views/GenresView";

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

  const scrollRef = useRef<HTMLDivElement>(null);

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

  const chrome = {
    albums,
    query,
    onQuery: setQuery,
    searchOpen: searchOpen || view === "search",
    onToggleSearch: () => setSearchOpen((o) => !o),
  };

  return (
    <div className="app">
      <div className="scroll" ref={scrollRef}>
        {view === "albums" && <AlbumsView title="Albums" {...chrome} />}
        {view === "search" && <AlbumsView title="Search" {...chrome} />}
        {view === "artists" && <AlbumsView title="Artists" groupByArtist {...chrome} />}
        {view === "genres" && <GenresView {...chrome} />}
      </div>

      <Nav view={view} onChange={changeView} />
    </div>
  );
}
