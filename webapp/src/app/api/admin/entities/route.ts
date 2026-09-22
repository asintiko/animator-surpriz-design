import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/server/proxy";
import { assertSameOrigin } from "@/lib/server/security";

export async function GET(request: Request) {
  const query = new URL(request.url).search;
  try {
    return await proxyJson(request, `/api/v2/admin/entities${query}`, "adapter");
  } catch {
    return NextResponse.json({ success: false, message: "Не удалось загрузить карточки." }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const rejection = await assertSameOrigin(request);
  if (rejection) return rejection;
  try {
    return await proxyJson(request, "/api/v2/admin/entities", "adapter");
  } catch {
    return NextResponse.json({ success: false, message: "Не удалось создать карточку." }, { status: 503 });
  }
}
