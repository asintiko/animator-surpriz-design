let csrfToken: string | null = null;

async function getCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  const response = await fetch("/api/csrf", { cache: "no-store", credentials: "same-origin" });
  if (!response.ok) throw new Error("Не удалось подготовить защищённую форму.");
  const payload = (await response.json()) as { token: string };
  csrfToken = payload.token;
  return payload.token;
}

export async function mutateJson<T>(url: string, payload: unknown, method = "POST"): Promise<T> {
  const token = await getCsrfToken();
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      "x-csrf-token": token,
    },
    body: method === "DELETE" ? undefined : JSON.stringify(payload),
  });
  const result = (await response.json()) as T & { message?: string };
  if (!response.ok) throw new Error(result.message || "Не удалось выполнить запрос.");
  return result;
}
