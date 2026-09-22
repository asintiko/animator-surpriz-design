import { forwardedCookieHeader } from "./security";

const legacyOrigin = process.env.SURPRIZ_BACKEND_ORIGIN ?? "http://127.0.0.1:5050";
const adapterOrigin = process.env.SURPRIZ_ADAPTER_ORIGIN ?? "http://127.0.0.1:5051";

export async function fetchAdapterJson<T>(path: string): Promise<T | null> {
  const token = process.env.SURPRIZ_ADAPTER_TOKEN?.trim();
  if (!token || !path.startsWith("/api/v2/admin/")) return null;
  try {
    const response = await fetch(new URL(path, adapterOrigin), {
      headers: {
        accept: "application/json",
        cookie: await forwardedCookieHeader(),
        "x-adapter-token": token,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return null;
    return await response.json() as T;
  } catch {
    return null;
  }
}

export async function proxyJson(
  request: Request,
  path: string,
  target: "legacy" | "adapter" = "legacy",
): Promise<Response> {
  const origin = target === "adapter" ? adapterOrigin : legacyOrigin;
  const body = await request.text();
  const response = await fetch(new URL(path, origin), {
    method: request.method,
    headers: {
      accept: "application/json",
      "content-type": request.headers.get("content-type") ?? "application/json",
      cookie: await forwardedCookieHeader(),
      "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "",
      "x-forwarded-host": request.headers.get("host") ?? "",
      "x-forwarded-proto": "https",
      ...(target === "adapter" && process.env.SURPRIZ_ADAPTER_TOKEN
        ? { "x-adapter-token": process.env.SURPRIZ_ADAPTER_TOKEN }
        : {}),
    },
    body: body || undefined,
    cache: "no-store",
    signal: AbortSignal.timeout(12_000),
  });

  const headers = new Headers({
    "content-type": response.headers.get("content-type") ?? "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  const setCookies = response.headers.getSetCookie();
  for (const value of setCookies) headers.append("set-cookie", value);
  return new Response(await response.arrayBuffer(), { status: response.status, headers });
}
