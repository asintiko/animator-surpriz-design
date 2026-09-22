import type { Metadata } from "next";
import { Suspense } from "react";

import { PartyBuilder } from "@/features/builder/party-builder";
import { getCatalogCards, getCharacters, getShows } from "@/lib/catalog";

export const metadata: Metadata = {
  title: "Собрать праздник",
  description: "Проверьте дату, выберите шоу и персонажей, укажите адрес и подтвердите заказ.",
};

export default function PartyBuilderPage() {
  return (
    <section className="builder-page">
      <div className="container">
        <div className="page-hero builder-page-hero">
          <p className="eyebrow">СОБЕРИТЕ ПРАЗДНИК</p>
          <h1>Сначала проверим дату — потом выберем всё остальное</h1>
          <p className="lead">Четыре понятных этапа. Контакты и регистрация — только перед подтверждением.</p>
        </div>
        <Suspense fallback={<div className="builder-panel">Загружаем конструктор…</div>}>
          <PartyBuilder characters={getCatalogCards(getCharacters())} shows={getCatalogCards(getShows())} />
        </Suspense>
      </div>
    </section>
  );
}
