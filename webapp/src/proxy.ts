import { NextRequest, NextResponse } from "next/server";

const adapterOrigin = process.env.SURPRIZ_ADAPTER_ORIGIN ?? "http://127.0.0.1:5051";

export async function proxy(request: NextRequest) {
  if (request.nextUrl.pathname === "/admin/login") return NextResponse.next();

  const token = process.env.SURPRIZ_ADAPTER_TOKEN?.trim();
  if (!token) return NextResponse.redirect(new URL("/admin/login", request.url));

  try {
    const response = await fetch(new URL("/api/v2/admin/session", adapterOrigin), {
      headers: {
        accept: "application/json",
        cookie: request.headers.get("cookie") ?? "",
        "x-adapter-token": token,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    });
    if (response.ok) return NextResponse.next();
  } catch {
    // The login page is the safe recovery path when the admin adapter is unavailable.
  }

  const login = new URL("/admin/login", request.url);
  login.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/admin/:path*"],
};
