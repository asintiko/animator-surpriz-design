# Catalog

Каталог костюмов и шоу-программ. Публичный URL: `/catalog/`. Шаблон: `templates/site/catalog_content.html`. Бэкенд: `core/catalog_site.py`.

## UI

- **Sidebar**: поиск ([[Search]]), категории, теги
- **Сетка карточек** 3-кол на десктопе, 1-кол на мобильных
- **Toggle grid/list** — сохраняется в localStorage `surprizCatalogView`
- **Пагинация** — стандартная WP-style
- **Карточка** (`.surpriz-card`): hero-фото с настраиваемым cover-offset, имя, краткое описание, кнопка «Подробнее»

## Hero-image positioning

Каждый персонаж в админке имеет:
- `cover_offset_x` (0..100, default 50) — горизонтальный сдвиг
- `cover_offset_y` (0..100, default 50) — вертикальный
- `cover_fit` (`cover` | `contain`)

В шаблоне:
```html
<img style="object-position: {{ x }}% {{ y }}%; object-fit: {{ fit }};">
```

В админке — слайдеры с live-preview (`templates/admin/character_form.html`).

## Категории и теги

- Каждая категория автоматически создаёт matching tag (см. `create_category` в `catalog_store.py`)
- У персонажа неограниченное число тегов (3, 5, 10, 40+)
- many-to-many через `character_categories` / `character_tags`

## Live-search

`/api/catalog/search?q=...` — debounced 220ms на input. JSON ответ → перерисовка `[data-products-list]` без перезагрузки.

### Картинки в результатах

Глобальный CSS в `loader.py` фейдит lazy-img: `img[loading="lazy"]:not([data-loaded]) { opacity: 0 }`. Атрибут `data-loaded="1"` ставится JS-функцией `bindImage()` после `load`/`error`.

Для картинок, инжектящихся через `innerHTML` (live-search, builder, header dropdown), используется **MutationObserver** на `<body>` — каждый новый `<img loading="lazy">` авто-байндится. Без observer'а такие картинки оставались с `opacity: 0`.

Точка фикса: `core/loader.py` → `bindImage()` + `imgObserver`.

## Связано

- [[Search]]
- [[Admin-Panel]]
- [[Architecture]]
