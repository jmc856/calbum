import { byNameAsc, byYearDesc, groupBy } from "../albums";
import { Empty, Screen, Stats } from "../components/Screen";
import { Section } from "../components/Section";
import type { ViewProps } from "./props";

/**
 * Albums and Search: the same year-grouped cover grid, differing only in
 * title and whether the search field starts open. Kept as one component
 * because that difference is genuinely two props, not two behaviours.
 *
 * `groupBy` is passed `a.artists` — every artist, not just the primary —
 * because a section heading per collaborator is correct here. The Artists
 * tab makes the opposite call; see artists.ts.
 */
export function AlbumsView({ title, albums, groupByArtist = false, ...chrome }: ViewProps & {
  title: string;
  groupByArtist?: boolean;
}) {
  const sections = groupByArtist
    ? groupBy(albums, (a) => a.artists, byNameAsc).map(([artist, list]) => ({
        key: `artist-${artist}`,
        label: `${artist} · ${list.length}`,
        albums: list,
      }))
    : groupBy(albums, (a) => a.year, byYearDesc).map(([year, list]) => ({
        key: `year-${year}`,
        label: String(year),
        albums: list,
      }));

  return (
    <Screen title={title} subtitle={<Stats albums={albums} />} {...chrome}>
      {sections.map((s) => (
        <Section key={s.key} label={s.label} albums={s.albums} />
      ))}
      {albums.length === 0 && <Empty />}
    </Screen>
  );
}
