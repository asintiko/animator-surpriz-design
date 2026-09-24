# Deployment

## Live-схема

- VPS: `150.241.78.173`, пользователь деплоя: `surpriz`.
- Публичный домен: `https://animator-surpriz.uz`.
- Живые сервисы: `surpriz-v2.service` (Gunicorn на `127.0.0.1:5052`),
  `surpriz-bot.service`, `surpriz-adapter.service` (закрытый API на
  `127.0.0.1:5051`) и `surpriz-webapp.service` (Next.js на
  `127.0.0.1:5053`).
- Nginx берёт боевую конфигурацию из `/etc/nginx/sites-enabled/surpriz` и проксирует приложение на `5052`.
- Каждый релиз находится в `/opt/surpriz-releases/<UTC-id>/`; оба активных сервиса должны указывать на один и тот же каталог релиза.

Не используйте `surpriz.service` (`:5050`) и `/etc/nginx/sites-available/surpriz`: это устаревшие, неактивные конфигурации.

## Общие данные

`/opt/surpriz` — постоянное хранилище, а не рабочая директория приложения. В нём находятся:

- виртуальное окружение `/opt/surpriz/.venv`;
- общий каталог `/opt/surpriz/content`;
- SQLite `/opt/surpriz/content/data/admin/site_admin.sqlite3` в WAL-режиме;
- медиа и старые статические алиасы, которые Nginx пока продолжает обслуживать.

Не восстанавливайте SQLite, WAL-файлы, общий `content` или медиа при откате кода: они общие для всех релизов. Секреты остаются в `.env`; файл не читается, не копируется в чат и не попадает в репозиторий.

## Безопасный релиз

1. Снимите online-backup SQLite и сохраните копии четырёх systemd-unit'ов в `/opt/surpriz-backups/<UTC-id>/`.
2. Создайте новый каталог релиза копированием текущего активного релиза. Это сохраняет ссылки на общий venv, content и legacy-медиа.
3. Загрузите в новый каталог только исходный код, шаблоны, `static/` и каталог фронтенда `surpriz/`. Не удаляйте файлы из нового релиза через `rsync --delete`.
4. Замените только известный путь старого релиза на новый в `.env` (если там указан `SURPRIZ_LANDING_ROOT`) и во всех четырёх unit-файлах: `surpriz-v2.service`, `surpriz-bot.service`, `surpriz-adapter.service`, `surpriz-webapp.service`.
4a. Порядок здесь важен: `.env` копируется вместе с релизом и до правки указывает `SURPRIZ_LANDING_ROOT` на **предыдущий** каталог. Разложите статику по явному пути `<новый релиз>/surpriz/`, а не по значению из `.env`, иначе файлы уедут в старый релиз и текущий прод обновится в обход переключения.
5. Обновите в `.env` ещё и `SURPRIZ_RELEASE_ID` с `NEXT_PUBLIC_SURPRIZ_BUILD_ID` — это голые идентификаторы, замена путей их не задевает. Только после этого собирайте `webapp/.next`: `headers()` из `next.config.ts` запекается в манифест во время сборки, поэтому пересборка со старым `SURPRIZ_RELEASE_ID` навсегда зафиксирует неверную метку версии.
6. Выполните `systemctl daemon-reload`, перезапустите сервисы в порядке Flask → adapter → Next → bot и проверьте их статус.
7. Обновите захардкоженный `add_header X-Surpriz-Build-Id` в `/etc/nginx/sites-enabled/surpriz` (несколько вхождений), затем `nginx -t` и `systemctl reload nginx`. Nginx скрывает заголовок Next через `proxy_hide_header` и подставляет своё значение, так что без этого шага сайт снаружи продолжит рапортовать предыдущий релиз.
8. Проверьте `/`, `/party-builder/`, `/admin/`, `/wp-admin/` и одну новую AVIF-картинку через HTTPS.
9. Если менялась статика в `surpriz/`, убедитесь, что `?v=` хэши в HTML пересчитаны (`python3 scripts/refresh_asset_versions.py --check` в репозитории surprizopus) — иначе браузеры продолжат отдавать закэшированные скрипты и правка до пользователей не доедет.

Перед переключением все четыре unit-файла обязаны указывать на один прежний каталог, а новый каталог обязан содержать `app.py`, `.env`, ссылку `.venv` на `/opt/surpriz/.venv`, `content` на `/opt/surpriz/content`, готовую сборку `webapp/.next` и `static/admin-media` на общий медиа-каталог.

## Google Календарь

Отдельного сервиса нет: синхронизация идёт потоком в `surpriz-bot.service`. Для OAuth нужен `ADMIN_PORTAL_BASE` (или `GOOGLE_OAUTH_REDIRECT_URI`) в `.env`; Client ID/Secret задаются в `/admin/calendar` или через `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`. Nginx менять не нужно: `/api/admin/google-calendar/callback` уже проксируется в Next. Подробно — [[Google-Calendar]].

## Админка и откат

- Рабочий адрес админки: `/admin/`.
- Старые закладки `/wp-admin/` и `/wp-login.php` должны перенаправляться на `/admin/` приложением.
- Для отката переключите **все четыре** активных сервиса на каталог предыдущего релиза и повторите smoke-проверки. Не откатывайте общую БД автоматически.

## Связано

- [[Surpriz]]
- [[Telegram-Integration]] — токены остаются вне репозитория
