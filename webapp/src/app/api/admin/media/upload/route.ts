import { NextResponse } from "next/server";

import {
  MAX_UPLOAD_BYTES,
  MediaStorageIntegrityError,
  MediaValidationError,
  processMediaUpload,
} from "@/lib/server/media";
import { assertSameOrigin, forwardedCookieHeader } from "@/lib/server/security";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const adapterOrigin =
  process.env.SURPRIZ_ADAPTER_ORIGIN ?? "http://127.0.0.1:5051";
const REQUEST_OVERHEAD_BYTES = 1024 * 1024;

type AdminSessionPayload = {
  authenticated?: boolean;
};

async function authenticateAdmin(): Promise<
  "authenticated" | "unauthenticated" | "unavailable"
> {
  const adapterToken = process.env.SURPRIZ_ADAPTER_TOKEN?.trim();
  if (!adapterToken) return "unavailable";

  try {
    const response = await fetch(
      new URL("/api/v2/admin/session", adapterOrigin),
      {
        method: "GET",
        headers: {
          accept: "application/json",
          cookie: await forwardedCookieHeader(),
          "x-adapter-token": adapterToken,
        },
        cache: "no-store",
        signal: AbortSignal.timeout(8_000),
      },
    );
    if (response.status === 401 || response.status === 403)
      return "unauthenticated";
    if (!response.ok) return "unavailable";
    const payload = (await response.json()) as AdminSessionPayload;
    return payload.authenticated === true ? "authenticated" : "unauthenticated";
  } catch {
    return "unavailable";
  }
}

export async function POST(request: Request) {
  const rejection = await assertSameOrigin(request);
  if (rejection) return rejection;

  const adminState = await authenticateAdmin();
  if (adminState === "unauthenticated") {
    return NextResponse.json(
      {
        success: false,
        code: "unauthenticated",
        message: "Войдите в админ-панель.",
      },
      { status: 401 },
    );
  }
  if (adminState === "unavailable") {
    return NextResponse.json(
      {
        success: false,
        code: "admin_session_unavailable",
        message: "Не удалось проверить сессию администратора.",
      },
      { status: 503 },
    );
  }

  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("multipart/form-data;")) {
    return NextResponse.json(
      {
        success: false,
        code: "multipart_required",
        message: "Отправьте фотографию как multipart/form-data.",
      },
      { status: 415 },
    );
  }
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (
    Number.isFinite(contentLength) &&
    contentLength > MAX_UPLOAD_BYTES + REQUEST_OVERHEAD_BYTES
  ) {
    return NextResponse.json(
      {
        success: false,
        code: "request_too_large",
        message: "Файл превышает допустимый размер 25 МБ.",
      },
      { status: 413 },
    );
  }

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json(
      {
        success: false,
        code: "invalid_multipart",
        message: "Не удалось прочитать загруженный файл.",
      },
      { status: 400 },
    );
  }
  const files = formData.getAll("file");
  if (files.length !== 1 || !(files[0] instanceof File)) {
    return NextResponse.json(
      {
        success: false,
        code: "single_file_required",
        message: "Выберите одну фотографию.",
      },
      { status: 400 },
    );
  }

  const file = files[0];
  if (file.size > MAX_UPLOAD_BYTES) {
    return NextResponse.json(
      {
        success: false,
        code: "file_too_large",
        message: "Файл превышает допустимый размер 25 МБ.",
      },
      { status: 413 },
    );
  }

  try {
    const media = await processMediaUpload({
      bytes: Buffer.from(await file.arrayBuffer()),
      originalFilename: file.name,
    });
    return NextResponse.json(
      { success: true, media },
      {
        status: media.deduplicated ? 200 : 201,
        headers: { "cache-control": "no-store" },
      },
    );
  } catch (error) {
    if (error instanceof MediaValidationError) {
      return NextResponse.json(
        { success: false, code: error.code, message: error.message },
        { status: error.status },
      );
    }
    if (error instanceof MediaStorageIntegrityError) {
      console.error("Media storage integrity failure", error);
      return NextResponse.json(
        {
          success: false,
          code: "storage_integrity",
          message: "Хранилище медиа требует проверки администратором.",
        },
        { status: 500 },
      );
    }
    console.error("Media upload failed", error);
    return NextResponse.json(
      {
        success: false,
        code: "media_processing_failed",
        message: "Не удалось обработать фотографию.",
      },
      { status: 500 },
    );
  }
}
