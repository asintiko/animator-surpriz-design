# Surpriz — Аниматоры в Ташкенте

Flask-приложение для booking-сайта детских праздников. Домен: `animator-surpriz.uz`.

## Быстрая навигация

- [[Architecture]] — стек, модули, структура
- [[Deployment]] — VPS, nginx, gunicorn, systemd, Let's Encrypt
- [[Search]] — умный поиск в каталоге костюмов
- [[Mobile-Bottom-Bar]] — закреплённая нижняя навигация на мобильных
- [[Telegram-Integration]] — TG Bot для админ-нотификаций + TG Gateway для login-кодов
- [[Order-Builder]] — пошаговая сборка заказа: программа → персонажи → дата/время → контакты
- [[Free-Choice-Bonus]] — бесплатный бонус на выбор внутри программы
- [[Catalog]] — каталог персонажей и шоу-программ
- [[Admin-Panel]] — админка
- [[Customer-Portal]] — личный кабинет клиента

## Стек

- Python 3.11+ / Flask 3 / gunicorn
- SQLite (WAL, FK on)
- nginx + Let's Encrypt (certbot)
- Ubuntu 26.04 LTS, systemd, ufw, fail2ban
- Telegram Bot API (notifications) + Telegram Gateway (auth codes)

## Локально

```bash
.venv/bin/python app.py    # http://127.0.0.1:5050
```

## На сервере

```bash
ssh -i ~/.ssh/surpriz_deploy surpriz@150.241.78.173
sudo systemctl restart surpriz.service
```
