import { Check, Clock3, UsersRound } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { formatDuration, formatPrice, getShows } from "@/lib/catalog";

export const metadata: Metadata = { title: "Цены", description: "Цены и условия шоу-программ Surpriz." };

export default function PricesPage() {
  return (
    <section className="page-section">
      <div className="container">
        <div className="page-hero compact"><p className="eyebrow">ПРОЗРАЧНО ДО ЗАКАЗА</p><h1>Цены и программы</h1><p className="lead">Базовая цена, длительность и состав берутся из актуального каталога. Итог виден в конструкторе до регистрации.</p></div>
        <div className="price-list">
          {getShows().map((show) => (
            <article key={show.id}>
              <div><h2>{show.name}</h2><p>{show.short_description}</p></div>
              <div className="price-facts"><span><Clock3 /> {formatDuration(show.default_duration_minutes)}</span><span><UsersRound /> {show.included_characters_count} персонажа</span><span><Check /> Оплата после</span></div>
              <strong>{formatPrice(show.base_price)}</strong>
              <Link className="button button-secondary" href={`/party-builder?program=${show.slug}`}>Проверить дату</Link>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
