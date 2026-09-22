"use client";

import { Eye, EyeOff, ImagePlus, Trash2 } from "lucide-react";
import Image from "next/image";
import { type ChangeEvent, useState } from "react";
import { toast } from "sonner";

import {
  AdminSectionState,
  type SectionEnvelope,
  useAdminSection,
  useSectionMutation,
} from "@/features/admin/admin-section-kit";

type Partner = {
  id: number;
  name: string;
  slug: string;
  logo_path: string;
  link_url: string;
  sort_order: number;
  status: "active" | "hidden";
};

type PartnersPayload = SectionEnvelope & { partners?: Partner[]; items?: Partner[] };

type UploadedMedia = {
  authenticated?: boolean;
  success?: boolean;
  message?: string;
  media?: {
    original: { path: string };
    variants: Array<{ path: string; width: number; format: "webp" | "avif" }>;
  };
};

async function uploadLogo(file: File): Promise<string> {
  const csrfResponse = await fetch("/api/csrf", { cache: "no-store", credentials: "same-origin" });
  if (!csrfResponse.ok) throw new Error("Не удалось подготовить защищённую загрузку.");
  const csrf = (await csrfResponse.json()) as { token: string };
  const body = new FormData();
  body.set("file", file);
  const response = await fetch("/api/admin/media/upload", {
    method: "POST",
    credentials: "same-origin",
    headers: { "x-csrf-token": csrf.token },
    body,
  });
  const uploaded = (await response.json()) as UploadedMedia;
  if (response.status === 401 || uploaded.authenticated === false) {
    window.location.assign("/admin/login");
    throw new Error("Сессия истекла.");
  }
  if (!response.ok || !uploaded.success || !uploaded.media) {
    throw new Error(uploaded.message || "Загрузка не выполнена.");
  }
  const widest = uploaded.media.variants
    .filter((variant) => variant.format === "webp")
    .toSorted((left, right) => right.width - left.width)[0];
  return (widest ?? uploaded.media.original).path;
}

export function AdminPartnersSection() {
  const section = useAdminSection<PartnersPayload>("partners");
  const mutation = useSectionMutation("partners", section.refresh);
  const partners = section.data?.partners ?? section.data?.items ?? [];

  const [name, setName] = useState("");
  const [linkUrl, setLinkUrl] = useState("");
  const [logoPath, setLogoPath] = useState("");
  const [uploading, setUploading] = useState(false);

  async function pickLogo(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      setLogoPath(await uploadLogo(file));
      toast.success("Логотип загружен — осталось сохранить партнёра");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить логотип.");
    } finally {
      setUploading(false);
    }
  }

  async function addPartner() {
    if (!name.trim()) {
      toast.error("Укажите название партнёра.");
      return;
    }
    if (!logoPath) {
      toast.error("Загрузите логотип партнёра.");
      return;
    }
    const result = await mutation.run(
      "create",
      { values: { name: name.trim(), link_url: linkUrl.trim(), logo_path: logoPath } },
      "Партнёр добавлен на главную",
    );
    if (result) {
      setName("");
      setLinkUrl("");
      setLogoPath("");
    }
  }

  return (
    <>
      <section className="admin-surface">
        <div className="admin-surface-head">
          <div>
            <p className="eyebrow">НОВЫЙ ПАРТНЁР</p>
            <h2>Добавить логотип</h2>
            <p>Логотип появится в блоке «Нам доверяют» на главной странице.</p>
          </div>
        </div>
        <div className="partner-form">
          <label>
            Название
            <input onChange={(event) => setName(event.target.value)} placeholder="Central Park" type="text" value={name} />
          </label>
          <label>
            Ссылка (необязательно)
            <input onChange={(event) => setLinkUrl(event.target.value)} placeholder="https://example.uz" type="url" value={linkUrl} />
          </label>
          <label className={`media-upload-button ${uploading ? "is-disabled" : ""}`}>
            <ImagePlus /> {uploading ? "Загружаем…" : logoPath ? "Заменить логотип" : "Загрузить логотип"}
            <input accept="image/avif,image/jpeg,image/png,image/webp" disabled={uploading} onChange={(event) => void pickLogo(event)} type="file" />
          </label>
          {logoPath ? (
            <div className="partner-preview">
              <Image alt="" height={60} sizes="180px" src={logoPath} unoptimized width={130} />
              <span>Логотип готов</span>
            </div>
          ) : null}
          <button
            className="button button-violet"
            disabled={mutation.pendingKey === "create" || uploading}
            onClick={() => void addPartner()}
            type="button"
          >
            {mutation.pendingKey === "create" ? "Добавляем…" : "Добавить партнёра"}
          </button>
        </div>
      </section>

      <section className="admin-surface">
        <div className="admin-surface-head">
          <div>
            <p className="eyebrow">НАМ ДОВЕРЯЮТ</p>
            <h2>Партнёры на главной ({partners.length})</h2>
            <p>Скрытые партнёры остаются в базе, но не показываются на сайте.</p>
          </div>
        </div>
        <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
        {!section.loading && !partners.length ? (
          <div className="admin-empty">Пока ни одного партнёра — добавьте первый логотип выше.</div>
        ) : null}
        <ul className="partner-list">
          {partners.map((partner) => (
            <li className={partner.status === "hidden" ? "is-hidden" : ""} key={partner.id}>
              <div className="partner-list__logo">
                {partner.logo_path ? (
                  <Image alt={partner.name} height={54} sizes="160px" src={partner.logo_path} unoptimized width={120} />
                ) : (
                  <span>нет логотипа</span>
                )}
              </div>
              <div className="partner-list__copy">
                <strong>{partner.name}</strong>
                {partner.link_url ? <a href={partner.link_url} rel="noopener" target="_blank">{partner.link_url}</a> : <span>без ссылки</span>}
              </div>
              <div className="partner-list__actions">
                <button
                  className="button button-secondary"
                  disabled={mutation.pendingKey === `status-${partner.id}`}
                  onClick={() => void mutation.run(
                    `status-${partner.id}`,
                    { id: partner.id, values: { status: partner.status === "active" ? "hidden" : "active" } },
                    partner.status === "active" ? "Партнёр скрыт" : "Партнёр показан на сайте",
                  )}
                  type="button"
                >
                  {partner.status === "active" ? <><EyeOff size={16} /> Скрыть</> : <><Eye size={16} /> Показать</>}
                </button>
                <button
                  className="button button-danger"
                  disabled={mutation.pendingKey === `delete-${partner.id}`}
                  onClick={() => {
                    if (!window.confirm(`Удалить партнёра «${partner.name}»? Логотип пропадёт с главной страницы.`)) return;
                    void mutation.run(`delete-${partner.id}`, { action: "delete", id: partner.id }, "Партнёр удалён");
                  }}
                  type="button"
                >
                  <Trash2 size={16} /> Удалить
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
