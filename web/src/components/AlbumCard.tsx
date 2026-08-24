import type { Album } from "../albums";
import { initial } from "../albums";

/**
 * A manual album has no Spotify URL, so it renders as a plain div rather
 * than a dead anchor — and says why, instead of looking broken.
 *
 * `sub` defaults to the artist, which is what every grid on the site wants.
 * The Artists tab overrides it: inside one artist's own expansion their name
 * on every card is noise, and the year says something the context doesn't.
 * The aria-label still names the artist either way.
 */
export function AlbumCard({ album, sub }: { album: Album; sub?: string }) {
  const art = album.cover ? (
    <img className="cover" src={album.cover} alt="" loading="lazy" decoding="async" />
  ) : (
    <div className="cover-fb" aria-hidden="true">
      {initial(album.title)}
    </div>
  );

  const body = (
    <>
      {art}
      <div className="c-title">{album.title}</div>
      <div className="c-sub">{sub ?? album.artists.join(", ")}</div>
      {!album.url && <span className="c-badge">Not on Spotify</span>}
    </>
  );

  if (!album.url) return <div className="card">{body}</div>;

  return (
    <a
      className="card"
      href={album.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${album.title} by ${album.artists.join(", ")} — open on Spotify`}
    >
      {body}
    </a>
  );
}
