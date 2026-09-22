import { readFile } from "node:fs/promises";
import path from "node:path";

import { expect, test } from "@playwright/test";

const CROP_FIELDS = [
  "cover_offset_x",
  "cover_offset_y",
  "cover_fit",
  "image_zoom",
  "mobile_cover_offset_x",
  "mobile_cover_offset_y",
  "mobile_cover_fit",
  "mobile_image_zoom",
];

function read(file: string) {
  return readFile(path.join(process.cwd(), file), "utf8");
}

test("the crop editor keeps zoom under its own control", async () => {
  const source = await read("src/features/admin/media-crop-editor.tsx");

  // react-easy-crop recomputed zoom from the crop box on every mount and handed it
  // back through onZoomChange, which silently collapsed a saved 150% to 100%.
  expect(source).not.toMatch(/react-easy-crop/);
  expect(source).not.toMatch(/initialCroppedAreaPercentages/);

  expect(source).toMatch(/type=["']range["']/);
  expect(source).toMatch(/Приближение/);
  expect(source).toMatch(/image_zoom/);
});

test("the crop editor paints through the shared crop formula", async () => {
  const source = await read("src/features/admin/media-crop-editor.tsx");

  // Editor, its preview and the public cards must derive CSS from one helper, or the
  // frame the owner adjusts drifts from what visitors see.
  expect(source).toMatch(/cropStyle/);
  expect(source).toMatch(/from "@\/lib\/catalog"/);
});

test("only the crop endpoint writes cropping", async () => {
  const [form, payload, media] = await Promise.all([
    read("src/features/admin/entity-details-form.tsx"),
    read("src/features/admin/entity-payload.ts"),
    read("src/features/admin/admin-media-section.tsx"),
  ]);

  // The card form used to carry a page-load snapshot of these columns and reverted
  // whatever the crop editor had just saved.
  expect(payload).toMatch(/delete payload\[field\]/);
  for (const field of CROP_FIELDS) {
    expect(media).not.toContain(`${field}:`);
  }
  expect(form).not.toMatch(/\.\.\.entity,/);
});
