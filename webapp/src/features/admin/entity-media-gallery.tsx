"use client";

import { ArrowDown, ArrowUp, Check, ImagePlus, Star, Trash2 } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { type ChangeEvent, useState, useTransition } from "react";
import { toast } from "sonner";

import {
  AdminSessionExpired,
  deleteEntityPhoto,
  setEntityCover,
  updateEntityPhoto,
  uploadEntityPhoto,
} from "@/features/admin/entity-media";
import type { CatalogEntity, MediaItem } from "@/lib/types";

function toLogin() {
  window.location.assign("/admin/login");
}

export function EntityMediaGallery({ entity }: { entity: CatalogEntity }) {
  const router = useRouter();
  const photos = [...(entity.media ?? [])].sort((left, right) =>
    left.sort_order - right.sort_order || left.id - right.id,
  );
  const [busy, setBusy] = useState<string>("");
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);
  const [altDrafts, setAltDrafts] = useState<Record<number, string>>({});
  const [uploading, setUploading] = useState(false);
  const [, startTransition] = useTransition();

  function run(key: string, work: () => Promise<void>, success: string) {
    setBusy(key);
    startTransition(async () => {
      try {
        await work();
        toast.success(success);
        router.refresh();
      } catch (error) {
        if (error instanceof AdminSessionExpired) {
          toLogin();
          return;
        }
        toast.error(error instanceof Error ? error.message : "Не удалось выполнить действие.");
      } finally {
        setBusy("");
        setConfirmingDelete(null);
      }
    });
  }

  async function add(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await uploadEntityPhoto(entity, file);
      toast.success("Фотография добавлена");
      router.refresh();
    } catch (error) {
      if (error instanceof AdminSessionExpired) {
        toLogin();
        return;
      }
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить фотографию.");
    } finally {
      setUploading(false);
    }
  }

  /** Order drives the public gallery, so swapping two neighbours is enough. */
  function move(index: number, direction: -1 | 1) {
    const target = photos[index + direction];
    const current = photos[index];
    if (!target || !current) return;
    run(`move-${current.id}`, async () => {
      await updateEntityPhoto(entity, current.id, {
        alt_text: current.alt_text,
        caption: current.caption,
        sort_order: target.sort_order,
      });
      await updateEntityPhoto(entity, target.id, {
        alt_text: target.alt_text,
        caption: target.caption,
        sort_order: current.sort_order,
      });
    }, "Порядок изменён");
  }

  function saveAlt(photo: MediaItem) {
    const next = altDrafts[photo.id] ?? photo.alt_text;
    run(`alt-${photo.id}`, () => updateEntityPhoto(entity, photo.id, {
      alt_text: next,
      caption: photo.caption,
      sort_order: photo.sort_order,
    }), "Подпись сохранена");
  }

  return (
    <section className="admin-surface entity-media-gallery">
      <div className="admin-surface-head">
        <div>
          <p className="eyebrow">ФОТОГРАФИИ КАРТОЧКИ</p>
          <h2>{photos.length ? `${photos.length} на карточке` : "Пока ни одной"}</h2>
          <p>Первая по порядку открывается в галерее первой. Обложка — то, что видно на карточках каталога.</p>
        </div>
        <label className={`button button-violet media-upload-button ${uploading ? "is-disabled" : ""}`}>
          <ImagePlus size={17} /> {uploading ? "Обрабатываем…" : "Добавить фотографию"}
          <input accept="image/avif,image/jpeg,image/png,image/webp" disabled={uploading} onChange={(event) => void add(event)} type="file" />
        </label>
      </div>

      {photos.length ? (
        <ul className="entity-media-list">
          {photos.map((photo, index) => {
            const isCover = entity.hero_media_id === photo.id;
            const alt = altDrafts[photo.id] ?? photo.alt_text;
            const altChanged = alt !== photo.alt_text;
            return (
              <li className={`entity-media-item ${isCover ? "is-cover" : ""}`} key={photo.id}>
                <div className="entity-media-thumb">
                  <Image alt={photo.alt_text} fill sizes="220px" src={photo.file_path} style={{ objectFit: "contain" }} unoptimized />
                  {isCover ? <span className="entity-media-badge"><Star size={13} /> Обложка</span> : null}
                </div>

                <div className="entity-media-body">
                  <label>Подпись для поиска и незрячих
                    <input
                      onChange={(event) => setAltDrafts((current) => ({ ...current, [photo.id]: event.target.value }))}
                      value={alt}
                    />
                  </label>

                  <div className="entity-media-actions">
                    {altChanged ? (
                      <button className="button button-violet" disabled={busy === `alt-${photo.id}`} onClick={() => saveAlt(photo)} type="button">
                        <Check size={16} /> Сохранить подпись
                      </button>
                    ) : null}

                    {!isCover ? (
                      <button className="button button-secondary" disabled={busy === `cover-${photo.id}`} onClick={() => run(`cover-${photo.id}`, () => setEntityCover(entity, photo.id), "Обложка изменена")} type="button">
                        <Star size={16} /> Сделать обложкой
                      </button>
                    ) : null}

                    <button aria-label="Выше" className="button button-secondary" disabled={index === 0 || busy.startsWith("move-")} onClick={() => move(index, -1)} type="button">
                      <ArrowUp size={16} />
                    </button>
                    <button aria-label="Ниже" className="button button-secondary" disabled={index === photos.length - 1 || busy.startsWith("move-")} onClick={() => move(index, 1)} type="button">
                      <ArrowDown size={16} />
                    </button>

                    {confirmingDelete === photo.id ? (
                      <>
                        <button className="button button-danger" disabled={busy === `delete-${photo.id}`} onClick={() => run(`delete-${photo.id}`, () => deleteEntityPhoto(photo.id), "Фотография удалена")} type="button">
                          <Trash2 size={16} /> Подтверждаю
                        </button>
                        <button className="button button-secondary" onClick={() => setConfirmingDelete(null)} type="button">Отмена</button>
                      </>
                    ) : (
                      <button className="button button-secondary" onClick={() => setConfirmingDelete(photo.id)} type="button">
                        <Trash2 size={16} /> Удалить
                      </button>
                    )}
                  </div>

                  {isCover && photos.length > 1 ? (
                    <p className="entity-media-hint">Удалите обложку — её место займёт следующая фотография.</p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="admin-empty">Загрузите первую фотографию — она сразу станет обложкой.</p>
      )}
    </section>
  );
}
