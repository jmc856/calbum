import type { Album } from "../albums";
import { byTitle } from "../albums";
import { AlbumCard } from "./AlbumCard";

/** One grouped block — a year, a genre, an artist. Heading plus cover grid. */
export function Section({ label, albums }: { label: string; albums: Album[] }) {
  return (
    <section>
      <h2 className="sec-head">{label}</h2>
      <div className="grid">
        {[...albums].sort(byTitle).map((a) => (
          <AlbumCard key={a.id} album={a} />
        ))}
      </div>
    </section>
  );
}
