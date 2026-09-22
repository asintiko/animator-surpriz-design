import { postAdminSection, type SectionEnvelope } from "@/features/admin/admin-section-kit";
import type { CatalogEntity } from "@/lib/types";

type UploadedMedia = {
  original: { path: string; width: number; height: number; bytes: number; mimeType: string };
  variants: Array<{ path: string; width: number; height: number; bytes: number; format: "webp" | "avif" }>;
};

type UploadEnvelope = {
  authenticated?: boolean;
  success?: boolean;
  message?: string;
  media?: UploadedMedia;
};

/** Thrown when the session expired; callers send the owner back to the login page. */
export class AdminSessionExpired extends Error {}

async function optimizeFile(file: File): Promise<UploadedMedia> {
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
  const result = (await response.json()) as UploadEnvelope;
  if (response.status === 401 || result.authenticated === false) throw new AdminSessionExpired();
  if (!response.ok || !result.success || !result.media) {
    throw new Error(result.message || "Загрузка не выполнена.");
  }
  return result.media;
}

/** Optimize the file and attach it to the card. Returns the new media id.
 *  attach_generated only claims the cover when the card has none, so adding a
 *  photo never steals the cover from the one already chosen. */
export async function uploadEntityPhoto(entity: CatalogEntity, file: File): Promise<number> {
  const media = await optimizeFile(file);
  const preferred = media.variants
    .filter((variant) => variant.format === "webp")
    .toSorted((left, right) => right.width - left.width)[0];
  const display = preferred ?? media.original;

  const attached = await postAdminSection<SectionEnvelope & { media_id?: number }>("media", {
    action: "attach_generated",
    owner_id: entity.id,
    owner_type: entity.entity_type,
    file_path: display.path,
    original_path: media.original.path,
    width: display.width,
    height: display.height,
    bytes: display.bytes,
    mime_type: "mimeType" in display ? display.mimeType : `image/${display.format}`,
    variants: media.variants,
  });
  if (attached.success === false || !attached.media_id) {
    throw new Error(attached.message || "Файл обработан, но не привязан к карточке.");
  }
  return attached.media_id;
}

export async function setEntityCover(entity: CatalogEntity, mediaId: number): Promise<void> {
  const result = await postAdminSection<SectionEnvelope>("media", {
    action: "set_hero",
    media_id: mediaId,
    owner_id: entity.id,
    owner_type: entity.entity_type,
  });
  if (result.success === false) throw new Error(result.message || "Не удалось назначить обложку.");
}

export async function deleteEntityPhoto(mediaId: number): Promise<void> {
  const result = await postAdminSection<SectionEnvelope>("media", { action: "delete", media_id: mediaId });
  if (result.success === false) throw new Error(result.message || "Не удалось удалить фотографию.");
}

export async function updateEntityPhoto(
  entity: CatalogEntity,
  mediaId: number,
  fields: { alt_text?: string; caption?: string; sort_order?: number },
): Promise<void> {
  const result = await postAdminSection<SectionEnvelope>("media", {
    action: "update",
    media_id: mediaId,
    owner_id: entity.id,
    owner_type: entity.entity_type,
    alt_text: fields.alt_text ?? "",
    caption: fields.caption ?? "",
    sort_order: fields.sort_order ?? 0,
  });
  if (result.success === false) throw new Error(result.message || "Не удалось сохранить фотографию.");
}

/** Replace the cover: attach the new file, then let the server swap it in and drop
 *  the old one. Uploading used to only ever append, which is how cards ended up
 *  showing the same character twice — the previous photo stayed in the gallery.
 *  The server reads the current cover itself, so a long-open tab cannot delete the
 *  wrong photo. */
export async function replaceEntityCover(entity: CatalogEntity, file: File): Promise<number> {
  const mediaId = await uploadEntityPhoto(entity, file);
  const result = await postAdminSection<SectionEnvelope>("media", {
    action: "replace_hero",
    media_id: mediaId,
    owner_id: entity.id,
    owner_type: entity.entity_type,
  });
  if (result.success === false) throw new Error(result.message || "Не удалось заменить обложку.");
  return mediaId;
}
