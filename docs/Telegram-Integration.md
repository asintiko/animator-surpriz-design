# Telegram Integration

Два разных Telegram-канала:

## 1. Bot для уведомлений админа

- Токен в БД: `admin_telegram_settings.bot_token` (приоритет) → env `TELEGRAM_NOTIFY_BOT_TOKEN` → env `TELEGRAM_BOT_TOKEN`
- Получатели: таблица `admin_telegram_recipients` (chat_id + name)
- Управление: `/admin/?tab=notifications`
- Код: `core/admin_notifications.py`

### Что отправляется при новом заказе

`_format_order_message(order)` собирает:
- Программа + персонажи (slug, имена)
- Дата, время начала/конца, длительность
- ФИО заказчика, телефон, TG
- Имя именинника, возраст, число детей
- Адрес + ссылка на карту (Yandex)
- Бесплатный бонус (если есть, маркер `[Бонус: …]` в notes)
- Сумма, способ оплаты, статус
- Inline-кнопки callback'ов (✅ Принять / ❌ Отмена / 📍 Локация)

`sendLocation` отдельным сообщением, если адрес распарсился в координаты.

### Перенос заказа

Под карточкой незавершённого заказа есть кнопка «🕒 Перенести». Бот присылает вопрос (force reply) — менеджер отвечает новой датой и/или временем начала: `06.10 15:00`, `6 октября в 15:30`, `завтра 12:00`, `в 17`, `07.10`. Длительность сохраняется, ограничения «за 24 часа» для менеджера нет, но время проверяется на пересечения с другими заказами и событиями календаря (без учёта самого заказа). При пересечении бот спрашивает «✅ Всё равно перенести / ✖️ Отмена»; ответ «отмена» прекращает перенос. После переноса карточки заказа во всех чатах и событие в Google Календаре обновляются, в `party_order_reschedule_events` пишется журнал (было/стало, кто, принудительно ли). Код: `customer_store.reschedule_order`, `admin_notifications._start_reschedule` / `_handle_reschedule_reply` / `_handle_reschedule_callback`, сессии — `admin_telegram_reschedule_sessions` (живут 30 минут).

### Google Календарь

«✅ Подтвердить» ставит заказ в очередь выгрузки в Google Календарь в той же транзакции, «↩️ Снять подтверждение» и «❌ Отклонить» — удаляют событие. Поток синхронизации живёт в этом же воркере, см. [[Google-Calendar]].

### Дедуп callback'ов

3 worker'а gunicorn раньше получали один callback трижды. Решение: таблица `admin_telegram_processed_updates` с PRIMARY KEY на `update_id`, `INSERT INTO ... ON CONFLICT DO NOTHING` для атомарного claim.

## 2. Telegram Gateway для login-кодов

- Токен в БД: `admin_telegram_settings.telegram_gateway_token`
- Endpoints: `sendVerificationMessage`, `checkVerificationStatus` (Bearer auth)
- Code length 4-8, TTL 30-3600 сек
- Dev-bypass: `CUSTOMER_AUTH_DEV_BYPASS=1` в окружении → код `000000` всегда валиден
- Код: `core/customer_panel.py` → `_send_gateway_code` / `_check_gateway_code`

## Управление токенами

В админке `/admin/?tab=notifications` две формы:
- **Bot token** (для уведомлений)
- **Gateway token** (для login)

Оба маскируются перед отображением (`bot_token_masked`, `gateway_token_masked`).

## Связано

- [[Customer-Portal]] — login flow
- [[Admin-Panel]] — UI настроек
- [[Order-Builder]] — заказы триггерят notifications
