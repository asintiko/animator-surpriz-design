import snapshotJson from "@/data/catalog.generated.json";
import type { CatalogCard, CatalogEntity, CatalogSnapshot } from "@/lib/types";

function withEnsembleDefaults(entity: CatalogEntity): CatalogEntity {
  const rawMembers: unknown = entity.ensemble_members;
  const ensembleMembers = Array.isArray(rawMembers)
    ? rawMembers.map(String).filter(Boolean)
    : String(rawMembers ?? "").split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean);
  return {
    ...entity,
    ensemble_members: ensembleMembers,
    ensemble_included_count: Number(entity.ensemble_included_count ?? 2),
    ensemble_extra_member_price: Number(entity.ensemble_extra_member_price ?? 300_000),
    mobile_cover_offset_x: Number(entity.mobile_cover_offset_x ?? entity.cover_offset_x ?? 50),
    mobile_cover_offset_y: Number(entity.mobile_cover_offset_y ?? entity.cover_offset_y ?? 50),
    mobile_cover_fit: entity.mobile_cover_fit ?? entity.cover_fit ?? "cover",
    mobile_image_zoom: Number(entity.mobile_image_zoom ?? entity.image_zoom ?? 100),
  };
}

const sourceSnapshot = snapshotJson as unknown as CatalogSnapshot;
const snapshot: CatalogSnapshot = {
  ...sourceSnapshot,
  characters: sourceSnapshot.characters.map(withEnsembleDefaults),
  shows: sourceSnapshot.shows.map(withEnsembleDefaults),
};

export function getCatalogSnapshot(): CatalogSnapshot {
  return snapshot;
}

export function getCharacters(): CatalogEntity[] {
  return snapshot.characters;
}

export function getShows(): CatalogEntity[] {
  return snapshot.shows;
}

export function getCharacter(slug: string): CatalogEntity | undefined {
  return snapshot.characters.find((item) => item.slug === slug);
}

export function getShow(slug: string): CatalogEntity | undefined {
  return snapshot.shows.find((item) => item.slug === slug);
}

export function getCatalogCards(items: CatalogEntity[]): CatalogCard[] {
  return items.map(
    ({
      id,
      name,
      slug,
      short_description,
      base_price,
      default_duration_minutes,
      included_characters_count,
      extra_character_price_3,
      extra_character_price_4_plus,
      age_from,
      age_to,
      entity_type,
      hero_file_path,
      cover_offset_x,
      cover_offset_y,
      cover_fit,
      image_zoom,
      mobile_cover_offset_x,
      mobile_cover_offset_y,
      mobile_cover_fit,
      mobile_image_zoom,
      categories,
      tags,
      promotions,
    }) => ({
      id,
      name,
      slug,
      short_description,
      base_price,
      default_duration_minutes,
      included_characters_count,
      extra_character_price_3,
      extra_character_price_4_plus,
      age_from,
      age_to,
      entity_type,
      hero_file_path,
      cover_offset_x,
      cover_offset_y,
      cover_fit,
      image_zoom,
      mobile_cover_offset_x,
      mobile_cover_offset_y,
      mobile_cover_fit,
      mobile_image_zoom,
      categories,
      tags,
      promotions,
    }),
  );
}

export function formatPrice(value: number): string {
  if (!value) return "Уточнить стоимость";
  return `от ${new Intl.NumberFormat("ru-RU").format(value)} сум`;
}

export function formatDuration(minutes: number): string {
  if (minutes === 60) return "1 час";
  if (minutes > 60 && minutes % 60 === 0) return `${minutes / 60} часа`;
  return `${minutes} минут`;
}

export function imagePosition(entity: Pick<CatalogEntity, "cover_offset_x" | "cover_offset_y">) {
  return `${entity.cover_offset_x}% ${entity.cover_offset_y}%`;
}

/** The one formula that turns stored cropping into CSS. Every surface that paints a
 *  cover — public cards, the admin editor, its preview — goes through here, so the
 *  frame the owner adjusts cannot drift from what visitors see. */
export function cropStyle(crop: {
  x: number;
  y: number;
  fit: "cover" | "contain";
  zoom: number;
}): { objectFit: "cover" | "contain"; objectPosition: string; transform: string; transformOrigin: string } {
  const position = `${crop.x}% ${crop.y}%`;
  return {
    objectFit: crop.fit,
    objectPosition: position,
    transform: `scale(${Math.min(200, Math.max(100, crop.zoom)) / 100})`,
    transformOrigin: position,
  };
}

/** Same formula, fed straight from a catalog row. */
export function entityCropStyle(
  entity: Pick<CatalogEntity, "cover_offset_x" | "cover_offset_y" | "cover_fit" | "image_zoom">,
) {
  return cropStyle({
    x: Number(entity.cover_offset_x ?? 50),
    y: Number(entity.cover_offset_y ?? 50),
    fit: entity.cover_fit === "contain" ? "contain" : "cover",
    zoom: Number(entity.image_zoom || 100),
  });
}
