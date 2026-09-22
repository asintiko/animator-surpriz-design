import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/server/proxy";
import { assertSameOrigin } from "@/lib/server/security";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    return await proxyJson(request, `/api/v2/admin/entities/${encodeURIComponent(id)}`, "adapter");
  } catch {
    return NextResponse.json({ success: false, message: "Не удалось загрузить карточку." }, { status: 503 });
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const rejection = await assertSameOrigin(request);
  if (rejection) return rejection;
  const { id } = await params;
  try {
    return await proxyJson(request, `/api/v2/admin/entities/${encodeURIComponent(id)}`, "adapter");
  } catch {
    return NextResponse.json({ success: false, message: "Не удалось сохранить карточку." }, { status: 503 });
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const rejection = await assertSameOrigin(request);
  if (rejection) return rejection;
  const { id } = await params;
  try {
    return await proxyJson(request, `/api/v2/admin/entities/${encodeURIComponent(id)}`, "adapter");
  } catch {
    return NextResponse.json({ success: false, message: "Не удалось удалить карточку." }, { status: 503 });
  }
}
