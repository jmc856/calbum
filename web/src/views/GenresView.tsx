import { useMemo, useState } from "react";
import { ALBUMS, matches, plural, stylesForGenre } from "../albums";
import { GenreChart } from "../components/GenreChart";
import { Screen } from "../components/Screen";
import { SectionList } from "../components/Section";
import type { CollapseApi, ViewProps } from "./props";

const GENRE_COUNT = new Set(ALBUMS.flatMap((a) => a.genres)).size;

/**
 * The era chart doubles as the filter control, so the selected genre is this
 * view's own state — App never sees it. That's the whole reason the view
 * split earns itself: the filter lives with the thing that sets it.
 */
export function GenresView({ albums, collapse, ...chrome }: ViewProps & { collapse: CollapseApi }) {
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

  // Counts `visible`, not ALBUMS, in both branches: a search narrows this tab
  // too, and a header claiming 87 albums above three of them is the bug.
  const subtitle = genre
    ? `${plural(visible.length, "album")} · ${genre}`
    : `${plural(visible.length, "album")} · ${GENRE_COUNT} genres`;

  return (
    <Screen title={genre ?? "Genres"} subtitle={subtitle} {...chrome}>
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

      <SectionList albums={visible} collapse={collapse} />
    </Screen>
  );
}
