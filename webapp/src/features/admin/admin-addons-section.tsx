"use client";

import { BadgePercent, Gift, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import Image from "next/image";
import { type FormEvent, useMemo, useState } from "react";

import {
  AdminSectionState,
  formatMoney,
  useAdminSection,
  useSectionMutation,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";

type AddonRecord = {
  id: number;
  name: string;
  slug: string;
  status: "active" | "hidden" | string;
  sort_order: number;
  image_path?: string;
  short_description?: string;
  description?: string;
  price: number;
  cost: number;
  duration_minutes: number;
  type?: string;
  seo_title?: string;
  seo_description?: string;
  program_names?: string[];
  usage_count?: number;
};

type PromotionRecord = {
  id: number;
  title: string;
  short_text: string;
  badge_text: string;
  tooltip_text: string;
  status: "active" | "hidden" | string;
  sort_order: number;
};

type AddonsPayload = SectionEnvelope & { addons?: AddonRecord[]; promotions?: PromotionRecord[] };
type AddonDraft = Omit<AddonRecord, "id" | "program_names" | "usage_count"> & { id?: number };
type PromotionDraft = Omit<PromotionRecord, "id"> & { id?: number };

const emptyAddon: AddonDraft = {
  name: "",
  slug: "",
  status: "active",
  sort_order: 0,
  image_path: "",
  short_description: "",
  description: "",
  price: 0,
  cost: 0,
  duration_minutes: 0,
  type: "",
  seo_title: "",
  seo_description: "",
};

const emptyPromotion: PromotionDraft = {
  title: "",
  short_text: "",
  badge_text: "",
  tooltip_text: "",
  status: "active",
  sort_order: 0,
};

export function AdminAddonsSection() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [editor, setEditor] = useState<AddonDraft | null>(null);
  const [promotionEditor, setPromotionEditor] = useState<PromotionDraft | null>(null);
  const query = useMemo(() => {
    const value = new URLSearchParams();
    if (search) value.set("search", search);
    if (status) value.set("status", status);
    return value;
  }, [search, status]);
  const section = useAdminSection<AddonsPayload>("addons", query);
  const mutation = useSectionMutation("addons", section.refresh);
  const addons = section.data?.addons ?? [];
  const promotions = section.data?.promotions ?? [];

  return (
    <>
      <div className="admin-metrics admin-metrics-compact"><article><span>Всего услуг</span><strong>{addons.length}</strong></article><article><span>Активные</span><strong>{addons.filter((item) => item.status === "active").length}</strong></article><article><span>Скрытые</span><strong>{addons.filter((item) => item.status === "hidden").length}</strong></article></div>
      <section className="admin-surface">
        <div className="admin-surface-head"><div><p className="eyebrow">ДОП. УСЛУГИ</p><h2>Усиления для программ</h2><p>Цена, себестоимость, длительность и привязки к шоу.</p></div><button className="button button-violet" onClick={() => { setPromotionEditor(null); setEditor({ ...emptyAddon }); }} type="button"><Plus size={17} /> Добавить</button></div>
        <div className="admin-filter-bar"><label><span>Поиск</span><span className="input-with-icon"><Search size={16} /><input placeholder="Аквагрим, фотограф…" value={search} onChange={(event) => setSearch(event.target.value)} /></span></label><label><span>Статус</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Все</option><option value="active">Активные</option><option value="hidden">Скрытые</option></select></label></div>
        <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
        {!section.loading && !section.error && !addons.length ? <div className="admin-empty"><Gift /> Дополнительных услуг пока нет.</div> : null}
        <div className="admin-addon-grid">{addons.map((addon) => <article className="admin-addon-card" key={addon.id}><div className="admin-addon-media">{addon.image_path ? <Image alt="" fill sizes="260px" src={addon.image_path} style={{ objectFit: "cover" }} /> : <Gift />}<span className={`content-status status-${addon.status}`}>{addon.status === "active" ? "Активна" : "Скрыта"}</span></div><div><h3>{addon.name}</h3><small>/{addon.slug}/</small><p>{addon.short_description || addon.description || "Описание пока не заполнено."}</p><div className="admin-chip-list"><span>{formatMoney(addon.price)}</span><span>Себестоимость {formatMoney(addon.cost)}</span><span>{addon.duration_minutes || 0} мин</span>{addon.type ? <span>{addon.type}</span> : null}</div><div className="admin-linked-list"><strong>Используется:</strong> {addon.program_names?.length ? addon.program_names.join(", ") : "не привязана"}</div><div className="admin-row-actions"><button className="button button-violet" onClick={() => { setPromotionEditor(null); setEditor({ ...addon }); }} type="button"><Pencil size={17} /> Редактировать</button><button className="button button-secondary" onClick={() => void mutation.run(`status-${addon.id}`, { action: "status", id: addon.id, status: addon.status === "active" ? "hidden" : "active" }, "Статус изменён")} type="button">{addon.status === "active" ? "Скрыть" : "Активировать"}</button><button aria-label="Удалить" className="button button-danger" onClick={() => { if (window.confirm(`Удалить «${addon.name}»?`)) void mutation.run(`delete-${addon.id}`, { action: "delete", id: addon.id }, "Услуга удалена"); }} type="button"><Trash2 size={17} /></button></div></div></article>)}</div>
      </section>
      <section className="admin-surface">
        <div className="admin-surface-head"><div><p className="eyebrow">АКЦИИ</p><h2>Промо-предложения</h2><p>Бейджи и пояснения, которые можно привязать к шоу-программам.</p></div><button className="button button-violet" onClick={() => { setEditor(null); setPromotionEditor({ ...emptyPromotion }); }} type="button"><Plus size={17} /> Добавить акцию</button></div>
        {!promotions.length ? <div className="admin-empty"><BadgePercent /> Акций пока нет.</div> : <div className="admin-promotion-grid">{promotions.map((promotion) => <article className="admin-promotion-card" key={promotion.id}><div><BadgePercent size={22} /><span className={`content-status status-${promotion.status}`}>{promotion.status === "active" ? "Активна" : "Скрыта"}</span></div><h3>{promotion.title}</h3><strong>{promotion.badge_text || promotion.title}</strong><p>{promotion.short_text || promotion.tooltip_text || "Пояснение пока не заполнено."}</p><div className="admin-row-actions"><button className="button button-violet" onClick={() => { setEditor(null); setPromotionEditor({ ...promotion }); }} type="button"><Pencil size={17} /> Редактировать</button><button className="button button-secondary" onClick={() => void mutation.run(`promotion-status-${promotion.id}`, { resource: "promotion", action: "status", id: promotion.id, status: promotion.status === "active" ? "hidden" : "active" }, "Статус акции изменён")} type="button">{promotion.status === "active" ? "Скрыть" : "Активировать"}</button><button aria-label="Удалить акцию" className="button button-danger" onClick={() => { if (window.confirm(`Удалить акцию «${promotion.title}»?`)) void mutation.run(`promotion-delete-${promotion.id}`, { resource: "promotion", action: "delete", id: promotion.id }, "Акция удалена"); }} type="button"><Trash2 size={17} /></button></div></article>)}</div>}
      </section>
      {editor ? <AddonEditor pending={mutation.pendingKey === `save-${editor.id ?? "new"}`} value={editor} onChange={setEditor} onClose={() => setEditor(null)} onSave={async () => { const result = await mutation.run(`save-${editor.id ?? "new"}`, { action: editor.id ? "update" : "create", ...editor }, editor.id ? "Услуга сохранена" : "Услуга создана"); if (result) setEditor(null); }} /> : null}
      {promotionEditor ? <PromotionEditor pending={mutation.pendingKey === `promotion-save-${promotionEditor.id ?? "new"}`} value={promotionEditor} onChange={setPromotionEditor} onClose={() => setPromotionEditor(null)} onSave={async () => { const result = await mutation.run(`promotion-save-${promotionEditor.id ?? "new"}`, { resource: "promotion", action: promotionEditor.id ? "update" : "create", ...promotionEditor }, promotionEditor.id ? "Акция сохранена" : "Акция создана"); if (result) setPromotionEditor(null); }} /> : null}
    </>
  );
}

function PromotionEditor({
  onChange,
  onClose,
  onSave,
  pending,
  value,
}: {
  onChange: (value: PromotionDraft) => void;
  onClose: () => void;
  onSave: () => Promise<void>;
  pending: boolean;
  value: PromotionDraft;
}) {
  function field<K extends keyof PromotionDraft>(key: K, next: PromotionDraft[K]) {
    onChange({ ...value, [key]: next });
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void onSave();
  }
  return <section className="admin-surface admin-editor-drawer"><div className="admin-surface-head"><div><p className="eyebrow">РЕДАКТОР АКЦИИ</p><h2>{value.id ? value.title : "Новая акция"}</h2></div><button aria-label="Закрыть" onClick={onClose} type="button"><X /></button></div><form onSubmit={submit}><div className="admin-form-grid"><label>Название<input required value={value.title} onChange={(event) => field("title", event.target.value)} /></label><label>Текст бейджа<input required value={value.badge_text} onChange={(event) => field("badge_text", event.target.value)} /></label><label>Статус<select value={value.status} onChange={(event) => field("status", event.target.value)}><option value="active">Активна</option><option value="hidden">Скрыта</option></select></label><label>Порядок<input min={0} type="number" value={value.sort_order} onChange={(event) => field("sort_order", Number(event.target.value))} /></label><label className="wide">Короткий текст<textarea value={value.short_text} onChange={(event) => field("short_text", event.target.value)} /></label><label className="wide">Подсказка<textarea rows={4} value={value.tooltip_text} onChange={(event) => field("tooltip_text", event.target.value)} /></label></div><div className="admin-row-actions"><button className="button button-violet" disabled={pending || !value.title || !value.badge_text} type="submit">{pending ? "Сохраняем…" : "Сохранить"}</button><button className="button button-secondary" onClick={onClose} type="button">Отмена</button></div></form></section>;
}

function AddonEditor({
  onChange,
  onClose,
  onSave,
  pending,
  value,
}: {
  onChange: (value: AddonDraft) => void;
  onClose: () => void;
  onSave: () => Promise<void>;
  pending: boolean;
  value: AddonDraft;
}) {
  function field<K extends keyof AddonDraft>(key: K, next: AddonDraft[K]) {
    onChange({ ...value, [key]: next });
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void onSave();
  }
  return <section className="admin-surface admin-editor-drawer"><div className="admin-surface-head"><div><p className="eyebrow">РЕДАКТОР</p><h2>{value.id ? value.name : "Новая доп. услуга"}</h2></div><button aria-label="Закрыть" onClick={onClose} type="button"><X /></button></div><form onSubmit={submit}><div className="admin-form-grid"><label>Название<input required value={value.name} onChange={(event) => field("name", event.target.value)} /></label><label>Slug<input value={value.slug} onChange={(event) => field("slug", event.target.value)} /></label><label>Статус<select value={value.status} onChange={(event) => field("status", event.target.value)}><option value="active">Активна</option><option value="hidden">Скрыта</option></select></label><label>Порядок<input min={0} type="number" value={value.sort_order} onChange={(event) => field("sort_order", Number(event.target.value))} /></label><label>Цена, сум<input min={0} step={1000} type="number" value={value.price} onChange={(event) => field("price", Number(event.target.value))} /></label><label>Себестоимость, сум<input min={0} step={1000} type="number" value={value.cost} onChange={(event) => field("cost", Number(event.target.value))} /></label><label>Длительность, мин<input min={0} step={5} type="number" value={value.duration_minutes} onChange={(event) => field("duration_minutes", Number(event.target.value))} /></label><label>Тип<input value={value.type ?? ""} onChange={(event) => field("type", event.target.value)} /></label><label className="wide">Короткое описание<textarea value={value.short_description ?? ""} onChange={(event) => field("short_description", event.target.value)} /></label><label className="wide">Полное описание<textarea rows={5} value={value.description ?? ""} onChange={(event) => field("description", event.target.value)} /></label><label>SEO title<input value={value.seo_title ?? ""} onChange={(event) => field("seo_title", event.target.value)} /></label><label>SEO description<textarea value={value.seo_description ?? ""} onChange={(event) => field("seo_description", event.target.value)} /></label></div><div className="admin-row-actions"><button className="button button-violet" disabled={pending || !value.name} type="submit">{pending ? "Сохраняем…" : "Сохранить"}</button><button className="button button-secondary" onClick={onClose} type="button">Отмена</button></div></form></section>;
}
