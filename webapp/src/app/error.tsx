"use client";

export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="empty-page container">
      <p className="eyebrow">ЧТО-ТО ПОШЛО НЕ ТАК</p>
      <h1>Не удалось загрузить страницу</h1>
      <p>Ваши выбранные данные не потеряны. Попробуйте ещё раз.</p>
      <button className="button button-primary" onClick={reset}>Повторить</button>
    </section>
  );
}
