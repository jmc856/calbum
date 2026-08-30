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
 *
 * `variant` picks the tile or the collapsed text row. Both live here rather
 * than in a second component so the link decision above — div vs anchor,
 * whether to carry the Spotify aria-label, how to say "not on Spotify" — is
 * made exactly once. Six manual albums exercise that branch today; two
 * components would eventually disagree about it.
 */
export function AlbumCard({
  album,
  sub,
  variant = "tile",
}: {
  album: Album;
  sub?: string;
  variant?: "tile" | "row";
}) {
  const subtext = sub ?? album.artists.join(", ");

  const body =
    variant === "row" ? (
      <>
        <span className="row-t">{album.title}</span>
        {/* The badge folds into the sub line here: a pill is too heavy in a
            dense list, but the album still has to say why it doesn't link. */}
        <span className="row-s">{album.url ? subtext : `${subtext} · Not on Spotify`}</span>
      </>
    ) : (
      <>
        {album.cover ? (
          <img className="cover" src={album.cover} alt="" loading="lazy" decoding="async" />
        ) : (
          <div className="cover-fb" aria-hidden="true">
            {initial(album.title)}
          </div>
        )}
        <div className="c-title">{album.title}</div>
        <div className="c-sub">{subtext}</div>
        {!album.url && <span className="c-badge">Not on Spotify</span>}
      </>
    );

  const cls = variant === "row" ? "row" : "card";

  if (!album.url) return <div className={cls}>{body}</div>;

  return (
    <a
      className={cls}
      href={album.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${album.title} by ${album.artists.join(", ")} — open on Spotify`}
    >
      {body}
    </a>
  );
}
