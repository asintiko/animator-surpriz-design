"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

export default function AdminPortalError({ reset }: { error: Error; reset: () => void }) {
  return <section className="admin-page"><div className="admin-empty admin-empty-error"><AlertTriangle /><strong>Не удалось загрузить актуальные данные админки.</strong><p>Изменения заблокированы, чтобы не перезаписать свежие данные устаревшей копией.</p><button className="button button-violet" onClick={reset} type="button"><RefreshCw size={17} /> Повторить</button></div></section>;
}
