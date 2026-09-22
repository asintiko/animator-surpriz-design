import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/server/proxy";

export async function GET(request: Request) {
  try {
    return await proxyJson(request, "/api/v2/account", "adapter");
  } catch {
    return NextResponse.json({ authenticated: false, orders: [] }, { status: 503 });
  }
}
