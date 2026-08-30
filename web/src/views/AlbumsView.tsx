import { byYearDesc, groupBy } from "../albums";
import { Empty, Screen } from "../components/Screen";
import { Section } from "../components/Section";
import type { ViewProps } from "./props";

/**
 * Albums and Search: the same year-grouped cover grid, differing only in
 * title and whether the search field starts open. Kept as one component
 * because that difference is genuinely one prop, not two behaviours.
 */
export function AlbumsView({ title, albums, collapse, ...chrome }: ViewProps & { title: string }) {
  const sections = groupBy(albums, (a) => a.year, byYearDesc);

  return (
    <Screen title={title} subtitle={{ kind: "stats", albums }} collapse={collapse} {...chrome}>
      {sections.map(([year, list]) => (
        <Section
          key={`year-${year}`}
          label={String(year)}
          albums={list}
          {...collapse.for(String(year))}
        />
      ))}
      {albums.length === 0 && <Empty />}
    </Screen>
  );
}
