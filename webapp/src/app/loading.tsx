export default function Loading() {
  return (
    <div className="page-loading" role="status" aria-live="polite">
      <span className="skeleton skeleton-title" />
      <span className="skeleton skeleton-line" />
      <div className="skeleton-grid">
        {Array.from({ length: 4 }, (_, index) => (
          <span className="skeleton skeleton-card" key={index} />
        ))}
      </div>
      <span className="sr-only">Загрузка страницы</span>
    </div>
  );
}
