/* eslint-disable @next/next/no-css-tags -- Preserve the brand's existing self-hosted font files. */
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Toaster } from "sonner";

import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";
import { MobileNav } from "@/components/layout/mobile-nav";
import { IntroCurtain } from "@/components/motion/intro-curtain";
import { MotionProvider } from "@/components/motion/motion-provider";
import { site } from "@/lib/site";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(site.canonicalUrl),
  title: {
    default: "Аниматоры и детские праздники в Ташкенте | Surpriz",
    template: "%s | Surpriz",
  },
  description:
    "Аниматоры, персонажи и готовые шоу-программы для детских праздников в Ташкенте.",
  icons: { icon: "/brand/logo.png" },
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
  openGraph: {
    type: "website",
    locale: "ru_RU",
    siteName: "Surpriz",
    title: "Детские праздники в Ташкенте",
    description: "Настоящие персонажи и готовые шоу-программы.",
    images: ["/brand/logo.png"],
  },
  twitter: {
    card: "summary_large_image",
    title: "Детские праздники в Ташкенте",
    description: "Настоящие персонажи и готовые шоу-программы.",
    images: ["/brand/logo.png"],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#F7F2E8",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <head>
        <link href="/wp-content/cache/fonts/1/google-fonts/css/4/9/c/39123062b63c94cb126779358765f.css" rel="stylesheet" />
        <link href="/wp-content/cache/fonts/1/google-fonts/css/c/2/a/87050f36a1f19ab95ec58185d2735.css" rel="stylesheet" />
        <link href="/wp-content/cache/fonts/1/google-fonts/css/c/1/0/bd82fe01883cd5f2584180f7566cc.css" rel="stylesheet" />
      </head>
      <body>
        <a className="skip-link" href="#main-content">Перейти к содержимому</a>
        <MotionProvider>
          <IntroCurtain />
          <Header />
          <main id="main-content">{children}</main>
          <Footer />
          <MobileNav />
          <Toaster richColors position="top-center" />
        </MotionProvider>
      </body>
    </html>
  );
}
