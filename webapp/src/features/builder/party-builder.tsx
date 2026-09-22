"use client";

import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  LocateFixed,
  MapPin,
  Search,
  ShieldCheck,
  Sparkles,
  UserRound,
} from "lucide-react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";
import { toast } from "sonner";

import { mutateJson } from "@/lib/client/mutate";
import { formatDuration, formatPrice } from "@/lib/catalog";
import type { CatalogCard } from "@/lib/types";

type BuilderState = {
  celebrationDate: string;
  timeFrom: string;
  age: number;
  childrenCount: number;
  programSlug: string;
  characterSlugs: string[];
  addressText: string;
  mapLabel: string;
  mapLat: number | null;
  mapLng: number | null;
  notes: string;
  celebrantName: string;
  fullName: string;
  phone: string;
  paymentMethod: "cash" | "bank";
};

type AvailabilityResponse = {
  success: boolean;
  available: boolean;
  message?: string;
};

type AddressSuggestion = {
  title: string;
  subtitle: string;
  uri: string;
  value: string;
};

const STORAGE_KEY = "surpriz-party-draft-v2";
const steps = ["Дата и детали", "Шоу и герои", "Адрес", "Контакты"];

function addMinutes(time: string, minutes: number) {
  const [hours = 0, currentMinutes = 0] = time.split(":").map(Number);
  const value = hours * 60 + currentMinutes + minutes;
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

function tomorrow() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  return date.toISOString().slice(0, 10);
}

function initialState(): BuilderState {
  return {
    celebrationDate: tomorrow(),
    timeFrom: "16:00",
    age: 6,
    childrenCount: 10,
    programSlug: "",
    characterSlugs: [],
    addressText: "",
    mapLabel: "",
    mapLat: null,
    mapLng: null,
    notes: "",
    celebrantName: "",
    fullName: "",
    phone: "+998 ",
    paymentMethod: "cash",
  };
}

export function PartyBuilder({
  shows,
  characters,
}: {
  shows: CatalogCard[];
  characters: CatalogCard[];
}) {
  const searchParams = useSearchParams();
  const [step, setStep] = useState(0);
  const [state, setState] = useState<BuilderState>(initialState);
  const [availability, setAvailability] = useState<"idle" | "available" | "unavailable">("idle");
  const [characterQuery, setCharacterQuery] = useState("");
  const [addressSuggestions, setAddressSuggestions] = useState<AddressSuggestion[]>([]);
  const [requestId, setRequestId] = useState("");
  const [code, setCode] = useState("");
  const [authPurpose, setAuthPurpose] = useState<"register" | "login">("register");
  const [verified, setVerified] = useState(false);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    const stored = window.sessionStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as Partial<BuilderState>;
        const timeout = window.setTimeout(() => setState((current) => ({ ...current, ...parsed })), 0);
        return () => window.clearTimeout(timeout);
      } catch {
        window.sessionStorage.removeItem(STORAGE_KEY);
      }
    }
  }, []);

  useEffect(() => {
    const program = searchParams.get("program");
    const selectedCharacters = searchParams.get("characters")?.split(",").filter(Boolean) ?? [];
    if (!program && !selectedCharacters.length) return;
    const timeout = window.setTimeout(() => {
      setState((current) => ({
        ...current,
        programSlug: program ?? current.programSlug,
        characterSlugs: selectedCharacters.length ? selectedCharacters : current.characterSlugs,
      }));
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [searchParams]);

  useEffect(() => {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const selectedShow = shows.find((show) => show.slug === state.programSlug);
  const selectedCharacters = characters.filter((character) => state.characterSlugs.includes(character.slug));
  const duration = selectedShow?.default_duration_minutes ?? 60;
  const extraCharacters = selectedShow
    ? Math.max(0, selectedCharacters.length - selectedShow.included_characters_count)
    : 0;
  const firstExtra = extraCharacters > 0 ? selectedShow?.extra_character_price_3 ?? 0 : 0;
  const followingExtras = Math.max(0, extraCharacters - 1) * (selectedShow?.extra_character_price_4_plus ?? 0);
  const total = (selectedShow?.base_price ?? 0) + firstExtra + followingExtras;

  const filteredCharacters = useMemo(() => {
    const query = characterQuery.trim().toLocaleLowerCase("ru");
    if (!query) return characters.slice(0, 18);
    return characters
      .filter((character) => `${character.name} ${character.short_description}`.toLocaleLowerCase("ru").includes(query))
      .slice(0, 18);
  }, [characterQuery, characters]);

  function update<K extends keyof BuilderState>(key: K, value: BuilderState[K]) {
    setState((current) => ({ ...current, [key]: value }));
    if (["celebrationDate", "timeFrom", "programSlug", "characterSlugs"].includes(key)) {
      setAvailability("idle");
    }
  }

  function checkDate() {
    startTransition(async () => {
      try {
        const result = await mutateJson<AvailabilityResponse>("/api/availability", {
          character_slugs: state.characterSlugs,
          program_slug: state.programSlug || null,
          celebration_date: state.celebrationDate,
          time_from: state.timeFrom,
          time_to: addMinutes(state.timeFrom, duration),
          duration_minutes: duration,
        });
        if (result.available) {
          setAvailability("available");
          setStep(1);
          toast.success("Дата предварительно доступна");
        } else {
          setAvailability("unavailable");
          toast.error(result.message || "Это время уже занято.");
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Не удалось проверить дату.");
      }
    });
  }

  function suggestAddress(value: string) {
    update("addressText", value);
    if (value.trim().length < 3) {
      setAddressSuggestions([]);
      return;
    }
    startTransition(async () => {
      try {
        const result = await mutateJson<{ results: AddressSuggestion[] }>("/api/address/suggest", { text: value });
        setAddressSuggestions(result.results);
      } catch {
        setAddressSuggestions([]);
      }
    });
  }

  function chooseAddress(suggestion: AddressSuggestion) {
    startTransition(async () => {
      try {
        const result = await mutateJson<{ success: boolean; lat: number; lng: number; label: string }>(
          "/api/address/resolve",
          { uri: suggestion.uri, text: suggestion.value },
        );
        update("addressText", suggestion.value);
        update("mapLabel", result.label);
        update("mapLat", result.lat);
        update("mapLng", result.lng);
        setAddressSuggestions([]);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Не удалось определить адрес.");
      }
    });
  }

  function useLocation() {
    if (!navigator.geolocation) {
      toast.error("Геолокация не поддерживается этим браузером.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        update("mapLat", coords.latitude);
        update("mapLng", coords.longitude);
        update("mapLabel", "Точка с устройства — подтвердит менеджер");
        toast.success("Геопозиция добавлена");
      },
      () => toast.error("Не удалось получить геопозицию."),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  function requestCode() {
    startTransition(async () => {
      try {
        const result = await mutateJson<{ success: boolean; request_id: string; message?: string }>("/api/auth/send-code", {
          phone: state.phone,
          purpose: authPurpose,
          full_name: state.fullName,
          next: "/party-builder",
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
        await mutateJson("/api/auth/verify-code", {
          phone: state.phone,
          request_id: requestId,
          code,
        });
        setVerified(true);
        toast.success("Номер подтверждён");
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Неверный код.");
      }
    });
  }

  function submitOrder() {
    startTransition(async () => {
      try {
        const result = await mutateJson<{ success: boolean; public_id: string }>("/api/orders", {
          program_slug: state.programSlug || null,
          character_slugs: state.characterSlugs,
          celebration_date: state.celebrationDate,
          time_from: state.timeFrom,
          time_to: addMinutes(state.timeFrom, duration),
          duration_minutes: duration,
          celebrant_name: state.celebrantName,
          celebrant_age: state.age,
          children_count: state.childrenCount,
          address_text: state.addressText,
          map_label: state.mapLabel,
          map_lat: state.mapLat,
          map_lng: state.mapLng,
          payment_method: state.paymentMethod,
          notes: state.notes,
          idempotency_key: crypto.randomUUID(),
        });
        window.sessionStorage.removeItem(STORAGE_KEY);
        window.location.assign(`/account/orders/${result.public_id}?just_created=1`);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Не удалось создать заказ.");
      }
    });
  }

  return (
    <div className="builder-layout">
      <section className="builder-flow">
        <ol className="builder-progress" aria-label="Этапы заказа">
          {steps.map((label, index) => (
            <li className={index === step ? "is-active" : index < step ? "is-done" : undefined} key={label}>
              <span>{index < step ? <Check size={15} /> : index + 1}</span>{label}
            </li>
          ))}
        </ol>

        {step === 0 ? (
          <div className="builder-panel">
            <div className="builder-panel-heading"><CalendarDays /><div><h2>Когда состоится праздник?</h2><p>Бронируем минимум за 24 часа. Время — с 09:00 до 22:00.</p></div></div>
            <div className="builder-fields two">
              <label>Дата<input type="date" min={tomorrow()} value={state.celebrationDate} onChange={(event) => update("celebrationDate", event.target.value)} /></label>
              <label>Начало<select value={state.timeFrom} onChange={(event) => update("timeFrom", event.target.value)}>{Array.from({ length: 27 }, (_, index) => { const minutes = 9 * 60 + index * 30; const value = `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`; return <option key={value}>{value}</option>; })}</select></label>
              <label>Возраст ребёнка<input max={18} min={1} type="number" value={state.age} onChange={(event) => update("age", Number(event.target.value))} /></label>
              <label>Количество детей<input max={100} min={1} type="number" value={state.childrenCount} onChange={(event) => update("childrenCount", Number(event.target.value))} /></label>
            </div>
            {availability === "unavailable" ? <p className="inline-status error" role="alert">Выберите другое время или позвоните менеджеру.</p> : null}
            <div className="builder-actions"><button className="button button-primary" disabled={isPending} onClick={checkDate} type="button">{isPending ? "Проверяем…" : "Проверить дату"} <ArrowRight size={18} /></button></div>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="builder-panel">
            <div className="builder-panel-heading"><Sparkles /><div><h2>Выберите шоу и персонажей</h2><p>Достаточно шоу или хотя бы одного персонажа. Сумма обновляется сразу.</p></div></div>
            <h3 className="builder-subtitle">Шоу-программа</h3>
            <div className="builder-show-list">
              <button className={!state.programSlug ? "is-selected" : undefined} onClick={() => update("programSlug", "")} type="button"><span className="empty-thumb">—</span><span><strong>Только персонажи</strong><small>Без готовой шоу-программы</small></span></button>
              {shows.map((show) => <button className={state.programSlug === show.slug ? "is-selected" : undefined} key={show.id} onClick={() => update("programSlug", show.slug)} type="button"><span className="builder-thumb"><Image src={show.hero_file_path || "/brand/logo.png"} alt="" fill sizes="92px" /></span><span><strong>{show.name}</strong><small>{formatDuration(show.default_duration_minutes)} · {formatPrice(show.base_price)}</small></span><Check /></button>)}
            </div>
            <div className="builder-character-heading"><h3 className="builder-subtitle">Персонажи</h3><label><Search size={17} /><input placeholder="Найти героя" value={characterQuery} onChange={(event) => setCharacterQuery(event.target.value)} /></label></div>
            <div className="builder-character-grid">
              {filteredCharacters.map((character) => {
                const selected = state.characterSlugs.includes(character.slug);
                return <button className={selected ? "is-selected" : undefined} key={character.id} onClick={() => update("characterSlugs", selected ? state.characterSlugs.filter((slug) => slug !== character.slug) : [...state.characterSlugs, character.slug])} type="button"><span><Image src={character.hero_file_path || "/brand/logo.png"} alt="" fill sizes="120px" /></span><strong>{character.name}</strong>{selected ? <Check /> : null}</button>;
              })}
            </div>
            <div className="builder-actions split"><button className="button button-secondary" onClick={() => setStep(0)} type="button"><ArrowLeft /> Назад</button><button className="button button-primary" disabled={!state.programSlug && !state.characterSlugs.length} onClick={() => setStep(2)} type="button">Продолжить <ArrowRight /></button></div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="builder-panel">
            <div className="builder-panel-heading"><MapPin /><div><h2>Где состоится праздник?</h2><p>Заказы доступны только внутри установленной зоны Ташкента.</p></div></div>
            <label className="address-search">Адрес<input autoComplete="street-address" placeholder="Улица, дом или название места" value={state.addressText} onChange={(event) => suggestAddress(event.target.value)} /></label>
            {addressSuggestions.length ? <div className="address-suggestions">{addressSuggestions.map((suggestion) => <button key={suggestion.uri} onClick={() => chooseAddress(suggestion)} type="button"><strong>{suggestion.title}</strong><span>{suggestion.subtitle}</span></button>)}</div> : null}
            <div className="map-preview">
              <div><MapPin /><strong>{state.mapLabel || "Выберите адрес из подсказок"}</strong><span>{state.mapLat && state.mapLng ? `${state.mapLat.toFixed(5)}, ${state.mapLng.toFixed(5)}` : "Координаты ещё не подтверждены"}</span></div>
              <button className="button button-secondary" onClick={useLocation} type="button"><LocateFixed size={18} /> Моё местоположение</button>
            </div>
            <label>Комментарий к месту<textarea maxLength={400} placeholder="Дом, подъезд, ориентир или важная деталь" value={state.notes} onChange={(event) => update("notes", event.target.value)} /></label>
            <div className="builder-actions split"><button className="button button-secondary" onClick={() => setStep(1)} type="button"><ArrowLeft /> Назад</button><button className="button button-primary" disabled={!state.mapLat || !state.mapLng || !state.addressText} onClick={() => setStep(3)} type="button">Продолжить <ArrowRight /></button></div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="builder-panel">
            <div className="builder-panel-heading"><UserRound /><div><h2>Контакты и подтверждение</h2><p>Регистрация нужна только сейчас — чтобы сохранить заказ и показать его в кабинете.</p></div></div>
            <div className="builder-fields two">
              <label>Имя именинника<input value={state.celebrantName} onChange={(event) => update("celebrantName", event.target.value)} /></label>
              <label>Ваше имя<input autoComplete="name" value={state.fullName} onChange={(event) => update("fullName", event.target.value)} /></label>
              <label className="wide">Телефон<input autoComplete="tel" inputMode="tel" value={state.phone} onChange={(event) => update("phone", event.target.value)} /></label>
            </div>
            <fieldset className="auth-purpose"><legend>Аккаунт</legend><label><input checked={authPurpose === "register"} name="purpose" onChange={() => setAuthPurpose("register")} type="radio" /> Я впервые</label><label><input checked={authPurpose === "login"} name="purpose" onChange={() => setAuthPurpose("login")} type="radio" /> У меня есть аккаунт</label></fieldset>
            {!verified ? <div className="otp-box">{requestId ? <><label>Код из Telegram<input autoComplete="one-time-code" inputMode="numeric" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} /></label><button className="button button-violet" disabled={isPending || code.length !== 6} onClick={verifyCode} type="button">Подтвердить номер</button></> : <button className="button button-violet" disabled={isPending || state.phone.length < 9 || !state.fullName} onClick={requestCode} type="button">{isPending ? "Отправляем…" : "Получить код в Telegram"}</button>}</div> : <p className="inline-status success"><ShieldCheck /> Номер подтверждён</p>}
            <fieldset className="payment-choice"><legend>Способ расчёта после праздника</legend><label><input checked={state.paymentMethod === "cash"} name="payment" onChange={() => update("paymentMethod", "cash")} type="radio" /><span><strong>Наличными</strong><small>После проведения мероприятия</small></span></label><label><input checked={state.paymentMethod === "bank"} name="payment" onChange={() => update("paymentMethod", "bank")} type="radio" /><span><strong>Переводом</strong><small>Реквизиты даст менеджер</small></span></label></fieldset>
            <div className="builder-actions split"><button className="button button-secondary" onClick={() => setStep(2)} type="button"><ArrowLeft /> Назад</button><button className="button button-primary" disabled={!verified || isPending || !state.celebrantName} onClick={submitOrder} type="button">{isPending ? "Сохраняем…" : "Подтвердить заказ"} <ArrowRight /></button></div>
          </div>
        ) : null}
      </section>

      <aside className="builder-summary">
        <p className="eyebrow">ВАШ ПРАЗДНИК</p>
        <h2>Уже собрано</h2>
        <dl>
          <div><dt>Дата</dt><dd>{state.celebrationDate}, {state.timeFrom}</dd></div>
          <div><dt>Возраст</dt><dd>{state.age} лет</dd></div>
          <div><dt>Детей</dt><dd>{state.childrenCount}</dd></div>
          <div><dt>Программа</dt><dd>{selectedShow?.name || "Не выбрана"}</dd></div>
          <div><dt>Персонажи</dt><dd>{selectedCharacters.length ? selectedCharacters.map((item) => item.name).join(", ") : "Не выбраны"}</dd></div>
          <div><dt>Адрес</dt><dd>{state.addressText || "Не указан"}</dd></div>
        </dl>
        <div className="builder-total"><span>Итого</span><strong>{new Intl.NumberFormat("ru-RU").format(total)} сум</strong></div>
        <p className="builder-summary-note"><ShieldCheck /> Без онлайн-оплаты. Наличными или переводом после мероприятия.</p>
        <div className="builder-summary-progress"><span style={{ width: `${((step + 1) / steps.length) * 100}%` }} /></div>
      </aside>
    </div>
  );
}
