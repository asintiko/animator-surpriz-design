"use client";

import { Check, ExternalLink, Palette } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

import { useSectionMutation } from "@/features/admin/admin-section-kit";
import type { SeasonId } from "@/lib/types";

type SeasonChoice = SeasonId | "none";

type SeasonCharacter = {
  id: number;
  name: string;
  slug: string;
  status: string;
  entity_type: "character" | "show_program";
  season_only: boolean;
};

export type SeasonAdminState = {
  active: SeasonChoice;
  effects: boolean;
  options: Array<{ id: SeasonChoice; label: string; emoji: string }>;
  characters: Record<SeasonId, SeasonCharacter[]>;
};

/** Legacy flags the season switch writes itself (see SEASON_OWNED_FLAGS in the adapter). */
export const SEASON_OWNED_FLAGS = new Set([
  "new_year_season_enabled",
  "show_new_year_menu_link",
  "show_home_new_year_showcase",
  "show_snow",
]);

const SEASON_DETAILS: Record<SeasonChoice, { caption: string; preview?: string }> = {
  none: { caption: "Базовое оформление круглый год.", preview: "/surpriz/основа.webp" },
  halloween: {
    caption: "Тыквенная ночь: баннеры, логотип, цвета, анимации.",
    preview: "/surpriz/assets/seasons/halloween/home-desktop.webp",
  },
  new_year: { caption: "Новогодняя палитра и сезонные герои. Баннеры добавим к зиме." },
};

function statusLabel(character: SeasonCharacter) {
  if (character.status !== "active") return "не опубликован";
  return character.season_only ? "только в сезон" : "круглый год";
}

export function AdminSeasonCard({ state, onChanged }: { state: SeasonAdminState; onChanged: () => Promise<void> }) {
  const mutation = useSectionMutation("settings", onChanged);
  const [selected, setSelected] = useState<SeasonChoice>(state.active);
  const [effects, setEffects] = useState(state.effects);
  const dirty = selected !== state.active || (selected !== "none" && effects !== state.effects);
  const heroes = selected === "none" ? [] : state.characters[selected] ?? [];
  const activeOption = state.options.find((option) => option.id === state.active);

  function apply() {
    const label = state.options.find((option) => option.id === selected)?.label ?? "";
    void mutation.run(
      "season",
      { action: "season", season: selected, effects },
      selected === "none" ? "Сезон выключен" : `Сезон «${label}» включён`,
    );
  }

  return (
    <section className="admin-surface admin-surface-wide admin-season-card" aria-labelledby="admin-season-title">
      <div className="admin-surface-head">
        <div>
          <p className="eyebrow">СЕЗОН САЙТА</p>
          <h2 id="admin-season-title">Оформление витрины</h2>
          <p>Сезон перекрашивает весь сайт: баннеры, логотип, цвета, сезонных героев и анимации. Применяется сразу, без пересборки.</p>
        </div>
        <span className={`admin-season-status${state.active === "none" ? "" : " is-on"}`}>
          {activeOption?.emoji} Сейчас: {activeOption?.label ?? "Обычный"}
        </span>
      </div>

      <div className="admin-season-options" role="radiogroup" aria-label="Сезон сайта">
        {state.options.map((option) => {
          const details = SEASON_DETAILS[option.id];
          const checked = selected === option.id;
          return (
            <button
              aria-checked={checked}
              className={`admin-season-option season-${option.id}`}
              key={option.id}
              onClick={() => setSelected(option.id)}
              role="radio"
              type="button"
            >
              <span className="admin-season-preview">
                {details.preview ? (
                  <Image alt="" fill sizes="(max-width: 900px) 100vw, 320px" src={details.preview} unoptimized />
                ) : (
                  <span aria-hidden="true">{option.emoji}</span>
                )}
                {state.active === option.id ? <em>На сайте</em> : null}
              </span>
              <span className="admin-season-option-text">
                <strong>{option.emoji} {option.label}</strong>
                <small>{details.caption}</small>
              </span>
              <i aria-hidden="true">{checked ? <Check size={15} /> : null}</i>
            </button>
          );
        })}
      </div>

      <div className="admin-season-body">
        <div className="admin-season-heroes">
          <h3>Сезонные герои</h3>
          {selected === "none" ? (
            <p>В обычном режиме все герои идут в своём порядке, герои «только в сезон» скрыты.</p>
          ) : heroes.length ? (
            <ul>
              {heroes.map((hero) => (
                <li key={hero.id}>
                  <Link href={hero.entity_type === "character" ? `/admin/catalog/characters/${hero.id}` : `/admin/show-programs/${hero.id}`}>{hero.name}</Link>
                  <span className={hero.season_only ? "is-only" : ""}>{statusLabel(hero)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p>Пока никого. Отметьте сезон в карточке персонажа, блок «Сезон».</p>
          )}
        </div>
        <label className={`admin-toggle${selected === "none" ? " is-disabled" : ""}`}>
          <span>
            <strong>Анимации сезона</strong>
            <small>Паучок над баннером и мерцающая тыква в подвале. Для посетителей с «уменьшением движения» отключены всегда.</small>
          </span>
          <input checked={effects} disabled={selected === "none"} onChange={(event) => setEffects(event.target.checked)} type="checkbox" />
          <i />
        </label>
      </div>

      <div className="admin-season-actions">
        <button className="button button-violet" disabled={!dirty || mutation.pendingKey === "season"} onClick={apply} type="button">
          <Palette size={17} /> {mutation.pendingKey === "season" ? "Применяем…" : "Применить"}
        </button>
        <a className="button button-secondary" href="/" rel="noopener" target="_blank">
          <ExternalLink size={17} /> Открыть сайт
        </a>
      </div>
    </section>
  );
}
