"use client";

import { Plus, Save, Tags, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";

import {
  AdminSectionState,
  useAdminSection,
  useSectionMutation,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";

type TaxonomyKind = "category" | "tag";
type TaxonomyRecord = {
  id: number;
  name: string;
  slug: string;
  description?: string;
  is_visible?: boolean;
  is_system?: boolean;
  sort_order?: number;
  character_count?: number;
  linked_tag_id?: number | null;
  linked_tag_name?: string;
};

type TaxonomyPayload = SectionEnvelope & {
  categories?: TaxonomyRecord[];
  tags?: TaxonomyRecord[];
};

export function AdminTaxonomySection() {
  const section = useAdminSection<TaxonomyPayload>("taxonomy");
  const mutation = useSectionMutation("taxonomy", section.refresh);
  const categories = section.data?.categories ?? [];
  const tags = section.data?.tags ?? [];

  return (
    <>
      <div className="admin-metrics admin-metrics-compact">
        <article><span>Категории</span><strong>{categories.length}</strong></article>
        <article><span>Теги</span><strong>{tags.length}</strong></article>
        <article><span>Публичные витрины</span><strong>{categories.filter((item) => item.is_visible).length}</strong></article>
      </div>
      <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
      {!section.loading && !section.error ? (
        <div className="admin-dashboard-grid taxonomy-layout">
          <TaxonomyColumn kind="category" items={categories} linkedTags={tags} pendingKey={mutation.pendingKey} run={mutation.run} />
          <TaxonomyColumn kind="tag" items={tags} linkedTags={[]} pendingKey={mutation.pendingKey} run={mutation.run} />
        </div>
      ) : null}
    </>
  );
}

function TaxonomyColumn({
  items,
  kind,
  linkedTags,
  pendingKey,
  run,
}: {
  items: TaxonomyRecord[];
  kind: TaxonomyKind;
  linkedTags: TaxonomyRecord[];
  pendingKey: string;
  run: (key: string, payload: Record<string, unknown>, successMessage: string) => Promise<SectionEnvelope | null>;
}) {
  const label = kind === "category" ? "Категории" : "Теги";
  const [creating, setCreating] = useState(false);

  return (
    <section className="admin-surface">
      <div className="admin-surface-head"><div><p className="eyebrow">{kind === "category" ? "ВИТРИНЫ" : "СВЯЗИ"}</p><h2>{label}</h2><p>{kind === "category" ? "Публичные подборки; связанный тег наполняет витрину автоматически." : "Метки, назначаемые карточкам персонажей."}</p></div><button className="button button-violet" onClick={() => setCreating((value) => !value)} type="button"><Plus size={17} /> Добавить</button></div>
      {creating ? <TaxonomyCreate kind={kind} linkedTags={linkedTags} onCancel={() => setCreating(false)} pending={pendingKey === `create-${kind}`} run={run} /> : null}
      <div className="taxonomy-manager-list">
        {items.map((item) => <TaxonomyRow item={item} kind={kind} linkedTags={linkedTags} pendingKey={pendingKey} run={run} key={item.id} />)}
        {!items.length ? <div className="admin-empty"><Tags /> Пока ничего не добавлено.</div> : null}
      </div>
    </section>
  );
}

function TaxonomyCreate({
  kind,
  linkedTags,
  onCancel,
  pending,
  run,
}: {
  kind: TaxonomyKind;
  linkedTags: TaxonomyRecord[];
  onCancel: () => void;
  pending: boolean;
  run: (key: string, payload: Record<string, unknown>, successMessage: string) => Promise<SectionEnvelope | null>;
}) {
  const [value, setValue] = useState({ name: "", slug: "", description: "", linked_tag_id: "", is_visible: true });

  async function submit(event: FormEvent) {
    event.preventDefault();
    const result = await run(`create-${kind}`, { action: "create", taxonomy: kind, ...value, linked_tag_id: value.linked_tag_id ? Number(value.linked_tag_id) : null }, `${kind === "category" ? "Категория" : "Тег"} создан`);
    if (result) onCancel();
  }

  return <form className="admin-inline-editor" onSubmit={(event) => void submit(event)}><div className="admin-form-grid"><label>Название<input required value={value.name} onChange={(event) => setValue((current) => ({ ...current, name: event.target.value }))} /></label><label>Slug<input value={value.slug} onChange={(event) => setValue((current) => ({ ...current, slug: event.target.value }))} /></label><label className="wide">Описание<textarea value={value.description} onChange={(event) => setValue((current) => ({ ...current, description: event.target.value }))} /></label>{kind === "category" ? <label>Связанный тег<select value={value.linked_tag_id} onChange={(event) => setValue((current) => ({ ...current, linked_tag_id: event.target.value }))}><option value="">Создать автоматически</option>{linkedTags.filter((tag) => !tag.is_system).map((tag) => <option value={tag.id} key={tag.id}>{tag.name}</option>)}</select></label> : null}<label className="admin-check"><input checked={value.is_visible} onChange={(event) => setValue((current) => ({ ...current, is_visible: event.target.checked }))} type="checkbox" /> Показывать публично</label></div><div className="admin-row-actions"><button className="button button-violet" disabled={pending || !value.name} type="submit">Создать</button><button className="button button-secondary" onClick={onCancel} type="button">Отмена</button></div></form>;
}

function TaxonomyRow({
  item,
  kind,
  linkedTags,
  pendingKey,
  run,
}: {
  item: TaxonomyRecord;
  kind: TaxonomyKind;
  linkedTags: TaxonomyRecord[];
  pendingKey: string;
  run: (key: string, payload: Record<string, unknown>, successMessage: string) => Promise<SectionEnvelope | null>;
}) {
  const [value, setValue] = useState({ ...item, linked_tag_id: item.linked_tag_id ? String(item.linked_tag_id) : "" });
  const key = `${kind}-${item.id}`;

  return (
    <details className="admin-manager-card">
      <summary><span><strong>{item.name}</strong><small>/{item.slug}/ · {item.character_count ?? 0} персонажей</small></span><span className={`content-status ${item.is_visible ? "status-active" : "status-hidden"}`}>{item.is_visible ? "виден" : "скрыт"}</span></summary>
      <form className="admin-inline-editor" onSubmit={(event) => { event.preventDefault(); void run(key, { action: "update", taxonomy: kind, ...value, id: item.id, linked_tag_id: value.linked_tag_id ? Number(value.linked_tag_id) : null }, "Изменения сохранены"); }}>
        <div className="admin-form-grid"><label>Название<input disabled={item.is_system} value={value.name} onChange={(event) => setValue((current) => ({ ...current, name: event.target.value }))} /></label><label>Slug<input disabled={item.is_system} value={value.slug} onChange={(event) => setValue((current) => ({ ...current, slug: event.target.value }))} /></label><label>Порядок<input min={0} type="number" value={value.sort_order ?? 0} onChange={(event) => setValue((current) => ({ ...current, sort_order: Number(event.target.value) }))} /></label>{kind === "category" ? <label>Связанный тег<select disabled={item.is_system} value={value.linked_tag_id} onChange={(event) => setValue((current) => ({ ...current, linked_tag_id: event.target.value }))}><option value="">Без связанного тега</option>{linkedTags.map((tag) => <option value={tag.id} key={tag.id}>{tag.name}</option>)}</select></label> : null}<label className="wide">Описание<textarea value={value.description ?? ""} onChange={(event) => setValue((current) => ({ ...current, description: event.target.value }))} /></label><label className="admin-check"><input checked={item.is_system || Boolean(value.is_visible)} disabled={item.is_system} onChange={(event) => setValue((current) => ({ ...current, is_visible: event.target.checked }))} type="checkbox" /> Показывать публично</label></div>
        <div className="admin-row-actions"><button className="button button-violet" disabled={pendingKey === key} type="submit"><Save size={17} /> Сохранить</button>{!item.is_system ? <button className="button button-danger" onClick={() => { if (window.confirm(`Удалить «${item.name}»?`)) void run(`delete-${key}`, { action: "delete", taxonomy: kind, id: item.id }, "Элемент удалён"); }} type="button"><Trash2 size={17} /> Удалить</button> : <span className="admin-note">Системный элемент защищён</span>}</div>
      </form>
    </details>
  );
}
