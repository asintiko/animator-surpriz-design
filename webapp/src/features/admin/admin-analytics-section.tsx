"use client";

import { BarChart3, CalendarCheck, Eye, MousePointerClick, TrendingUp, UsersRound } from "lucide-react";

import {
  AdminSectionState,
  formatMoney,
  formatNumber,
  useAdminSection,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";

type RankedItem = { name: string; slug?: string; order_count: number };
type PageItem = { path: string; visit_count: number };
type Visit = { path: string; visitor?: string; masked_ip?: string; visited_at: string };
type AnalyticsPayload = SectionEnvelope & {
  metrics?: Record<string, number>;
  top_pages?: PageItem[];
  recent_visits?: Visit[];
  popular_programs?: RankedItem[];
  popular_characters?: RankedItem[];
  revenue?: { total?: number; count?: number; avg?: number; today_count?: number; today_total?: number };
};

const metricCards = [
  { key: "total_page_views", label: "Просмотры", icon: Eye },
  { key: "unique_visitors", label: "Посетители", icon: UsersRound },
  { key: "form_submissions", label: "Заявки", icon: MousePointerClick },
  { key: "orders_total", label: "Заказы", icon: CalendarCheck },
] as const;

export function AdminAnalyticsSection() {
  const section = useAdminSection<AnalyticsPayload>("analytics");
  const data = section.data;
  const metrics = data?.metrics ?? {};
  const revenue = data?.revenue ?? {};
  const maximumPageViews = Math.max(1, ...(data?.top_pages ?? []).map((item) => item.visit_count));

  return (
    <>
      <div className="admin-metrics">
        {metricCards.map(({ key, label, icon: Icon }) => <article key={key}><Icon /><span>{label}</span><strong>{formatNumber(metrics[key])}</strong></article>)}
        <article><TrendingUp /><span>Выручка</span><strong>{formatMoney(revenue.total ?? metrics.revenue_total)}</strong></article>
        <article><BarChart3 /><span>Средний чек</span><strong>{formatMoney(revenue.avg ?? metrics.revenue_avg)}</strong></article>
      </div>

      <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
      {!section.loading && !section.error ? (
        <div className="admin-dashboard-grid">
          <section className="admin-surface">
            <div className="admin-surface-head"><div><p className="eyebrow">ТРАФИК</p><h2>Популярные страницы</h2><p>Какие разделы сайта чаще всего открывают.</p></div></div>
            {data?.top_pages?.length ? <ol className="admin-ranking admin-ranking-bars">{data.top_pages.map((item) => <li key={item.path}><span><b>{item.path}</b><i style={{ width: `${Math.max(4, Math.round((item.visit_count / maximumPageViews) * 100))}%` }} /></span><strong>{formatNumber(item.visit_count)}</strong></li>)}</ol> : <div className="admin-empty">Данных о просмотрах пока нет.</div>}
          </section>
          <aside className="admin-surface">
            <div className="admin-surface-head"><div><p className="eyebrow">СЕГОДНЯ</p><h2>Активность</h2></div></div>
            <div className="admin-mini-stats"><article><span>Просмотры</span><strong>{formatNumber(metrics.today_page_views)}</strong></article><article><span>Посетители</span><strong>{formatNumber(metrics.today_unique_visitors)}</strong></article><article><span>Подтверждённых заказов</span><strong>{formatNumber(revenue.today_count ?? 0)}</strong></article></div>
          </aside>

          <section className="admin-surface">
            <div className="admin-surface-head"><div><p className="eyebrow">СПРОС</p><h2>Шоу-программы</h2></div></div>
            <Ranking items={data?.popular_programs ?? []} empty="Заказов шоу-программ пока нет." />
          </section>
          <section className="admin-surface">
            <div className="admin-surface-head"><div><p className="eyebrow">ПЕРСОНАЖИ</p><h2>Кого выбирают</h2></div></div>
            <Ranking items={data?.popular_characters ?? []} empty="Статистика персонажей пока не накоплена." />
          </section>

          <section className="admin-surface admin-surface-wide">
            <div className="admin-surface-head"><div><p className="eyebrow">LIVE</p><h2>Последние посещения</h2></div></div>
            {data?.recent_visits?.length ? <div className="admin-table-wrap"><table className="admin-data-table"><thead><tr><th>Страница</th><th>Посетитель</th><th>IP</th><th>Время</th></tr></thead><tbody>{data.recent_visits.map((visit, index) => <tr key={`${visit.visited_at}-${visit.path}-${index}`}><td><strong>{visit.path}</strong></td><td>{visit.visitor || "Анонимный"}</td><td>{visit.masked_ip || "—"}</td><td>{visit.visited_at}</td></tr>)}</tbody></table></div> : <div className="admin-empty">Посещений пока нет.</div>}
          </section>
        </div>
      ) : null}
    </>
  );
}

function Ranking({ empty, items }: { empty: string; items: RankedItem[] }) {
  if (!items.length) return <div className="admin-empty">{empty}</div>;
  return <ol className="admin-ranking">{items.map((item) => <li key={`${item.slug ?? item.name}-${item.name}`}><span>{item.name}</span><strong>{formatNumber(item.order_count)}</strong></li>)}</ol>;
}
