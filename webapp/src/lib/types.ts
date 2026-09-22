export type MediaItem = {
  id: number;
  character_id: number;
  media_type: "image" | "video" | string;
  file_path: string;
  alt_text: string;
  caption: string;
  sort_order: number;
};

export type Addon = {
  id: number;
  status: string;
  name: string;
  slug: string;
  price: number;
  duration_minutes: number;
  image_path: string;
  short_description: string;
  is_available: boolean;
  is_recommended: boolean;
  is_default: boolean;
  is_free_choice: boolean;
  gift_mode: "none" | "choice_one" | "bundle_all";
  gift_group: string;
  sort_order: number;
};

export type PartyOrderAddon = {
  addon_id: number | null;
  slug: string;
  name: string;
  price: number;
  price_label: string;
  duration_minutes: number;
  duration_label: string;
  sort_order: number;
};

export type Promotion = {
  id: number;
  title: string;
  short_text: string;
  badge_text: string;
  tooltip_text: string;
  sort_order: number;
};

export type CatalogEntity = {
  id: number;
  name: string;
  slug: string;
  short_description: string;
  description: string;
  seo_title: string;
  seo_description: string;
  search_terms: string;
  duplicate_count: number;
  contact_phone: string;
  telegram_url: string;
  base_price: number;
  default_duration_minutes: number;
  sort_order: number;
  age_from: number | null;
  age_to: number | null;
  show_category: string;
  format_tags: string;
  included_items: string;
  suitable_for: string;
  restrictions: string;
  video_url: string;
  status: string;
  entity_type: "character" | "show_program";
  hero_media_id: number | null;
  source_path: string;
  created_at: string;
  updated_at: string;
  variant_group_slug: string;
  variant_group_name: string;
  variant_label: string;
  cover_offset_x: number;
  cover_offset_y: number;
  cover_fit: "cover" | "contain";
  image_zoom: number;
  mobile_cover_offset_x: number;
  mobile_cover_offset_y: number;
  mobile_cover_fit: "cover" | "contain";
  mobile_image_zoom: number;
  included_characters_count: number;
  extra_character_price_3: number;
  extra_character_price_4_plus: number;
  ensemble_members: string[];
  ensemble_included_count: number;
  ensemble_extra_member_price: number;
  media: MediaItem[];
  categories: string[];
  tags: string[];
  linked_character_slugs: string[];
  addons: Addon[];
  promotions: Promotion[];
  hero_file_path: string;
};

export type TaxonomyItem = {
  id: number;
  name: string;
  slug: string;
  description: string;
  is_system: number;
  is_visible?: boolean;
  sort_order: number;
};

export type CatalogSnapshot = {
  generated_at: string;
  source: string;
  characters: CatalogEntity[];
  shows: CatalogEntity[];
  categories: TaxonomyItem[];
  tags: TaxonomyItem[];
  settings: Record<string, string>;
};

export type CatalogCard = Pick<
  CatalogEntity,
  | "id"
  | "name"
  | "slug"
  | "short_description"
  | "base_price"
  | "default_duration_minutes"
  | "age_from"
  | "age_to"
  | "entity_type"
  | "hero_file_path"
  | "cover_offset_x"
  | "cover_offset_y"
  | "cover_fit"
  | "image_zoom"
  | "mobile_cover_offset_x"
  | "mobile_cover_offset_y"
  | "mobile_cover_fit"
  | "mobile_image_zoom"
  | "included_characters_count"
  | "extra_character_price_3"
  | "extra_character_price_4_plus"
  | "categories"
  | "tags"
  | "promotions"
>;

export type AdminEntityListItem = Pick<
  CatalogEntity,
  | "id"
  | "name"
  | "status"
  | "hero_file_path"
  | "cover_fit"
  | "cover_offset_x"
  | "cover_offset_y"
  | "image_zoom"
  | "mobile_cover_offset_x"
  | "mobile_cover_offset_y"
  | "mobile_cover_fit"
  | "mobile_image_zoom"
  | "base_price"
  | "default_duration_minutes"
  | "categories"
  | "variant_group_slug"
  | "variant_group_name"
  | "variant_label"
>;
