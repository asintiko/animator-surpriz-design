# Mobile Bottom Bar

Закреплённая нижняя навигация на мобильных (5 кнопок: Главная / Шоу / Собрать (CTA) / Костюмы / Профиль). Реализована в `core/loader.py` → `MOBILE_BOTTOM_BAR_BLOCK`.

## Связанная сага: sticky-header (#c-header)

Та же Astra `transform: matrix(1,0,0,1,0,0)` ломала и **верхний** sticky-хедер (двоился, дёргался при скролле на iOS). Решено через `STICKY_HEADER_FIX_BLOCK` в `core/loader.py`:
- CSS снимает `transform/perspective/filter` со всех ancestor-обёрток (`html, body, #page, .site, .ast-container, .elementor-location-header, .elementor-location-header > *`)
- JS `stripBodyTransform()` + MutationObserver удаляет inline `transform:` на body, если Astra пытается переинжектить.
- Не используем move-to-html для хедера — ломает Elementor inline-styles потомков. Только нейтрализация transform.

## Проблема, которую решали

Astra-тема (legacy WP-наследие) применяет к `<body>` ноп-трансформ типа `transform: matrix(1,0,0,1,0,0)`. По CSS-спеке это создаёт **containing block**, и `position: fixed` начинает резолвиться относительно `<body>`, а не viewport. Бар на мобильных «летал» вместе со скроллом.

## Решение

При инициализации скрипт **переносит** `<nav id="site-mobile-bottom-bar">` из `<body>` в `<html>` (`document.documentElement.appendChild(bar)`). У `<html>` нет ancestor с transform — `position: fixed` всегда привязан к viewport.

```js
if (bar.parentElement !== document.documentElement) {
  document.documentElement.appendChild(bar);
}
```

`MutationObserver` на `<html>` восстанавливает позицию, если кто-то (Elementor sticky kit, page transitions) утаскивает бар обратно в body.

## Что НЕ работало (и почему)

| Подход | Почему провалился |
|---|---|
| `transform: none !important` на `body` через CSS | Astra переписывает inline-style уже после загрузки |
| MutationObserver на `body[style]` | Срабатывает с задержкой, бар успевает «взлететь» |
| JS scroll-binding с `position:absolute` + `top = scrollY+innerH-h` | Мерцание/дрожь на каждом scroll-event |

## CSS

`@media (max-width: 860px)` в `MOBILE_BOTTOM_BAR_BLOCK`:
- `position: fixed; bottom: 0; left: 0; right: 0; z-index: 2147483646`
- `body { padding-bottom: 76px }` — компенсация под бар
- `env(safe-area-inset-bottom)` для iPhone notch

## Связано

- [[Architecture]]
- [[Deployment]]
