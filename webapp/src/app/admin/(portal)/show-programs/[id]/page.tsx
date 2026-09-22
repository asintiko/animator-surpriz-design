import { notFound } from "next/navigation";

import { EntityMediaGallery } from "@/features/admin/entity-media-gallery";
import { MediaCropEditor } from "@/features/admin/media-crop-editor";
import { EntityDetailsForm } from "@/features/admin/entity-details-form";
import { getAdminEntity, getAdminTaxonomy, getVariantGroups } from "@/lib/server/admin-entities";

export default async function AdminShowEditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [show, taxonomy, variantGroups] = await Promise.all([
    getAdminEntity(Number(id)),
    getAdminTaxonomy(),
    getVariantGroups(),
  ]);
  if (!show || show.entity_type !== "show_program") notFound();
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">ШОУ-ПРОГРАММА</p><h1>{show.name}</h1><p>Содержание, цена, состав, форматы, SEO и медиа.</p></div></header><EntityDetailsForm categories={taxonomy.categories} entity={show} kind="show_program" tags={taxonomy.tags} variantGroups={variantGroups} /><MediaCropEditor entity={show} key={`${show.id}:${show.updated_at}:${show.hero_media_id ?? "none"}`} /><EntityMediaGallery entity={show} key={`gallery:${show.id}:${show.updated_at}`} /></section>;
}
