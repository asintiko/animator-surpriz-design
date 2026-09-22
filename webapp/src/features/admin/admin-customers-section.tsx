"use client";

import { Ban, ExternalLink, Phone, Search, ShieldCheck, UsersRound } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import {
  AdminSectionState,
  formatMoney,
  useAdminSection,
  useSectionMutation,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";

type Customer = {
  id: number;
  phone: string;
  name?: string;
  order_count: number;
  total_spent: number;
  cancelled_count: number;
  last_order_at?: string;
  created_at?: string;
  is_blocked?: boolean;
  blocked_until?: string;
  block_reason?: string;
};

type CustomersPayload = SectionEnvelope & { customers?: Customer[] };

export function AdminCustomersSection() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const query = useMemo(() => {
    const value = new URLSearchParams();
    if (search) value.set("search", search);
    if (status) value.set("status", status);
    return value;
  }, [search, status]);
  const section = useAdminSection<CustomersPayload>("customers", query);
  const mutation = useSectionMutation("customers", section.refresh);
  const customers = section.data?.customers ?? [];
  const blocked = customers.filter((customer) => customer.is_blocked).length;
  const revenue = customers.reduce((sum, customer) => sum + Number(customer.total_spent || 0), 0);

  return (
    <>
      <div className="admin-metrics admin-metrics-compact">
        <article><span>Клиенты</span><strong>{customers.length}</strong></article>
        <article><span>Повторные</span><strong>{customers.filter((customer) => customer.order_count > 1).length}</strong></article>
        <article><span>Заблокированы</span><strong>{blocked}</strong></article>
        <article><span>Выручка</span><strong>{formatMoney(revenue)}</strong></article>
      </div>

      <section className="admin-surface">
        <div className="admin-surface-head">
          <div><p className="eyebrow">КЛИЕНТСКАЯ БАЗА</p><h2>Клиенты и история заказов</h2><p>Контакты, повторные обращения, выручка и ограничения.</p></div>
        </div>
        <div className="admin-filter-bar">
          <label><span>Поиск</span><span className="input-with-icon"><Search size={16} /><input placeholder="Имя или телефон" value={search} onChange={(event) => setSearch(event.target.value)} /></span></label>
          <label><span>Статус</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Все клиенты</option><option value="active">Активные</option><option value="blocked">Заблокированные</option><option value="repeat">Повторные</option></select></label>
        </div>

        <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
        {!section.loading && !section.error && !customers.length ? <div className="admin-empty"><UsersRound /> Клиенты появятся после первого заказа.</div> : null}
        {customers.length ? (
          <div className="admin-table-wrap">
            <table className="admin-data-table">
              <thead><tr><th>Клиент</th><th>Заказы</th><th>Расходы</th><th>Последняя активность</th><th>Статус</th><th>Действия</th></tr></thead>
              <tbody>{customers.map((customer) => {
                const cleanPhone = customer.phone.replace(/[^+\d]/g, "");
                return (
                  <tr key={customer.id}>
                    <td><strong>{customer.name || "Без имени"}</strong><small>{customer.phone || "—"}</small></td>
                    <td><strong>{customer.order_count}</strong><small>{customer.cancelled_count ? `Отменено: ${customer.cancelled_count}` : "Без отмен"}</small></td>
                    <td><b>{formatMoney(customer.total_spent)}</b></td>
                    <td><span>{customer.last_order_at || "Заказов ещё нет"}</span><small>{customer.created_at ? `С нами с ${customer.created_at}` : ""}</small></td>
                    <td>{customer.is_blocked ? <div><span className="content-status status-hidden"><Ban size={14} /> Заблокирован</span><small>{customer.blocked_until ? `До ${customer.blocked_until}` : "Без срока"}</small>{customer.block_reason ? <small>{customer.block_reason}</small> : null}</div> : <span className="content-status status-active"><ShieldCheck size={14} /> Активен</span>}</td>
                    <td><div className="admin-row-actions">{cleanPhone ? <a aria-label="Позвонить" href={`tel:${cleanPhone}`}><Phone size={17} /></a> : null}<Link aria-label="Заказы клиента" href={`/admin/orders?customer_id=${customer.id}`}><ExternalLink size={17} /></Link>{customer.is_blocked ? <button className="button button-secondary" disabled={mutation.pendingKey === `unblock-${customer.id}`} onClick={() => void mutation.run(`unblock-${customer.id}`, { action: "unblock", customer_id: customer.id }, "Клиент разблокирован")} type="button">Разблокировать</button> : null}</div></td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        ) : null}
      </section>
    </>
  );
}
