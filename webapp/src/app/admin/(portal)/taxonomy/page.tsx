import { AdminTaxonomySection } from "@/features/admin/admin-taxonomy-section";

export default function AdminTaxonomyPage() {
  return <section className="admin-page"><header className="admin-page-head"><div><p className="eyebrow">СТРУКТУРА КАТАЛОГА</p><h1>Категории и теги</h1><p>Навигация, фильтры и тематические подборки сайта.</p></div></header><AdminTaxonomySection /></section>;
}
