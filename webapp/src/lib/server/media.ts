import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { chmod, link, lstat, mkdir, open, readFile, unlink } from "node:fs/promises";
import path from "node:path";

import sharp, { type Metadata, type OutputInfo } from "sharp";

export const MEDIA_PIPELINE_VERSION = "v1-sharp035";
export const MEDIA_VARIANT_WIDTHS = [480, 768, 1280, 1920] as const;
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
export const MAX_IMAGE_DIMENSION = 16_000;
export const MAX_INPUT_PIXELS = 100_000_000;

const WEBP_QUALITY = 82;
const AVIF_QUALITY = 60;
const PUBLIC_MEDIA_PREFIX = "/media/";

type InputFormat = "jpeg" | "png" | "webp" | "avif";
type VariantFormat = "webp" | "avif";

export interface StoredOriginal {
  path: string;
  sha256: string;
  format: InputFormat;
  mimeType: string;
  width: number;
  height: number;
  bytes: number;
}

export interface StoredVariant {
  path: string;
  sha256: string;
  format: VariantFormat;
  width: number;
  height: number;
  bytes: number;
  quality: number;
}

export interface MediaManifest {
  version: typeof MEDIA_PIPELINE_VERSION;
  sourceSha256: string;
  configuredWidths: number[];
  original: StoredOriginal;
  variants: StoredVariant[];
}

export interface MediaUploadResult extends MediaManifest {
  deduplicated: boolean;
  uploadedFilename: string;
  manifestPath: string;
}

export interface ProcessMediaUploadInput {
  bytes: Buffer;
  originalFilename: string;
  privateRoot?: string;
  publicRoot?: string;
  limits?: Partial<{
    maxBytes: number;
    maxDimension: number;
    maxPixels: number;
  }>;
}

export class MediaValidationError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status = 400) {
    super(message);
    this.name = "MediaValidationError";
    this.code = code;
    this.status = status;
  }
}

export class MediaStorageIntegrityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MediaStorageIntegrityError";
  }
}

function sha256(value: Buffer | string): string {
  return createHash("sha256").update(value).digest("hex");
}

async function sha256File(filePath: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(filePath)) {
    digest.update(chunk);
  }
  return digest.digest("hex");
}

export function sanitizeUploadFilename(value: string): string {
  const normalized = value
    .normalize("NFKC")
    .replace(/[\u0000-\u001f\u007f]/g, "");
  const basename =
    normalized
      .split(/[\\/]+/)
      .filter(Boolean)
      .at(-1) ?? "";
  const safe = basename
    .replace(/[^\p{L}\p{N}._-]+/gu, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^[._-]+/, "")
    .replace(/[.-]+$/, "")
    .slice(0, 128);
  return safe || "upload";
}

function mediaRoots(input: ProcessMediaUploadInput): {
  privateRoot: string;
  publicRoot: string;
} {
  const privateRoot = path.resolve(
    /* turbopackIgnore: true */
    input.privateRoot ??
      process.env.SURPRIZ_MEDIA_PRIVATE_ROOT ??
      path.join(process.cwd(), "media"),
  );
  const publicRoot = path.resolve(
    /* turbopackIgnore: true */
    input.publicRoot ??
      process.env.SURPRIZ_MEDIA_PUBLIC_ROOT ??
      path.join(process.cwd(), "public/media"),
  );
  return { privateRoot, publicRoot };
}

function insideRoot(root: string, ...segments: string[]): string {
  const destination = path.resolve(/* turbopackIgnore: true */ root, ...segments);
  if (destination !== root && !destination.startsWith(`${root}${path.sep}`)) {
    throw new MediaStorageIntegrityError(
      "Media path escaped its configured storage root.",
    );
  }
  return destination;
}

function inputFormat(metadata: Metadata): {
  format: InputFormat;
  extension: string;
  mimeType: string;
} {
  if (metadata.format === "jpeg") {
    return { format: "jpeg", extension: "jpg", mimeType: "image/jpeg" };
  }
  if (metadata.format === "png") {
    return { format: "png", extension: "png", mimeType: "image/png" };
  }
  if (metadata.format === "webp") {
    return { format: "webp", extension: "webp", mimeType: "image/webp" };
  }
  if (metadata.format === "heif" && metadata.compression === "av1") {
    return { format: "avif", extension: "avif", mimeType: "image/avif" };
  }
  throw new MediaValidationError(
    "Поддерживаются только JPEG, PNG, WebP и AVIF.",
    "unsupported_format",
    415,
  );
}

function orientedDimensions(metadata: Metadata): {
  width: number;
  height: number;
} {
  const width = metadata.autoOrient?.width ?? metadata.width;
  const height = metadata.autoOrient?.height ?? metadata.height;
  if (
    !Number.isSafeInteger(width) ||
    !Number.isSafeInteger(height) ||
    width <= 0 ||
    height <= 0
  ) {
    throw new MediaValidationError(
      "Не удалось определить размеры изображения.",
      "invalid_dimensions",
      415,
    );
  }
  return { width, height };
}

async function validateDecode(
  bytes: Buffer,
  maxPixels: number,
): Promise<Metadata> {
  let metadata: Metadata;
  try {
    const image = sharp(bytes, {
      animated: false,
      failOn: "error",
      limitInputPixels: maxPixels,
      sequentialRead: true,
    });
    metadata = await image.metadata();
    if ((metadata.pages ?? 1) !== 1) {
      throw new MediaValidationError(
        "Анимированные и многостраничные изображения не поддерживаются.",
        "multiple_frames",
        415,
      );
    }
    inputFormat(metadata);
    const dimensions = orientedDimensions(metadata);
    await image
      .clone()
      .rotate()
      .resize({
        width: Math.min(dimensions.width, 64),
        height: Math.min(dimensions.height, 64),
        fit: "inside",
        withoutEnlargement: true,
      })
      .toColourspace("srgb")
      .toBuffer();
  } catch (error) {
    if (error instanceof MediaValidationError) throw error;
    throw new MediaValidationError(
      "Файл повреждён или не является поддерживаемым изображением.",
      "decode_failed",
      415,
    );
  }
  return metadata;
}

async function assertImmutableFile(
  destination: string,
  expectedHash: string,
  expectedBytes: number,
): Promise<void> {
  const existing = await lstat(destination);
  if (
    !existing.isFile() ||
    existing.isSymbolicLink() ||
    existing.size !== expectedBytes
  ) {
    throw new MediaStorageIntegrityError(
      `Existing media object is invalid: ${destination}`,
    );
  }
  if ((await sha256File(destination)) !== expectedHash) {
    throw new MediaStorageIntegrityError(
      `Existing media object failed SHA-256 verification: ${destination}`,
    );
  }
}

async function fsyncDirectory(directory: string): Promise<void> {
  try {
    const handle = await open(directory, "r");
    try {
      await handle.sync();
    } finally {
      await handle.close();
    }
  } catch {
    // Some filesystems do not allow directory fsync. File fsync + atomic link still protects contents.
  }
}

async function ensureDirectoryHierarchy(
  root: string,
  directory: string,
  mode: number,
): Promise<void> {
  const rootPath = path.resolve(/* turbopackIgnore: true */ root);
  const directoryPath = path.resolve(/* turbopackIgnore: true */ directory);
  if (directoryPath !== rootPath && !directoryPath.startsWith(`${rootPath}${path.sep}`)) {
    throw new MediaStorageIntegrityError(
      "Media directory escaped its configured storage root.",
    );
  }
  await mkdir(rootPath, { recursive: true, mode });
  await chmod(rootPath, mode);
  const relative = path.relative(rootPath, directoryPath);
  if (!relative) return;
  let current = rootPath;
  for (const segment of relative.split(path.sep).filter(Boolean)) {
    current = insideRoot(rootPath, path.relative(rootPath, current), segment);
    await mkdir(current, { recursive: true, mode });
    await chmod(current, mode);
  }
}

async function publishImmutable(
  destination: string,
  contents: Buffer,
  expectedHash: string,
  mode: number,
  storageRoot: string,
  directoryMode: number,
): Promise<{ existed: boolean }> {
  await ensureDirectoryHierarchy(storageRoot, path.dirname(destination), directoryMode);
  try {
    await assertImmutableFile(destination, expectedHash, contents.byteLength);
    await chmod(destination, mode);
    return { existed: true };
  } catch (error) {
    if (
      !(error instanceof Error) ||
      !("code" in error) ||
      error.code !== "ENOENT"
    ) {
      throw error;
    }
  }

  const temporary = path.join(
    path.dirname(destination),
    `.${path.basename(destination)}.${process.pid}.${randomUUID()}.tmp`,
  );
  const handle = await open(temporary, "wx", mode);
  try {
    await handle.writeFile(contents);
    await handle.sync();
  } finally {
    await handle.close();
  }

  try {
    await link(temporary, destination);
    await chmod(destination, mode);
    await fsyncDirectory(path.dirname(destination));
    return { existed: false };
  } catch (error) {
    if (
      !(error instanceof Error) ||
      !("code" in error) ||
      error.code !== "EEXIST"
    ) {
      throw error;
    }
    await assertImmutableFile(destination, expectedHash, contents.byteLength);
    await chmod(destination, mode);
    return { existed: true };
  } finally {
    await unlink(temporary).catch(() => undefined);
  }
}

function variantPublicPath(
  sourceSha256: string,
  width: number,
  format: VariantFormat,
): string {
  return `${PUBLIC_MEDIA_PREFIX}generated/${MEDIA_PIPELINE_VERSION}/${sourceSha256.slice(0, 2)}/${sourceSha256}/${width}.${format}`;
}

function publicPathToDisk(publicRoot: string, publicPath: string): string {
  if (!publicPath.startsWith(PUBLIC_MEDIA_PREFIX)) {
    throw new MediaStorageIntegrityError(
      `Unexpected media public path: ${publicPath}`,
    );
  }
  return insideRoot(publicRoot, publicPath.slice(PUBLIC_MEDIA_PREFIX.length));
}

function manifestDiskPath(privateRoot: string, sourceSha256: string): string {
  return insideRoot(
    privateRoot,
    "manifests",
    MEDIA_PIPELINE_VERSION,
    sourceSha256.slice(0, 2),
    `${sourceSha256}.json`,
  );
}

function manifestStoragePath(sourceSha256: string): string {
  return `media/manifests/${MEDIA_PIPELINE_VERSION}/${sourceSha256.slice(0, 2)}/${sourceSha256}.json`;
}

async function existingManifest(
  privateRoot: string,
  publicRoot: string,
  sourceSha256: string,
): Promise<MediaManifest | null> {
  let parsed: MediaManifest;
  try {
    parsed = JSON.parse(
      await readFile(manifestDiskPath(privateRoot, sourceSha256), "utf8"),
    ) as MediaManifest;
  } catch (error) {
    if (error instanceof SyntaxError) return null;
    if (error instanceof Error && "code" in error && error.code === "ENOENT")
      return null;
    throw error;
  }
  if (
    parsed.version !== MEDIA_PIPELINE_VERSION ||
    parsed.sourceSha256 !== sourceSha256 ||
    !parsed.original ||
    !Array.isArray(parsed.variants)
  ) {
    return null;
  }

  const originalDiskPath = insideRoot(
    privateRoot,
    parsed.original.path.replace(/^media\//, ""),
  );
  await assertImmutableFile(
    originalDiskPath,
    sourceSha256,
    parsed.original.bytes,
  );
  await Promise.all(
    parsed.variants.map(async (variant) => {
      const variantPath = publicPathToDisk(publicRoot, variant.path);
      await assertImmutableFile(variantPath, variant.sha256, variant.bytes);
      await ensureDirectoryHierarchy(publicRoot, path.dirname(variantPath), 0o755);
      await chmod(variantPath, 0o644);
    }),
  );
  return parsed;
}

async function encodeVariant(
  bytes: Buffer,
  width: number,
  format: VariantFormat,
  maxPixels: number,
): Promise<{ data: Buffer; info: OutputInfo }> {
  const image = sharp(bytes, {
    animated: false,
    failOn: "error",
    limitInputPixels: maxPixels,
    sequentialRead: true,
  })
    .rotate()
    .resize({ width, fit: "inside", withoutEnlargement: true })
    .toColourspace("srgb");

  if (format === "webp") {
    return image
      .webp({ quality: WEBP_QUALITY, smartSubsample: true })
      .toBuffer({ resolveWithObject: true });
  }
  return image
    .avif({ quality: AVIF_QUALITY })
    .toBuffer({ resolveWithObject: true });
}

export async function processMediaUpload(
  input: ProcessMediaUploadInput,
): Promise<MediaUploadResult> {
  const maxBytes = input.limits?.maxBytes ?? MAX_UPLOAD_BYTES;
  const maxDimension = input.limits?.maxDimension ?? MAX_IMAGE_DIMENSION;
  const maxPixels = input.limits?.maxPixels ?? MAX_INPUT_PIXELS;
  if (input.bytes.byteLength === 0) {
    throw new MediaValidationError(
      "Выберите непустой файл изображения.",
      "empty_file",
    );
  }
  if (input.bytes.byteLength > maxBytes) {
    throw new MediaValidationError(
      `Файл превышает допустимый размер ${Math.floor(maxBytes / 1024 / 1024)} МБ.`,
      "file_too_large",
      413,
    );
  }

  const safeFilename = sanitizeUploadFilename(input.originalFilename);
  const sourceSha256 = sha256(input.bytes);
  const metadata = await validateDecode(input.bytes, maxPixels);
  const detected = inputFormat(metadata);
  const dimensions = orientedDimensions(metadata);
  if (dimensions.width > maxDimension || dimensions.height > maxDimension) {
    throw new MediaValidationError(
      `Сторона изображения не должна превышать ${maxDimension} px.`,
      "dimensions_too_large",
      413,
    );
  }
  if (dimensions.width * dimensions.height > maxPixels) {
    throw new MediaValidationError(
      "Изображение содержит слишком много пикселей.",
      "pixel_limit",
      413,
    );
  }

  const { privateRoot, publicRoot } = mediaRoots(input);
  const cached = await existingManifest(privateRoot, publicRoot, sourceSha256);
  if (cached) {
    return {
      ...cached,
      deduplicated: true,
      uploadedFilename: safeFilename,
      manifestPath: manifestStoragePath(sourceSha256),
    };
  }

  const originalRelativePath = `originals/${sourceSha256.slice(0, 2)}/${sourceSha256}.${detected.extension}`;
  const originalDiskPath = insideRoot(privateRoot, originalRelativePath);
  const originalPublish = await publishImmutable(
    originalDiskPath,
    input.bytes,
    sourceSha256,
    0o600,
    privateRoot,
    0o700,
  );
  const original: StoredOriginal = {
    path: `media/${originalRelativePath}`,
    sha256: sourceSha256,
    format: detected.format,
    mimeType: detected.mimeType,
    width: dimensions.width,
    height: dimensions.height,
    bytes: input.bytes.byteLength,
  };

  const actualWidths = [
    ...new Set(
      MEDIA_VARIANT_WIDTHS.map((width) => Math.min(width, dimensions.width)),
    ),
  ].sort((left, right) => left - right);
  const variants: StoredVariant[] = [];
  let everyVariantExisted = true;
  for (const width of actualWidths) {
    for (const format of ["webp", "avif"] as const) {
      const encoded = await encodeVariant(
        input.bytes,
        width,
        format,
        maxPixels,
      );
      const variantHash = sha256(encoded.data);
      const publicPath = variantPublicPath(
        sourceSha256,
        encoded.info.width,
        format,
      );
      const published = await publishImmutable(
        publicPathToDisk(publicRoot, publicPath),
        encoded.data,
        variantHash,
        0o644,
        publicRoot,
        0o755,
      );
      everyVariantExisted &&= published.existed;
      variants.push({
        path: publicPath,
        sha256: variantHash,
        format,
        width: encoded.info.width,
        height: encoded.info.height,
        bytes: encoded.info.size,
        quality: format === "webp" ? WEBP_QUALITY : AVIF_QUALITY,
      });
    }
  }

  const manifest: MediaManifest = {
    version: MEDIA_PIPELINE_VERSION,
    sourceSha256,
    configuredWidths: [...MEDIA_VARIANT_WIDTHS],
    original,
    variants,
  };
  const manifestBytes = Buffer.from(
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
  const manifestPublish = await publishImmutable(
    manifestDiskPath(privateRoot, sourceSha256),
    manifestBytes,
    sha256(manifestBytes),
    0o600,
    privateRoot,
    0o700,
  );

  return {
    ...manifest,
    deduplicated:
      originalPublish.existed && everyVariantExisted && manifestPublish.existed,
    uploadedFilename: safeFilename,
    manifestPath: manifestStoragePath(sourceSha256),
  };
}
