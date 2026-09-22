import { Asterisk, ArrowRight, CalendarCheck, CheckCircle2, MapPin, PartyPopper, Search, Sparkles } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { CharacterCard } from "@/components/catalog/character-card";
import { InstagramIcon } from "@/components/icons/instagram-icon";
import { ShowCard } from "@/components/catalog/show-card";
import { Reveal } from "@/components/motion/reveal";
import { getCatalogCards, getCharacters, getShows } from "@/lib/catalog";
import { site } from "@/lib/site";

const popularSlugs = [
  "labubu",
  "spider-man",
  "alice-mad-hatter",
  "stitch-angel",
];

export default function HomePage() {
  const shows = getCatalogCards(getShows()).slice(0, 3);
  const allCharacters = getCharacters();
  const popular = popularSlugs
    .map((slug) => allCharacters.find((item) => item.slug === slug))
    .filter((item) => item !== undefined);
  const characters = getCatalogCards(popular.length >= 4 ? popular : allCharacters.slice(0, 4));
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: site.name,
    url: site.canonicalUrl,
    logo: `${site.canonicalUrl}/brand/logo.png`,
    image: `${site.canonicalUrl}/wp-content/uploads/2025/10/IMG_6723.webp`,
    telephone: "+998998926565",
    areaServed: { "@type": "City", name: "Ташкент" },
    address: { "@type": "PostalAddress", addressLocality: "Ташкент", addressCountry: "UZ" },
    sameAs: [site.instagram, site.telegram],
    priceRange: "1 000 000–2 000 000 UZS",
  };

  return (
    <>
      <script
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
        type="application/ld+json"
      />
      <section className="home-hero">
        <div className="container home-hero-grid">
          <div className="home-hero-copy">
            <p className="eyebrow">ДЕТСКИЕ ПРАЗДНИКИ В ТАШКЕНТЕ</p>
            <h1>Праздник, который ребёнок <strong>запомнит</strong></h1>
            <p className="lead">
              Настоящие герои, готовые шоу-программы и команда, которая берёт
              заботы на себя. Выберите формат — мы соберём остальное.
            </p>
            <div className="hero-actions">
              <Link className="button button-primary" href="/party-builder">
                <CalendarCheck size={19} /> Проверить дату <ArrowRight size={18} />
              </Link>
              <Link className="text-link" href="/show-programs">Смотреть программы</Link>
            </div>
          </div>
          <div className="home-hero-media">
            <Image
              className="home-hero-photo"
              src="/wp-content/uploads/2025/10/IMG_6723.webp"
              alt="Аниматоры Surpriz в костюмах Лабубу"
              fill
              priority
              sizes="(max-width: 900px) 100vw, 50vw"
            />
            <div className="home-hero-accent">
              <Image
                src="/wp-content/uploads/2025/10/IMG_4965.webp"
                alt="Алиса и Шляпник"
                fill
                sizes="180px"
              />
            </div>
            <Sparkles aria-hidden="true" className="hero-spark one" />
            <Asterisk aria-hidden="true" className="hero-spark two" />
          </div>
        </div>
      </section>

      <section className="home-trust" aria-label="Ключевые преимущества">
        <div className="container home-trust-grid">
          <div><strong>150+ персонажей</strong><span>с настоящими фотографиями</span></div>
          <div><strong>Готовые шоу</strong><span>понятный состав и цена</span></div>
          <div><strong>Только Ташкент</strong><span>работаем в доступной зоне</span></div>
          <div><strong>Оплата после</strong><span>наличными или переводом</span></div>
        </div>
      </section>

      <section className="section home-choice-section">
        <div className="container">
          <Reveal className="section-heading">
            <div><p className="eyebrow">КАК ХОТИТЕ НАЧАТЬ?</p><h2>Выберите свой праздник</h2></div>
            <p>Можно взять готовое шоу, найти любимого героя или собрать собственный вариант по шагам.</p>
          </Reveal>
          <div className="home-choice-grid">
            <Reveal>
              <Link className="home-choice" href="/show-programs">
                <div><PartyPopper size={26} /><h3>Готовое шоу</h3><p>Программа, реквизит, артисты и понятная длительность.</p></div>
                <ArrowRight />
              </Link>
            </Reveal>
            <Reveal delay={0.08}>
              <Link className="home-choice is-violet" href="/catalog">
                <div><Search size={26} /><h3>Любимый персонаж</h3><p>Найдите героя по возрасту, теме или имени.</p></div>
                <ArrowRight />
              </Link>
            </Reveal>
            <Reveal delay={0.16}>
              <Link className="home-choice is-peach" href="/party-builder">
                <div><Sparkles size={26} /><h3>Собрать самому</h3><p>Выберите программу, персонажей, дату и адрес.</p></div>
                <ArrowRight />
              </Link>
            </Reveal>
          </div>
        </div>
      </section>

      <section className="section section-soft home-shows-section">
        <div className="container">
          <Reveal className="section-heading">
            <div><p className="eyebrow">ГОТОВЫЙ СЦЕНАРИЙ</p><h2>Шоу-программы</h2></div>
            <Link className="text-link" href="/show-programs">Все программы</Link>
          </Reveal>
          <div className="show-grid">
            {shows.map((show, index) => (
              <Reveal delay={index * 0.07} key={show.id}>
                <ShowCard featured={index === 0} show={show} />
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="section home-characters-section">
        <div className="container">
          <Reveal className="section-heading">
            <div><p className="eyebrow">НАСТОЯЩИЕ КОСТЮМЫ</p><h2>Популярные персонажи</h2></div>
            <Link className="text-link" href="/catalog">Открыть весь каталог</Link>
          </Reveal>
          <div className="entity-grid">
            {characters.map((character, index) => (
              <Reveal delay={index * 0.06} key={character.id}>
                <CharacterCard character={character} />
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="section process-section">
        <div className="container process-grid">
          <Reveal className="process-intro">
            <p className="eyebrow">БЕЗ ЛИШНЕЙ ПЕРЕПИСКИ</p>
            <h2>Три шага до готового праздника</h2>
            <p>Сначала проверяем доступность. Контакты и регистрация понадобятся только перед подтверждением.</p>
            <Link className="button button-primary" href="/party-builder">Начать сборку <ArrowRight size={18} /></Link>
          </Reveal>
          <div className="process-steps">
            <Reveal><article><span>01</span><CalendarCheck /><h3>Дата и время</h3><p>Покажем доступные варианты с учётом уже созданных заказов.</p></article></Reveal>
            <Reveal delay={0.08}><article><span>02</span><Sparkles /><h3>Шоу и герои</h3><p>Сразу увидите длительность, состав и итоговую стоимость.</p></article></Reveal>
            <Reveal delay={0.16}><article><span>03</span><MapPin /><h3>Адрес в Ташкенте</h3><p>Проверим точку на карте и сохраним детали для команды.</p></article></Reveal>
          </div>
        </div>
      </section>

      <section className="section social-section">
        <div className="container social-grid">
          <Reveal className="social-copy">
            <InstagramIcon height={32} width={32} />
            <p className="eyebrow">ЖИВЫЕ ПРАЗДНИКИ</p>
            <h2>Смотрите нас в Instagram</h2>
            <p>Новые костюмы, фрагменты программ и настоящие эмоции с мероприятий.</p>
            <a className="button button-secondary" href={site.instagram}>@animator.surpriz <ArrowRight size={18} /></a>
          </Reveal>
          <div className="social-photos">
            <div><Image src="/wp-content/uploads/2025/10/IMG_5108-scaled.webp" alt="Спайдермен Surpriz" fill sizes="30vw" /></div>
            <div><Image src="/wp-content/uploads/2025/10/IMG_4965.webp" alt="Алиса и Шляпник Surpriz" fill sizes="30vw" /></div>
          </div>
        </div>
      </section>

      <section className="section final-cta">
        <div className="container final-cta-inner">
          <div><CheckCircle2 size={34} /><p className="eyebrow">МОЖНО НАЧАТЬ БЕЗ РЕГИСТРАЦИИ</p><h2>Проверим вашу дату?</h2></div>
          <Link className="button" href="/party-builder">Собрать праздник <ArrowRight size={19} /></Link>
        </div>
      </section>
    </>
  );
}
