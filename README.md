# Event Surpriz Local Codebase

Local coded version of `eventsurpriz.uz` built around Flask, route bundles, and local static assets.

## Project Layout

- `app.py` - Flask entry point.
- `core/config.py` - project paths and shared constants.
- `core/routing.py` - route normalization and canonical redirects.
- `core/loader.py` - route-bundle loader.
- `core/static_assets.py` - static file resolver.
- `core/forms.py` - Elementor form endpoint emulation and form persistence.
- `templates/base.html` - shared HTML shell for all pages.
- `content/routes/` - page bundles mapped by route path.
- `content/routes/errors/404/` - shared 404 page bundle.
- `content/data/forms/` - saved form submissions.
- `static/` - CSS, JS, images, fonts, and other local assets.
- `diagnostics/` - comparison screenshots and temporary verification artifacts.
- `docs/site-design-guide.md` - current site design system and UI rules for future pages.

## Route Bundle Format

Each page is stored as a route bundle:

- `meta.json`
- `head.html`
- `body_prefix.html`
- `header.html`
- `content.html`
- `footer.html`
- `body_suffix.html`

This keeps the site structure predictable while still preserving the exact live markup where needed.

## Run Locally

```bash
python -m pip install -r requirements.txt
python app.py
```

The site will be available at `http://127.0.0.1:5000`.

## Yandex Maps

The party builder uses Yandex Maps for location selection.

Set these environment variables before running the app:

```powershell
$env:YANDEX_MAPS_API_KEY="your-yandex-javascript-api-key"
$env:YANDEX_SUGGEST_API_KEY="your-yandex-suggest-api-key"
python app.py
```

Or create a local `.env` file in the project root:

```env
YANDEX_MAPS_API_KEY=your-yandex-javascript-api-key
YANDEX_SUGGEST_API_KEY=your-yandex-suggest-api-key
```

`YANDEX_MAPS_API_KEY` is required for search/geocoding suggestions. Without it, users can still place the marker manually on the map, but address autocomplete will be disabled.

## Telegram Gateway Auth

Registration and login use Telegram Gateway verification codes. SMS is disabled in the public auth flow.

Add this backend-only variable to `.env`:

```env
TELEGRAM_GATEWAY_TOKEN=
```

Get the token in Telegram Gateway, then restart `python app.py`. The phone input stays in the site format, for example `+998 (33) 236-77-81`; backend normalizes it to E.164 before calling Telegram Gateway, for example `+998332367781`.

Test flow:

- Open `/register/`, enter name and phone, submit, then enter the 6-digit code from Telegram Verification Codes on `/auth/telegram-code/`.
- Open `/login/`, enter the registered phone, submit, then enter the 6-digit Telegram code.

## Google Calendar

Admin page `/admin/calendar` connects the manager calendar through Google OAuth. Events in the calendar close time on the site (date and time come from the event, show programs and characters are recognised in the title/description); orders confirmed in the Telegram bot or the admin panel are written back to the calendar in the Telegram order-card format. The sync runs inside the Telegram worker (`python -m core.admin_notifications`) or standalone via `python -m core.google_calendar`. Setup steps and details: `docs/Google-Calendar.md`.
