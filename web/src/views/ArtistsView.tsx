import { useMemo, useState } from "react";
import { artistEntries, isRepeat } from "../artists";
import { ArtistLanes } from "../components/ArtistLanes";
import { ArtistList } from "../components/ArtistList";
import { Empty, Screen } from "../components/Screen";
import type { ViewProps } from "./props";

/**
 * Two sections over the same artists: a loyalty view of the ones you've
 * returned to, then a directory of all of them.
 *
 * There is no album grid below — tapping an artist expands their albums in
 * place, which is why this view needs no filter state and `matches()` needs
 * no artist parameter.
 *
 * The selection carries which section it was made in, not just an ID: a
 * repeat artist appears in both sections, and keying on the ID alone expands
 * them twice at once.
 */
type Section = "lanes" | "list";

export function ArtistsView({ albums, collapse, ...chrome }: ViewProps) {
  const [open, setOpen] = useState<{ id: string; section: Section } | null>(null);

  const entries = useMemo(() => artistEntries(albums), [albums]);
  const repeats = useMemo(() => entries.filter(isRepeat), [entries]);

  const expandedIn = (section: Section) => (open?.section === section ? open.id : null);
  const toggle = (section: Section) => (id: string) =>
    setOpen((cur) => (cur?.id === id && cur.section === section ? null : { id, section }));

  return (
    <Screen
      title="Artists"
      subtitle={{
        kind: "text",
        text: `${entries.length} artist${entries.length === 1 ? "" : "s"} · ${repeats.length} you came back to`,
      }}
      collapse={collapse}
      {...chrome}
    >
      {repeats.length > 0 && (
        <>
          <h2 className="sec-head">
            Who I come back to <span className="sec-n">· {repeats.length}</span>
          </h2>
          <ArtistLanes
            entries={repeats}
            expanded={expandedIn("lanes")}
            onToggle={toggle("lanes")}
            textOnly={collapse.allCollapsed}
          />
        </>
      )}

      {entries.length > 0 && (
        <>
          <h2 className="sec-head">
            All artists <span className="sec-n">· {entries.length}</span>
          </h2>
          <ArtistList
            entries={entries}
            expanded={expandedIn("list")}
            onToggle={toggle("list")}
            textOnly={collapse.allCollapsed}
          />
        </>
      )}

      {entries.length === 0 && <Empty />}
    </Screen>
  );
}
