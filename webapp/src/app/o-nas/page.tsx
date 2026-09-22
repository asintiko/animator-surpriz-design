import { CalendarHeart, MapPinned, Sparkles, UsersRound } from "lucide-react";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = { title: "О нас", description: "Команда Surpriz и подход к детским праздникам." };

export default function AboutPage() {
  return (
    <>
      <section className="detail-hero about-hero"><div className="container detail-grid"><div className="detail-copy"><p className="eyebrow">С 2017 ГОДА</p><h1>Команда, которая любит праздник не меньше детей</h1><p className="lead">Мы создаём события в Ташкенте, подбираем героев под возраст и внимательно относимся к каждой детали — от костюма до адреса.</p><Link className="button button-primary" href="/party-builder">Проверить дату</Link></div><div className="detail-media landscape"><Image src="/wp-content/uploads/2025/10/IMG_4965.webp" alt="Команда Surpriz" fill priority sizes="50vw" /></div></div></section>
      <section className="section section-soft"><div className="container values-grid"><article><CalendarHeart /><strong>С 2017 года</strong><p>Опыт камерных дней рождения и крупных событий.</p></article><article><UsersRound /><strong>150+ образов</strong><p>Сохраняем реальные фотографии каждого костюма.</p></article><article><Sparkles /><strong>Готовые шоу</strong><p>Понятная длительность, состав и итоговая стоимость.</p></article><article><MapPinned /><strong>Ташкент</strong><p>Работаем внутри установленной зоны на карте.</p></article></div></section>
    </>
  );
}
