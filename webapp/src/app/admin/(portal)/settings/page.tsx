import { AdminSettingsSection } from "@/features/admin/admin-settings-section";

export default function AdminSettingsPage() {
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">УПРАВЛЕНИЕ САЙТОМ</p><h1>Настройки</h1><p>Функции витрины, сезонность и параметры конструктора.</p></div></header><AdminSettingsSection /></section>;
}
