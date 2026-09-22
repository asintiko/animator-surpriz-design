import { notFound } from "next/navigation";

import { EntityMediaGallery } from "@/features/admin/entity-media-gallery";
import { MediaCropEditor } from "@/features/admin/media-crop-editor";
import { EntityDetailsForm } from "@/features/admin/entity-details-form";
import { getAdminEntity, getAdminTaxonomy } from "@/lib/server/admin-entities";

export default async function AdminCharacterEditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [character, taxonomy] = await Promise.all([
    getAdminEntity(Number(id)),
    getAdminTaxonomy(),
  ]);
  if (!character || character.entity_type !== "character") notFound();
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">ПЕРСОНАЖ</p><h1>{character.name}</h1><p>Контент, таксономия, SEO, обложка и предпросмотр.</p></div></header><EntityDetailsForm categories={taxonomy.categories} entity={character} kind="character" tags={taxonomy.tags} /><MediaCropEditor entity={character} key={`${character.id}:${character.updated_at}:${character.hero_media_id ?? "none"}`} /><EntityMediaGallery entity={character} key={`gallery:${character.id}:${character.updated_at}`} /></section>;
}
