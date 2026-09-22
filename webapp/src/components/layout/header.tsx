import { CalendarCheck, Menu, Phone, UserRound } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { site } from "@/lib/site";

const links = [
  { href: "/show-programs", label: "Шоу" },
  { href: "/catalog", label: "Персонажи" },
  { href: "/o-nas", label: "О нас" },
  { href: "/contacts", label: "Контакты" },
];

export function Header() {
  return (
    <header className="site-header">
      <div className="container site-header-inner">
        <Link className="site-logo" href="/" aria-label="Surpriz — на главную">
          <Image src="/brand/logo.png" alt="Surpriz" width={66} height={66} priority />
        </Link>
        <nav className="site-nav" aria-label="Основная навигация">
          {links.map((link) => (
            <Link href={link.href} key={link.href}>
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="site-header-actions">
          <a className="site-phone" href={site.phoneHref}>
            {site.phoneDisplay}
          </a>
          <Link className="button button-primary header-cta" href="/party-builder">
            <CalendarCheck size={18} aria-hidden="true" />
            Проверить дату
          </Link>
          <details className="mobile-menu">
            <summary aria-label="Открыть меню">
              <Menu size={24} />
            </summary>
            <nav aria-label="Мобильная навигация">
              {links.map((link) => (
                <Link href={link.href} key={link.href}>
                  {link.label}
                </Link>
              ))}
              <Link href="/account">
                <UserRound size={18} /> Личный кабинет
              </Link>
              <a href={site.phoneHref}>
                <Phone size={18} /> {site.phoneDisplay}
              </a>
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}
