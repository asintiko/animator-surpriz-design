import { ArrowLeft, CalendarCheck, Clock3, Gift, ShieldCheck, UsersRound } from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { entityCropStyle, formatDuration, formatPrice, getShow, getShows } from "@/lib/catalog";

export function generateStaticParams() {
  return getShows().map((show) => ({ slug: show.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const show = getShow(slug);
  if (!show) return {};
  return {
    title: show.seo_title || show.name,
    description: show.seo_description || show.short_description,
  };
}

export default async function ShowDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const show = getShow(slug);
  if (!show) notFound();

  return (
    <>
      <section className="detail-hero show-detail-hero">
        <div className="container">
          <Link className="back-link" href="/show-programs"><ArrowLeft size={18} /> Все шоу</Link>
          <div className="detail-grid">
            <div className="detail-media landscape">
              <Image
                src={show.hero_file_path || "/brand/logo.png"}
                alt={show.name}
                fill
                priority
                sizes="(max-width: 900px) 100vw, 52vw"
                style={entityCropStyle(show)}
              />
            </div>
            <div className="detail-copy">
              <p className="eyebrow">ГОТОВАЯ ШОУ-ПРОГРАММА</p>
              <h1>{show.variant_group_name || show.name}</h1>
              {show.variant_label ? <span className="variant-label">Вариант: {show.variant_label}</span> : null}
              <p className="lead">{show.short_description}</p>
              <div className="detail-facts">
                <span><Clock3 /> {formatDuration(show.default_duration_minutes)}</span>
                <span><UsersRound /> {show.included_characters_count} персонажа включено</span>
                <span><ShieldCheck /> Оплата после мероприятия</span>
              </div>
              <div className="show-price">{formatPrice(show.base_price)}</div>
              <Link className="button button-primary" href={`/party-builder?program=${show.slug}`}>
                <CalendarCheck size={19} /> Проверить дату
              </Link>
            </div>
          </div>
        </div>
      </section>
      <section className="section">
        <div className="container editorial-grid">
          <div><p className="eyebrow">СЦЕНАРИЙ</p><h2>Как проходит шоу</h2></div>
          <div className="rich-copy"><p>{show.description || show.short_description}</p>{show.included_items ? <p><strong>Что входит:</strong> {show.included_items}</p> : null}</div>
        </div>
      </section>
      <section className="section section-soft">
        <div className="container package-grid">
          <article><Clock3 /><h3>Длительность</h3><strong>{formatDuration(show.default_duration_minutes)}</strong><p>Время можно увеличить при сборке заказа.</p></article>
          <article><UsersRound /><h3>Команда</h3><strong>{show.included_characters_count} персонажа</strong><p>Третий и последующие персонажи — по {formatPrice(show.extra_character_price_3).replace("от ", "")}.</p></article>
          <article><Gift /><h3>Дополнения</h3><strong>{show.addons.length ? `${show.addons.length} варианта` : "По запросу"}</strong><p>Покажем доступные дополнения внутри конструктора.</p></article>
        </div>
      </section>
    </>
  );
}
