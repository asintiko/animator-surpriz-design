import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/server/proxy";
import { assertSameOrigin } from "@/lib/server/security";

const allowedSections = new Set([
  "orders",
  "visitors",
  "media",
  "taxonomy",
  "addons",
  "partners",
  "recommendations",
  "customers",
  "analytics",
  "notifications",
  "calendar",
  "settings",
]);

function adapterPath(request: Request, section: string) {
  const query = new URL(request.url).search;
  return `/api/v2/admin/section/${encodeURIComponent(section)}${query}`;
}

function unavailable(section: string) {
  return NextResponse.json(
    { success: false, section, message: "Раздел временно недоступен." },
    { status: 503 },
  );
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ section: string }> },
) {
  const { section } = await params;
  if (!allowedSections.has(section)) {
    return NextResponse.json({ message: "Неизвестный раздел." }, { status: 404 });
  }
  try {
    return await proxyJson(request, adapterPath(request, section), "adapter");
  } catch {
    return unavailable(section);
  }
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ section: string }> },
) {
  const rejection = await assertSameOrigin(request);
  if (rejection) return rejection;

  const { section } = await params;
  if (!allowedSections.has(section)) {
    return NextResponse.json({ message: "Неизвестный раздел." }, { status: 404 });
  }
  try {
    return await proxyJson(request, adapterPath(request, section), "adapter");
  } catch {
    return unavailable(section);
  }
}
