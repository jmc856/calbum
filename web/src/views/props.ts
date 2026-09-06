import type { Album } from "../albums";

/**
 * Collapse controls, as one object rather than three loose props.
 *
 * The storage behind this — a per-tab `all` flag plus a set of exceptions —
 * is App's business and deliberately does not appear here. A caller asks
 * `for(key)` and spreads the answer; it never sees a Set, and never has to
 * know that "collapsed" is an XOR rather than a lookup.
 *
 * Not part of ViewProps: only the year-grouped tabs take it, and SectionList
 * is the single consumer.
 */
export interface CollapseApi {
  /** Everything a Section needs, as one spread. */
  for: (key: string) => { collapsed: boolean; onToggle: () => void };
  /** Whether the tab is collapsed wholesale — drives the collapse-all label. */
  allCollapsed: boolean;
  onToggleAll: () => void;
}

/**
 * What App hands every view: the search-filtered albums plus the search
 * chrome it owns. Declared once so adding a view means implementing this,
 * not rediscovering which props App happens to pass.
 */
export interface ViewProps {
  albums: Album[];
  query: string;
  onQuery: (q: string) => void;
  searchOpen: boolean;
  onToggleSearch: () => void;
}
