"use client";

import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ImagePlus,
  Minus,
  Monitor,
  MousePointer2,
  Move,
  Plus,
  RotateCcw,
  Save,
  Smartphone,
} from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  type ChangeEvent,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";
import { toast } from "sonner";

import { AdminSessionExpired, replaceEntityCover } from "@/features/admin/entity-media";
import { cropStyle, formatDuration, formatPrice } from "@/lib/catalog";
import { mutateJson } from "@/lib/client/mutate";
import type { CatalogEntity } from "@/lib/types";

type CropMode = "desktop" | "mobile";
type CropProfile = {
  x: number;
  y: number;
  fit: "cover" | "contain";
  zoom: number;
};
type CropProfiles = Record<CropMode, CropProfile>;

function clampOffset(value: number) {
  return Math.min(100, Math.max(0, Math.round(value)));
}

function clampZoom(value: number) {
  return Math.min(200, Math.max(100, Math.round(value)));
}

function readFit(value: unknown, fallback: CropProfile["fit"]): CropProfile["fit"] {
  return value === "cover" || value === "contain" ? value : fallback;
}

function profilesFromEntity(entity: CatalogEntity): CropProfiles {
  const desktop: CropProfile = {
    x: clampOffset(entity.cover_offset_x ?? 50),
    y: clampOffset(entity.cover_offset_y ?? 50),
    fit: readFit(entity.cover_fit, "cover"),
    zoom: clampZoom(entity.image_zoom || 100),
  };
  return {
    desktop,
    mobile: {
      x: clampOffset(entity.mobile_cover_offset_x ?? desktop.x),
      y: clampOffset(entity.mobile_cover_offset_y ?? desktop.y),
      fit: readFit(entity.mobile_cover_fit, desktop.fit),
      zoom: clampZoom(entity.mobile_image_zoom ?? desktop.zoom),
    },
  };
}

/** The editing frame and every public card render through the same helper, so what
 *  the owner drags here is literally what the site paints. */
function previewStyle(profile: CropProfile): CSSProperties {
  return cropStyle(profile);
}

function CropPreviewCard({
  entity,
  mode,
  onSourceError,
  profile,
  source,
}: {
  entity: CatalogEntity;
  mode: CropMode;
  onSourceError?: () => void;
  profile: CropProfile;
  source: string;
}) {
  const isShow = entity.entity_type === "show_program";
  return (
    <article className={`crop-preview ${isShow ? "is-show" : ""} is-${mode}`}>
      <div>
        <Image alt="" fill onError={onSourceError} sizes={mode === "mobile" ? "360px" : "520px"} src={source} style={previewStyle(profile)} unoptimized />
      </div>
      <span className="crop-preview-device">{mode === "mobile" ? <Smartphone /> : <Monitor />} {mode === "mobile" ? "Телефон" : "Компьютер"}</span>
      <h3>{entity.name}</h3>
      <p>{isShow ? `${formatDuration(entity.default_duration_minutes)} · ${formatPrice(entity.base_price)}` : entity.short_description}</p>
    </article>
  );
}

export function MediaCropEditor({ entity }: { entity: CatalogEntity }) {
  const router = useRouter();
  const initialProfiles = useMemo(() => profilesFromEntity(entity), [entity]);
  const [profiles, setProfiles] = useState<CropProfiles>(initialProfiles);
  const [savedProfiles, setSavedProfiles] = useState<CropProfiles>(initialProfiles);
  const [mode, setMode] = useState<CropMode>("desktop");
  const [isDragging, setIsDragging] = useState(false);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const dragStart = useRef<{ pointerId: number; x: number; y: number; baseX: number; baseY: number } | null>(null);
  const [isPending, startTransition] = useTransition();
  const [uploading, setUploading] = useState(false);
  const [sourceBroken, setSourceBroken] = useState(false);
  const hasHero = Boolean(entity.hero_file_path);
  const source = entity.hero_file_path || "/brand/logo.png";
  const isShow = entity.entity_type === "show_program";
  const profile = profiles[mode];
  const aspect = isShow ? (mode === "mobile" ? 16 / 11 : 16 / 10) : mode === "mobile" ? 1 : 4 / 5;
  const hasChanges = JSON.stringify(profiles) !== JSON.stringify(savedProfiles);

  const updateProfile = useCallback((target: CropMode, next: Partial<CropProfile>) => {
    setProfiles((current) => ({
      ...current,
      [target]: { ...current[target], ...next },
    }));
  }, []);

  function changeZoom(delta: number) {
    updateProfile(mode, { zoom: clampZoom(profile.zoom + delta) });
  }

  const nudge = useCallback((x: number, y: number) => {
    setProfiles((current) => ({
      ...current,
      [mode]: {
        ...current[mode],
        x: clampOffset(current[mode].x + x),
        y: clampOffset(current[mode].y + y),
      },
    }));
  }, [mode]);

  function onEditorKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 5 : 1;
    const directions: Partial<Record<string, [number, number]>> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const direction = directions[event.key];
    if (!direction) return;
    event.preventDefault();
    nudge(...direction);
  }

  // Dragging right reveals more of the left edge, so the focus percentage moves the
  // other way. Offsets are measured from where the drag began rather than step by
  // step, so rounding to whole percents never eats part of the movement.
  function startDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (!hasHero || event.button !== 0) return;
    event.preventDefault();
    dragStart.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      baseX: profile.x,
      baseY: profile.y,
    };
    // Capture keeps the drag alive past the frame edge; a pointer the browser no
    // longer tracks makes it throw, and that must not abort the drag itself.
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // no capture — dragging still works while the pointer stays over the frame
    }
    setIsDragging(true);
  }

  function onDrag(event: ReactPointerEvent<HTMLDivElement>) {
    const start = dragStart.current;
    if (!start || start.pointerId !== event.pointerId) return;
    const rect = frameRef.current?.getBoundingClientRect();
    if (!rect?.width || !rect.height) return;
    updateProfile(mode, {
      x: clampOffset(start.baseX - ((event.clientX - start.x) / rect.width) * 100),
      y: clampOffset(start.baseY - ((event.clientY - start.y) / rect.height) * 100),
    });
  }

  function endDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragStart.current?.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragStart.current = null;
    setIsDragging(false);
  }

  // React attaches wheel handlers passively, and a passive listener cannot stop the
  // page from scrolling while the pointer is over the frame.
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const direction = event.deltaY > 0 ? -1 : 1;
      setProfiles((current) => ({
        ...current,
        [mode]: { ...current[mode], zoom: clampZoom(current[mode].zoom + direction * 4) },
      }));
    };
    frame.addEventListener("wheel", onWheel, { passive: false });
    return () => frame.removeEventListener("wheel", onWheel);
  }, [mode]);

  function resetCurrent() {
    updateProfile(mode, { x: 50, y: 50, fit: "cover", zoom: 100 });
  }

  function copyDesktopToMobile() {
    updateProfile("mobile", profiles.desktop);
    setMode("mobile");
  }

  function save() {
    startTransition(async () => {
      try {
        await mutateJson(`/api/admin/entities/${entity.id}/crop`, {
          cover_offset_x: profiles.desktop.x,
          cover_offset_y: profiles.desktop.y,
          cover_fit: profiles.desktop.fit,
          image_zoom: profiles.desktop.zoom,
          mobile_cover_offset_x: profiles.mobile.x,
          mobile_cover_offset_y: profiles.mobile.y,
          mobile_cover_fit: profiles.mobile.fit,
          mobile_image_zoom: profiles.mobile.zoom,
        });

        const response = await fetch(`/api/admin/entities/${entity.id}`, {
          cache: "no-store",
          credentials: "same-origin",
        });
        const result = (await response.json()) as { authenticated?: boolean; success?: boolean; entity?: CatalogEntity; message?: string };
        if (response.status === 401 || result.authenticated === false) {
          window.location.assign("/admin/login");
          return;
        }
        if (!response.ok || !result.success || !result.entity) {
          throw new Error(result.message || "Сервер не вернул сохранённое кадрирование.");
        }
        const persisted = profilesFromEntity(result.entity);
        setProfiles(persisted);
        setSavedProfiles(persisted);
        router.refresh();
        toast.success("Кадрирование сохранено и применено на сайте");
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Не удалось сохранить.");
      }
    });
  }

  async function replaceCover(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await replaceEntityCover(entity, file);
      toast.success(hasHero ? "Обложка заменена" : "Фотография загружена и назначена обложкой");
      router.refresh();
    } catch (error) {
      if (error instanceof AdminSessionExpired) {
        window.location.assign("/admin/login");
        return;
      }
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить фотографию.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="media-editor-grid">
      <section className="admin-surface media-editor-main">
        <div className="admin-surface-head crop-editor-heading">
          <div>
            <p className="eyebrow">РЕДАКТОР ОБЛОЖКИ</p>
            <h2>Кадрирование без потери оригинала</h2>
            <p>Рамка ниже — это в точности та карточка, которую увидят на сайте. Тащите фото мышью, приближайте колёсиком.</p>
          </div>
          <span className={`crop-save-state ${hasChanges ? "is-dirty" : "is-saved"}`}>{hasChanges ? "Есть несохранённые изменения" : "Все изменения сохранены"}</span>
        </div>

        <div className="crop-mode-switch" role="tablist" aria-label="Формат кадрирования">
          <button aria-selected={mode === "desktop"} className={mode === "desktop" ? "is-active" : ""} onClick={() => setMode("desktop")} role="tab" type="button"><Monitor /> Компьютер</button>
          <button aria-selected={mode === "mobile"} className={mode === "mobile" ? "is-active" : ""} onClick={() => setMode("mobile")} role="tab" type="button"><Smartphone /> Телефон</button>
          <button className="crop-copy-button" onClick={copyDesktopToMobile} type="button">Скопировать desktop → mobile</button>
        </div>

        {!hasHero ? (
          <p className="crop-source-warning">У карточки ещё нет обложки — загрузите фотографию, чтобы кадрировать её.</p>
        ) : sourceBroken ? (
          <p className="crop-source-warning">Файл обложки <code>{source}</code> не отдаётся. Проверьте, что статика <code>/surpriz/</code> доступна этому серверу (переменная <code>SURPRIZ_PUBLIC_ASSET_ORIGIN</code>).</p>
        ) : null}

        <div className="cropper-stage" onKeyDown={onEditorKeyDown} tabIndex={0} aria-label="Рабочая область кадрирования. Стрелками — точная настройка.">
          <div
            className={`cropper-frame ${isDragging ? "is-dragging" : ""}`}
            onPointerCancel={endDrag}
            onPointerDown={startDrag}
            onPointerMove={onDrag}
            onPointerUp={endDrag}
            ref={frameRef}
            style={{ aspectRatio: `${aspect}` }}
          >
            <Image alt="" draggable={false} fill onError={() => setSourceBroken(true)} priority sizes="620px" src={source} style={previewStyle(profile)} unoptimized />
          </div>
          <div className="cropper-help"><MousePointer2 /> Перетащить · колёсико — масштаб · стрелки — точная настройка</div>
        </div>

        <div className="crop-controls crop-controls-pro">
          <label>Режим<select value={profile.fit} onChange={(event) => updateProfile(mode, { fit: event.target.value as CropProfile["fit"] })}><option value="cover">Заполнить рамку</option><option value="contain">Показать целиком</option></select></label>
          <div className="crop-zoom-stepper" aria-label="Управление масштабом">
            <span>Масштаб</span>
            <div><button aria-label="Уменьшить" onClick={() => changeZoom(-5)} type="button"><Minus /></button><output>{profile.zoom}%</output><button aria-label="Увеличить" onClick={() => changeZoom(5)} type="button"><Plus /></button></div>
          </div>
          <label className="crop-zoom-control"><span>Точная настройка <output>{profile.zoom}%</output></span><input aria-label="Приближение" min="100" max="200" step="1" type="range" value={profile.zoom} onChange={(event) => updateProfile(mode, { zoom: clampZoom(Number(event.target.value)) })} /></label>
          <div className="crop-nudge-control" aria-label="Перемещение фокуса">
            <span><Move /> Положение</span>
            <div className="crop-nudge-pad">
              <button aria-label="Поднять выше" onClick={() => nudge(0, -1)} type="button"><ChevronUp /></button>
              <button aria-label="Сместить влево" onClick={() => nudge(-1, 0)} type="button"><ChevronLeft /></button>
              <button aria-label="Опустить ниже" onClick={() => nudge(0, 1)} type="button"><ChevronDown /></button>
              <button aria-label="Сместить вправо" onClick={() => nudge(1, 0)} type="button"><ChevronRight /></button>
            </div>
          </div>
        </div>

        <div className="crop-editor-footer">
          <div className="crop-meta"><span>X: <strong>{profile.x}%</strong></span><span>Y: <strong>{profile.y}%</strong></span><span>Масштаб: <strong>{profile.zoom}%</strong></span><span>Режим: <strong>{profile.fit === "cover" ? "Заполнение" : "Целиком"}</strong></span></div>
          <div className="crop-editor-actions"><button className="button button-secondary" onClick={resetCurrent} type="button"><RotateCcw size={17} /> Сбросить текущий кадр</button><button className="button button-violet" disabled={isPending || !hasChanges} onClick={save} type="button"><Save size={17} /> {isPending ? "Сохраняем…" : "Сохранить и применить"}</button></div>
        </div>
      </section>

      <aside className="media-preview-stack">
        <section className="admin-surface">
          <div className="admin-surface-head"><div><p className="eyebrow">РЕЗУЛЬТАТ НА САЙТЕ</p><h2>Живой предпросмотр</h2><p>Эти кадры соответствуют пропорциям публичных карточек.</p></div></div>
          <div className="crop-preview-grid">
            <CropPreviewCard entity={entity} mode="desktop" onSourceError={() => setSourceBroken(true)} profile={profiles.desktop} source={source} />
            <CropPreviewCard entity={entity} mode="mobile" profile={profiles.mobile} source={source} />
          </div>
        </section>
        <section className="admin-surface">
          <div className="media-pipeline"><div><span>Оригинал</span><strong>Хранится без изменений</strong></div><div><span>WebP</span><strong>480 · 768 · 1280 · 1920</strong></div><div><span>AVIF</span><strong>Автоматически</strong></div><div><span>EXIF/GPS</span><strong>Удаляется из вариантов</strong></div></div>
          <label className={`media-upload-button ${uploading ? "is-disabled" : ""}`}><ImagePlus /> {uploading ? "Обрабатываем…" : hasHero ? "Заменить обложку" : "Загрузить фотографию"}<input accept="image/avif,image/jpeg,image/png,image/webp" disabled={uploading} onChange={(event) => void replaceCover(event)} type="file" /></label>
          <p className="media-upload-note">Заменяет текущую обложку, а не добавляет вторую. Чтобы карточка держала несколько фотографий, пользуйтесь блоком ниже.</p>
        </section>
      </aside>
    </div>
  );
}
