"use client";

import { LogOut } from "lucide-react";
import { useState } from "react";

import { mutateJson } from "@/lib/client/mutate";

export function AdminLogout() {
  const [pending, setPending] = useState(false);

  async function logout() {
    setPending(true);
    try {
      await mutateJson("/api/admin/logout", {});
      window.location.assign("/admin/login");
    } finally {
      setPending(false);
    }
  }

  return <button className="admin-site-link" disabled={pending} onClick={() => void logout()} type="button"><LogOut size={15} /> {pending ? "Выходим…" : "Выйти"}</button>;
}
