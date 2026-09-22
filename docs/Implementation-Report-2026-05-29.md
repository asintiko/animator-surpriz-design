# Отчёт по доработкам Surpriz — 29.05.2026

## Сводка

Реализован план из аудита: исправлены баги сборщика, добавлены подарки с режимами выбора, CRUD акций с жёлтыми бейджами, настройки доплаты за персонажей в админке.

## Чеклист требований

| Требование | Статус | Файлы / как проверить |
|------------|--------|------------------------|
| Подарки: XOR-группа и bundle в админке | Готово | `addon_gift_mode_*`, `addon_gift_group_*` в [show_program_form.html](../templates/admin/show_program_form.html); миграция в [addon_store.py](../core/addon_store.py) |
| Подарки на карточке шоу и в сборщике | Готово | [show_program_content.html](../templates/site/show_program_content.html), [order_builder_content.html](../templates/site/order_builder_content.html) блок `party-gifts` |
| Акции: CRUD + привязка к программе | Готово | [promotion_store.py](../core/promotion_store.py), вкладка «Акции» в админке, чекбоксы в форме шоу |
| Жёлтый бейдж на карточках | Готово | CSS `.surpriz-promo-badge` в [managed-catalog.css](../static/managed-catalog.css) |
| Inline «Подтвердить» под стандартной программой | Готово | `.party-program-inline-confirm` в сборщике |
| `?character=` → персонаж выбран | Исправлено | [customer_panel.py](../core/customer_panel.py) не мержит draft поверх URL; `applyDeepLinkIntent()` в JS |
| Выбор шоу-программы без залипания | Исправлено | `data-program-linked-slugs`, автовыбор варианта, `syncProgramInlineConfirm` |
| 2 бесплатных персонажа, доплата за 3+ | Готово | Вкладка «Сборщик» в админке; [admin_store.py](../core/admin_store.py) `calculate_character_surcharge`; total в заказе |
| Заказ не раньше 24 ч + toast менеджеру | Готово | Текст сервера исправлен; toast на календаре и слотах |
| Toast на занятое время | Готово | `notifyBlockedTimeSelection`, блок `data-busy-list` |
| Оплата: одна кнопка | Уже было | Шаг 6 сборщика |
| «Подтвердить» вместо «Дальше» | Уже было | Все шаги сборщика |
| «Выбрать всех» в админке шоу | Уже было | [show_program_form.html](../templates/admin/show_program_form.html) |

## Фаза 0 — быстрые исправления

- Lead-time: сообщение «24 часа» в `check_booking_lead_time()`.
- `get_program_addon_settings()` возвращает `is_free_choice`, `gift_mode`, `gift_group`.
- Deep-link: при `?character=` / `?program=` session draft не перетирает URL.
- Блок занятости на дату, toast при заблокированном времени.
- Кнопка «Подтвердить» под карточкой группы стандартных программ.

## Фаза 1 — подарки

- Поля `gift_mode` (`none` / `choice_one` / `bundle_all`) и `gift_group` в `show_program_addons`.
- Админка: селект режима подарка у каждой привязанной доп. услуги.
- Публичка: `gift_choice_groups`, `gift_bundles` на программе.
- Сборщик: блок «Подарки детям» с radio (на выбор) и статикой (набор).
- Заказ: маркеры `[Подарок: …]` в notes, TG-уведомление.

## Фаза 2 — акции

- Таблицы `promotions`, `show_program_promotions`.
- Админка: вкладка «Акции», форма `/admin/promotions/new|edit`.
- Привязка акций к шоу в форме программы.
- Бейдж `.surpriz-promo-badge` (янтарный градиент) в каталоге, деталке, сборщике.

## Фаза 3 — настройки сборщика

- Ключи `party_included_characters`, `party_extra_character_3_price`, `party_extra_character_4_plus_price` в `site_settings`.
- Вкладка «Сборщик» в админке.
- Клиент: доплата в summary и `total_price_snapshot` при создании заказа.

## Как проверить локально

```bash
cd /Users/kulacidmyt/Documents/animator
SURPRIZ_PORT=5001 .venv/bin/python app.py
```

1. Админка `/admin/` → «Акции» → создать акцию → привязать к шоу.
2. Форма шоу → у допа выставить «Подарок: на выбор / набор».
3. «Сборщик» → задать 2 бесплатных, доплаты 200000.
4. `/party-builder/?character=<slug>` — персонаж отмечен.
5. `/catalog/` и `/show-programs/` — жёлтые бейджи акций.

## Примечания

- Для демо акций и подарков нужно заполнить данные в админке (в БД по умолчанию пусто).
- Legacy-флаг `is_free_choice` по-прежнему работает и трактуется как `choice_one`.
