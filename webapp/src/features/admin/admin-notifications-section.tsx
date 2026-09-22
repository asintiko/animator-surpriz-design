"use client";

import { BellRing, Bot, CheckCircle2, Plus, Send, ShieldCheck, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";

import {
  AdminSectionState,
  useAdminSection,
  useSectionMutation,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";

type Recipient = {
  id: number;
  chat_id: string;
  label?: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
};

type NotificationsPayload = SectionEnvelope & {
  configured?: boolean;
  bot_token_masked?: string;
  gateway_token_masked?: string;
  recipients?: Recipient[];
};

export function AdminNotificationsSection() {
  const section = useAdminSection<NotificationsPayload>("notifications");
  const mutation = useSectionMutation("notifications", section.refresh);
  const [botToken, setBotToken] = useState("");
  const [gatewayToken, setGatewayToken] = useState("");
  const [recipient, setRecipient] = useState({ chat_id: "", label: "" });
  const recipients = section.data?.recipients ?? [];

  async function saveSecret(event: FormEvent, target: "bot" | "gateway") {
    event.preventDefault();
    const token = target === "bot" ? botToken : gatewayToken;
    if (!token.trim()) return;
    const result = await mutation.run(`secret-${target}`, { action: target === "bot" ? "save_bot_token" : "save_gateway_token", token: token.trim() }, "Токен сохранён");
    if (result) {
      if (target === "bot") setBotToken("");
      else setGatewayToken("");
    }
  }

  async function addRecipient(event: FormEvent) {
    event.preventDefault();
    if (!recipient.chat_id.trim()) return;
    const result = await mutation.run("recipient-new", { action: "add_recipient", chat_id: recipient.chat_id.trim(), label: recipient.label.trim() }, "Получатель добавлен");
    if (result) setRecipient({ chat_id: "", label: "" });
  }

  return (
    <>
      <div className="admin-metrics admin-metrics-compact">
        <article><span>Интеграция</span><strong>{section.data?.configured ? "Работает" : "Нужна настройка"}</strong></article>
        <article><span>Получатели</span><strong>{recipients.length}</strong></article>
        <article><span>Активные</span><strong>{recipients.filter((item) => item.is_active).length}</strong></article>
      </div>

      <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
      {!section.loading && !section.error ? (
        <div className="admin-dashboard-grid">
          <section className="admin-surface">
            <div className="admin-surface-head"><div><p className="eyebrow">TELEGRAM BOT</p><h2>Уведомления о заказах</h2><p>Секреты не показываются после сохранения.</p></div>{section.data?.configured ? <span className="content-status status-active"><CheckCircle2 size={14} /> Подключено</span> : null}</div>
            <form className="admin-token-form" onSubmit={(event) => void saveSecret(event, "bot")}><label><span>Bot token</span><input autoComplete="new-password" placeholder={section.data?.bot_token_masked || "123456:AA…"} type="password" value={botToken} onChange={(event) => setBotToken(event.target.value)} /></label><button className="button button-violet" disabled={!botToken.trim() || mutation.pendingKey === "secret-bot"} type="submit"><Bot size={17} /> Сохранить токен</button></form>
            <form className="admin-token-form" onSubmit={(event) => void saveSecret(event, "gateway")}><label><span>Gateway token</span><input autoComplete="new-password" placeholder={section.data?.gateway_token_masked || "Не настроен"} type="password" value={gatewayToken} onChange={(event) => setGatewayToken(event.target.value)} /></label><button className="button button-secondary" disabled={!gatewayToken.trim() || mutation.pendingKey === "secret-gateway"} type="submit"><ShieldCheck size={17} /> Сохранить gateway</button></form>
          </section>

          <aside className="admin-surface">
            <div className="admin-surface-head"><div><p className="eyebrow">НОВЫЙ ЧАТ</p><h2>Добавить получателя</h2><p>Личный chat ID или ID рабочей группы.</p></div></div>
            <form className="admin-form-stack" onSubmit={(event) => void addRecipient(event)}><label>Chat ID<input required placeholder="-1001234567890" value={recipient.chat_id} onChange={(event) => setRecipient((current) => ({ ...current, chat_id: event.target.value }))} /></label><label>Название<input placeholder="Менеджеры" value={recipient.label} onChange={(event) => setRecipient((current) => ({ ...current, label: event.target.value }))} /></label><button className="button button-violet" disabled={!recipient.chat_id.trim() || mutation.pendingKey === "recipient-new"} type="submit"><Plus size={17} /> Добавить</button></form>
          </aside>

          <section className="admin-surface admin-surface-wide">
            <div className="admin-surface-head"><div><p className="eyebrow">МАРШРУТИЗАЦИЯ</p><h2>Получатели</h2><p>Тестируйте доставку перед публикацией сайта.</p></div></div>
            {!recipients.length ? <div className="admin-empty"><BellRing /> Добавьте хотя бы одного получателя.</div> : <div className="admin-table-wrap"><table className="admin-data-table"><thead><tr><th>Получатель</th><th>Chat ID</th><th>Статус</th><th>Добавлен</th><th>Действия</th></tr></thead><tbody>{recipients.map((item) => <tr key={item.id}><td><strong>{item.label || "Без названия"}</strong></td><td><code>{item.chat_id}</code></td><td><span className={`content-status status-${item.is_active ? "active" : "hidden"}`}>{item.is_active ? "Активен" : "Выключен"}</span></td><td>{item.created_at || "—"}</td><td><div className="admin-row-actions"><button className="button button-secondary" disabled={mutation.pendingKey === `test-${item.id}`} onClick={() => void mutation.run(`test-${item.id}`, { action: "test_recipient", recipient_id: item.id }, "Тест отправлен")} type="button"><Send size={16} /> Тест</button><button className="button button-secondary" disabled={mutation.pendingKey === `toggle-${item.id}`} onClick={() => void mutation.run(`toggle-${item.id}`, { action: "toggle_recipient", recipient_id: item.id, is_active: !item.is_active }, "Статус изменён")} type="button">{item.is_active ? "Выключить" : "Включить"}</button><button aria-label="Удалить" className="button button-danger" onClick={() => { if (window.confirm(`Удалить получателя «${item.label || item.chat_id}»?`)) void mutation.run(`delete-${item.id}`, { action: "delete_recipient", recipient_id: item.id }, "Получатель удалён"); }} type="button"><Trash2 size={16} /></button></div></td></tr>)}</tbody></table></div>}
          </section>
        </div>
      ) : null}
    </>
  );
}
