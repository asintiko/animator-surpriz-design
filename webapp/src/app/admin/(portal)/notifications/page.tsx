import { AdminNotificationsSection } from "@/features/admin/admin-notifications-section";

export default function AdminNotificationsPage() {
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">СВЯЗЬ</p><h1>Уведомления</h1><p>Telegram-бот, получатели и тестирование доставки.</p></div></header><AdminNotificationsSection /></section>;
}
