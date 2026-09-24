# Order Builder

Пошаговая сборка заказа на `/party-builder/`. Файл: `templates/site/order_builder_content.html`. Бэкенд: `core/customer_panel.py`.

## Шаги

1. **Программа** — выбор шоу-программы (опционально)
2. **Персонажи** — список аниматоров (опционально, можно несколько)
3. **Бесплатный бонус** — если у программы есть [[Free-Choice-Bonus]], radio-выбор
4. **Дата и время** — календарь с busy-list, проверкой 1ч лида
5. **Адрес** — Yandex-карта с полигоном границы Ташкента (шаг 5 в UI)
6. **Оплата** — итог + способ оплаты после мероприятия

## Карта: только Ташкент (OSM)

- Зона обслуживания: [`content/geo/tashkent-city-polygon.json`](../content/geo/tashkent-city-polygon.json) — официальная граница **города Ташкент** (OSM relation `2216724`, ODbL), упрощённый `polygon`, `mask_outer` для затемнения снаружи.
- Логика: [`core/tashkent_geo.py`](../core/tashkent_geo.py) — `is_inside_tashkent()`, валидация колец при загрузке.
- В шаблон: `tashkent_map_polygon`, `tashkent_map_mask_outer`, `tashkent_map_bbox`.
- UX **hard-lock**: карта удерживается в пределах зоны Ташкента; подтверждение вне фиолетовой границы недоступно.
- На карте: затемнение вне полигона + фиолетовая граница допустимой зоны (кольца с корректной ориентацией для «дыры»).
- На сервере: `create_party_order()` отклоняет координаты вне полигона (`errors.map_location`).

## Календарь и busy-list

`get_busy_dates_summary()` возвращает `{by_date: {iso: {count, bookings: [{public_id, time_from, time_to, program_slug, character_slugs, ...}]}}}`. Билдер фильтрует busy-list **только** по выбранной программе/персонажу — на странице видно занятость только релевантных ресурсов.

## Лид-тайм и буферы

```python
MIN_ORDER_LEAD_TIME_MINUTES = 1440
CHARACTER_BOOKING_BUFFER_BEFORE_MINUTES = 180
CHARACTER_BOOKING_BUFFER_AFTER_MINUTES = 60
```

Проверка через `_check_program_conflict` и `check_character_availability(program_slug=...)`.

События подключённого Google Календаря закрывают время так же, как заказы: распознанные персонажи и шоу — только для себя, нераспознанные — для всех, если это включено в настройках ([[Google-Calendar]]).

## Persistence в браузере

`localStorage` ключ `surpriz_party_builder_draft_v1` — сохраняет выбор между перезагрузками.

### Гочa: stale draft vs deep-link `?character=`

`collectDraft()` собирает все `<input type="checkbox">` (включая пустые `character_slugs: []`). Без защиты `applyDraft()` потом сбрасывал серверный preselect, когда пользователь приходил с `/character/<slug>/` → `/party-builder/?character=<slug>`.

Защита в `applyDraft`:
```js
const urlHasCharacterParam = name === "character_slugs" && /[?&]character=/.test(window.location.search);
if (urlHasCharacterParam && list.length === 0) return;
```
Если URL содержит `?character=` и в drafте пустой список — **не трогаем** чекбоксы (сервер их уже выставил).

## Submit

`create_party_order()` в `customer_store.py`:
- Извлекает `[Бонус: <name>]` маркер из form_data → пишет в notes
- Парсит координаты адреса
- Триггерит TG-уведомление через `admin_notifications.send_new_order_notification`

## Связано

- [[Free-Choice-Bonus]]
- [[Catalog]]
- [[Telegram-Integration]]
- [[Customer-Portal]]
