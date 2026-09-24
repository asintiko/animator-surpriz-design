import {
  BarChart3,
  BellRing,
  Boxes,
  CalendarDays,
  ExternalLink,
  Gift,
  Handshake,
  Images,
  LayoutDashboard,
  ListChecks,
  PartyPopper,
  Settings,
  Sparkles,
  Tags,
  UsersRound,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

import { AdminBuildStamp } from "@/components/admin/build-stamp";
import { AdminLogout } from "@/components/admin/admin-logout";

const navigation = [
  { href: "/admin", label: "Обзор", icon: LayoutDashboard },
  { href: "/admin/orders", label: "Заказы", icon: ListChecks },
  { href: "/admin/calendar", label: "Календарь", icon: CalendarDays },
  { href: "/admin/visitors", label: "Посетители", icon: UsersRound },
  { href: "/admin/catalog/characters", label: "Персонажи", icon: Boxes },
  { href: "/admin/show-programs", label: "Шоу-программы", icon: PartyPopper },
  { href: "/admin/media", label: "Медиатека", icon: Images },
  { href: "/admin/taxonomy", label: "Категории и теги", icon: Tags },
  { href: "/admin/addons", label: "Доп. услуги", icon: Gift },
  { href: "/admin/partners", label: "Партнёры", icon: Handshake },
  { href: "/admin/recommendations", label: "Рекомендации", icon: Sparkles },
  { href: "/admin/customers", label: "Клиенты", icon: UsersRound },
  { href: "/admin/analytics", label: "Аналитика", icon: BarChart3 },
  { href: "/admin/notifications", label: "Уведомления", icon: BellRing },
  { href: "/admin/settings", label: "Настройки", icon: Settings },
];

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <Link className="admin-brand" href="/admin">
          <Image src="/brand/logo.png" alt="" width={52} height={52} />
          <span><strong>Surpriz</strong><small>Панель управления</small></span>
        </Link>
        <nav aria-label="Разделы админки">
          {navigation.map(({ href, label, icon: Icon }) => (
            <Link href={href} key={href}><Icon size={19} /> {label}</Link>
          ))}
        </nav>
        <div className="admin-sidebar-foot"><Link className="admin-site-link" href="/">Открыть сайт <ExternalLink size={15} /></Link><AdminLogout /><AdminBuildStamp /></div>
      </aside>
      <div className="admin-content">{children}</div>
    </div>
  );
}
