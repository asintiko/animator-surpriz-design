import type { MetadataRoute } from "next";

import { site } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      // Каталог, сетка шоу и карусели на главной рисуются клиентским fetch к этим
      // двум эндпоинтам. Пока они были закрыты, Googlebot видел хабы пустыми: ноль
      // ссылок на 74 страницы персонажей. Более длинное правило Allow выигрывает
      // у Disallow, поэтому остальное под /api/ остаётся закрытым.
      userAgent: "*",
      allow: ["/", "/api/catalogs", "/api/shows"],
      disallow: ["/admin/", "/account/", "/api/"],
    },
    sitemap: `${site.canonicalUrl}/sitemap.xml`,
    host: site.canonicalUrl,
  };
}
