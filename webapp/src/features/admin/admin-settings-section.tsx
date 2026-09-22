"use client";

import { CalendarDays, Save, Settings2, Snowflake, Sparkles } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

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
};

const defaultLabels: Record<string, { title: string; description: string }> = {
  new_year_season_enabled: { title: "Новогодний сезон", description: "Главный переключатель сезонного оформления и контента." },
  show_new_year_menu_link: { title: "Ссылка в меню", description: "Показывать новогодний раздел в основной навигации." },
  show_home_new_year_showcase: { title: "Витрина на главной", description: "Добавить сезонный блок на главную страницу." },
  show_snow: { title: "Эффект снега", description: "Лёгкая декоративная анимация без влияния на управление." },
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
  const booleanEntries = Object.entries(draft).filter(([, value]) => typeof value === "boolean");
  const valueEntries = Object.entries(draft).filter(([, value]) => typeof value !== "boolean");

  return (
    <>
      <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
      {!section.loading && !section.error ? (
        <form onSubmit={(event) => void save(event)}>
          <div className="admin-dashboard-grid">
            <section className="admin-surface">
              <div className="admin-surface-head"><div><p className="eyebrow">ПУБЛИЧНЫЙ САЙТ</p><h2>Функции и сезонность</h2><p>Изменения применяются к витрине без пересборки фронтенда.</p></div><Settings2 /></div>
              {!booleanEntries.length ? <div className="admin-empty">Переключатели появятся после ответа adapter API.</div> : <div className="admin-toggle-list">{booleanEntries.map(([key, value]) => {
                const label = labels[key] ?? { title: key, description: "" };
                return <label className="admin-toggle" key={key}><span><strong>{label.title}</strong><small>{label.description || key}</small></span><input checked={Boolean(value)} onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.checked }))} type="checkbox" /><i /></label>;
              })}</div>}
            </section>

            <aside className="admin-surface admin-season-card">
              <div className="admin-surface-head"><div><p className="eyebrow">БЫСТРЫЙ РЕЖИМ</p><h2>Сезонный пресет</h2><p>Одним действием включает связанные новогодние элементы.</p></div><Snowflake /></div>
              <div className="admin-season-visual"><Sparkles /><strong>{draft.new_year_season_enabled ? "Сезон активен" : "Обычный режим"}</strong></div>
              <div className="admin-row-actions"><button className="button button-violet" disabled={mutation.pendingKey === "season-on"} onClick={() => void mutation.run("season-on", { action: "season_preset", enabled: true }, "Новогодний режим включён")} type="button"><CalendarDays size={17} /> Включить сезон</button><button className="button button-secondary" disabled={mutation.pendingKey === "season-off"} onClick={() => void mutation.run("season-off", { action: "season_preset", enabled: false }, "Обычный режим включён")} type="button">Выключить</button></div>
            </aside>

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
