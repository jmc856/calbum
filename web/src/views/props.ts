import type { Album } from "../albums";

/**
 * Collapse controls, as one object rather than four loose props.
 *
 * The storage behind this — a per-tab `all` flag plus a set of exceptions —
 * is App's business and deliberately does not appear here. A caller asks
 * `for(key)` and spreads the answer; it never sees a Set, and never has to
 * know that "collapsed" is an XOR rather than a lookup.
 */
export interface CollapseApi {
  /** Everything a Section needs, as one spread. */
  for: (key: string) => { collapsed: boolean; onToggle: () => void };
  /** Whether the tab is collapsed wholesale — drives the header indicator. */
  allCollapsed: boolean;
  onToggleAll: () => void;
}

/**
 * What App hands every view: the search-filtered albums plus the search
 * chrome it owns. Declared once so adding a view means implementing this,
 * not rediscovering which props App happens to pass.
 *
 * `collapse` is required rather than optional on purpose: the compiler then
 * lists every view and every Screen that has not been wired up, which is what
 * makes "the control is on all tabs" checkable instead of a thing to remember.
 */
export interface ViewProps {
  albums: Album[];
  query: string;
  onQuery: (q: string) => void;
  searchOpen: boolean;
  onToggleSearch: () => void;
  collapse: CollapseApi;
}
