import type { Metadata } from "next";

import { ShowCard } from "@/components/catalog/show-card";
import { getCatalogCards, getShows } from "@/lib/catalog";

export const metadata: Metadata = {
  title: "Шоу-программы",
  description: "Готовые шоу-программы Surpriz с длительностью, составом и ценами.",
};

export default function ShowProgramsPage() {
  const shows = getCatalogCards(getShows());

  return (
    <section className="page-section">
      <div className="container">
        <div className="page-hero compact">
          <p className="eyebrow">ГОТОВЫЕ ПРОГРАММЫ</p>
          <h1>Шоу-программы</h1>
          <p className="lead">Сравните длительность, состав и цену. После выбора можно сразу проверить дату и добавить персонажей.</p>
        </div>
        <div className="show-grid show-list-grid">
          {shows.map((show, index) => <ShowCard featured={index === 0} key={show.id} show={show} />)}
        </div>
      </div>
    </section>
  );
}
