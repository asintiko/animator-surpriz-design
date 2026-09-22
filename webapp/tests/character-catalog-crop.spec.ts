import path from "node:path";

import { expect, test } from "@playwright/test";

const catalogRenderer = path.resolve(
  process.cwd(),
  "../../surprizopus/assets/catalog.js",
);

const character = {
  id: "regression-character",
  title: "Тестовый персонаж",
  description: "Проверка сохранённого кадрирования",
  image: "/media/character.webp",
  image_position: { x: 41, y: 22 },
  image_zoom: 145,
  cover_fit: "cover",
  mobile_image_position: { x: 63, y: 18 },
  mobile_image_zoom: 115,
  mobile_cover_fit: "contain",
  href: "/party-builder/?character=regression-character",
  categories: [],
  placements: ["catalog"],
  active: true,
};

test("character catalog applies saved fit, offsets and mobile profile", async ({ page }) => {
  await page.setContent(`
    <main>
      <div data-filters></div>
      <div data-character-grid aria-busy="true"></div>
      <p data-empty hidden></p>
      <input data-character-search />
      <button data-search-clear></button>
      <p data-search-status></p>
    </main>
  `);

  await page.evaluate((payload) => {
    Object.defineProperty(window, "__catalogFetchOptions", { configurable: true, writable: true, value: null });
    window.fetch = async (_input, init) => {
      window.__catalogFetchOptions = init ?? null;
      return new Response(JSON.stringify({ characters: [payload], filters: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };
  }, character);

  await page.addScriptTag({ path: catalogRenderer });

  const image = page.locator(".cat-card img").first();
  await expect(image).toHaveCSS("object-fit", "cover");
  await expect(image).toHaveCSS("object-position", "41% 22%");
  await expect(image).toHaveCSS("--image-zoom", "1.45");
  await expect(image).toHaveCSS("--mobile-image-x", "63%");
  await expect(image).toHaveCSS("--mobile-image-y", "18%");
  await expect(image).toHaveCSS("--mobile-image-fit", "contain");
  await expect(image).toHaveCSS("--mobile-image-zoom", "1.15");

  const cacheMode = await page.evaluate(() => window.__catalogFetchOptions?.cache);
  expect(cacheMode).toBe("no-cache");
});

test("character catalog falls back to contain when the admin never set a fit", async ({ page }) => {
  await page.setContent(`
    <main>
      <div data-filters></div>
      <div data-character-grid aria-busy="true"></div>
      <p data-empty hidden></p>
      <input data-character-search />
      <button data-search-clear></button>
      <p data-search-status></p>
    </main>
  `);

  await page.evaluate((payload) => {
    window.fetch = async () =>
      new Response(JSON.stringify({ characters: [payload], filters: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
  }, { ...character, cover_fit: undefined, mobile_cover_fit: undefined });

  await page.addScriptTag({ path: catalogRenderer });

  const image = page.locator(".cat-card img").first();
  await expect(image).toHaveCSS("object-fit", "contain");
  await expect(image).toHaveCSS("--mobile-image-fit", "contain");
});

declare global {
  interface Window {
    __catalogFetchOptions: RequestInit | null;
  }
}
