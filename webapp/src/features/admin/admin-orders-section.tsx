"use client";

import { BellRing, CalendarCheck2, MapPin, Phone, RefreshCw, Search, Send } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  AdminSectionState,
  formatMoney,
  useAdminSection,
  useSectionMutation,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";
import type { PartyOrderAddon } from "@/lib/types";

type Order = {
  id: number;
  public_id: string;
  status: string;
  status_label?: string;
  confirmation_state?: "unconfirmed" | "confirmed";
  display_status?: "unconfirmed" | "confirmed" | "cancelled";
  confirmation_label?: string;
  customer_name?: string;
  customer_phone?: string;
  celebrant_name?: string;
  celebrant_age?: number | null;
  children_count?: number | null;
  program_name?: string;
  character_names?: string[];
  addons?: PartyOrderAddon[];
  addon_total?: number;
  addon_total_label?: string;
  celebration_date: string;
  celebration_date_label?: string;
  time_from: string;
  time_to: string;
  duration_minutes?: number;
  address_text?: string;
  location_label?: string;
  yandex_map_url?: string;
  payment_method_label?: string;
  notes?: string;
  total_price?: number;
  total_price_label?: string;
  created_at?: string;
  created_at_label?: string;
  calendar_event_link?: string;
};

type OrdersPayload = SectionEnvelope & {
  orders?: Order[];
  summary?: Record<string, number>;
  status_labels?: Record<string, string>;
};

const fallbackStatuses = {
  unconfirmed: "Не подтверждён",
  confirmed: "Подтверждён",
  cancelled: "Отменён",
};

const emptyFilters = { search: "", status: "", date_from: "", date_to: "" };

export function AdminOrdersSection({ initialCustomerId = "", initialSearch = "" }: { initialCustomerId?: string; initialSearch?: string }) {
  const [draft, setDraft] = useState(() => ({ ...emptyFilters, search: initialSearch }));
  const [filters, setFilters] = useState(() => ({ ...emptyFilters, search: initialSearch }));
  const [customerId, setCustomerId] = useState(initialCustomerId);
  const query = useMemo(() => {
    const value = new URLSearchParams();
    Object.entries(filters).forEach(([key, item]) => item && value.set(key, item));
    if (customerId) value.set("customer_id", customerId);
    return value;
  }, [customerId, filters]);
  const section = useAdminSection<OrdersPayload>("orders", query);
  const refresh = section.refresh;
  const mutation = useSectionMutation("orders", refresh);
  const statuses: Record<string, string> = section.data?.status_labels ?? fallbackStatuses;
  const orders = section.data?.orders ?? [];
  const summary = section.data?.summary ?? {};

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && !mutation.pendingKey) void refresh();
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [mutation.pendingKey, refresh]);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setFilters(draft);
  }

  return (
    <>
      <div className="admin-metrics admin-metrics-compact">
        <article><span>Всего</span><strong>{summary.total ?? orders.length}</strong></article>
        {Object.entries(statuses).map(([key, label]) => (
          <article key={key}><span>{label}</span><strong>{summary[key] ?? 0}</strong></article>
        ))}
      </div>

      <section className="admin-surface">
        <div className="admin-surface-head">
          <div><p className="eyebrow">ПОТОК ЗАКАЗОВ</p><h2>Заказы с сайта</h2><p>Статусы, контакты, адрес и повторная отправка в Telegram.</p></div>
          <button className="button button-secondary" onClick={() => void section.refresh()} type="button"><RefreshCw size={17} /> Обновить</button>
        </div>
        <form className="admin-filter-bar" onSubmit={applyFilters}>
          <label><span>Поиск</span><input placeholder="SRP-00012, телефон, имя" value={draft.search} onChange={(event) => setDraft((current) => ({ ...current, search: event.target.value }))} /></label>
          <label><span>Статус</span><select value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}><option value="">Все</option>{Object.entries(statuses).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
          <label><span>Дата с</span><input type="date" value={draft.date_from} onChange={(event) => setDraft((current) => ({ ...current, date_from: event.target.value }))} /></label>
          <label><span>Дата по</span><input type="date" value={draft.date_to} onChange={(event) => setDraft((current) => ({ ...current, date_to: event.target.value }))} /></label>
          <button className="button button-violet" type="submit"><Search size={17} /> Найти</button>
          {Object.values(filters).some(Boolean) || customerId ? <button className="button button-secondary" onClick={() => { setDraft(emptyFilters); setFilters(emptyFilters); setCustomerId(""); window.history.replaceState(null, "", "/admin/orders"); }} type="button">Сбросить{customerId ? ` клиента #${customerId}` : ""}</button> : null}
        </form>

        <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
        {!section.loading && !section.error && !orders.length ? <div className="admin-empty">Заказов по выбранному фильтру нет.</div> : null}
        {orders.length ? (
          <div className="admin-table-wrap">
            <table className="admin-data-table admin-orders-table">
              <thead><tr><th>Заказ</th><th>Клиент</th><th>Праздник</th><th>Адрес и расчёт</th><th>Связь</th><th>Статус</th></tr></thead>
              <tbody>
                {orders.map((order) => {
                  const cleanPhone = (order.customer_phone ?? "").replace(/[^+\d]/g, "");
                  const confirmationState = order.confirmation_state ?? "unconfirmed";
                  const displayStatus = order.display_status ?? (order.status === "cancelled" ? "cancelled" : confirmationState);
                  const confirmationLabel = order.status_label ?? order.confirmation_label ?? statuses[displayStatus] ?? displayStatus;
                  const confirmationLocked = order.status === "cancelled" || order.status === "done";
                  return (
                    <tr key={order.id || order.public_id}>
                      <td><strong>{order.public_id}</strong><small>{order.created_at_label || order.created_at || ""}</small><b>{order.total_price_label || formatMoney(order.total_price)}</b></td>
                      <td><strong>{order.customer_name || "Без имени"}</strong><small>{order.customer_phone || "—"}</small>{order.celebrant_name ? <small>Именинник: {order.celebrant_name}{order.celebrant_age ? `, ${order.celebrant_age} лет` : ""}</small> : null}{order.children_count != null ? <small>Гостей: {order.children_count}</small> : null}</td>
                      <td><strong>{order.program_name || "Без шоу-программы"}</strong><small>{order.celebration_date_label || order.celebration_date} · {order.time_from}–{order.time_to}{order.duration_minutes ? ` · ${order.duration_minutes} мин` : ""}</small>{order.character_names?.length ? <small>{order.character_names.join(", ")}</small> : null}{order.addons?.length ? <small>Доп. услуги: {order.addons.map((addon) => `${addon.name} (+${addon.price_label})`).join(", ")}</small> : null}</td>
                      <td><span>{order.address_text || "—"}</span>{order.location_label && order.location_label !== order.address_text ? <small>{order.location_label}</small> : null}<small>{order.payment_method_label || ""}</small>{order.notes ? <details><summary>Комментарий</summary><p>{order.notes}</p></details> : null}</td>
                      <td><div className="admin-row-actions">{cleanPhone ? <a aria-label="Позвонить" href={`tel:${cleanPhone}`}><Phone size={17} /></a> : null}{cleanPhone ? <a aria-label="Открыть Telegram" href={`https://t.me/+${cleanPhone.replace("+", "")}`} rel="noreferrer" target="_blank"><Send size={17} /></a> : null}{order.yandex_map_url ? <a aria-label="Открыть карту" href={order.yandex_map_url} rel="noreferrer" target="_blank"><MapPin size={17} /></a> : null}{order.calendar_event_link ? <a aria-label="Открыть в Google Календаре" href={order.calendar_event_link} rel="noreferrer" target="_blank" title="Заказ в Google Календаре"><CalendarCheck2 size={17} /></a> : null}<button aria-label="Повторить уведомление" disabled={mutation.pendingKey === `notify-${order.id}`} onClick={() => void mutation.run(`notify-${order.id}`, { action: "notify", order_id: order.id }, "Уведомление отправлено") } type="button"><BellRing size={17} /></button></div></td>
                      <td><div className="admin-status-control"><span className={`order-status status-${displayStatus}`}>{confirmationLabel}</span><select aria-label={`Статус ${order.public_id}`} disabled={confirmationLocked || mutation.pendingKey === `confirmation-${order.id}`} value={displayStatus} onChange={(event) => { const next = event.target.value; if (next !== "cancelled" || window.confirm(`Отменить заказ ${order.public_id}? Время и костюмы снова станут доступны.`)) void mutation.run(`confirmation-${order.id}`, { action: "update_status", order_id: order.id, status: next }, "Статус обновлён"); }}>{Object.entries(statuses).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select>{confirmationLocked ? <small>Заказ завершён или отменён</small> : null}</div></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </>
  );
}
