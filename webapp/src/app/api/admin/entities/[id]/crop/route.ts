import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/server/proxy";
import { assertSameOrigin } from "@/lib/server/security";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const rejection = await assertSameOrigin(request);
  if (rejection) return rejection;
  const { id } = await params;
  try {
    return await proxyJson(request, `/api/v2/admin/entities/${encodeURIComponent(id)}/crop`, "adapter");
  } catch {
    return NextResponse.json({ success: false, message: "Не удалось сохранить кадрирование." }, { status: 503 });
  }
}
