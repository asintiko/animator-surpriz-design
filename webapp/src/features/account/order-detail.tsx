"use client";

import { CalendarClock, MapPin, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

type OrderPayload = {
  success: boolean;
  order?: Record<string, string | number | string[] | null>;
  message?: string;
};

export function OrderDetail({ publicId }: { publicId: string }) {
  const [payload, setPayload] = useState<OrderPayload | null>(null);
  useEffect(() => {
    fetch(`/api/account/orders/${encodeURIComponent(publicId)}`, { cache: "no-store" })
      .then((response) => response.json())
      .then((result: OrderPayload) => setPayload(result))
      .catch(() => setPayload({ success: false, message: "Не удалось загрузить заказ." }));
  }, [publicId]);

  if (!payload) return <div className="account-skeleton" />;
  if (!payload.success || !payload.order) return <div className="account-empty"><h2>{payload.message || "Заказ не найден"}</h2></div>;
  const order = payload.order;
  return <div className="order-detail"><div className="order-detail-head"><div><p className="eyebrow">ЗАКАЗ</p><h1>{publicId}</h1></div><span className={`order-status status-${order.status}`}>{String(order.status_label || order.status)}</span></div><div className="order-detail-grid"><article><CalendarClock /><h2>Дата и время</h2><p>{String(order.celebration_date)} · {String(order.time_from)}–{String(order.time_to)}</p></article><article><MapPin /><h2>Адрес</h2><p>{String(order.map_label || order.address_text)}</p></article><article><ShieldCheck /><h2>Расчёт</h2><p>После мероприятия · {new Intl.NumberFormat("ru-RU").format(Number(order.total_amount || 0))} сум</p></article></div></div>;
}
