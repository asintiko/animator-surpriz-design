"use client";

import { ChevronLeft, ChevronRight, Search, UserRoundCheck } from "lucide-react";
import Link from "next/link";
import { type FormEvent, useMemo, useState } from "react";

import {
  AdminSectionState,
  formatNumber,
  useAdminSection,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";

type Visitor = {
  display_id: string;
  masked_ip: string;
  first_seen_label: string;
  last_seen_label: string;
  page_views: number;
  sessions: number;
  first_path: string;
  last_path: string;
  referrer: string;
  has_referrer: boolean;
  browser: string;
  device: string;
  customer?: { id: number; name: string; phone: string } | null;
};

type VisitorsPayload = SectionEnvelope & {
  items?: Visitor[];
  summary?: Record<string, number>;
  pagination?: { page: number; pages: number; total: number; has_previous: boolean; has_next: boolean };
  unavailable?: boolean;
};

export function AdminVisitorsSection() {
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const query = useMemo(() => {
    const value = new URLSearchParams({ page: String(page) });
    if (search) value.set("search", search);
    return value;
  }, [page, search]);
  const section = useAdminSection<VisitorsPayload>("visitors", query);
  const summary = section.data?.summary ?? {};
  const pagination = section.data?.pagination;
  const visitors = section.data?.items ?? [];

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setSearch(draft.trim());
  }

  return <>
    <div className="admin-metrics admin-metrics-compact">
      <article><span>Посетители</span><strong>{formatNumber(summary.visitors)}</strong></article>
      <article><span>Сегодня</span><strong>{formatNumber(summary.today)}</strong></article>
      <article><span>Сессии</span><strong>{formatNumber(summary.sessions)}</strong></article>
      <article><span>Просмотры</span><strong>{formatNumber(summary.page_views)}</strong></article>
      <article><span>Связаны с клиентом</span><strong>{formatNumber(summary.identified)}</strong></article>
    </div>
    <section className="admin-surface">
      <div className="admin-surface-head"><div><p className="eyebrow">ПОСЕТИТЕЛИ САЙТА</p><h2>История заходов</h2><p>Сессии, страницы, источник и устройство. IP показывается только в маскированном виде.</p></div></div>
      <form className="admin-filter-bar" onSubmit={applySearch}>
        <label><span>Поиск</span><input placeholder="VIS-…, путь, клиент или устройство" value={draft} onChange={(event) => setDraft(event.target.value)} /></label>
        <button className="button button-violet" type="submit"><Search size={17} /> Найти</button>
        {search ? <button className="button button-secondary" onClick={() => { setDraft(""); setSearch(""); setPage(1); }} type="button">Сбросить</button> : null}
      </form>
      <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
      {section.data?.unavailable ? <div className="admin-empty">Статистика временно занята. Обновите страницу через несколько секунд.</div> : null}
      {!section.loading && !section.error && !visitors.length ? <div className="admin-empty">Посетители по выбранному фильтру не найдены.</div> : null}
      {visitors.length ? <div className="admin-table-wrap"><table className="admin-data-table"><thead><tr><th>Посетитель</th><th>Активность</th><th>Маршрут</th><th>Источник</th><th>Устройство</th><th>Клиент</th></tr></thead><tbody>{visitors.map((visitor) => <tr key={visitor.display_id}><td><strong>{visitor.display_id}</strong><small>{visitor.masked_ip}</small></td><td><strong>{visitor.last_seen_label}</strong><small>Первый визит: {visitor.first_seen_label}</small><small>{visitor.sessions} сессий · {visitor.page_views} страниц</small></td><td><strong>{visitor.last_path}</strong><small>Начал: {visitor.first_path}</small></td><td>{visitor.has_referrer ? visitor.referrer : "Прямой заход"}</td><td><strong>{visitor.device}</strong><small>{visitor.browser}</small></td><td>{visitor.customer ? <Link href={`/admin/customers?search=${encodeURIComponent(visitor.customer.phone || visitor.customer.name)}`}><UserRoundCheck size={16} /> {visitor.customer.name || visitor.customer.phone}</Link> : "Не зарегистрирован"}</td></tr>)}</tbody></table></div> : null}
      {pagination && pagination.pages > 1 ? <div className="admin-row-actions"><button className="button button-secondary" disabled={!pagination.has_previous} onClick={() => setPage((value) => Math.max(1, value - 1))} type="button"><ChevronLeft size={17} /> Назад</button><span>Страница {pagination.page} из {pagination.pages}</span><button className="button button-secondary" disabled={!pagination.has_next} onClick={() => setPage((value) => value + 1)} type="button">Далее <ChevronRight size={17} /></button></div> : null}
    </section>
  </>;
}
