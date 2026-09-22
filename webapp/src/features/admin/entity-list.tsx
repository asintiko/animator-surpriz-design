"use client";

import { ArrowDown, ArrowRight, ArrowUp, ImageIcon, Layers, Plus } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { mutateJson } from "@/lib/client/mutate";

import { entityCropStyle, formatDuration, formatPrice } from "@/lib/catalog";
import type { AdminEntityListItem } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  active: "опубликовано",
  draft: "черновик",
  hidden: "скрыто",
};

type ProgramGroup = {
  slug: string;
  name: string;
  items: AdminEntityListItem[];
};

/** Variants of one programme are separate rows tied together only by
 *  variant_group_slug. Listed flat they read as unrelated programmes — which is why
 *  "Бумажное шоу" looked missing instead of merely hidden. */
function groupByVariant(items: AdminEntityListItem[]) {
  const groups = new Map<string, ProgramGroup>();
  const standalone: AdminEntityListItem[] = [];

  for (const item of items) {
    const slug = String(item.variant_group_slug || "").trim();
    if (!slug) {
      standalone.push(item);
      continue;
    }
    const existing = groups.get(slug);
    if (existing) {
      existing.items.push(item);
      continue;
    }
    groups.set(slug, {
      slug,
      name: String(item.variant_group_name || "").trim() || slug,
      items: [item],
    });
  }

  return { standalone, groups: [...groups.values()] };
}

function EntityCard({
  base,
  item,
  kind,
  position,
}: {
  base: string;
  item: AdminEntityListItem;
  kind: "characters" | "shows";
  position?: number;
}) {
  const heading = kind === "shows" ? String(item.variant_label || "").trim() || item.name : item.name;
  const meta = kind === "shows"
    ? `${formatDuration(item.default_duration_minutes)} · ${formatPrice(item.base_price)}`
    : item.categories.filter((slug) => slug !== "all").join(" · ") || "Без категории";
  return (
    <Link className="admin-entity-card" href={`${base}/${item.id}`}>
      <div className="admin-entity-media">
        {item.hero_file_path ? <Image src={item.hero_file_path} alt="" fill sizes="240px" style={entityCropStyle(item)} unoptimized /> : <ImageIcon />}
        <span className={`content-status status-${item.status}`}>{STATUS_LABELS[item.status] ?? item.status}</span>
        {position ? <span className="admin-entity-position" title="Место формата внутри программы">{position}</span> : null}
      </div>
      <div className="admin-entity-copy">
        <h2>{heading}</h2>
        <p>{meta}</p>
        <span>Открыть редактор <ArrowRight size={16} /></span>
      </div>
    </Link>
  );
}

export function AdminEntityList({
  items,
  kind,
}: {
  items: AdminEntityListItem[];
  kind: "characters" | "shows";
}) {
  const router = useRouter();
  const [reordering, setReordering] = useState("");
  const base = kind === "characters" ? "/admin/catalog/characters" : "/admin/show-programs";
  const activeItems = items.filter((item) => item.status === "active").length;

  /** Swapping neighbours reuses the sort_order slots the group already holds, so the
   *  order of the standalone programmes around it never shifts. */
  function move(group: ProgramGroup, index: number, direction: -1 | 1) {
    const next = [...group.items];
    const current = next[index];
    const target = next[index + direction];
    if (!current || !target) return;
    next[index] = target;
    next[index + direction] = current;
    setReordering(group.slug);
    void mutateJson("/api/admin/entities/reorder", { ids: next.map((item) => item.id) })
      .then(() => {
        toast.success("Порядок форматов обновлён");
        router.refresh();
      })
      .catch((error: unknown) => {
        toast.error(error instanceof Error ? error.message : "Не удалось изменить порядок.");
      })
      .finally(() => setReordering(""));
  }
  const { standalone, groups } = kind === "shows"
    ? groupByVariant(items)
    : { standalone: items, groups: [] as ProgramGroup[] };

  return (
    <>
      <div className="admin-list-toolbar">
        <div><strong>{activeItems}</strong><span>{kind === "characters" ? "активных персонажей" : "активных шоу-программ"}</span></div>
        <Link className="button button-violet" href={`${base}/new`}><Plus size={18} /> Добавить</Link>
      </div>

      {groups.map((group) => (
        <section className="admin-variant-group" key={group.slug}>
          <header className="admin-variant-group-head">
            <div>
              <p className="eyebrow"><Layers size={14} /> ОДНА ПРОГРАММА, НЕСКОЛЬКО ФОРМАТОВ</p>
              <h2>{group.name}</h2>
              <p>{group.items.length} {group.items.length === 1 ? "формат" : "формата"} · на сайте {group.items.filter((item) => item.status === "active").length}</p>
            </div>
            <Link
              className="button button-secondary"
              href={`${base}/new?group_slug=${encodeURIComponent(group.slug)}&group_name=${encodeURIComponent(group.name)}`}
            >
              <Plus size={17} /> Добавить формат
            </Link>
          </header>
          <div className="admin-entity-grid">
            {group.items.map((item, index) => (
              <div className="admin-variant-cell" key={item.id}>
                <EntityCard base={base} item={item} kind={kind} position={index + 1} />
                <div className="admin-variant-order">
                  <button aria-label={`Поднять «${item.variant_label || item.name}»`} disabled={index === 0 || reordering === group.slug} onClick={() => move(group, index, -1)} type="button"><ArrowUp size={14} /></button>
                  <button aria-label={`Опустить «${item.variant_label || item.name}»`} disabled={index === group.items.length - 1 || reordering === group.slug} onClick={() => move(group, index, 1)} type="button"><ArrowDown size={14} /></button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      {standalone.length ? (
        <section className="admin-variant-group">
          {groups.length ? (
            <header className="admin-variant-group-head">
              <div>
                <p className="eyebrow">ОТДЕЛЬНЫЕ ПРОГРАММЫ</p>
                <h2>Без форматов</h2>
                <p>Каждая продаётся сама по себе</p>
              </div>
            </header>
          ) : null}
          <div className="admin-entity-grid">
            {standalone.map((item) => <EntityCard base={base} item={item} key={item.id} kind={kind} />)}
          </div>
        </section>
      ) : null}
    </>
  );
}
