"use client";

import { LockKeyhole } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { AdminBuildStamp } from "@/components/admin/build-stamp";
import { mutateJson } from "@/lib/client/mutate";

export function AdminLogin() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isPending, startTransition] = useTransition();

  function login() {
    startTransition(async () => {
      try {
        await mutateJson("/api/admin/login", { username, password });
        window.location.assign("/admin");
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Не удалось войти.");
      }
    });
  }

  return (
    <div className="admin-login-card">
      <span><LockKeyhole /></span>
      <p className="eyebrow">SURPRIZ ADMIN</p>
      <h1>Вход в панель</h1>
      <p>Управление заказами, каталогом, медиа и настройками.</p>
      <label>Логин<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
      <label>Пароль<input autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <button className="button button-violet" disabled={isPending || !username || !password} onClick={login} type="button">{isPending ? "Проверяем…" : "Войти"}</button>
      <AdminBuildStamp />
    </div>
  );
}
