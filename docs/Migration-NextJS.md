# Миграция на Next.js

Перенос Flask-сайта Surpriz на современный стек. **Прод (Flask) не трогаем** — вся новая работа в папке `webapp/`.

## Стек нового приложения

- **Next.js 16** (App Router, Turbopack) + TypeScript
- **Tailwind CSS v4** (дизайн-токены через `@theme`)
- **Prisma + SQLite** — схема 1:1 с текущими 22 таблицами
- **next/font/google** — самохостинг шрифтов (zero layout shift)
- Node 22 / pnpm 10

## Принципы

- Дизайн повторяем **1:1** по [[site-design-guide]] (палитра, шрифты, радиусы).
- Чистый рерайт на Tailwind вместо порта Elementor/WordPress CSS (убираем `!important`-войны и баги).
- Инкрементально по слайсам, каждый слайс сверяем скриншотами с продом через Playwright.
- БД: на dev работаем с копией `webapp/data/site_admin.sqlite3`, прод-файл не трогаем.

## Шрифты (приоритет — повторяем точно)

Из [[site-design-guide]] + `content/routes/index/head.html`:

| Шрифт | Роль | CSS-переменная |
|---|---|---|
| **Rubik** | базовый UI, body, nav, кнопки, цены, футер, формы | `--font-rubik` |
| **Balsamiq Sans** | крупные тёплые заголовки | `--font-balsamiq` |
| **Amatic SC** | рукописный pretitle / eyebrow секций | `--font-amatic` |
| **Montserrat Alternates** | заголовки карточек шоу-программ | `--font-montserrat-alt` |
| **Roboto / Roboto Slab** | редкий вспомогательный текст (Elementor-наследие) | `--font-roboto`, `--font-roboto-slab` |

Подключены в `webapp/src/app/layout.tsx` через `next/font/google`, навешены на `<html>` как CSS-переменные, замаплены в Tailwind-токены `font-rubik` / `font-balsamiq` / `font-amatic` / `font-montserrat-alt`.

## Цветовая палитра (бренд-ядро)

| Токен | HEX | Назначение |
|---|---|---|
| purple | `#6C1BE3` | бренд-якоря, футер, вторичные CTA |
| orange | `#F26A20` | основное действие, тёплый акцент |
| pink | `#F80D66` | заголовки шоу-секций, подложки карточек |
| yellow | `#FFCA24` | иконки, хайлайты, кнопки заказа |
| yellow-alt | `#FEC02D` | вариант акцентного жёлтого |
| beige | `#F6F3ED` | фон секций цен/шоу |
| blue-hover | `#0088CC` | hover многих CTA |
| dark | `#181818` | основной тёмный текст |

Радиусы: `15px` (карточки/картинки/карты), `20px` (формы/мобильные блоки), `35px` (CTA-пилюли), `999px` (круглые/чипы).

## Статус слайсов

- [x] Скелет Next.js + шрифты + дизайн-токены
- [ ] Layout-шелл: header (sticky, лого, nav, телефон, orange CTA) + footer (purple бренд-зона)
- [ ] Публичные страницы: главная (hero), цены, контакты, о-нас
- [ ] Каталог + категории/теги + карточка персонажа + поиск
- [ ] Шоу-программы (табы/карусели, festive cards)
- [ ] Конструктор заказа (6 шагов, календарь, Яндекс-карты, бонусы)
- [ ] Клиентский портал (OTP-auth, кабинет, детали заказа)
- [ ] Админка (дашборд, CRUD, формы с превью обложек)
- [ ] Telegram-бот (нотификации + inline confirm/cancel + sendLocation)
- [ ] Prisma-схема + миграция данных
- [ ] Деплой (решаем отдельно)

## Соответствие модулей Flask → Next

| Flask | Next.js |
|---|---|
| `loader.py` (рендер, motion, bottom-bar) | layout + компоненты + CSS-токены |
| `catalog_store.py` / `catalog_site.py` | `lib/catalog/*` + server components |
| `customer_store.py` / `customer_panel.py` | `lib/orders/*` + API routes + portal pages |
| `admin_store.py` / `admin_panel.py` | `lib/admin/*` + `/admin` route group |
| `admin_notifications.py` (TG-бот) | `lib/telegram/*` + webhook route |
| route bundles (`content/routes/`) | React-страницы App Router |
