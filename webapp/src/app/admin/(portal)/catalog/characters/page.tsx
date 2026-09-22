import { AdminEntityList } from "@/features/admin/entity-list";
import { getAdminEntities } from "@/lib/server/admin-entities";

export default async function AdminCharactersPage() {
  const items = await getAdminEntities("character");
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">КОНТЕНТ</p><h1>Персонажи</h1><p>Обложки, описания, категории, теги и порядок отображения.</p></div></header><AdminEntityList items={items} kind="characters" /></section>;
}
