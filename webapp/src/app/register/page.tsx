import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AuthPanel } from "@/features/auth/auth-panel";

export const metadata: Metadata = { title: "Регистрация" };

export default function RegisterPage() {
  return <section className="auth-page"><Suspense fallback={null}><AuthPanel mode="register" /></Suspense><p>Уже есть аккаунт? <Link href="/login">Войти</Link></p></section>;
}
