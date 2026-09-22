"use client";

import { Check, ImagePlus, Save, Search, Star, Trash2, Upload } from "lucide-react";
import Image from "next/image";
import { type ChangeEvent, type FormEvent, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  AdminSectionState,
  formatNumber,
  postAdminSection,
  useAdminSection,
  useSectionMutation,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";

type MediaAsset = {
  id: number;
  owner_id: number;
  owner_type: "character" | "show_program" | "addon" | string;
  owner_name: string;
  media_type: "image" | "video" | string;
  file_path: string;
  alt_text?: string;
  caption?: string;
  sort_order?: number;
  is_hero?: boolean;
  width?: number;
  height?: number;
  bytes?: number;
  mime_type?: string;
  processing_status?: string;
  cover_offset_x?: number;
  cover_offset_y?: number;
  cover_fit?: "cover" | "contain";
  image_zoom?: number;
};

type MediaOwner = { id: number; name: string; owner_type: string };
type RawMediaAsset = Partial<MediaAsset> & {
  id: number;
  entity_id?: number;
  entity_name?: string;
  entity_type?: string;
  file_path: string;
};
type MediaPayload = SectionEnvelope & {
  media?: MediaAsset[];
  items?: RawMediaAsset[];
  owners?: MediaOwner[];
  stats?: { originals?: number; optimized?: number; bytes_saved?: number; processing?: number };
};

type UploadResult = SectionEnvelope & {
  media?: {
    original: { path: string; width: number; height: number; bytes: number; mimeType: string };
    variants: Array<{ path: string; width: number; height: number; bytes: number; format: "webp" | "avif" }>;
  };
};

export function AdminMediaSection() {
  const [search, setSearch] = useState("");
  const [ownerType, setOwnerType] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [uploadOwner, setUploadOwner] = useState("");
  const [uploading, setUploading] = useState(false);
  const query = useMemo(() => {
    const value = new URLSearchParams();
    if (search) value.set("search", search);
    if (ownerType) value.set("owner_type", ownerType);
    return value;
  }, [ownerType, search]);
  const section = useAdminSection<MediaPayload>("media", query);
  const mutation = useSectionMutation("media", section.refresh);
  const media = useMemo<MediaAsset[]>(() => {
    if (section.data?.media) return section.data.media;
    return (section.data?.items ?? []).map((item) => ({
      ...item,
      owner_id: item.owner_id ?? item.entity_id ?? 0,
      owner_name: item.owner_name ?? item.entity_name ?? "Без привязки",
      owner_type: item.owner_type ?? item.entity_type ?? "unknown",
      media_type: item.media_type ?? "image",
    }));
  }, [section.data]);
  const selected = media.find((item) => item.id === selectedId) ?? media[0] ?? null;

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    const owner = section.data?.owners?.find((item) => `${item.owner_type}:${item.id}` === uploadOwner);
    event.target.value = "";
    if (!file) return;
    if (!owner) {
      toast.error("Сначала выберите карточку для фотографии.");
      return;
    }
    setUploading(true);
    try {
      const csrfResponse = await fetch("/api/csrf", { cache: "no-store", credentials: "same-origin" });
      if (!csrfResponse.ok) throw new Error("Не удалось подготовить защищённую загрузку.");
      const csrf = (await csrfResponse.json()) as { token: string };
      const body = new FormData();
      body.set("file", file);
      const uploadResponse = await fetch("/api/admin/media/upload", {
        method: "POST",
        credentials: "same-origin",
        headers: { "x-csrf-token": csrf.token },
        body,
      });
      const uploaded = (await uploadResponse.json()) as UploadResult;
      if (uploadResponse.status === 401 || uploaded.authenticated === false) {
        window.location.assign("/admin/login");
        return;
      }
      if (!uploadResponse.ok || !uploaded.success || !uploaded.media) {
        throw new Error(uploaded.message || "Загрузка не выполнена.");
      }
      const variants = uploaded.media.variants;
      const preferred = variants
        .filter((variant) => variant.format === "webp")
        .toSorted((left, right) => right.width - left.width)[0];
      const display = preferred ?? uploaded.media.original;
      const result = await postAdminSection<SectionEnvelope & { media_id?: number }>("media", {
        action: "attach_generated",
        owner_id: owner.id,
        owner_type: owner.owner_type,
        file_path: display.path,
        original_path: uploaded.media.original.path,
        width: display.width,
        height: display.height,
        bytes: display.bytes,
        mime_type: "mimeType" in display ? display.mimeType : `image/${display.format}`,
        variants,
      });
      if (result.success === false) throw new Error(result.message || "Файл обработан, но не привязан к карточке.");
      toast.success(result.message || "Фото оптимизировано и добавлено в карточку");
      if (result.media_id) setSelectedId(result.media_id);
      await section.refresh();
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "Не удалось загрузить фотографию.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <div className="admin-metrics admin-metrics-compact">
        <article><span>Оригиналы</span><strong>{formatNumber(section.data?.stats?.originals ?? media.length)}</strong></article>
        <article><span>Оптимизировано</span><strong>{formatNumber(section.data?.stats?.optimized)}</strong></article>
        <article><span>В обработке</span><strong>{formatNumber(section.data?.stats?.processing)}</strong></article>
        <article><span>Сэкономлено</span><strong>{formatNumber(Math.round((section.data?.stats?.bytes_saved ?? 0) / 1024 / 1024))} МБ</strong></article>
      </div>

      <section className="admin-surface">
        <div className="admin-surface-head"><div><p className="eyebrow">МЕДИАТЕКА</p><h2>Оригиналы и варианты</h2><p>Оригиналы не изменяются; crop и быстрые форматы хранятся отдельно.</p></div></div>
        <div className="admin-filter-bar media-toolbar">
          <label><span>Поиск</span><span className="input-with-icon"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Персонаж, шоу, alt" /></span></label>
          <label><span>Раздел</span><select value={ownerType} onChange={(event) => setOwnerType(event.target.value)}><option value="">Все</option><option value="character">Персонажи</option><option value="show_program">Шоу</option><option value="addon">Доп. услуги</option></select></label>
          <label className="media-owner-select"><span>Добавить в карточку</span><select value={uploadOwner} onChange={(event) => setUploadOwner(event.target.value)}><option value="">Выберите карточку</option>{section.data?.owners?.map((owner) => <option key={`${owner.owner_type}:${owner.id}`} value={`${owner.owner_type}:${owner.id}`}>{owner.name} · {owner.owner_type === "show_program" ? "шоу" : owner.owner_type === "character" ? "персонаж" : "услуга"}</option>)}</select></label>
          <label className={`button button-violet media-upload-trigger ${uploading ? "is-disabled" : ""}`}><Upload size={17} /> {uploading ? "Загрузка…" : "Загрузить"}<input accept="image/avif,image/jpeg,image/png,image/webp" disabled={uploading} onChange={(event) => void upload(event)} type="file" /></label>
        </div>

        <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
        {!section.loading && !section.error && !media.length ? <div className="admin-empty"><ImagePlus /> Медиа по этому фильтру не найдено.</div> : null}
        {media.length ? <div className="admin-media-library">{media.map((item) => <button className={selected?.id === item.id ? "is-selected" : ""} key={item.id} onClick={() => setSelectedId(item.id)} type="button"><span className="admin-media-thumb">{item.media_type === "image" ? <Image alt="" fill sizes="180px" src={item.file_path} style={{ objectFit: "cover" }} unoptimized /> : <span>VIDEO</span>}{item.is_hero ? <b><Star size={14} /> Обложка</b> : null}{item.processing_status ? <em>{item.processing_status}</em> : null}</span><strong>{item.owner_name}</strong><small>{item.width && item.height ? `${item.width}×${item.height}` : item.mime_type || item.media_type}</small></button>)}</div> : null}
      </section>

      {selected ? <MediaWorkspace asset={selected} key={selected.id} pendingKey={mutation.pendingKey} run={mutation.run} /> : null}
    </>
  );
}

function MediaWorkspace({
  asset,
  pendingKey,
  run,
}: {
  asset: MediaAsset;
  pendingKey: string;
  run: (key: string, payload: Record<string, unknown>, successMessage: string) => Promise<SectionEnvelope | null>;
}) {
  const [alt, setAlt] = useState(asset.alt_text ?? "");
  const [caption, setCaption] = useState(asset.caption ?? "");
  const [sortOrder, setSortOrder] = useState(asset.sort_order ?? 0);
  const isShow = asset.owner_type === "show_program";

  function save(event: FormEvent) {
    event.preventDefault();
    void run(`save-${asset.id}`, {
      action: "update",
      media_id: asset.id,
      owner_id: asset.owner_id,
      owner_type: asset.owner_type,
      alt_text: alt,
      caption,
      sort_order: sortOrder,
    }, "Медиа сохранено");
  }

  return (
    <div className="media-editor-grid">
      <section className="admin-surface media-editor-main">
        <div className="admin-surface-head"><div><p className="eyebrow">ФАЙЛ</p><h2>{asset.owner_name}</h2><p>Оригинал {asset.width && asset.height ? `${asset.width}×${asset.height}` : "без изменений"} · кадрирование настраивается в карточке</p></div><span className="content-status">{asset.processing_status || "ready"}</span></div>
        {asset.media_type === "image" ? <div className="media-file-preview"><Image alt={alt} fill sizes="620px" src={asset.file_path} style={{ objectFit: "contain" }} unoptimized /></div> : <div className="admin-empty">Для видео настраиваются обложка и метаданные.</div>}
        <form className="admin-media-form" onSubmit={save}>
          <div className="admin-form-grid"><label>Alt-текст<input value={alt} onChange={(event) => setAlt(event.target.value)} /></label><label>Порядок<input type="number" value={sortOrder} onChange={(event) => setSortOrder(Number(event.target.value))} /></label><label className="wide">Подпись<textarea value={caption} onChange={(event) => setCaption(event.target.value)} /></label></div>
          <div className="admin-row-actions"><button className="button button-violet" disabled={pendingKey === `save-${asset.id}`} type="submit"><Save size={17} /> Сохранить</button>{!asset.is_hero ? <button className="button button-secondary" onClick={() => void run(`hero-${asset.id}`, { action: "set_hero", media_id: asset.id, owner_id: asset.owner_id, owner_type: asset.owner_type }, "Обложка изменена")} type="button"><Star size={17} /> Сделать обложкой</button> : <span className="admin-success-label"><Check size={17} /> Текущая обложка</span>}<button className="button button-danger" onClick={() => { if (window.confirm("Переместить медиа в корзину? Оригинал не будет удалён сразу.")) void run(`delete-${asset.id}`, { action: "delete", media_id: asset.id }, "Медиа перемещено в корзину"); }} type="button"><Trash2 size={17} /> В корзину</button></div>
        </form>
      </section>
      <aside className="media-preview-stack">
        <section className="admin-surface"><div className="admin-surface-head"><div><p className="eyebrow">LIVE PREVIEW</p><h2>{isShow ? "Карточка шоу" : "Карточка персонажа"}</h2></div></div><div className={`crop-preview ${isShow ? "is-show" : ""}`}><div><Image alt={alt} fill sizes="420px" src={asset.file_path} style={{ objectFit: "cover" }} unoptimized /></div><h3>{asset.owner_name}</h3><p>{caption || alt || "Подпись появится здесь"}</p></div></section>
        <section className="admin-surface"><h3>Файл</h3><dl className="admin-detail-list"><div><dt>Тип</dt><dd>{asset.mime_type || asset.media_type}</dd></div><div><dt>Размер</dt><dd>{asset.bytes ? `${formatNumber(Math.round(asset.bytes / 1024))} КБ` : "—"}</dd></div><div><dt>Производные</dt><dd>AVIF · WebP · JPEG</dd></div></dl></section>
      </aside>
    </div>
  );
}
