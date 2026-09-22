"use client";

import { AlertCircle, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { mutateJson } from "@/lib/client/mutate";

export type SectionEnvelope = {
  authenticated?: boolean;
  message?: string;
  success?: boolean;
};

export function useAdminSection<T extends SectionEnvelope>(
  section: string,
  query?: URLSearchParams,
) {
  const queryString = query?.toString() ?? "";
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const url = useMemo(
    () => `/api/admin/section/${section}${queryString ? `?${queryString}` : ""}`,
    [queryString, section],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(url, {
        cache: "no-store",
        credentials: "same-origin",
      });
      const result = (await response.json()) as T;
      if (result.authenticated === false || response.status === 401) {
        window.location.assign("/admin/login");
        return;
      }
      if (!response.ok) throw new Error(result.message || "Не удалось загрузить раздел.");
      setData(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить раздел.");
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timeout);
  }, [refresh]);

  return { data, error, loading, refresh, setData };
}

export async function postAdminSection<T extends SectionEnvelope>(
  section: string,
  payload: Record<string, unknown>,
) {
  return mutateJson<T>(`/api/admin/section/${section}`, payload);
}

export function AdminSectionState({
  error,
  loading,
  onRetry,
}: {
  error: string;
  loading: boolean;
  onRetry: () => void;
}) {
  if (loading) {
    return <div className="admin-empty"><LoaderCircle className="spin" /> Загружаем актуальные данные…</div>;
  }
  if (!error) return null;
  return (
    <div className="admin-empty admin-empty-error">
      <AlertCircle />
      <strong>{error}</strong>
      <button className="button button-secondary" onClick={onRetry} type="button">
        <RefreshCw size={17} /> Повторить
      </button>
    </div>
  );
}

export function useSectionMutation(section: string, refresh: () => Promise<void>) {
  const [pendingKey, setPendingKey] = useState("");

  return {
    pendingKey,
    run: async (
      key: string,
      payload: Record<string, unknown>,
      successMessage: string,
    ) => {
      setPendingKey(key);
      try {
        const result = await postAdminSection<SectionEnvelope>(section, payload);
        if (result.success === false) throw new Error(result.message || "Операция не выполнена.");
        toast.success(result.message || successMessage);
        await refresh();
        return result;
      } catch (reason) {
        toast.error(reason instanceof Error ? reason.message : "Операция не выполнена.");
        return null;
      } finally {
        setPendingKey("");
      }
    },
  };
}

export function formatMoney(value: number | string | null | undefined) {
  const amount = Number(value || 0);
  return `${new Intl.NumberFormat("ru-RU").format(Number.isFinite(amount) ? amount : 0)} сум`;
}

export function formatNumber(value: number | string | null | undefined) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("ru-RU").format(Number.isFinite(amount) ? amount : 0);
}
