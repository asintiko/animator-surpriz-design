import { ArrowUpRight, Clock3, UsersRound } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { entityCropStyle, formatDuration, formatPrice } from "@/lib/catalog";
import type { CatalogCard } from "@/lib/types";

export function ShowCard({ show, featured = false }: { show: CatalogCard; featured?: boolean }) {
  const href = `/show-programs/${show.slug}`;
  const src = show.hero_file_path || "/brand/logo.png";
  const badge = show.promotions.find((promotion) => promotion.badge_text.trim())?.badge_text;

  return (
    <article className={`show-card${featured ? " is-featured" : ""}`}>
      <Link className="show-card-media" href={href} aria-label={`Подробнее: ${show.name}`}>
        <Image
          src={src}
          alt={show.name}
          fill
          sizes="(max-width: 760px) 100vw, 33vw"
          style={entityCropStyle(show)}
        />
        {badge ? <span className="show-badge">{badge}</span> : null}
      </Link>
      <div className="show-card-copy">
        <div>
          <h3><Link href={href}>{show.name}</Link></h3>
          <p>{show.short_description}</p>
        </div>
        <div className="show-facts">
          <span><Clock3 size={17} /> {formatDuration(show.default_duration_minutes)}</span>
          <span><UsersRound size={17} /> {show.included_characters_count} персонажа</span>
        </div>
        <div className="show-card-footer">
          <strong>{formatPrice(show.base_price)}</strong>
          <Link className="button button-secondary" href={href}>
            Подробнее <ArrowUpRight size={17} />
          </Link>
        </div>
      </div>
    </article>
  );
}
