import { AdminEntityList } from "@/features/admin/entity-list";
import { getAdminEntities } from "@/lib/server/admin-entities";

export default async function AdminShowsPage() {
  const items = await getAdminEntities("show_program");
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">КОНТЕНТ</p><h1>Шоу-программы</h1><p>Цены, длительность, состав, дополнения, акции и медиа.</p></div></header><AdminEntityList items={items} kind="shows" /></section>;
}
