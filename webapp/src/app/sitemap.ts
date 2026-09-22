import type { MetadataRoute } from "next";

import { getCatalogSnapshot } from "@/lib/catalog";
import { site } from "@/lib/site";

/** The catalog changes whenever the owner adds a character, so the sitemap is
 *  rebuilt hourly instead of being frozen into the deployment. */
export const revalidate = 3600;

type CatalogItem = { detail_href?: string; id?: string };
type LiveCatalog = { characters?: CatalogItem[]; shows?: CatalogItem[] };

/** The public catalog endpoint already returns detail links with the trailing
 *  slash the canonical tags use, so the sitemap stops pointing at redirects. */
async function loadLiveCatalog(): Promise<LiveCatalog | null> {
  try {
    const response = await fetch(`${site.canonicalUrl}/api/catalogs`, {
      next: { revalidate },
    });
    if (!response.ok) return null;
    return (await response.json()) as LiveCatalog;
  } catch {
    return null;
  }
}

function detailUrls(items: CatalogItem[] | undefined, prefix: string): string[] {
  return (items ?? [])
    .map((item) => {
      const href = String(item.detail_href || "").trim();
      if (href) return href;
      const slug = String(item.id || "").trim();
      return slug ? `${prefix}${slug}/` : "";
    })
    .filter(Boolean)
    .map((href) => `${site.canonicalUrl}${href}`);
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const live = await loadLiveCatalog();
  // Falling back to the bundled snapshot keeps a build green when the site is
  // unreachable; it is stale, which is exactly why it is only the fallback.
  const snapshot = live ? null : getCatalogSnapshot();

  const characterUrls = live
    ? detailUrls(live.characters, "/character/")
    : (snapshot?.characters ?? []).map((item) => `${site.canonicalUrl}/character/${item.slug}/`);
  const showUrls = live
    ? detailUrls(live.shows, "/show-programs/")
    : (snapshot?.shows ?? []).map((item) => `${site.canonicalUrl}/show-programs/${item.slug}/`);

  const publicRoutes = [
    "/",
    "/catalog/",
    "/show-programs/",
    "/prices/",
    "/o-nas/",
    "/contacts/",
    "/party-builder/",
  ];

  // lastModified is deliberately absent: the only date available was the
  // snapshot's build time, and a wrong date is worse than none.
  return [
    ...publicRoutes.map((route) => ({
      url: `${site.canonicalUrl}${route}`,
      changeFrequency: route === "/" ? ("weekly" as const) : ("monthly" as const),
      priority: route === "/" ? 1 : route === "/catalog/" || route === "/show-programs/" ? 0.9 : 0.7,
    })),
    ...characterUrls.map((url) => ({
      url,
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
    ...showUrls.map((url) => ({
      url,
      changeFrequency: "monthly" as const,
      priority: 0.85,
    })),
  ];
}
