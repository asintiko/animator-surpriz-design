"use client";

import { ArrowRight, BarChart3, CalendarCheck, Eye, ImageIcon, PartyPopper, UsersRound } from "lucide-react";
import { useEffect, useState } from "react";

type Dashboard = {
  authenticated?: boolean;
  stats?: Record<string, number>;
  recent_orders?: Array<Record<string, string | number>>;
  popular_programs?: Array<{ name: string; orders_count: number }>;
};

const defaultMetrics = [
  { key: "total_visits", label: "Просмотры", icon: Eye },
  { key: "orders_total", label: "Заказы", icon: CalendarCheck },
  { key: "customers_total", label: "Клиенты", icon: UsersRound },
  { key: "characters_total", label: "Персонажи", icon: ImageIcon },
  { key: "shows_total", label: "Шоу", icon: PartyPopper },
  { key: "revenue_total", label: "Выручка", icon: BarChart3 },
];

export function AdminDashboard({ fallback }: { fallback: Record<string, number> }) {
  const [dashboard, setDashboard] = useState<Dashboard>({ stats: fallback });

  useEffect(() => {
    fetch("/api/admin/dashboard", { cache: "no-store", credentials: "same-origin" })
      .then((response) => response.json())
      .then((result: Dashboard) => {
        if (result.authenticated === false) window.location.assign("/admin/login");
        else setDashboard(result);
      })
      .catch(() => undefined);
  }, []);

  const stats = { ...fallback, ...dashboard.stats };
  return (
    <>
      <div className="admin-metrics">{defaultMetrics.map(({ key, label, icon: Icon }) => <article key={key}><Icon /><span>{label}</span><strong>{new Intl.NumberFormat("ru-RU").format(stats[key] ?? 0)}</strong></article>)}</div>
      <div className="admin-dashboard-grid">
        <section className="admin-surface"><div className="admin-surface-head"><div><p className="eyebrow">ОПЕРАЦИИ</p><h2>Последние заказы</h2></div><a href="/admin/orders">Все заказы <ArrowRight size={16} /></a></div>{dashboard.recent_orders?.length ? <div className="admin-table">{dashboard.recent_orders.slice(0, 8).map((order) => <a href="/admin/orders" key={String(order.public_id)}><strong>{String(order.public_id)}</strong><span>{String(order.customer_name || order.customer_phone)}</span><span>{String(order.celebration_date)} · {String(order.time_from)}</span><span className={`order-status status-${order.status}`}>{String(order.status_label || order.status)}</span></a>)}</div> : <div className="admin-empty">Заказы появятся после подключения adapter API.</div>}</section>
        <aside className="admin-surface"><div className="admin-surface-head"><div><p className="eyebrow">СПРОС</p><h2>Популярные шоу</h2></div></div>{dashboard.popular_programs?.length ? <ol className="admin-ranking">{dashboard.popular_programs.map((item) => <li key={item.name}><span>{item.name}</span><strong>{item.orders_count}</strong></li>)}</ol> : <div className="admin-empty">Данные появятся после первых заказов.</div>}</aside>
      </div>
    </>
  );
}
