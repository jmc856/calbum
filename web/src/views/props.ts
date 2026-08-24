import type { Album } from "../albums";

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
