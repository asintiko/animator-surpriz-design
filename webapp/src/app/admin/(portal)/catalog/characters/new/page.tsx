import { EntityDetailsForm } from "@/features/admin/entity-details-form";
import { getAdminTaxonomy } from "@/lib/server/admin-entities";

export default async function NewCharacterPage() {
  const taxonomy = await getAdminTaxonomy();
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">ПЕРСОНАЖ</p><h1>Новая карточка</h1></div></header><EntityDetailsForm categories={taxonomy.categories} kind="character" tags={taxonomy.tags} /></section>;
}
