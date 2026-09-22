import type { Metadata } from "next";

import { AccountDashboard } from "@/features/account/account-dashboard";

export const metadata: Metadata = { title: "Личный кабинет" };

export default function AccountPage() {
  return <section className="page-section account-page"><div className="container"><div className="page-hero compact"><p className="eyebrow">ЛИЧНЫЙ КАБИНЕТ</p><h1>Ваши праздники</h1></div><AccountDashboard /></div></section>;
}
