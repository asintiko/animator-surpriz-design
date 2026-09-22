# Admin Panel

Администрирование на `/admin/`. Бэкенд: `core/admin_panel.py`. Шаблон-хаб: `templates/admin/dashboard.html`.

## Логин

Хардкод-простой, через `ADMIN_PASSWORD` env. Сессия через Flask `session`.

## Вкладки (tab=...)

| Tab | Что |
|---|---|
| `orders` | Список заказов с поиском по тел/TG, фильтрами по дате, иконками действий (карта, TG, повтор уведомления) |
| `characters` | CRUD персонажей |
| `programs` | CRUD шоу-программ + addons + [[Free-Choice-Bonus]] |
| `categories` | Категории (auto-tag) |
| `tags` | Теги |
| `notifications` | Telegram bot+gateway токены, recipients ([[Telegram-Integration]]) |
| `settings` | Глобальные флаги |

## Auto-refresh заказов

JS-скрипт раз в 8 секунд опрашивает `/admin/api/orders/recent` и обновляет таблицу — админ видит новые заказы без F5.

## Формы

- `character_form.html` — слайдеры cover-offset, теги, категории
- `program_form.html` — addons block, лента-шоу варианты (атлас/серпантин/бумага)

## Связано

- [[Architecture]]
- [[Catalog]]
- [[Telegram-Integration]]
