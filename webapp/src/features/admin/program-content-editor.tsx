"use client";

import { ArrowDown, ArrowUp, Info, Plus, Trash2, UsersRound } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import type { ProgramFeature } from "@/lib/types";

/** Same set and order as SHOW_FEATURE_ICONS in core/catalog_store.py. */
export const PROGRAM_FEATURE_ICONS = [
  { id: "note", label: "Музыка, диджей" },
  { id: "users", label: "Герои, ведущие" },
  { id: "sparkles", label: "Пузыри, эффекты" },
  { id: "confetti", label: "Ленты, серпантин" },
  { id: "star", label: "Свет, прожекторы" },
  { id: "wand", label: "Аквагрим, рисунки" },
  { id: "clock", label: "Время" },
  { id: "gift", label: "Подарок" },
  { id: "mask", label: "Маски, шары" },
  { id: "box", label: "Реквизит" },
  { id: "map-pin", label: "Место" },
  { id: "home", label: "Помещение" },
  { id: "calendar", label: "Дата" },
  { id: "cash", label: "Оплата" },
  { id: "info", label: "Важно" },
  { id: "party-hat", label: "Праздник" },
] as const;

const FEATURES_LIMIT = 20;
const FEATURE_TEXT_LIMIT = 160;
const CAST_LIMIT = 12;

function iconSrc(icon: string) {
  return `/v2/show-detail/icons/${icon}.webp`;
}

function iconLabel(icon: string) {
  return PROGRAM_FEATURE_ICONS.find((item) => item.id === icon)?.label ?? "Иконка";
}

function IconPicker({ value, onPick, onClose }: { value: string; onPick: (icon: string) => void; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.querySelector<HTMLButtonElement>("[aria-pressed='true']")?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    function onPointer(event: PointerEvent) {
      if (ref.current && !ref.current.parentElement?.contains(event.target as Node)) onClose();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [onClose]);

  return (
    <div className="program-icon-picker" ref={ref} role="group" aria-label="Выбор иконки">
      {PROGRAM_FEATURE_ICONS.map((icon) => (
        <button aria-pressed={icon.id === value} key={icon.id} onClick={() => onPick(icon.id)} type="button">
          <Image alt="" height={44} src={iconSrc(icon.id)} unoptimized width={44} />
          <span>{icon.label}</span>
        </button>
      ))}
    </div>
  );
}

export function ProgramFeaturesEditor({
  features,
  source,
  onChange,
}: {
  features: ProgramFeature[];
  source?: "stored" | "text";
  onChange: (next: ProgramFeature[]) => void;
}) {
  const [picking, setPicking] = useState<number | null>(null);

  function update(index: number, next: Partial<ProgramFeature>) {
    onChange(features.map((feature, itemIndex) => (itemIndex === index ? { ...feature, ...next } : feature)));
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= features.length) return;
    const next = [...features];
    const current = next[index];
    const other = next[target];
    if (!current || !other) return;
    next[index] = other;
    next[target] = current;
    onChange(next);
    setPicking(null);
  }

  function remove(index: number) {
    onChange(features.filter((_, itemIndex) => itemIndex !== index));
    setPicking(null);
  }

  return (
    <section className="ensemble-editor program-content-editor" aria-labelledby="program-features-title">
      <div className="ensemble-editor-head">
        <div>
          <p className="eyebrow">СТРАНИЦА ПРОГРАММЫ</p>
          <h3 id="program-features-title">Что входит в программу</h3>
          <p>Каждый пункт — отдельная плитка с иконкой на странице шоу. Подарок из блока «Услуги и подарки» показывается своей плиткой, здесь его повторять не нужно.</p>
        </div>
        <button
          className="button button-secondary"
          disabled={features.length >= FEATURES_LIMIT}
          onClick={() => {
            onChange([...features, { icon: "party-hat", text: "" }]);
            setPicking(null);
          }}
          type="button"
        >
          <Plus size={17} /> Добавить пункт
        </button>
      </div>
      {source === "text" && features.length ? (
        <p className="program-content-note"><Info size={16} /> Список собран из старого текстового поля. Проверьте иконки и нажмите «Сохранить».</p>
      ) : null}
      {features.length ? (
        <ol className="program-feature-list">
          {features.map((feature, index) => (
            <li className="program-feature" key={index}>
              <div className="program-feature-icon">
                <button
                  aria-expanded={picking === index}
                  aria-label={`Иконка пункта ${index + 1}: ${iconLabel(feature.icon)}. Изменить`}
                  onClick={() => setPicking(picking === index ? null : index)}
                  type="button"
                >
                  <Image alt="" height={48} src={iconSrc(feature.icon)} unoptimized width={48} />
                </button>
                {picking === index ? (
                  <IconPicker
                    onClose={() => setPicking(null)}
                    onPick={(icon) => {
                      update(index, { icon });
                      setPicking(null);
                    }}
                    value={feature.icon}
                  />
                ) : null}
              </div>
              <input
                aria-label={`Текст пункта ${index + 1}`}
                maxLength={FEATURE_TEXT_LIMIT}
                onChange={(event) => update(index, { text: event.target.value })}
                placeholder="Например: 2 неоновых прожектора"
                value={feature.text}
              />
              <div className="program-feature-actions">
                <button aria-label={`Пункт ${index + 1} выше`} disabled={index === 0} onClick={() => move(index, -1)} type="button"><ArrowUp size={16} /></button>
                <button aria-label={`Пункт ${index + 1} ниже`} disabled={index === features.length - 1} onClick={() => move(index, 1)} type="button"><ArrowDown size={16} /></button>
                <button aria-label={`Удалить пункт ${index + 1}`} className="is-danger" onClick={() => remove(index)} type="button"><Trash2 size={16} /></button>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className="ensemble-empty"><Plus size={21} /><span><strong>Пунктов пока нет</strong><small>На странице шоу в блоке «Что входит» останется только плитка подарка, если он настроен.</small></span></div>
      )}
      <p className="program-content-count">{features.length} из {FEATURES_LIMIT}</p>
    </section>
  );
}

export function ProgramCastEditor({ cast, onChange }: { cast: string[]; onChange: (next: string[]) => void }) {
  return (
    <section className="ensemble-editor" aria-labelledby="program-cast-title">
      <div className="ensemble-editor-head">
        <div>
          <p className="eyebrow">СОСТАВ</p>
          <h3 id="program-cast-title">Кто проведёт праздник</h3>
          <p>Для программ с фиксированным составом — артисты, которые приедут. Для обычных программ оставьте пустым: клиент выберет героев в конструкторе. У неоновых программ и «Игры в кальмара» состав задан тарифом — имена можно менять, а пустой список вернёт стандартный состав.</p>
        </div>
        <button className="button button-secondary" disabled={cast.length >= CAST_LIMIT} onClick={() => onChange([...cast, ""])} type="button">
          <Plus size={17} /> Добавить артиста
        </button>
      </div>
      {cast.length ? (
        <div className="ensemble-member-list">
          {cast.map((member, index) => (
            <label className="ensemble-member" key={index}>
              <span>Артист {index + 1}</span>
              <span className="ensemble-member-control">
                <input aria-label={`Артист ${index + 1}`} onChange={(event) => onChange(cast.map((item, itemIndex) => (itemIndex === index ? event.target.value : item)))} placeholder="Например: Неоновая ведущая" value={member} />
                <button aria-label={`Удалить артиста ${index + 1}`} onClick={() => onChange(cast.filter((_, itemIndex) => itemIndex !== index))} type="button"><Trash2 size={17} /></button>
              </span>
            </label>
          ))}
        </div>
      ) : (
        <div className="ensemble-empty"><UsersRound size={21} /><span><strong>Герои на выбор клиента</strong><small>Состав не фиксирован — клиент выбирает персонажей в конструкторе.</small></span></div>
      )}
    </section>
  );
}
