"use client";

import { ArrowRight, CheckCircle2, Send, ShieldCheck } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { mutateJson } from "@/lib/client/mutate";

export function AuthPanel({ mode }: { mode: "login" | "register" }) {
  const searchParams = useSearchParams();
  const [phone, setPhone] = useState("+998 ");
  const [fullName, setFullName] = useState("");
  const [requestId, setRequestId] = useState("");
  const [code, setCode] = useState("");
  const [isPending, startTransition] = useTransition();
  const next = searchParams.get("next") || "/account";

  function requestCode() {
    startTransition(async () => {
      try {
        const result = await mutateJson<{ request_id: string }>("/api/auth/send-code", {
          phone,
          full_name: fullName,
          purpose: mode,
          next,
        });
        setRequestId(result.request_id);
        toast.success("Код отправлен в Telegram");
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Не удалось отправить код.");
      }
    });
  }

  function verifyCode() {
    startTransition(async () => {
      try {
        const result = await mutateJson<{ redirect_url?: string }>("/api/auth/verify-code", {
          phone,
          request_id: requestId,
          code,
        });
        window.location.assign(result.redirect_url || next);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Неверный код.");
      }
    });
  }

  return (
    <div className="auth-card">
      <div className="auth-icon">{requestId ? <ShieldCheck /> : <Send />}</div>
      <h1>{mode === "register" ? "Создать аккаунт" : "Войти в кабинет"}</h1>
      <p>{requestId ? "Введите шестизначный код, который пришёл в Telegram." : "Пароль не нужен — подтвердите телефон кодом в Telegram."}</p>
      {!requestId ? (
        <>
          {mode === "register" ? <label>Ваше имя<input autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} /></label> : null}
          <label>Телефон<input autoComplete="tel" inputMode="tel" value={phone} onChange={(event) => setPhone(event.target.value)} /></label>
          <button className="button button-primary" disabled={isPending || phone.length < 9 || (mode === "register" && !fullName)} onClick={requestCode} type="button">
            {isPending ? "Отправляем…" : "Получить код"} <ArrowRight />
          </button>
        </>
      ) : (
        <>
          <label>Код из Telegram<input autoComplete="one-time-code" inputMode="numeric" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} /></label>
          <button className="button button-primary" disabled={isPending || code.length !== 6} onClick={verifyCode} type="button">
            {isPending ? "Проверяем…" : "Подтвердить"} <CheckCircle2 />
          </button>
          <button className="auth-back" onClick={() => { setRequestId(""); setCode(""); }} type="button">Изменить номер</button>
        </>
      )}
    </div>
  );
}
