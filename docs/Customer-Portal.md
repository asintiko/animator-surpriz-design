# Customer Portal

Личный кабинет клиента. URL: `/account/`. Бэкенд: `core/customer_panel.py`.

## Login flow

1. Клиент вводит TG-username или phone на `/login/`
2. `_send_gateway_code` отправляет код через [[Telegram-Integration]] Gateway API
3. Клиент вводит код → `_check_gateway_code` валидирует
4. Сессия в Flask `session['customer_id']`

### Dev-bypass

`CUSTOMER_AUTH_DEV_BYPASS=1` → код `000000` всегда валиден (для тестов и пока Gateway-баланс не пополнен).

## Что в личном кабинете

- История заказов
- Активные заказы (статус, дата, сумма)
- Возможность повторить заказ
- Профиль (имя, контакты)

## Guest-режим

Если клиент не залогинен, builder сохраняет черновик в `session` (server-side) + в `localStorage` (client-side). После логина черновик подтягивается.

## Стили

```python
PORTAL_STYLESHEET = '<link rel="stylesheet" href="/customer-portal.css?v=stage22-busy-filter-20260527">'
```

Cache-buster обновляется при крупных правках UI.

## Связано

- [[Order-Builder]]
- [[Telegram-Integration]]
- [[Architecture]]
