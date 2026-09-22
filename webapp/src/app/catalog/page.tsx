import type { Metadata } from "next";

import { CatalogExplorer } from "@/components/catalog/catalog-explorer";
import { getCatalogCards, getCatalogSnapshot, getCharacters } from "@/lib/catalog";

export const metadata: Metadata = {
  title: "Каталог персонажей",
  description: "Все доступные персонажи Surpriz для детских праздников в Ташкенте.",
};

export default function CatalogPage() {
  const snapshot = getCatalogSnapshot();
  const cards = getCatalogCards(getCharacters());

  return (
    <section className="page-section catalog-page">
      <div className="container">
        <div className="page-hero compact">
          <p className="eyebrow">56 АКТИВНЫХ КАРТОЧЕК · КОЛЛЕКЦИЯ ПОПОЛНЯЕТСЯ</p>
          <h1>Каталог персонажей</h1>
          <p className="lead">Выберите настоящего героя по фотографии, категории или имени. Все показанные персонажи доступны для заказа.</p>
        </div>
        <CatalogExplorer categories={snapshot.categories} items={cards} />
      </div>
    </section>
  );
}
