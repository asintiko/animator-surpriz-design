import { Home, PartyPopper, Search, Sparkles, UserRound } from "lucide-react";
import Link from "next/link";

const items = [
  { href: "/", label: "Главная", icon: Home },
  { href: "/show-programs", label: "Шоу", icon: PartyPopper },
  { href: "/party-builder", label: "Собрать", icon: Sparkles, primary: true },
  { href: "/catalog", label: "Персонажи", icon: Search },
  { href: "/account", label: "Профиль", icon: UserRound },
];

export function MobileNav() {
  return (
    <nav className="mobile-bottom-nav" aria-label="Быстрая навигация">
      {items.map(({ href, label, icon: Icon, primary }) => (
        <Link className={primary ? "is-primary" : undefined} href={href} key={href}>
          <Icon size={primary ? 24 : 21} aria-hidden="true" />
          <span>{label}</span>
        </Link>
      ))}
    </nav>
  );
}
