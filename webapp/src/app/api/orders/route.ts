import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/server/proxy";
import { assertSameOrigin } from "@/lib/server/security";

export async function POST(request: Request) {
  const rejection = await assertSameOrigin(request);
  if (rejection) return rejection;
  try {
    return await proxyJson(request, "/api/v2/orders", "adapter");
  } catch {
    return NextResponse.json(
      { success: false, message: "Не удалось сохранить заказ. Позвоните менеджеру." },
      { status: 503 },
    );
  }
}
