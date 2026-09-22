import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/server/proxy";
import { assertSameOrigin } from "@/lib/server/security";

export async function POST(request: Request) {
  const rejection = await assertSameOrigin(request);
  if (rejection) return rejection;
  try {
    return await proxyJson(request, "/api/party-builder/suggest-address");
  } catch {
    return NextResponse.json({ configured: false, results: [] }, { status: 503 });
  }
}
