"use client";

import { ArrowDown, ArrowUp, Save, X } from "lucide-react";
import { useState } from "react";

import {
  AdminSectionState,
  type SectionEnvelope,
  useAdminSection,
  useSectionMutation,
} from "@/features/admin/admin-section-kit";

type CatalogItem = { slug: string; name: string; status: string };
type CatalogBlock = { items: CatalogItem[]; featured: string[] };
type RecommendationsPayload = SectionEnvelope & {
  homepage_slots?: number;
  characters?: CatalogBlock;
  shows?: CatalogBlock;
};

type Kind = "character" | "show_program";

function CatalogPicker({
  block,
  busy,
  kind,
  onSave,
  slots,
  title,
  subtitle,
}: {
  block: CatalogBlock;
  busy: boolean;
  kind: Kind;
  onSave: (kind: Kind, featured: string[]) => Promise<void>;
  slots: number;
  title: string;
  subtitle: string;
}) {
  // Remounted via key when the server answer changes, so the draft resets
  // without an effect writing state back.
  const [featured, setFeatured] = useState<string[]>(block.featured);

  const bySlug = new Map(block.items.map((item) => [item.slug, item]));
  const rest = block.items.filter((item) => !featured.includes(item.slug));
  const dirty = featured.join("|") !== block.featured.join("|");

  function toggle(slug: string) {
    setFeatured((current) =>
      current.includes(slug) ? current.filter((item) => item !== slug) : [...current, slug],
    );
  }

  function move(index: number, delta: number) {
    setFeatured((current) => {
      const target = index + delta;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      const moved = next.splice(index, 1)[0];
      if (moved === undefined) return current;
      next.splice(target, 0, moved);
      return next;
    });
  }

  return (
    <section className="admin-surface">
      <div className="admin-surface-head">
        <div>
          <p className="eyebrow">{title}</p>
          <h2>Порядок показа</h2>
          <p>{subtitle}</p>
        </div>
        <button
          className="button button-violet"
          disabled={busy || !dirty}
          onClick={() => void onSave(kind, featured)}
          type="button"
        >
          <Save size={17} /> {busy ? "Сохраняем…" : "Сохранить порядок"}
        </button>
      </div>

      <ol className="recommend-order">
        {featured.map((slug, index) => (
          <li className={index < slots ? "is-homepage" : ""} key={slug}>
            <span className="recommend-order__num">{index + 1}</span>
            <span className="recommend-order__name">
              {bySlug.get(slug)?.name ?? slug}
              {index < slots ? <small>на главной</small> : null}
            </span>
            <span className="recommend-order__actions">
              <button aria-label="Выше" disabled={index === 0} onClick={() => move(index, -1)} type="button"><ArrowUp size={15} /></button>
              <button aria-label="Ниже" disabled={index === featured.length - 1} onClick={() => move(index, 1)} type="button"><ArrowDown size={15} /></button>
              <button aria-label="Убрать" onClick={() => toggle(slug)} type="button"><X size={15} /></button>
            </span>
          </li>
        ))}
      </ol>
      {!featured.length ? (
        <div className="admin-empty">Ничего не выбрано — отметьте карточки ниже, порядок задаётся кликами.</div>
      ) : null}

      <p className="recommend-hint">
        Отмечайте в том порядке, в котором хотите видеть. Первые {slots} попадут в карусель на главной,
        остальные отмеченные встанут в начало каталога. Неотмеченные идут после них.
      </p>

      <div className="recommend-pool">
        {rest.map((item) => (
          <button className="recommend-chip" key={item.slug} onClick={() => toggle(item.slug)} type="button">
            {item.name}
            {item.status !== "active" ? <small>скрыт</small> : null}
          </button>
        ))}
        {!rest.length ? <span className="recommend-hint">Все карточки уже в списке.</span> : null}
      </div>
    </section>
  );
}

export function AdminRecommendationsSection() {
  const section = useAdminSection<RecommendationsPayload>("recommendations");
  const mutation = useSectionMutation("recommendations", section.refresh);
  const slots = section.data?.homepage_slots ?? 8;

  async function save(kind: Kind, featured: string[]) {
    await mutation.run(
      `save-${kind}`,
      { entity_type: kind, featured },
      kind === "character" ? "Порядок персонажей сохранён" : "Порядок шоу-программ сохранён",
    );
  }

  return (
    <>
      <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
      {section.data?.characters ? (
        <CatalogPicker
          block={section.data.characters}
          key={`character:${section.data.characters.featured.join("|")}`}
          busy={mutation.pendingKey === "save-character"}
          kind="character"
          onSave={save}
          slots={slots}
          subtitle="Эти персонажи открывают каталог, первые — крутятся на главной."
          title="ПЕРСОНАЖИ"
        />
      ) : null}
      {section.data?.shows ? (
        <CatalogPicker
          block={section.data.shows}
          key={`show:${section.data.shows.featured.join("|")}`}
          busy={mutation.pendingKey === "save-show_program"}
          kind="show_program"
          onSave={save}
          slots={slots}
          subtitle="Порядок шоу-программ в каталоге и в карусели на главной."
          title="ШОУ-ПРОГРАММЫ"
        />
      ) : null}
    </>
  );
}
