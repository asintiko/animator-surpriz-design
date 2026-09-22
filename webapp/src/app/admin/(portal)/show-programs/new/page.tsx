import { EntityDetailsForm } from "@/features/admin/entity-details-form";
import { getAdminTaxonomy, getVariantGroups } from "@/lib/server/admin-entities";

export default async function NewShowPage({
  searchParams,
}: {
  searchParams: Promise<{ group_slug?: string; group_name?: string }>;
}) {
  const [taxonomy, variantGroups, query] = await Promise.all([
    getAdminTaxonomy(),
    getVariantGroups(),
    searchParams,
  ]);
  // "Добавить формат" from the programme list arrives with the group already chosen,
  // so a new branch never needs its slug typed by hand.
  const presetGroup = query.group_slug
    ? { slug: query.group_slug, name: query.group_name ?? query.group_slug }
    : undefined;
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">ШОУ-ПРОГРАММА</p><h1>{presetGroup ? `Новый формат: ${presetGroup.name}` : "Новая программа"}</h1></div></header><EntityDetailsForm categories={taxonomy.categories} kind="show_program" presetGroup={presetGroup} tags={taxonomy.tags} variantGroups={variantGroups} /></section>;
}
