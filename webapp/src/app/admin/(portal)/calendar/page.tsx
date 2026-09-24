import { AdminCalendarSection } from "@/features/admin/admin-calendar-section";

export default async function AdminCalendarPage({
  searchParams,
}: {
  searchParams: Promise<{ google?: string; message?: string }>;
}) {
  const { google = "", message = "" } = await searchParams;
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">РАСПИСАНИЕ</p><h1>Google Календарь</h1><p>Записи из календаря закрывают время на сайте, подтверждённые заказы появляются в календаре сами.</p></div></header><AdminCalendarSection oauthMessage={message} oauthResult={google} /></section>;
}
