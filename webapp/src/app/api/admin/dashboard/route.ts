import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/server/proxy";

export async function GET(request: Request) {
  try {
    return await proxyJson(request, "/api/v2/admin/dashboard", "adapter");
  } catch {
    return NextResponse.json({ authenticated: true, stats: {} }, { status: 503 });
  }
}
