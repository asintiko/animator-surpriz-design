import { AdminDashboard } from "@/features/admin/admin-dashboard";
import { getCharacters, getShows } from "@/lib/catalog";

export default function AdminPage() {
  return (
    <section className="admin-page">
      <header className="admin-page-head"><div><p className="eyebrow">17 ИЮЛЯ 2026</p><h1>Обзор</h1><p>Актуальное состояние каталога и заказов.</p></div></header>
      <AdminDashboard fallback={{ characters_total: getCharacters().length, shows_total: getShows().length }} />
    </section>
  );
}
