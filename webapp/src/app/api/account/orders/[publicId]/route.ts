import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/server/proxy";

export async function GET(request: Request, { params }: { params: Promise<{ publicId: string }> }) {
  const { publicId } = await params;
  try {
    return await proxyJson(request, `/api/v2/orders/${encodeURIComponent(publicId)}`, "adapter");
  } catch {
    return NextResponse.json({ success: false, message: "Заказ не найден." }, { status: 503 });
  }
}
