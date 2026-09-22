"use client";

import { ArrowRight, CalendarClock, LogIn, PackageOpen, PartyPopper } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

type Order = {
  public_id: string;
  status: string;
  status_label?: string;
  celebration_date: string;
  time_from: string;
  program_name?: string;
  total_amount: number;
};

type AccountPayload = {
  authenticated: boolean;
  customer?: { full_name: string; phone_display: string };
  orders: Order[];
};

export function AccountDashboard() {
  const [payload, setPayload] = useState<AccountPayload | null>(null);

  useEffect(() => {
    fetch("/api/account", { cache: "no-store", credentials: "same-origin" })
      .then((response) => response.json())
      .then((result: AccountPayload) => setPayload(result))
      .catch(() => setPayload({ authenticated: false, orders: [] }));
  }, []);

  if (!payload) return <div className="account-skeleton" aria-label="Загружаем кабинет" />;

  if (!payload.authenticated) {
    return (
      <div className="account-empty">
        <LogIn />
        <h2>Войдите по номеру телефона</h2>
        <p>Заказы и их статусы доступны после подтверждения кода в Telegram.</p>
        <Link className="button button-primary" href="/login?next=/account">Войти <ArrowRight /></Link>
      </div>
    );
  }

  return (
    <div className="account-layout">
      <aside className="account-profile"><div><span>{payload.customer?.full_name?.slice(0, 1) || "S"}</span><h2>{payload.customer?.full_name || "Клиент Surpriz"}</h2><p>{payload.customer?.phone_display}</p></div><Link className="button button-primary" href="/party-builder">Собрать ещё праздник</Link></aside>
      <section>
        <div className="section-heading"><div><p className="eyebrow">ИСТОРИЯ</p><h2>Ваши заказы</h2></div></div>
        {payload.orders.length ? <div className="account-orders">{payload.orders.map((order) => <Link href={`/account/orders/${order.public_id}`} key={order.public_id}><div><PartyPopper /><span><strong>{order.program_name || "Праздник Surpriz"}</strong><small>{order.public_id}</small></span></div><div><CalendarClock /><span><strong>{order.celebration_date}</strong><small>{order.time_from}</small></span></div><span className={`order-status status-${order.status}`}>{order.status_label || order.status}</span><strong>{new Intl.NumberFormat("ru-RU").format(order.total_amount)} сум</strong><ArrowRight /></Link>)}</div> : <div className="account-empty"><PackageOpen /><h2>Заказов пока нет</h2><p>Соберите первый праздник — он появится здесь.</p><Link className="button button-primary" href="/party-builder">Начать</Link></div>}
      </section>
    </div>
  );
}
