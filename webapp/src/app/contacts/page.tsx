import { Clock3, MapPin, Phone, Send } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { InstagramIcon } from "@/components/icons/instagram-icon";
import { site } from "@/lib/site";

export const metadata: Metadata = { title: "Контакты", description: "Телефон, Telegram и Instagram команды Surpriz." };

export default function ContactsPage() {
  return (
    <section className="page-section contacts-page"><div className="container"><div className="page-hero compact"><p className="eyebrow">МЫ НА СВЯЗИ</p><h1>Контакты</h1><p className="lead">Для срочного заказа на сегодня лучше позвонить. Обычный заказ можно собрать на сайте без регистрации.</p></div><div className="contact-grid"><div className="contact-main"><a href={site.phoneHref}><Phone /><span>Телефон<strong>{site.phoneDisplay}</strong></span></a><a href={site.telegram}><Send /><span>Telegram<strong>Написать менеджеру</strong></span></a><a href={site.instagram}><InstagramIcon /><span>Instagram<strong>@animator.surpriz</strong></span></a></div><aside><div><MapPin /><h2>География</h2><p>Ташкент, внутри доступной зоны на карте конструктора.</p></div><div><Clock3 /><h2>Срочные заказы</h2><p>На сегодня или ночное время — только после звонка менеджеру.</p></div><Link className="button button-primary" href="/party-builder">Проверить дату</Link></aside></div></div></section>
  );
}
