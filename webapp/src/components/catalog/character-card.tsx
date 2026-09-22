import { ArrowUpRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { entityCropStyle, formatDuration, formatPrice } from "@/lib/catalog";
import type { CatalogCard } from "@/lib/types";

export function CharacterCard({ character }: { character: CatalogCard }) {
  const href = `/character/${character.slug}`;
  const src = character.hero_file_path || "/brand/logo.png";
  const age = character.age_from ? `от ${character.age_from} лет` : "для детского праздника";

  return (
    <article className="entity-card">
      <Link className="entity-media" href={href} aria-label={`Подробнее: ${character.name}`}>
        <Image
          src={src}
          alt={character.name}
          fill
          sizes="(max-width: 560px) 46vw, (max-width: 1000px) 31vw, 24vw"
          style={entityCropStyle(character)}
        />
      </Link>
      <div className="entity-card-body">
        <h3><Link href={href}>{character.name}</Link></h3>
        <p className="entity-meta">{age} · {formatDuration(character.default_duration_minutes)}</p>
        <div className="entity-card-footer">
          <strong>{formatPrice(character.base_price)}</strong>
          <Link href={href} aria-label={`Открыть ${character.name}`}><ArrowUpRight size={19} /></Link>
        </div>
      </div>
    </article>
  );
}
