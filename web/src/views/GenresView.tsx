import { useMemo, useState } from "react";
import { ALBUMS, byYearDesc, groupBy, matches, stylesForGenre } from "../albums";
import { GenreChart } from "../components/GenreChart";
import { Empty, Screen } from "../components/Screen";
import { Section } from "../components/Section";
import type { ViewProps } from "./props";

const GENRE_COUNT = new Set(ALBUMS.flatMap((a) => a.genres)).size;

/**
 * The era chart doubles as the filter control, so the selected genre is this
 * view's own state — App never sees it. That's the whole reason the view
 * split earns itself: the filter lives with the thing that sets it.
 */
export function GenresView({ albums, ...chrome }: ViewProps) {
  const [genre, setGenre] = useState<string | null>(null);

  // `albums` arrives already filtered by the search query; this narrows it
  // again by the selected genre.
  const visible = useMemo(
    () => (genre ? albums.filter((a) => matches(a, "", genre)) : albums),
    [albums, genre],
  );

  // Capped: Rock alone has 24 styles, and the count-1 tail is noise that
  // pushed the album grid entirely below the fold.
  const styles = useMemo(
    () => (genre ? stylesForGenre(ALBUMS, genre).slice(0, 12) : []),
    [genre],
  );

  const sections = useMemo(
    () => groupBy(visible, (a) => a.year, byYearDesc),
    [visible],
  );

  return (
    <Screen
      title={genre ?? "Genres"}
      subtitle={{
        kind: "text",
        text: genre
          ? `${visible.length} album${visible.length === 1 ? "" : "s"} · ${genre}`
          : `${ALBUMS.length} albums · ${GENRE_COUNT} genres`,
      }}
      {...chrome}
    >
      {/* Charts the whole catalogue, never the filtered set: a chart that
          reshaped itself as you filtered would describe your filter rather
          than the collection. */}
      <GenreChart albums={ALBUMS} selected={genre} onSelect={setGenre} />

      {styles.length > 0 && (
        <div className="gstyles">
          <p className="gstyles-lab">{genre} → styles</p>
          <div className="gchips">
            {styles.map(([name, n]) => (
              <span className="gchip" key={name}>
                {name}
                <span className="gchip-n tnum">{n}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {sections.map(([year, list]) => (
        <Section key={`year-${year}`} label={String(year)} albums={list} />
      ))}
      {visible.length === 0 && <Empty />}
    </Screen>
  );
}
