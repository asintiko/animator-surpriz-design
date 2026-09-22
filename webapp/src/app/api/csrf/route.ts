import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { CSRF_COOKIE } from "@/lib/server/security";

export const dynamic = "force-dynamic";

export async function GET() {
  const cookieStore = await cookies();
  const existing = cookieStore.get(CSRF_COOKIE)?.value;
  const token = existing ?? randomBytes(32).toString("base64url");
  const response = NextResponse.json({ token });
  if (!existing) {
    response.cookies.set(CSRF_COOKIE, token, {
      httpOnly: false,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 4,
    });
  }
  return response;
}
