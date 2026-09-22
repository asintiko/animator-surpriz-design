import { ArrowLeft, CalendarCheck, Clock3, Images, Phone, Sparkles } from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { entityCropStyle, formatDuration, getCharacter, getCharacters } from "@/lib/catalog";
import { site } from "@/lib/site";

export function generateStaticParams() {
  return getCharacters().map((character) => ({ slug: character.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const character = getCharacter(slug);
  if (!character) return {};
  return {
    title: character.seo_title || character.name,
    description: character.seo_description || character.short_description,
  };
}

export default async function CharacterDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const character = getCharacter(slug);
  if (!character) notFound();

  const hero = character.hero_file_path || "/brand/logo.png";
  const gallery = character.media.filter((item) => item.media_type === "image");

  return (
    <>
      <section className="detail-hero">
        <div className="container">
          <Link className="back-link" href="/catalog"><ArrowLeft size={18} /> Все персонажи</Link>
          <div className="detail-grid">
            <div className="detail-media">
              <Image
                src={hero}
                alt={character.name}
                fill
                priority
                sizes="(max-width: 900px) 100vw, 52vw"
                style={entityCropStyle(character)}
              />
            </div>
            <div className="detail-copy">
              <p className="eyebrow">ПЕРСОНАЖ SURPRIZ</p>
              <h1>{character.name}</h1>
              <p className="lead">{character.short_description}</p>
              <div className="detail-facts">
                <span><Clock3 /> {formatDuration(character.default_duration_minutes)}</span>
                <span><Sparkles /> Настоящий костюм</span>
                <span><Images /> Фото именно этого образа</span>
              </div>
              <div className="hero-actions">
                <Link className="button button-primary" href={`/party-builder?characters=${character.slug}`}>
                  <CalendarCheck size={19} /> Проверить дату
                </Link>
                <a className="button button-secondary" href={site.phoneHref}><Phone size={18} /> Позвонить</a>
              </div>
              <p className="payment-note">Оплата наличными или переводом после праздника.</p>
            </div>
          </div>
        </div>
      </section>
      <section className="section">
        <div className="container editorial-grid">
          <div><p className="eyebrow">ОБРАЗ И ПРОГРАММА</p><h2>Что ждёт детей</h2></div>
          <div className="rich-copy"><p>{character.description || character.short_description}</p><p>Точный сценарий и состав команды менеджер подтвердит после проверки даты и места проведения.</p></div>
        </div>
      </section>
      {gallery.length > 1 ? (
        <section className="section section-soft">
          <div className="container">
            <div className="section-heading"><div><p className="eyebrow">ГАЛЕРЕЯ</p><h2>Фотографии костюма</h2></div></div>
            <div className="gallery-grid">
              {gallery.slice(0, 6).map((media) => (
                <div key={media.id}><Image src={media.file_path} alt={media.alt_text || character.name} fill sizes="33vw" /></div>
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </>
  );
}
