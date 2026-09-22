from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_ROOT = PROJECT_ROOT / "content"
ROUTES_ROOT = CONTENT_ROOT / "routes"
STATIC_ROOT = PROJECT_ROOT / "static"
DATA_ROOT = CONTENT_ROOT / "data"
FORMS_ROOT = DATA_ROOT / "forms"

REMOTE_BASE_URL = "https://eventsurpriz.uz"
REMOTE_HOST = "eventsurpriz.uz"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)
