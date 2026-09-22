import { AdminOrdersSection } from "@/features/admin/admin-orders-section";

export default async function AdminOrdersPage({
  searchParams,
}: {
  searchParams: Promise<{ customer_id?: string; search?: string }>;
}) {
  const { customer_id: customerId = "", search = "" } = await searchParams;
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">ОПЕРАЦИОННЫЙ ЦЕНТР</p><h1>Заказы</h1><p>Все заявки, статусы и связь с клиентами в одном потоке.</p></div><a className="button button-secondary" href="/party-builder/?preview=availability" rel="noreferrer" target="_blank">Открыть демо занятости</a></header><AdminOrdersSection initialCustomerId={customerId} initialSearch={search} /></section>;
}
