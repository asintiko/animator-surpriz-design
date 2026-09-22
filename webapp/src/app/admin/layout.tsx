import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: { default: "Админка", template: "%s | Surpriz Admin" },
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const fetchCache = "force-no-store";

export default function AdminRootLayout({ children }: { children: ReactNode }) {
  return <div className="admin-app">{children}</div>;
}
