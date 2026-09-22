import path from "node:path";

import { expect, test } from "@playwright/test";

const publicRenderer = path.resolve(
  process.cwd(),
  "../../surprizopus/assets/show-programs.js",
);

test("public show catalog applies saved fit and revalidates catalog data", async ({ page }) => {
  await page.setContent(`
    <main>
      <div data-show-list aria-busy="true"></div>
    </main>
  `);

  await page.evaluate(() => {
    Object.defineProperty(window, "__showFetchOptions", {
      configurable: true,
      writable: true,
      value: null,
    });

    window.fetch = async (_input, init) => {
      window.__showFetchOptions = init ?? null;
      return new Response(JSON.stringify({
        shows: [{
          id: "regression-show",
          title: "Тестовая программа",
          description: "Проверка сохранённого кадрирования",
          image: "/media/test.webp",
          image_width: 1200,
          image_height: 1600,
          image_position: { x: 37, y: 64 },
          image_zoom: 135,
          cover_fit: "contain",
          mobile_image_position: { x: 24, y: 71 },
          mobile_image_zoom: 120,
          mobile_cover_fit: "cover",
          href: "/party-builder/?show=regression-show",
          placements: ["catalog"],
          active: true,
        }],
      }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };
  });

  await page.addScriptTag({ path: publicRenderer });

  const image = page.locator("[data-show-id='regression-show'] img");
  await expect(image).toHaveCSS("object-fit", "contain");
  await expect(image).toHaveCSS("object-position", "37% 64%");
  await expect(image).toHaveCSS("--image-zoom", "1.35");
  await expect(image).toHaveCSS("--mobile-image-x", "24%");
  await expect(image).toHaveCSS("--mobile-image-y", "71%");
  await expect(image).toHaveCSS("--mobile-image-fit", "cover");
  await expect(image).toHaveCSS("--mobile-image-zoom", "1.2");

  const cacheMode = await page.evaluate(() => window.__showFetchOptions?.cache);
  expect(cacheMode).toBe("no-cache");
});

declare global {
  interface Window {
    __showFetchOptions: RequestInit | null;
  }
}
