import { readFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { mkdtemp } from "node:fs/promises";
import sharp from "sharp";
import { describe, expect, it } from "vitest";

import { processMediaUpload, sanitizeUploadFilename } from "./media";

async function roots() {
  const root = await mkdtemp(path.join(tmpdir(), "surpriz-media-test-"));
  return {
    privateRoot: path.join(root, "private"),
    publicRoot: path.join(root, "public"),
  };
}

describe("processMediaUpload", () => {
  it("preserves the source, applies orientation, strips metadata and deduplicates", async () => {
    const storage = await roots();
    const source = await sharp({
      create: { width: 1200, height: 800, channels: 3, background: "#7c3aed" },
    })
      .jpeg({ quality: 91 })
      .withMetadata({ orientation: 6 })
      .toBuffer();

    const first = await processMediaUpload({
      bytes: source,
      originalFilename: "../../Фото праздника?.jpg",
      ...storage,
    });

    expect(first.deduplicated).toBe(false);
    expect(first.uploadedFilename).toBe("Фото-праздника-.jpg");
    expect(first.original.width).toBe(800);
    expect(first.original.height).toBe(1200);
    expect(first.variants.map(({ width }) => width)).toEqual([
      480, 480, 768, 768, 800, 800,
    ]);
    expect(first.variants.map(({ format }) => format)).toEqual([
      "webp",
      "avif",
      "webp",
      "avif",
      "webp",
      "avif",
    ]);

    const storedOriginal = await readFile(
      path.join(
        storage.privateRoot,
        first.original.path.replace(/^media\//, ""),
      ),
    );
    expect(storedOriginal.equals(source)).toBe(true);
    for (const variant of first.variants) {
      const variantPath = path.join(
        storage.publicRoot,
        variant.path.replace(/^\/media\//, ""),
      );
      const metadata = await sharp(variantPath).metadata();
      expect(metadata.width).toBe(variant.width);
      expect(metadata.height).toBe(variant.height);
      expect(metadata.exif).toBeUndefined();
      expect(metadata.xmp).toBeUndefined();
      expect(metadata.space).toBe("srgb");
      expect((await stat(variantPath)).mode & 0o777).toBe(0o644);
      expect((await stat(path.dirname(variantPath))).mode & 0o777).toBe(0o755);
    }

    const second = await processMediaUpload({
      bytes: source,
      originalFilename: "same-content.jpeg",
      ...storage,
    });
    expect(second.deduplicated).toBe(true);
    expect(second.sourceSha256).toBe(first.sourceSha256);
    expect(second.variants).toEqual(first.variants);
  });

  it("rejects corrupt data regardless of the supplied filename", async () => {
    const storage = await roots();
    await expect(
      processMediaUpload({
        bytes: Buffer.from("not an image"),
        originalFilename: "looks-safe.jpg",
        ...storage,
      }),
    ).rejects.toMatchObject({ code: "decode_failed", status: 415 });
  });

  it("enforces configured dimension and byte limits", async () => {
    const storage = await roots();
    const source = await sharp({
      create: { width: 20, height: 10, channels: 3, background: "white" },
    })
      .png()
      .toBuffer();

    await expect(
      processMediaUpload({
        bytes: source,
        originalFilename: "wide.png",
        ...storage,
        limits: { maxDimension: 15 },
      }),
    ).rejects.toMatchObject({ code: "dimensions_too_large", status: 413 });

    await expect(
      processMediaUpload({
        bytes: source,
        originalFilename: "large.png",
        ...storage,
        limits: { maxBytes: source.byteLength - 1 },
      }),
    ).rejects.toMatchObject({ code: "file_too_large", status: 413 });
  });
});

describe("sanitizeUploadFilename", () => {
  it("removes traversal and control characters", () => {
    expect(sanitizeUploadFilename("../../\u0000party / hero.png")).toBe(
      "hero.png",
    );
  });
});
