"use client";

import { Save, Settings2 } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { AdminSeasonCard, SEASON_OWNED_FLAGS, type SeasonAdminState } from "@/features/admin/admin-season-card";

import {
  AdminSectionState,
  useAdminSection,
  useSectionMutation,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";

type SettingValue = boolean | number | string;
type SettingsPayload = SectionEnvelope & {
  settings?: Record<string, SettingValue>;
  labels?: Record<string, { title: string; description?: string; type?: "boolean" | "number" | "string" }>;
  party_builder?: Record<string, SettingValue>;
  season?: SeasonAdminState;
};

const defaultLabels: Record<string, { title: string; description: string }> = {
  show_promotions: { title: "Акции", description: "Показывать промо-предложения посетителям." },
  hide_easter_egg: { title: "Скрыть пасхалку", description: "Отключить секретную интерактивную сцену." },
  picker_enabled: { title: "Конструктор праздника", description: "Разрешить покупателю самостоятельно собирать программу." },
};

export function AdminSettingsSection() {
  const section = useAdminSection<SettingsPayload>("settings");
  const mutation = useSectionMutation("settings", section.refresh);
  const [draft, setDraft] = useState<Record<string, SettingValue>>({});

  useEffect(() => {
    if (!section.data) return;
    const timeout = window.setTimeout(
      () => setDraft({ ...(section.data?.settings ?? {}), ...(section.data?.party_builder ?? {}) }),
      0,
    );
    return () => window.clearTimeout(timeout);
  }, [section.data]);

  async function save(event: FormEvent) {
    event.preventDefault();
    await mutation.run("save", { action: "save", settings: draft }, "Настройки сохранены");
  }

  const labels = { ...defaultLabels, ...(section.data?.labels ?? {}) };
  // The New Year flags follow the season card and are not edited by hand.
  const booleanEntries = Object.entries(draft).filter(([key, value]) => typeof value === "boolean" && !SEASON_OWNED_FLAGS.has(key));
  const valueEntries = Object.entries(draft).filter(([, value]) => typeof value !== "boolean");

  return (
    <>
      <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
      {!section.loading && !section.error ? (
        <form onSubmit={(event) => void save(event)}>
          <div className="admin-dashboard-grid">
            {section.data?.season ? <AdminSeasonCard onChanged={section.refresh} state={section.data.season} /> : null}
            <section className="admin-surface admin-surface-wide">
              <div className="admin-surface-head"><div><p className="eyebrow">ПУБЛИЧНЫЙ САЙТ</p><h2>Функции витрины</h2><p>Изменения применяются к витрине без пересборки фронтенда.</p></div><Settings2 /></div>
              {!booleanEntries.length ? <div className="admin-empty">Переключатели появятся после ответа adapter API.</div> : <div className="admin-toggle-list">{booleanEntries.map(([key, value]) => {
                const label = labels[key] ?? { title: key, description: "" };
                return <label className="admin-toggle" key={key}><span><strong>{label.title}</strong><small>{label.description || key}</small></span><input checked={Boolean(value)} onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.checked }))} type="checkbox" /><i /></label>;
              })}</div>}
            </section>


            {valueEntries.length ? <section className="admin-surface admin-surface-wide"><div className="admin-surface-head"><div><p className="eyebrow">КОНСТРУКТОР</p><h2>Параметры праздника</h2><p>Лимиты, значения по умолчанию и текстовые настройки.</p></div></div><div className="admin-form-grid">{valueEntries.map(([key, value]) => {
              const label = labels[key] ?? { title: key, description: "" };
              const isNumber = typeof value === "number";
              return <label key={key}>{label.title}<input type={isNumber ? "number" : "text"} value={typeof value === "boolean" ? "" : value} onChange={(event) => setDraft((current) => ({ ...current, [key]: isNumber ? Number(event.target.value) : event.target.value }))} /><small>{label.description || key}</small></label>;
            })}</div></section> : null}
          </div>
          <div className="admin-sticky-actions"><button className="button button-violet" disabled={mutation.pendingKey === "save"} type="submit"><Save size={17} /> {mutation.pendingKey === "save" ? "Сохраняем…" : "Сохранить настройки"}</button></div>
        </form>
      ) : null}
    </>
  );
}
