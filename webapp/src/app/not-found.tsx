import Link from "next/link";

export default function NotFound() {
  return (
    <section className="empty-page container">
      <p className="eyebrow">404</p>
      <h1>Такой страницы пока нет</h1>
      <p>Вернитесь в каталог или соберите праздник по шагам.</p>
      <div className="hero-actions">
        <Link className="button button-primary" href="/catalog">Каталог персонажей</Link>
        <Link className="button button-secondary" href="/party-builder">Собрать праздник</Link>
      </div>
    </section>
  );
}
