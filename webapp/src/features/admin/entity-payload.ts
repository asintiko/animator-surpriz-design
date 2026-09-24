import type { ProgramFeature } from "@/lib/types";

type EnsembleFields = {
  ensemble_members: unknown;
  ensemble_included_count: number;
  ensemble_extra_member_price: number;
};

const MEMBER_SEPARATOR = /[\n,;]+/;

export function normalizeEnsembleMembers(value: unknown): string[] {
  const candidates = Array.isArray(value) ? value : String(value ?? "").split(MEMBER_SEPARATOR);
  const members: string[] = [];
  const seen = new Set<string>();

  for (const candidate of candidates) {
    const member = String(candidate).trim();
    const key = member.toLocaleLowerCase("ru-RU");
    if (!member || seen.has(key)) continue;
    seen.add(key);
    members.push(member);
  }

  return members;
}

export function normalizeProgramFeatures(features: ProgramFeature[] | undefined): ProgramFeature[] {
  return (features ?? [])
    .map((feature) => ({ icon: feature.icon, text: feature.text.replace(/\s+/g, " ").trim() }))
    .filter((feature) => feature.text);
}

export function normalizeProgramCast(cast: string[] | undefined): string[] {
  return (cast ?? []).map((name) => name.replace(/\s+/g, " ").trim()).filter(Boolean);
}

/** Owned by the crop editor and its own endpoint; the card form must never send
 *  them, or a stale snapshot reverts the cropping that was just saved. */
const CROP_FIELDS = [
  "cover_offset_x",
  "cover_offset_y",
  "cover_fit",
  "image_zoom",
  "mobile_cover_offset_x",
  "mobile_cover_offset_y",
  "mobile_cover_fit",
  "mobile_image_zoom",
] as const;

export function createEntityMutationPayload<T extends EnsembleFields>(
  value: T,
  entityType: "character" | "show_program",
) {
  const members = normalizeEnsembleMembers(value.ensemble_members);
  if (members.length === 1) {
    throw new Error("Для групповой карточки нужны минимум два персонажа.");
  }
  const includedCount = members.length
    ? Math.min(Math.max(2, value.ensemble_included_count), members.length)
    : 2;

  const payload: Record<string, unknown> = {
    ...value,
    entity_type: entityType,
    ensemble_members: members.join("\n"),
    ensemble_included_count: includedCount,
    ensemble_extra_member_price: Math.max(0, value.ensemble_extra_member_price),
  };
  for (const field of CROP_FIELDS) delete payload[field];
  if (entityType === "show_program") {
    const features = normalizeProgramFeatures(payload.program_features as ProgramFeature[] | undefined);
    payload.program_features = features;
    payload.program_cast = normalizeProgramCast(payload.program_cast as string[] | undefined);
    // The legacy text feeds listing cards and the builder; an emptied list must
    // clear it too, or the site would fall back to the old items.
    payload.included_items = features.map((feature) => feature.text).join("; ");
  } else {
    delete payload.program_features;
    delete payload.program_cast;
  }
  delete payload.program_features_source;
  return payload;
}
