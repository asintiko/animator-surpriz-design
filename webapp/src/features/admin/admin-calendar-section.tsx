"use client";

import {
  AlertTriangle,
  BookOpenText,
  CalendarCheck2,
  CalendarDays,
  CheckCircle2,
  Copy,
  ExternalLink,
  EyeOff,
  Link2,
  ListPlus,
  LogOut,
  RefreshCw,
  Save,
  ScanSearch,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
  AdminSectionState,
  postAdminSection,
  useAdminSection,
  useSectionMutation,
  type SectionEnvelope,
} from "@/features/admin/admin-section-kit";

type CalendarStatus = {
  client_configured: boolean;
  client_source: "admin" | "env" | "";
  client_id: string;
  redirect_uri: string;
  connected: boolean;
  account_email: string;
  connected_at_label: string;
  auth_error: string;
  calendar_id: string;
  calendar_summary: string;
  last_import_at_label: string;
  last_import_error: string;
  last_export_at_label: string;
  last_export_error: string;
  queue_pending: number;
  queue_failing: number;
  worker_hint: string;
};

type CalendarSettings = {
  import_enabled: boolean;
  export_enabled: boolean;
  block_unmatched: boolean;
  poll_minutes: number;
  title_template: string;
  color_id: string;
};

type CalendarEvent = {
  event_key: string;
  date: string;
  date_label: string;
  time_label: string;
  summary: string;
  html_link: string;
  program_names: string[];
  character_names: string[];
  match_status: "matched" | "unmatched" | "free" | "own" | "own_moved" | "ignored";
  status_label: string;
  blocks_time: boolean;
  blocks_all: boolean;
  order_public_id: string;
  note: string;
};

type CalendarAlias = { id: number; phrase: string; entity_slug: string; entity_name: string; kind: string };
type CatalogEntity = { slug: string; name: string; kind: "program" | "character" };
type EventColor = { id: string; name: string; hex: string };
type Placeholder = { key: string; label: string };

type CalendarPayload = SectionEnvelope & {
  status?: CalendarStatus;
  settings?: CalendarSettings;
  title_preview?: string;
  events?: CalendarEvent[];
  event_stats?: Record<string, number>;
  aliases?: CalendarAlias[];
  entities?: CatalogEntity[];
  colors?: EventColor[];
  poll_choices?: number[];
  placeholders?: Placeholder[];
  default_title_template?: string;
};

type GoogleCalendarItem = { id: string; summary: string; primary: boolean; access_role: string; background_color: string };
type Recognition = { programs: string[]; characters: string[]; matched: boolean };

const statusClass: Record<CalendarEvent["match_status"], string> = {
  matched: "status-active",
  unmatched: "status-new",
  free: "status-muted",
  own: "status-contacted",
  own_moved: "status-new",
  ignored: "status-muted",
};

const eventFilters = [
  { key: "", label: "Все" },
  { key: "matched", label: "Закрывают время" },
  { key: "unmatched", label: "Не распознаны" },
  { key: "own", label: "Заказы с сайта" },
] as const;

const sampleValues: Record<string, string> = {
  program: "Стандарт",
  characters: "Леди Баг + Супер-Кот",
  celebrant: "Аня",
  age: "6 лет",
  children: "12 детей",
  client: "Дилноза",
  phone: "+998 (90) 123-45-67",
  address: "Юнусабад, 4 квартал",
  time: "15:00–16:00",
  total: "950 000 сум",
  order: "SRP-00042",
};

function previewTitle(template: string) {
  return template
    .replace(/\{(\w+)\}/g, (match, key: string) => sampleValues[key] ?? match)
    .replace(/\s+/g, " ")
    .trim();
}

export function AdminCalendarSection({ oauthResult = "", oauthMessage = "" }: { oauthResult?: string; oauthMessage?: string }) {
  const section = useAdminSection<CalendarPayload>("calendar");
  const mutation = useSectionMutation("calendar", section.refresh);
  const status = section.data?.status;
  const events = useMemo(() => section.data?.events ?? [], [section.data?.events]);
  const aliases = section.data?.aliases ?? [];
  const entities = useMemo(() => section.data?.entities ?? [], [section.data?.entities]);
  const stats = section.data?.event_stats ?? {};

  const [client, setClient] = useState({ client_id: "", client_secret: "" });
  const [draft, setDraft] = useState<CalendarSettings | null>(null);
  const [calendars, setCalendars] = useState<GoogleCalendarItem[]>([]);
  const [calendarChoice, setCalendarChoice] = useState("");
  const [loadingCalendars, setLoadingCalendars] = useState(false);
  const [filter, setFilter] = useState<string>("");
  const [alias, setAlias] = useState({ phrase: "", entity_slug: "" });
  const [testText, setTestText] = useState("");
  const [recognition, setRecognition] = useState<Recognition | null>(null);
  const aliasInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!oauthResult) return;
    if (oauthResult === "connected") toast.success("Google Календарь подключён");
    else toast.error(oauthMessage || "Не удалось подключить Google Календарь");
    window.history.replaceState(null, "", "/admin/calendar");
  }, [oauthMessage, oauthResult]);

  useEffect(() => {
    if (!section.data?.settings) return;
    const timeout = window.setTimeout(() => {
      setDraft({ ...(section.data?.settings as CalendarSettings) });
      setCalendarChoice(section.data?.status?.calendar_id ?? "");
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [section.data]);

  const visibleEvents = useMemo(
    () => (filter ? events.filter((item) => item.match_status === filter || (filter === "own" && item.match_status === "own_moved")) : events),
    [events, filter],
  );
  const programs = entities.filter((item) => item.kind === "program");
  const characters = entities.filter((item) => item.kind === "character");

  async function saveClient(event: FormEvent) {
    event.preventDefault();
    const result = await mutation.run("client", { action: "save_client", ...client }, "Данные сохранены");
    if (result) setClient({ client_id: "", client_secret: "" });
  }

  async function connect() {
    const result = (await mutation.run("connect", { action: "oauth_start" }, "Открываем Google…")) as (SectionEnvelope & { auth_url?: string }) | null;
    if (result?.auth_url) window.location.assign(result.auth_url);
  }

  async function loadCalendars() {
    setLoadingCalendars(true);
    try {
      const result = await postAdminSection<SectionEnvelope & { calendars?: GoogleCalendarItem[] }>("calendar", { action: "list_calendars" });
      if (result.success === false) throw new Error(result.message || "Не удалось получить календари.");
      const items = result.calendars ?? [];
      setCalendars(items);
      if (!calendarChoice && items[0]) setCalendarChoice(items[0].id);
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "Не удалось получить календари.");
    } finally {
      setLoadingCalendars(false);
    }
  }

  async function saveSettings(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    await mutation.run("settings", { action: "save_settings", settings: draft }, "Настройки сохранены");
  }

  async function addAlias(event: FormEvent) {
    event.preventDefault();
    if (!alias.phrase.trim() || !alias.entity_slug) return;
    const result = await mutation.run("alias-new", { action: "add_alias", ...alias }, "Слово добавлено");
    if (result) setAlias({ phrase: "", entity_slug: "" });
  }

  async function testRecognition(event: FormEvent) {
    event.preventDefault();
    if (!testText.trim()) return;
    try {
      const result = await postAdminSection<SectionEnvelope & { recognition?: Recognition }>("calendar", { action: "preview", text: testText });
      setRecognition(result.recognition ?? null);
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "Не удалось проверить текст.");
    }
  }

  function prefillAlias(summary: string) {
    setAlias((current) => ({ ...current, phrase: summary.slice(0, 80) }));
    aliasInput.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    aliasInput.current?.focus();
  }

  function insertPlaceholder(key: string) {
    setDraft((current) => (current ? { ...current, title_template: `${current.title_template} {${key}}`.trim() } : current));
  }

  async function copyRedirect() {
    if (!status?.redirect_uri) return;
    try {
      await navigator.clipboard.writeText(status.redirect_uri);
      toast.success("Адрес скопирован");
    } catch {
      toast.error("Скопируйте адрес вручную");
    }
  }

  const connected = Boolean(status?.connected);
  const alerts = [status?.auth_error, status?.last_import_error, status?.last_export_error].filter(Boolean) as string[];

  return (
    <>
      <div className="admin-metrics admin-metrics-compact">
        <article><span>Подключение</span><strong>{connected ? (status?.auth_error ? "Нужно переподключить" : "Работает") : "Не подключено"}</strong></article>
        <article><span>Календарь</span><strong title={status?.calendar_summary}>{status?.calendar_summary || "Не выбран"}</strong></article>
        <article><span>Закрывают время</span><strong>{stats.matched ?? 0}</strong></article>
        <article><span>Не распознано</span><strong>{stats.unmatched ?? 0}</strong></article>
        <article><span>Ждут выгрузки</span><strong>{status?.queue_pending ?? 0}</strong></article>
        <article><span>Прочитано</span><strong>{status?.last_import_at_label || "—"}</strong></article>
      </div>

      <AdminSectionState error={section.error} loading={section.loading} onRetry={() => void section.refresh()} />
      {!section.loading && !section.error && status ? (
        <div className="admin-calendar-stack">
          {alerts.length ? (
            <div className="admin-calendar-alert" role="alert">
              <AlertTriangle />
              <div>{alerts.map((message) => <p key={message}>{message}</p>)}</div>
            </div>
          ) : null}

          <div className="admin-dashboard-grid">
            <section className="admin-surface">
              <div className="admin-surface-head">
                <div><p className="eyebrow">ШАГ 1 · ПОДКЛЮЧЕНИЕ</p><h2>Аккаунт Google</h2><p>Доступ выдаётся через экран Google — пароль от почты сайт не видит.</p></div>
                {connected ? <span className="content-status status-active"><CheckCircle2 size={14} /> Подключено</span> : null}
              </div>

              {!status.client_configured ? (
                <form className="admin-form-stack" onSubmit={(event) => void saveClient(event)}>
                  <p className="admin-note">Один раз создайте OAuth-клиент в Google Cloud (инструкция ниже) и вставьте его данные.</p>
                  <label>Client ID<input autoComplete="off" placeholder="1234567890-abc.apps.googleusercontent.com" required value={client.client_id} onChange={(event) => setClient((current) => ({ ...current, client_id: event.target.value }))} /></label>
                  <label>Client Secret<input autoComplete="new-password" required type="password" value={client.client_secret} onChange={(event) => setClient((current) => ({ ...current, client_secret: event.target.value }))} /></label>
                  <button className="button button-violet" disabled={mutation.pendingKey === "client"} type="submit"><Save size={17} /> Сохранить данные приложения</button>
                </form>
              ) : !connected ? (
                <div className="admin-form-stack">
                  <p className="admin-note">Нажмите кнопку, войдите в Google-аккаунт, в котором ведётся календарь заказов, и разрешите доступ к календарю.</p>
                  <button className="button button-primary admin-calendar-connect" disabled={mutation.pendingKey === "connect"} onClick={() => void connect()} type="button"><CalendarDays size={18} /> Подключить Google Календарь</button>
                  {status.client_source === "admin" ? (
                    <details className="admin-calendar-details">
                      <summary>Заменить данные приложения Google</summary>
                      <form className="admin-form-stack" onSubmit={(event) => void saveClient(event)}>
                        <label>Client ID<input autoComplete="off" placeholder={status.client_id} required value={client.client_id} onChange={(event) => setClient((current) => ({ ...current, client_id: event.target.value }))} /></label>
                        <label>Client Secret<input autoComplete="new-password" required type="password" value={client.client_secret} onChange={(event) => setClient((current) => ({ ...current, client_secret: event.target.value }))} /></label>
                        <button className="button button-secondary" disabled={mutation.pendingKey === "client"} type="submit"><Save size={17} /> Сохранить</button>
                      </form>
                    </details>
                  ) : null}
                </div>
              ) : (
                <div className="admin-form-stack">
                  <dl className="admin-calendar-facts">
                    <div><dt>Аккаунт</dt><dd>{status.account_email || "—"}</dd></div>
                    <div><dt>Подключён</dt><dd>{status.connected_at_label || "—"}</dd></div>
                    <div><dt>Календарь заказов</dt><dd>{status.calendar_summary || "Не выбран"}</dd></div>
                  </dl>
                  <div className="admin-calendar-picker">
                    {calendars.length ? (
                      <>
                        <label>Какой календарь использовать<select value={calendarChoice} onChange={(event) => setCalendarChoice(event.target.value)}>{calendars.map((item) => <option key={item.id} value={item.id}>{item.summary}{item.primary ? " (основной)" : ""}</option>)}</select></label>
                        <button className="button button-violet" disabled={!calendarChoice || mutation.pendingKey === "select"} onClick={() => void mutation.run("select", { action: "select_calendar", calendar_id: calendarChoice }, "Календарь выбран")} type="button"><CalendarCheck2 size={17} /> Использовать</button>
                      </>
                    ) : (
                      <button className="button button-secondary" disabled={loadingCalendars} onClick={() => void loadCalendars()} type="button"><CalendarDays size={17} /> {loadingCalendars ? "Загружаем…" : status.calendar_id ? "Сменить календарь" : "Выбрать календарь"}</button>
                    )}
                  </div>
                  <div className="admin-row-actions">
                    {status.auth_error ? <button className="button button-primary" disabled={mutation.pendingKey === "connect"} onClick={() => void connect()} type="button"><RefreshCw size={17} /> Переподключить</button> : null}
                    <button className="button button-danger" disabled={mutation.pendingKey === "disconnect"} onClick={() => { if (window.confirm("Отключить Google Календарь? События из календаря перестанут закрывать время на сайте.")) void mutation.run("disconnect", { action: "disconnect" }, "Календарь отключён"); }} type="button"><LogOut size={17} /> Отключить</button>
                  </div>
                </div>
              )}

              <details className="admin-calendar-details">
                <summary>Как создать доступ в Google Cloud (один раз)</summary>
                <ol className="admin-calendar-steps">
                  <li>Откройте <a href="https://console.cloud.google.com/" rel="noreferrer" target="_blank">console.cloud.google.com</a> и создайте проект, например «Surpriz».</li>
                  <li>В «APIs &amp; Services → Library» включите <b>Google Calendar API</b>.</li>
                  <li>В «OAuth consent screen» выберите тип <b>External</b>, укажите название и почту, затем нажмите <b>Publish app</b> (статус «In production»), иначе доступ будет слетать каждые 7 дней.</li>
                  <li>В «Credentials → Create credentials → OAuth client ID» выберите тип <b>Web application</b> и добавьте в «Authorized redirect URIs» адрес ниже.</li>
                  <li>Скопируйте Client ID и Client Secret в форму выше и нажмите «Подключить». Google покажет предупреждение о непроверенном приложении — нажмите «Дополнительно → Перейти».</li>
                </ol>
                <div className="admin-calendar-copy"><code>{status.redirect_uri}</code><button className="button button-secondary" onClick={() => void copyRedirect()} type="button"><Copy size={16} /> Копировать</button></div>
              </details>
            </section>

            <aside className="admin-surface">
              <div className="admin-surface-head"><div><p className="eyebrow">КАК ЭТО РАБОТАЕТ</p><h2>Обмен с календарём</h2></div><BookOpenText /></div>
              <ul className="admin-calendar-howto">
                <li><b>Календарь → сайт.</b> Дата и время берутся из события, шоу и персонажи — из названия и описания. Распознанные персонажи становятся занятыми на это время (с запасом 1 час до и после).</li>
                <li><b>Сайт → календарь.</b> Когда заказ подтверждают в Telegram-боте или в админке, он появляется в календаре с полной карточкой заказа. Отмена заказа удаляет событие.</li>
                <li><b>Пишите как привыкли:</b> «Стандарт — Леди Баг и Супер-Кот, Аня 6 лет». Если слово не распознаётся, добавьте его в словарь ниже.</li>
              </ul>
              <form className="admin-form-stack admin-calendar-test" onSubmit={(event) => void testRecognition(event)}>
                <label>Проверить распознавание<textarea placeholder="Например: Neon Lux, Человек-паук №2 + Дэдпул" rows={3} value={testText} onChange={(event) => setTestText(event.target.value)} /></label>
                <button className="button button-secondary" disabled={!testText.trim()} type="submit"><ScanSearch size={17} /> Проверить</button>
                {recognition ? (
                  recognition.matched ? (
                    <div className="admin-chip-list admin-calendar-chips">{[...recognition.programs, ...recognition.characters].map((name) => <span key={name}>{name}</span>)}</div>
                  ) : <p className="admin-note">Ничего не распознано — добавьте слово в словарь.</p>
                ) : null}
              </form>
            </aside>
          </div>

          {draft ? (
            <form className="admin-surface" onSubmit={(event) => void saveSettings(event)}>
              <div className="admin-surface-head">
                <div><p className="eyebrow">ШАГ 2 · НАСТРОЙКИ</p><h2>Синхронизация</h2><p>{status.worker_hint}</p></div>
                <div className="admin-row-actions">
                  <button className="button button-secondary" disabled={!connected || mutation.pendingKey === "sync"} onClick={() => void mutation.run("sync", { action: "sync_now" }, "Синхронизировано")} type="button"><RefreshCw size={17} /> {mutation.pendingKey === "sync" ? "Синхронизируем…" : "Синхронизировать сейчас"}</button>
                </div>
              </div>
              <div className="admin-calendar-settings">
                <div className="admin-toggle-list">
                  <label className="admin-toggle"><span><strong>Закрывать время по календарю</strong><small>События календаря делают персонажей и шоу занятыми в конструкторе и при оформлении заказа.</small></span><input checked={draft.import_enabled} onChange={(event) => setDraft({ ...draft, import_enabled: event.target.checked })} type="checkbox" /><i /></label>
                  <label className="admin-toggle"><span><strong>Добавлять подтверждённые заказы</strong><small>После подтверждения в Telegram-боте или админке заказ появляется в календаре.</small></span><input checked={draft.export_enabled} onChange={(event) => setDraft({ ...draft, export_enabled: event.target.checked })} type="checkbox" /><i /></label>
                  <label className="admin-toggle"><span><strong>Нераспознанные события закрывают всё время</strong><small>Включите, если в календаре только заказы: тогда запись без узнаваемых персонажей закроет это время для всех.</small></span><input checked={draft.block_unmatched} onChange={(event) => setDraft({ ...draft, block_unmatched: event.target.checked })} type="checkbox" /><i /></label>
                </div>
                <div className="admin-form-stack">
                  <label>Как часто читать календарь<select value={draft.poll_minutes} onChange={(event) => setDraft({ ...draft, poll_minutes: Number(event.target.value) })}>{(section.data?.poll_choices ?? [5]).map((minutes) => <option key={minutes} value={minutes}>Каждые {minutes} мин</option>)}</select></label>
                  <label>Цвет заказов с сайта<select value={draft.color_id} onChange={(event) => setDraft({ ...draft, color_id: event.target.value })}>{(section.data?.colors ?? []).map((color) => <option key={color.id || "default"} value={color.id}>{color.name}</option>)}</select></label>
                  <label>Название события<input maxLength={200} value={draft.title_template} onChange={(event) => setDraft({ ...draft, title_template: event.target.value })} /></label>
                  <div className="admin-calendar-placeholders" aria-label="Подстановки">
                    {(section.data?.placeholders ?? []).map((item) => <button key={item.key} onClick={() => insertPlaceholder(item.key)} title={item.label} type="button">{`{${item.key}}`}</button>)}
                    <button onClick={() => setDraft({ ...draft, title_template: section.data?.default_title_template ?? draft.title_template })} type="button">по умолчанию</button>
                  </div>
                  <p className="admin-note">Пример: <b>{previewTitle(draft.title_template)}</b>. В описание события попадает та же карточка заказа, что приходит в Telegram.</p>
                </div>
              </div>
              <div className="admin-row-actions admin-calendar-actions">
                <button className="button button-violet" disabled={mutation.pendingKey === "settings"} type="submit"><Save size={17} /> {mutation.pendingKey === "settings" ? "Сохраняем…" : "Сохранить настройки"}</button>
                <button className="button button-secondary" disabled={!connected || !status.calendar_id || mutation.pendingKey === "backfill"} onClick={() => { if (window.confirm("Добавить в календарь все будущие подтверждённые заказы? Уже добавленные не задвоятся.")) void mutation.run("backfill", { action: "backfill" }, "Заказы выгружены"); }} type="button"><UploadCloud size={17} /> Выгрузить подтверждённые заказы</button>
              </div>
            </form>
          ) : null}

          <section className="admin-surface">
            <div className="admin-surface-head">
              <div><p className="eyebrow">БЛИЖАЙШИЕ СОБЫТИЯ</p><h2>Что видит сайт</h2><p>События на 6 месяцев вперёд. Нераспознанные записи сайт не закрывает — проверьте их.</p></div>
              <div className="admin-calendar-filter" role="group" aria-label="Фильтр событий">
                {eventFilters.map((item) => <button aria-pressed={filter === item.key} className={filter === item.key ? "is-active" : ""} key={item.key || "all"} onClick={() => setFilter(item.key)} type="button">{item.label}</button>)}
              </div>
            </div>
            {!visibleEvents.length ? (
              <div className="admin-empty"><CalendarDays /> {connected ? "Событий по фильтру нет." : "Подключите календарь, чтобы увидеть события."}</div>
            ) : (
              <div className="admin-table-wrap">
                <table className="admin-data-table admin-calendar-table">
                  <thead><tr><th>Когда</th><th>Событие</th><th>Распознано</th><th>Статус</th><th>Действия</th></tr></thead>
                  <tbody>
                    {visibleEvents.map((item) => {
                      const recognized = [...item.program_names, ...item.character_names];
                      return (
                        <tr key={item.event_key}>
                          <td data-label="Когда"><strong>{item.date_label}</strong><small>{item.time_label}</small></td>
                          <td data-label="Событие"><strong>{item.summary}</strong>{item.order_public_id ? <small>Заказ {item.order_public_id}</small> : null}</td>
                          <td data-label="Распознано">{recognized.length ? <div className="admin-chip-list">{recognized.map((name) => <span key={name}>{name}</span>)}</div> : <small>{item.match_status === "own" ? "Заказ уже учтён на сайте" : "—"}</small>}</td>
                          <td data-label="Статус"><span className={`content-status ${statusClass[item.match_status] ?? ""}`}>{item.status_label}</span>{item.blocks_all ? <small>Закрывает время для всех</small> : null}{item.note ? <small>{item.note}</small> : null}</td>
                          <td data-label="Действия">
                            <div className="admin-row-actions">
                              {item.html_link ? <a aria-label="Открыть в Google Календаре" href={item.html_link} rel="noreferrer" target="_blank"><ExternalLink size={17} /></a> : null}
                              {item.match_status === "unmatched" ? <button aria-label="Добавить слово в словарь" onClick={() => prefillAlias(item.summary)} title="Добавить слово в словарь" type="button"><ListPlus size={17} /></button> : null}
                              {item.match_status !== "own" ? (
                                <button
                                  aria-label={item.match_status === "ignored" ? "Снова учитывать" : "Не учитывать"}
                                  disabled={mutation.pendingKey === `ignore-${item.event_key}`}
                                  onClick={() => void mutation.run(`ignore-${item.event_key}`, { action: "toggle_ignore", event_key: item.event_key, ignored: item.match_status !== "ignored" }, "Событие обновлено")}
                                  title={item.match_status === "ignored" ? "Снова учитывать" : "Не учитывать это событие"}
                                  type="button"
                                >
                                  {item.match_status === "ignored" ? <Link2 size={17} /> : <EyeOff size={17} />}
                                </button>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="admin-surface">
            <div className="admin-surface-head"><div><p className="eyebrow">СЛОВАРЬ</p><h2>Свои сокращения</h2><p>Научите сайт вашим словам: «ЛБ» → Леди Баг и Супер-Кот, «Кальмар» → Игра в кальмара.</p></div></div>
            <form className="admin-calendar-alias-form" onSubmit={(event) => void addAlias(event)}>
              <label>Как пишут в календаре<input maxLength={80} placeholder="ЛБ" ref={aliasInput} required value={alias.phrase} onChange={(event) => setAlias((current) => ({ ...current, phrase: event.target.value }))} /></label>
              <label>Что это значит<select required value={alias.entity_slug} onChange={(event) => setAlias((current) => ({ ...current, entity_slug: event.target.value }))}><option value="">Выберите…</option><optgroup label="Шоу-программы">{programs.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}</optgroup><optgroup label="Персонажи">{characters.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}</optgroup></select></label>
              <button className="button button-violet" disabled={!alias.phrase.trim() || !alias.entity_slug || mutation.pendingKey === "alias-new"} type="submit"><ListPlus size={17} /> Добавить</button>
            </form>
            {aliases.length ? (
              <ul className="admin-calendar-aliases">
                {aliases.map((item) => (
                  <li key={item.id}>
                    <span><b>{item.phrase}</b> → {item.entity_name}</span>
                    <button aria-label={`Удалить «${item.phrase}»`} disabled={mutation.pendingKey === `alias-${item.id}`} onClick={() => void mutation.run(`alias-${item.id}`, { action: "delete_alias", id: item.id }, "Слово удалено")} type="button"><Trash2 size={16} /></button>
                  </li>
                ))}
              </ul>
            ) : <p className="admin-note">Своих слов пока нет — стандартные названия шоу и персонажей из каталога распознаются сами.</p>}
          </section>
        </div>
      ) : null}
    </>
  );
}
