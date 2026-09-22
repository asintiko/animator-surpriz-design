"use client";

import { Search, SlidersHorizontal, X } from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";

import { CharacterCard } from "@/components/catalog/character-card";
import type { CatalogCard, TaxonomyItem } from "@/lib/types";

const PAGE_SIZE = 12;

export function CatalogExplorer({
  items,
  categories,
}: {
  items: CatalogCard[];
  categories: TaxonomyItem[];
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const deferredQuery = useDeferredValue(query.trim().toLocaleLowerCase("ru"));

  const filtered = useMemo(
    () =>
      items.filter((item) => {
        const matchesCategory = category === "all" || item.categories.includes(category);
        const haystack = `${item.name} ${item.short_description} ${item.tags.join(" ")}`.toLocaleLowerCase("ru");
        return matchesCategory && (!deferredQuery || haystack.includes(deferredQuery));
      }),
    [category, deferredQuery, items],
  );

  const visible = filtered.slice(0, visibleCount);

  return (
    <div>
      <div className="catalog-toolbar">
        <label className="catalog-search">
          <Search size={20} aria-hidden="true" />
          <span className="sr-only">Найти персонажа</span>
          <input
            onChange={(event) => {
              setQuery(event.target.value);
              setVisibleCount(PAGE_SIZE);
            }}
            placeholder="Например, Лабубу или Спайдермен"
            value={query}
          />
          {query ? (
            <button aria-label="Очистить поиск" onClick={() => setQuery("")} type="button">
              <X size={18} />
            </button>
          ) : null}
        </label>
        <div className="catalog-count" aria-live="polite">
          <SlidersHorizontal size={17} />
          Найдено: {filtered.length}
        </div>
      </div>
      <div className="category-scroll">
        <div className="category-row" aria-label="Категории персонажей">
          {categories
            .filter((item) => item.slug === "all" || !item.is_system)
            .map((item) => (
              <button
                className={category === item.slug ? "is-active" : undefined}
                key={item.id}
                onClick={() => {
                  setCategory(item.slug);
                  setVisibleCount(PAGE_SIZE);
                }}
                type="button"
              >
                {item.name}
              </button>
            ))}
        </div>
      </div>
      {visible.length ? (
        <div className="entity-grid">
          {visible.map((character) => (
            <CharacterCard character={character} key={character.id} />
          ))}
        </div>
      ) : (
        <div className="catalog-empty">
          <h2>Ничего не найдено</h2>
          <p>Попробуйте другое имя или вернитесь ко всем категориям.</p>
          <button
            className="button button-secondary"
            onClick={() => {
              setQuery("");
              setCategory("all");
            }}
            type="button"
          >
            Сбросить фильтры
          </button>
        </div>
      )}
      {visibleCount < filtered.length ? (
        <div className="load-more">
          <button className="button button-secondary" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)} type="button">
            Показать ещё
          </button>
        </div>
      ) : null}
    </div>
  );
}
