import { AdminVisitorsSection } from "@/features/admin/admin-visitors-section";

export default function AdminVisitorsPage() {
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">АУДИТОРИЯ</p><h1>Посетители</h1><p>Кто заходил на сайт, откуда пришёл и какие страницы смотрел.</p></div></header><AdminVisitorsSection /></section>;
}
