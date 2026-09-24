# Architecture

## Точка входа

`app.py` — Flask app, роуты, view-функции. Все публичные страницы рендерятся через `render_public_page(page)`, где `page` — `PageBundle` (head, body, content, footer).

## Модули `core/`

| Модуль | Что делает |
|---|---|
| `loader.py` | Загрузка legacy WP-страниц, нормализация HTML, инжекция кастомного хедера/футера, [[Mobile-Bottom-Bar]] |
| `catalog_store.py` | Персонажи, категории, теги, [[Search]] |
| `customer_store.py` | Заказы, проверка доступности, лента-шоу варианты |
| `customer_panel.py` | Builder заказа, личный кабинет |
| `admin_store.py` | CRUD-операции для всех сущностей админки |
| `admin_panel.py` | Routes админки, формы, таблицы |
| `admin_notifications.py` | TG-bot для уведомлений админу о новых заказах + callback-кнопки |
| `addon_store.py` | Доп. услуги к программам ([[Free-Choice-Bonus]]) |
| `catalog_site.py` | Публичная страница `/catalog/` |
| `google_calendar.py` / `google_calendar_store.py` | Синхронизация с Google Календарём ([[Google-Calendar]]) |

## Данные

SQLite в `content/data/admin/` на сервере, `content/data/admin/` локально. Основные таблицы:

- `managed_characters` — персонажи + show-программы (общая таблица, разделение по `entity_type`)
- `managed_categories`, `managed_tags`
- `character_categories`, `character_tags` — many-to-many
- `show_program_addons` — допы к программам, столбец `is_free_choice`
- `customer_orders` — заказы
- `admin_telegram_settings` — токены TG бота и Gateway
- `admin_telegram_recipients` — кому слать notifications
- `admin_telegram_processed_updates` — дедуп callback'ов
- `google_calendar_*` — настройки, события календаря, очередь выгрузки заказов ([[Google-Calendar]])

## Шаблоны

Jinja2 в `templates/`. Public — `templates/site/`, админка — `templates/admin/`.
