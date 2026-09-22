import { AdminCustomersSection } from "@/features/admin/admin-customers-section";

export default function AdminCustomersPage() {
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">CRM</p><h1>Клиенты</h1><p>Контакты, повторные заказы и история отношений.</p></div></header><AdminCustomersSection /></section>;
}
