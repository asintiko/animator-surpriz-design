import type { AdminEntityListItem, CatalogEntity, TaxonomyItem } from "../types";
import { fetchAdapterJson } from "./proxy";

type EntityEnvelope = { success: boolean; entity?: CatalogEntity };
type EntityListEnvelope = { success: boolean; items?: AdminEntityListItem[] };
type TaxonomyEnvelope = {
  success: boolean;
  categories?: TaxonomyItem[];
  tags?: TaxonomyItem[];
};

export type AdminTaxonomy = {
  categories: TaxonomyItem[];
  tags: TaxonomyItem[];
};

export async function getAdminEntity(
  id: number,
): Promise<CatalogEntity | undefined> {
  const result = await fetchAdapterJson<EntityEnvelope>(
    `/api/v2/admin/entities/${encodeURIComponent(id)}`,
  );
  return result?.success && result.entity ? result.entity : undefined;
}

export async function getAdminEntities(
  entityType: "character" | "show_program",
): Promise<AdminEntityListItem[]> {
  const result = await fetchAdapterJson<EntityListEnvelope>(
    `/api/v2/admin/entities?entity_type=${encodeURIComponent(entityType)}`,
  );
  if (!result?.success || !result.items) throw new Error("Каталог админки временно недоступен.");
  return result.items;
}

export function resolveAdminTaxonomy(
  result: TaxonomyEnvelope | null,
): AdminTaxonomy {
  if (!result?.success || !result.categories || !result.tags) {
    throw new Error("Таксономия админки временно недоступна.");
  }
  return {
    categories: result.categories.filter((item) => item.is_visible !== false),
    tags: result.tags.filter((item) => item.is_visible !== false),
  };
}

export async function getAdminTaxonomy(): Promise<AdminTaxonomy> {
  const result = await fetchAdapterJson<TaxonomyEnvelope>("/api/v2/admin/section/taxonomy");
  return resolveAdminTaxonomy(result);
}

export type VariantGroup = { slug: string; name: string; variantCount: number };

/** The groups an owner can attach a programme to, derived from what already exists —
 *  no separate table, and no need to type a slug by hand. */
export async function getVariantGroups(): Promise<VariantGroup[]> {
  const items = await getAdminEntities("show_program");
  const groups = new Map<string, VariantGroup>();
  for (const item of items) {
    const slug = String(item.variant_group_slug || "").trim();
    if (!slug) continue;
    const existing = groups.get(slug);
    if (existing) {
      existing.variantCount += 1;
      continue;
    }
    groups.set(slug, {
      slug,
      name: String(item.variant_group_name || "").trim() || slug,
      variantCount: 1,
    });
  }
  return [...groups.values()].sort((left, right) => left.name.localeCompare(right.name, "ru"));
}
