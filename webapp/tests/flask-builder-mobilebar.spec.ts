import { expect, test } from "@playwright/test";

const baseUrl = process.env.FLASK_BASE_URL ?? "http://127.0.0.1:5152";

for (const width of [320, 375, 430, 768, 1023]) {
  test(`mobile builder bar stays above the footer at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 932 });
    await page.goto(`${baseUrl}/party-builder/`, { waitUntil: "networkidle" });
    await page.locator(".v2-builder-mobilebar").waitFor({ state: "visible" });
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(200);

    const state = await page.locator(".v2-builder-mobilebar").evaluate((bar) => {
      const rect = bar.getBoundingClientRect();
      const hitTarget = document.elementFromPoint(
        rect.left + rect.width / 2,
        rect.top + rect.height / 2,
      );
      return {
        position: getComputedStyle(bar).position,
        bottom: rect.bottom,
        viewportHeight: window.innerHeight,
        hitInside: hitTarget === bar || (hitTarget instanceof Node && bar.contains(hitTarget)),
      };
    });

    expect(state.position).toBe("fixed");
    expect(Math.abs(state.bottom - state.viewportHeight)).toBeLessThanOrEqual(1);
    expect(state.hitInside).toBe(true);
  });
}
