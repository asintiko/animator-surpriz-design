import { forwardedCookieHeader } from "@/lib/server/security";

const adapterOrigin = process.env.SURPRIZ_ADAPTER_ORIGIN ?? "http://127.0.0.1:5051";

function redirectTo(location: string) {
  // A relative Location keeps the browser on the public domain behind nginx.
  return new Response(null, { status: 303, headers: { location, "cache-control": "no-store" } });
}

function backToCalendar(status: "connected" | "error", message = "") {
  const params = new URLSearchParams({ google: status });
  if (message) params.set("message", message.slice(0, 300));
  return redirectTo(`/admin/calendar?${params.toString()}`);
}

// Google sends the admin back here after the consent screen (OAuth redirect URI).
export async function GET(request: Request) {
  const incoming = new URL(request.url).searchParams;
  if (incoming.get("error")) return backToCalendar("error", "Доступ к Google Календарю не выдан.");

  const query = new URLSearchParams({
    code: incoming.get("code") ?? "",
    state: incoming.get("state") ?? "",
  });
  const token = process.env.SURPRIZ_ADAPTER_TOKEN?.trim();
  try {
    const response = await fetch(new URL(`/api/v2/admin/google-calendar/callback?${query.toString()}`, adapterOrigin), {
      headers: {
        accept: "application/json",
        cookie: await forwardedCookieHeader(),
        ...(token ? { "x-adapter-token": token } : {}),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(45_000),
    });
    if (response.status === 401) return redirectTo("/admin/login?next=/admin/calendar");
    const result = (await response.json().catch(() => ({}))) as { success?: boolean; message?: string };
    if (!response.ok || !result.success) {
      return backToCalendar("error", result.message || "Не удалось подключить Google Календарь.");
    }
    return backToCalendar("connected");
  } catch {
    return backToCalendar("error", "Сервис админки не ответил. Попробуйте подключить ещё раз.");
  }
}
