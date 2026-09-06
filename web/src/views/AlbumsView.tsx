import { plural } from "../albums";
import { Screen } from "../components/Screen";
import { SectionList } from "../components/Section";
import type { CollapseApi, ViewProps } from "./props";

/** The whole catalogue, grouped by year. The subtitle counts what is actually
 *  on screen, so a search narrowing the list says so. */
export function AlbumsView({ albums, collapse, ...chrome }: ViewProps & { collapse: CollapseApi }) {
  return (
    <Screen title="Albums" subtitle={plural(albums.length, "album")} {...chrome}>
      <SectionList albums={albums} collapse={collapse} />
    </Screen>
  );
}
