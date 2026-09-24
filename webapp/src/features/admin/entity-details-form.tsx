"use client";

import { Plus, Save, Trash2, UsersRound } from "lucide-react";
import { useEffect, useMemo, useState, useTransition } from "react";
import { toast } from "sonner";

import { createEntityMutationPayload, normalizeEnsembleMembers } from "@/features/admin/entity-payload";
import { ProgramCastEditor, ProgramFeaturesEditor } from "@/features/admin/program-content-editor";
import { mutateJson } from "@/lib/client/mutate";
import type { VariantGroup } from "@/lib/server/admin-entities";
import type { Addon, CatalogEntity, TaxonomyItem } from "@/lib/types";

type EditableEntity = Pick<
  CatalogEntity,
  | "id"
  | "name"
  | "slug"
  | "short_description"
  | "description"
  | "seo_title"
  | "seo_description"
  | "search_terms"
  | "status"
  | "sort_order"
  | "base_price"
  | "default_duration_minutes"
  | "age_from"
  | "age_to"
  | "included_characters_count"
  | "extra_character_price_3"
  | "extra_character_price_4_plus"
  | "ensemble_members"
  | "ensemble_included_count"
  | "ensemble_extra_member_price"
  | "included_items"
  | "suitable_for"
  | "restrictions"
  | "video_url"
  | "variant_group_slug"
  | "variant_group_name"
  | "variant_label"
  | "categories"
  | "tags"
  | "addons"
> & {
  program_features: NonNullable<CatalogEntity["program_features"]>;
  program_cast: string[];
};

function normalizeAddonSettings(addons: Array<Partial<Addon> & Pick<Addon, "id" | "name" | "slug" | "price" | "duration_minutes">>): Addon[] {
  return addons.map((addon) => ({
    status: "active",
    image_path: "",
    short_description: "",
    is_available: false,
    is_recommended: false,
    is_default: false,
    is_free_choice: false,
    gift_mode: "none",
    gift_group: "",
    sort_order: 0,
    ...addon,
  }));
}

function emptyEntity(kind: "character" | "show_program"): EditableEntity {
  return {
    id: 0,
    name: "",
    slug: "",
    short_description: "",
    description: "",
    seo_title: "",
    seo_description: "",
    search_terms: "",
    status: "draft",
    sort_order: 0,
    base_price: kind === "show_program" ? 1_000_000 : 0,
    default_duration_minutes: 60,
    age_from: null,
    age_to: null,
    included_characters_count: 2,
    extra_character_price_3: 200_000,
    extra_character_price_4_plus: 200_000,
    ensemble_members: [],
    ensemble_included_count: 2,
    ensemble_extra_member_price: 300_000,
    included_items: "",
    suitable_for: "",
    restrictions: "",
    video_url: "",
    variant_group_slug: "",
    variant_group_name: "",
    variant_label: "",
    categories: ["all"],
    tags: ["all"],
    addons: [],
    program_features: [],
    program_cast: [],
  };
}

function initialEntity(entity: CatalogEntity | undefined, kind: "character" | "show_program"): EditableEntity {
  const base = emptyEntity(kind);
  if (!entity) return base;
  // Pick<> hides fields from TypeScript only — spreading the whole entity carried
  // server-owned columns (crop, media, timestamps) into the save payload, where
  // they overwrote whatever the crop editor had just written.
  const editable = Object.fromEntries(
    (Object.keys(base) as Array<keyof EditableEntity>).map((key) => [
      key,
      entity[key] === undefined ? base[key] : entity[key],
    ]),
  ) as EditableEntity;
  return {
    ...editable,
    ensemble_members: normalizeEnsembleMembers(entity.ensemble_members),
    addons: normalizeAddonSettings(entity.addons ?? []),
    program_features: (entity.program_features ?? []).map((feature) => ({ ...feature })),
    program_cast: [...(entity.program_cast ?? [])],
  };
}

const priceFormatter = new Intl.NumberFormat("ru-RU");

const NEW_GROUP = "__new__";

function slugifyGroup(name: string) {
  const map: Record<string, string> = {
    а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z", и: "i",
    й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t",
    у: "u", ф: "f", х: "h", ц: "c", ч: "ch", ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "",
    э: "e", ю: "yu", я: "ya",
  };
  return name
    .toLocaleLowerCase("ru-RU")
    .split("")
    .map((letter) => (letter in map ? map[letter] : letter))
    .join("")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function EntityDetailsForm({
  entity,
  kind,
  categories,
  tags,
  variantGroups = [],
  presetGroup,
}: {
  entity?: CatalogEntity;
  kind: "character" | "show_program";
  categories: TaxonomyItem[];
  tags: TaxonomyItem[];
  variantGroups?: VariantGroup[];
  presetGroup?: { slug: string; name: string };
}) {
  const [value, setValue] = useState<EditableEntity>(() => {
    const start = initialEntity(entity, kind);
    if (!entity && presetGroup?.slug) {
      return { ...start, variant_group_slug: presetGroup.slug, variant_group_name: presetGroup.name };
    }
    return start;
  });
  const [isPending, startTransition] = useTransition();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const isNew = !value.id;
  const ensembleMemberCount = normalizeEnsembleMembers(value.ensemble_members).length;
  const groupOptions = useMemo(() => {
    const known = new Map(variantGroups.map((group) => [group.slug, group]));
    const own = String(value.variant_group_slug || "").trim();
    if (own && !known.has(own)) {
      known.set(own, { slug: own, name: String(value.variant_group_name || "").trim() || own, variantCount: 1 });
    }
    return [...known.values()];
  }, [variantGroups, value.variant_group_slug, value.variant_group_name]);
  // Derived state would flip the select away from "new group" the moment the first
  // letter of the name produced a slug, so the mode is held explicitly.
  const [creatingGroup, setCreatingGroup] = useState(false);
  const groupChoice = creatingGroup ? NEW_GROUP : String(value.variant_group_slug || "").trim();

  function chooseGroup(next: string) {
    if (next === NEW_GROUP) {
      setCreatingGroup(true);
      setValue((current) => ({ ...current, variant_group_slug: "", variant_group_name: "" }));
      return;
    }
    setCreatingGroup(false);
    if (!next) {
      setValue((current) => ({ ...current, variant_group_slug: "", variant_group_name: "", variant_label: "" }));
      return;
    }
    const picked = groupOptions.find((group) => group.slug === next);
    setValue((current) => ({
      ...current,
      variant_group_slug: next,
      variant_group_name: picked?.name ?? next,
    }));
  }


  useEffect(() => {
    if (kind !== "show_program" || value.addons.length) return;
    let cancelled = false;
    void fetch("/api/admin/section/addons?status=active", { cache: "no-store", credentials: "same-origin" })
      .then((response) => response.json() as Promise<{ authenticated?: boolean; addons?: Addon[] }>)
      .then((result) => {
        if (result.authenticated === false) {
          window.location.assign("/admin/login");
          return;
        }
        if (!cancelled && result.addons) {
          setValue((current) => ({ ...current, addons: normalizeAddonSettings(result.addons ?? []) }));
        }
      })
      .catch(() => toast.error("Не удалось загрузить дополнительные услуги."));
    return () => { cancelled = true; };
  }, [kind, value.addons.length]);

  function field<K extends keyof EditableEntity>(key: K, next: EditableEntity[K]) {
    setValue((current) => ({ ...current, [key]: next }));
  }

  function toggleList(key: "categories" | "tags", slug: string) {
    const current = value[key];
    field(key, current.includes(slug) ? current.filter((item) => item !== slug) : [...current, slug]);
  }

  function setEnsembleMembers(members: string[]) {
    setValue((current) => ({
      ...current,
      ensemble_members: members,
      ensemble_included_count: members.length
        ? Math.min(Math.max(2, current.ensemble_included_count), members.length)
        : 2,
    }));
  }

  function updateAddon(addonId: number, next: Partial<Addon>) {
    setValue((current) => ({
      ...current,
      addons: current.addons.map((addon) => addon.id === addonId ? { ...addon, ...next } : addon),
    }));
  }

  function save() {
    const members = normalizeEnsembleMembers(value.ensemble_members);
    if (members.length === 1) {
      toast.error("Для групповой карточки укажите минимум двух персонажей.");
      return;
    }
    const payload = createEntityMutationPayload({ ...value, ensemble_members: members }, kind);
    startTransition(async () => {
      try {
        const result = await mutateJson<{ success: boolean; id?: number }>(
          isNew ? "/api/admin/entities" : `/api/admin/entities/${value.id}`,
          payload,
        );
        toast.success(isNew ? "Карточка создана" : "Изменения сохранены");
        if (isNew && result.id) {
          window.location.assign(kind === "character" ? `/admin/catalog/characters/${result.id}` : `/admin/show-programs/${result.id}`);
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Не удалось сохранить.");
      }
    });
  }

  function remove() {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      return;
    }
    startTransition(async () => {
      try {
        await mutateJson(`/api/admin/entities/${value.id}`, null, "DELETE");
        toast.success(`Карточка «${value.name}» удалена`);
        window.location.assign(kind === "character" ? "/admin/catalog/characters" : "/admin/show-programs");
      } catch (error) {
        setConfirmingDelete(false);
        toast.error(error instanceof Error ? error.message : "Не удалось удалить карточку.");
      }
    });
  }

  return (
    <section className="admin-surface entity-form">
      <div className="admin-surface-head"><div><p className="eyebrow">ОСНОВНЫЕ ДАННЫЕ</p><h2>{isNew ? "Новая карточка" : "Содержание и параметры"}</h2></div><div className="entity-form-actions">{!isNew && (confirmingDelete ? (<><button className="button button-danger" disabled={isPending} onClick={remove} type="button"><Trash2 size={17} /> {isPending ? "Удаляем…" : "Подтверждаю"}</button><button className="button button-secondary" disabled={isPending} onClick={() => setConfirmingDelete(false)} type="button">Отмена</button></>) : (<button className="button button-secondary" disabled={isPending} onClick={remove} type="button"><Trash2 size={17} /> Удалить</button>))}<button className="button button-violet" disabled={isPending || !value.name} onClick={save} type="button"><Save size={17} /> {isPending ? "Сохраняем…" : "Сохранить"}</button></div></div>
      <div className="admin-form-grid">
        <label>Название<input value={value.name} onChange={(event) => field("name", event.target.value)} /></label>
        <label>Slug<input value={value.slug} onChange={(event) => field("slug", event.target.value)} /></label>
        <label>Статус<select value={value.status} onChange={(event) => field("status", event.target.value)}><option value="active">Опубликовано</option><option value="draft">Черновик</option><option value="hidden">Скрыто</option></select></label>
        <label>Порядок<input type="number" value={value.sort_order} onChange={(event) => field("sort_order", Number(event.target.value))} /></label>
        <label className="wide">Короткое описание<textarea value={value.short_description} onChange={(event) => field("short_description", event.target.value)} /></label>
        <label className="wide">Полное описание<textarea rows={6} value={value.description} onChange={(event) => field("description", event.target.value)} /></label>
        <label>Возраст от<input min={1} type="number" value={value.age_from ?? ""} onChange={(event) => field("age_from", event.target.value ? Number(event.target.value) : null)} /></label>
        <label>Возраст до<input min={1} type="number" value={value.age_to ?? ""} onChange={(event) => field("age_to", event.target.value ? Number(event.target.value) : null)} /></label>
        <label>Длительность, мин<input min={1} type="number" value={value.default_duration_minutes} onChange={(event) => field("default_duration_minutes", Number(event.target.value))} /></label>
        {kind === "show_program" ? <><label>Цена, сум<input min={0} step={50_000} type="number" value={value.base_price} onChange={(event) => field("base_price", Number(event.target.value))} /></label><label>Персонажей включено<input min={0} type="number" value={value.included_characters_count} onChange={(event) => field("included_characters_count", Number(event.target.value))} /></label><label>Доплата за третьего<input min={0} step={50_000} type="number" value={value.extra_character_price_3} onChange={(event) => field("extra_character_price_3", Number(event.target.value))} /></label><label>Доплата за следующих<input min={0} step={50_000} type="number" value={value.extra_character_price_4_plus} onChange={(event) => field("extra_character_price_4_plus", Number(event.target.value))} /></label><label className="wide">Формат программы<select value={groupChoice} onChange={(event) => chooseGroup(event.target.value)}><option value="">Отдельная программа</option>{groupOptions.map((group) => <option key={group.slug} value={group.slug}>{group.name} — {group.variantCount} {group.variantCount === 1 ? "формат" : "формата"}</option>)}<option value={NEW_GROUP}>Новая группа форматов…</option></select><small className="admin-field-hint">{groupChoice ? "Карточки одной группы показываются на сайте как одна программа с выбором формата." : "Программа продаётся сама по себе, без выбора формата."}</small></label>{groupChoice === NEW_GROUP ? <label>Название группы<input placeholder="Например: Лента-шоу" value={value.variant_group_name} onChange={(event) => { const name = event.target.value; setValue((current) => ({ ...current, variant_group_name: name, variant_group_slug: slugifyGroup(name) })); }} /></label> : null}{groupChoice ? <label>Название формата<input placeholder="Например: Бумажное" value={value.variant_label} onChange={(event) => field("variant_label", event.target.value)} /></label> : null}<label>Видео URL<input value={value.video_url} onChange={(event) => field("video_url", event.target.value)} /></label><label className="wide">Для кого подходит<textarea value={value.suitable_for} onChange={(event) => field("suitable_for", event.target.value)} /></label><label className="wide">Важно знать<textarea value={value.restrictions} onChange={(event) => field("restrictions", event.target.value)} /><small className="admin-field-hint">Каждый пункт с новой строки. На странице шоу выделяется в блоке «Важно знать», например: «Проводится только в закрытом помещении».</small></label></> : null}
      </div>
      {kind === "character" ? (
        <section className="ensemble-editor" aria-labelledby="ensemble-editor-title">
          <div className="ensemble-editor-head">
            <div><p className="eyebrow">СОСТАВ КАРТОЧКИ</p><h3 id="ensemble-editor-title">Парные и групповые персонажи</h3><p>Оставьте список пустым для одиночного героя. В паре клиент получит обоих, а в тройке выберет включённый состав.</p></div>
            <button className="button button-secondary" onClick={() => setEnsembleMembers([...value.ensemble_members, ""])} type="button"><Plus size={17} /> Добавить участника</button>
          </div>
          {value.ensemble_members.length ? (
            <div className="ensemble-member-list">
              {value.ensemble_members.map((member, index) => (
                <label className="ensemble-member" key={index}>
                  <span>Участник {index + 1}</span>
                  <span className="ensemble-member-control"><input aria-label={`Имя участника ${index + 1}`} value={member} onChange={(event) => setEnsembleMembers(value.ensemble_members.map((item, itemIndex) => itemIndex === index ? event.target.value : item))} /><button aria-label={`Удалить участника ${index + 1}`} onClick={() => setEnsembleMembers(value.ensemble_members.filter((_, itemIndex) => itemIndex !== index))} type="button"><Trash2 size={17} /></button></span>
                </label>
              ))}
            </div>
          ) : <div className="ensemble-empty"><UsersRound size={21} /><span><strong>Одиночный персонаж</strong><small>Карточка занимает одно место в выбранной программе.</small></span></div>}
          {ensembleMemberCount >= 2 ? (
            <div className="ensemble-settings">
              <label>Участников включено<input max={ensembleMemberCount} min={2} type="number" value={value.ensemble_included_count} onChange={(event) => field("ensemble_included_count", Number(event.target.value))} /></label>
              <label>Доплата за следующего, сум<input min={0} step={50_000} type="number" value={value.ensemble_extra_member_price} onChange={(event) => field("ensemble_extra_member_price", Number(event.target.value))} /></label>
              <div className="ensemble-preview" aria-live="polite"><span>Как увидит клиент</span><strong>{ensembleMemberCount === 2 ? "Пара — выбираются оба персонажа" : `${value.ensemble_included_count} из ${ensembleMemberCount} включены`}</strong><small>{ensembleMemberCount > value.ensemble_included_count ? `Ещё один участник: +${priceFormatter.format(value.ensemble_extra_member_price)} сум` : "Доплаты внутри карточки нет"}</small></div>
            </div>
          ) : null}
        </section>
      ) : null}
      {kind === "show_program" ? (
        <>
          <ProgramFeaturesEditor features={value.program_features} onChange={(next) => field("program_features", next)} source={entity?.program_features_source} />
          <ProgramCastEditor cast={value.program_cast} onChange={(next) => field("program_cast", next)} />
        </>
      ) : null}
      {kind === "show_program" ? (
        <section className="ensemble-editor" aria-labelledby="program-addons-title">
          <div className="ensemble-editor-head">
            <div><p className="eyebrow">ДОПОЛНИТЕЛЬНЫЕ УСЛУГИ</p><h3 id="program-addons-title">Услуги и подарки программы</h3><p>Платные услуги доступны клиенту отдельно. Подарки остаются бесплатными и не увеличивают сумму заказа.</p></div>
          </div>
          {value.addons.length ? value.addons.map((addon) => (
            <article className="admin-surface" key={addon.id}>
              <div className="admin-surface-head">
                <div><h3>{addon.name}</h3><p>+{priceFormatter.format(addon.price)} сум{addon.duration_minutes ? ` · +${addon.duration_minutes} мин` : ""}</p></div>
                <label><input checked={addon.is_available} onChange={(event) => updateAddon(addon.id, { is_available: event.target.checked })} type="checkbox" /> Доступна для шоу</label>
              </div>
              <div className="admin-form-grid">
                <label>Режим<select disabled={!addon.is_available} value={addon.gift_mode} onChange={(event) => updateAddon(addon.id, { gift_mode: event.target.value as Addon["gift_mode"] })}><option value="none">Платная услуга</option><option value="choice_one">Один подарок на выбор</option><option value="bundle_all">Подарок в комплекте</option></select></label>
                <label>Группа подарка<input disabled={!addon.is_available || addon.gift_mode !== "choice_one"} value={addon.gift_group} onChange={(event) => updateAddon(addon.id, { gift_group: event.target.value })} placeholder="default" /></label>
                <label>Порядок<input disabled={!addon.is_available} min={0} type="number" value={addon.sort_order} onChange={(event) => updateAddon(addon.id, { sort_order: Number(event.target.value) })} /></label>
                <label><input checked={addon.is_recommended} disabled={!addon.is_available} onChange={(event) => updateAddon(addon.id, { is_recommended: event.target.checked })} type="checkbox" /> Рекомендуем</label>
                <label><input checked={addon.is_default} disabled={!addon.is_available} onChange={(event) => updateAddon(addon.id, { is_default: event.target.checked })} type="checkbox" /> Выбрана по умолчанию</label>
              </div>
            </article>
          )) : <div className="ensemble-empty"><span><strong>Активных услуг нет</strong><small>Создайте или активируйте услугу в разделе «Доп. услуги».</small></span></div>}
        </section>
      ) : null}
      <div className="taxonomy-picker"><fieldset><legend>Категории</legend>{categories.filter((item) => item.slug !== "all").map((item) => <label key={item.id}><input checked={value.categories.includes(item.slug)} onChange={() => toggleList("categories", item.slug)} type="checkbox" /> {item.name}</label>)}</fieldset><fieldset><legend>Теги</legend>{tags.filter((item) => item.slug !== "all").map((item) => <label key={item.id}><input checked={value.tags.includes(item.slug)} onChange={() => toggleList("tags", item.slug)} type="checkbox" /> {item.name}</label>)}</fieldset></div>
      <div className="seo-fields"><h3>SEO</h3><label>SEO title<input value={value.seo_title} onChange={(event) => field("seo_title", event.target.value)} /></label><label>SEO description<textarea value={value.seo_description} onChange={(event) => field("seo_description", event.target.value)} /></label><label>Поисковые фразы<input value={value.search_terms} onChange={(event) => field("search_terms", event.target.value)} /></label></div>
    </section>
  );
}
