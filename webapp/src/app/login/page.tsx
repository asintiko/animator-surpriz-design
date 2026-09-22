import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AuthPanel } from "@/features/auth/auth-panel";

export const metadata: Metadata = { title: "Вход" };

export default function LoginPage() {
  return <section className="auth-page"><Suspense fallback={null}><AuthPanel mode="login" /></Suspense><p>Впервые у нас? <Link href="/register">Создать аккаунт</Link></p></section>;
}
