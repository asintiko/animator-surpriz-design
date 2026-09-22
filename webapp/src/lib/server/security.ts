import { cookies, headers } from "next/headers";
import { NextResponse } from "next/server";

export const CSRF_COOKIE = "surpriz_csrf";

export async function assertSameOrigin(request: Request): Promise<NextResponse | null> {
  const requestHeaders = await headers();
  const origin = requestHeaders.get("origin");
  const host = requestHeaders.get("host");
  if (origin && host && new URL(origin).host !== host) {
    return NextResponse.json({ success: false, message: "Недопустимый источник запроса." }, { status: 403 });
  }

  const cookieStore = await cookies();
  const cookieToken = cookieStore.get(CSRF_COOKIE)?.value;
  const headerToken = request.headers.get("x-csrf-token");
  if (!cookieToken || !headerToken || cookieToken !== headerToken) {
    return NextResponse.json({ success: false, message: "Сессия формы устарела. Обновите страницу." }, { status: 403 });
  }

  return null;
}

export async function forwardedCookieHeader(): Promise<string> {
  const cookieStore = await cookies();
  return cookieStore
    .getAll()
    .map(({ name, value }) => `${name}=${value}`)
    .join("; ");
}
