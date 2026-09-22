import { Phone, Send } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { InstagramIcon } from "@/components/icons/instagram-icon";
import { site } from "@/lib/site";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container footer-grid">
        <div className="footer-brand">
          <Image src="/brand/logo.png" alt="Surpriz" width={92} height={92} />
          <p>Детские праздники, настоящие персонажи и шоу-программы в Ташкенте.</p>
        </div>
        <div>
          <h2>Выбрать</h2>
          <Link href="/show-programs">Шоу-программы</Link>
          <Link href="/catalog">Персонажи</Link>
          <Link href="/prices">Цены</Link>
          <Link href="/party-builder">Собрать праздник</Link>
        </div>
        <div>
          <h2>Surpriz</h2>
          <Link href="/o-nas">О нас</Link>
          <Link href="/contacts">Контакты</Link>
          <Link href="/account">Личный кабинет</Link>
          <Link href="/admin">Админка</Link>
        </div>
        <div>
          <h2>Связаться</h2>
          <a href={site.phoneHref}><Phone size={18} /> {site.phoneDisplay}</a>
          <a href={site.telegram}><Send size={18} /> Telegram</a>
          <a href={site.instagram}><InstagramIcon height={18} width={18} /> Instagram</a>
        </div>
      </div>
      <div className="container footer-bottom">
        <span>© 2026 Surpriz</span>
        <span>Ташкент · Оплата после мероприятия</span>
      </div>
    </footer>
  );
}
