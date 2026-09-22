import { describe, expect, it } from "vitest";

import { resolveAdminTaxonomy } from "./admin-entities";

const all = { id: 1, name: "Все", slug: "all", description: "", is_system: 1, sort_order: 0 };

describe("resolveAdminTaxonomy", () => {
  it("uses fresh visible filters from the canonical adapter response", () => {
    const taxonomy = resolveAdminTaxonomy(
      {
        success: true,
        categories: [all, { ...all, id: 2, name: "Супергерои", slug: "superheroes", is_system: 0, is_visible: true }],
        tags: [all, { ...all, id: 3, name: "Скрытый", slug: "hidden", is_system: 0, is_visible: false }],
      },
    );

    expect(taxonomy.categories.map((item) => item.slug)).toEqual(["all", "superheroes"]);
    expect(taxonomy.tags.map((item) => item.slug)).toEqual(["all"]);
  });

  it("fails closed when the adapter is unavailable", () => {
    expect(() => resolveAdminTaxonomy(null)).toThrow("Таксономия админки временно недоступна");
  });
});
