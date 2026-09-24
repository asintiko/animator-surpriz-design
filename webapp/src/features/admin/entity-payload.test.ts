import { describe, expect, it } from "vitest";

import { createEntityMutationPayload, normalizeEnsembleMembers } from "./entity-payload";

describe("normalizeEnsembleMembers", () => {
  it("accepts adapter arrays and canonical text without duplicate members", () => {
    expect(normalizeEnsembleMembers(["Анна", " Эльза ", "анна", "Олаф"])).toEqual([
      "Анна",
      "Эльза",
      "Олаф",
    ]);
    expect(normalizeEnsembleMembers("Леди Баг, Супер-Кот\nЛеди Баг")).toEqual([
      "Леди Баг",
      "Супер-Кот",
    ]);
  });
});

describe("createEntityMutationPayload", () => {
  it("preserves the adapter's snake_case ensemble contract", () => {
    const payload = createEntityMutationPayload(
      {
        name: "Анна, Эльза и Олаф",
        ensemble_members: ["Анна", "Эльза", "Олаф"],
        ensemble_included_count: 2,
        ensemble_extra_member_price: 300_000,
      },
      "character",
    );

    expect(payload).toMatchObject({
      entity_type: "character",
      ensemble_members: "Анна\nЭльза\nОлаф",
      ensemble_included_count: 2,
      ensemble_extra_member_price: 300_000,
    });
    expect(payload).not.toHaveProperty("ensembleMembers");
  });

  it("clamps included members and prices before sending to the adapter", () => {
    const payload = createEntityMutationPayload(
      {
        ensemble_members: ["Микки", "Минни"],
        ensemble_included_count: 5,
        ensemble_extra_member_price: -1,
      },
      "character",
    );

    expect(payload.ensemble_included_count).toBe(2);
    expect(payload.ensemble_extra_member_price).toBe(0);
  });

  it("never sends cropping, even when the form state still carries it", () => {
    const payload = createEntityMutationPayload(
      {
        ensemble_members: [],
        ensemble_included_count: 2,
        ensemble_extra_member_price: 0,
        cover_offset_x: 48,
        cover_offset_y: 57,
        cover_fit: "contain",
        image_zoom: 120,
        mobile_cover_offset_x: 50,
        mobile_cover_offset_y: 40,
        mobile_cover_fit: "contain",
        mobile_image_zoom: 125,
      },
      "character",
    );

    for (const field of [
      "cover_offset_x",
      "cover_offset_y",
      "cover_fit",
      "image_zoom",
      "mobile_cover_offset_x",
      "mobile_cover_offset_y",
      "mobile_cover_fit",
      "mobile_image_zoom",
    ]) {
      expect(payload).not.toHaveProperty(field);
    }
  });

  it("cannot persist an ambiguous one-member group", () => {
    expect(() => createEntityMutationPayload(
      {
        ensemble_members: ["Олаф"],
        ensemble_included_count: 2,
        ensemble_extra_member_price: 300_000,
      },
      "character",
    )).toThrow("минимум два персонажа");
  });
});

describe("show program content", () => {
  const base = { ensemble_members: [], ensemble_included_count: 2, ensemble_extra_member_price: 0 };

  it("trims items, drops blanks and keeps the legacy text in sync", () => {
    const payload = createEntityMutationPayload(
      {
        ...base,
        included_items: "старый текст",
        program_features: [
          { icon: "note", text: "  1   диджей " },
          { icon: "gift", text: "   " },
          { icon: "star", text: "4 прожектора" },
        ],
        program_cast: [" Ведущий ", "", "Охранник"],
        program_features_source: "text",
      },
      "show_program",
    );

    expect(payload.program_features).toEqual([
      { icon: "note", text: "1 диджей" },
      { icon: "star", text: "4 прожектора" },
    ]);
    expect(payload.program_cast).toEqual(["Ведущий", "Охранник"]);
    expect(payload.included_items).toBe("1 диджей; 4 прожектора");
    expect(payload).not.toHaveProperty("program_features_source");
  });

  it("clears the legacy text when every item was removed", () => {
    const payload = createEntityMutationPayload(
      { ...base, included_items: "1 диджей", program_features: [], program_cast: [] },
      "show_program",
    );
    expect(payload.included_items).toBe("");
  });

  it("never sends show content for characters", () => {
    const payload = createEntityMutationPayload(
      { ...base, program_features: [{ icon: "note", text: "x" }], program_cast: ["y"] },
      "character",
    );
    expect(payload).not.toHaveProperty("program_features");
    expect(payload).not.toHaveProperty("program_cast");
  });
});
