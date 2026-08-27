"""Environment-driven configuration. Nothing here reads the database."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


class Config:
    # --- storage -----------------------------------------------------------
    DATA_DIR = _path("DATA_DIR", BASE_DIR / "data")
    MEDIA_DIR = _path("MEDIA_DIR", BASE_DIR / "media")
    DB_PATH = Path(os.environ.get("DB_PATH", "")) if os.environ.get("DB_PATH") else DATA_DIR / "pokemon.db"

    CATALOG_IMG_DIR = MEDIA_DIR / "catalog"
    COLLECTION_IMG_DIR = MEDIA_DIR / "collection"
    THUMB_DIR = MEDIA_DIR / "thumbs"

    # --- http --------------------------------------------------------------
    HOST = os.environ.get("HOST", "127.0.0.1")   # not 0.0.0.0: see PLAN.md §2.7
    PORT = int(os.environ.get("PORT", "8080"))
    DEBUG = _bool("DEBUG", False)

    # Optional shared secret. Unset => no auth (spec §31). Set => X-App-Token required.
    APP_TOKEN = os.environ.get("APP_TOKEN") or None

    # --- uploads -----------------------------------------------------------
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    IMAGE_MAX_EDGE = int(os.environ.get("IMAGE_MAX_EDGE", "1600"))
    THUMB_MAX_EDGE = int(os.environ.get("THUMB_MAX_EDGE", "400"))
    JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "85"))

    # --- catalog / price source -------------------------------------------
    # Cardmarket's own API is application-gated; pokemontcg.io republishes
    # Cardmarket EUR prices with no account needed. See PLAN.md §2.2.
    # Catalog and images still come from pokemontcg.io; only prices move.
    SOURCE = os.environ.get("SOURCE", "pokemontcgio")
    # TCGdex is the only source found that prices print runs apart — pokemontcg.io
    # reports one number per card id, so Unlimited and Shadowless read the same.
    PRICE_SOURCE = os.environ.get("PRICE_SOURCE", "tcgdex")
    TCGDEX_BASE_URL = os.environ.get("TCGDEX_BASE_URL", "https://api.tcgdex.net/v2")
    TCGDEX_LANG = os.environ.get("TCGDEX_LANG", "en")
    POKEMONTCG_API_KEY = os.environ.get("POKEMONTCG_API_KEY") or None
    POKEMONTCG_BASE_URL = "https://api.pokemontcg.io/v2"
    HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "45"))
    HTTP_RETRIES = int(os.environ.get("HTTP_RETRIES", "5"))  # upstream 500s are routine
    HTTP_MAX_BACKOFF = int(os.environ.get("HTTP_MAX_BACKOFF", "30"))

    # Link resolution is one request per card. Kept low deliberately: without an
    # API key the whole daily allowance is 1,000 requests.
    LINK_RESOLVE_WORKERS = int(os.environ.get("LINK_RESOLVE_WORKERS", "3"))

    # Cardmarket locale for outbound product links (en/es/fr/it/de).
    CARDMARKET_LOCALE = os.environ.get("CARDMARKET_LOCALE", "es")

    # averageSellPrice is steadier than trendPrice, which can be 3x off on thin markets.
    PRICE_BASIS = os.environ.get("PRICE_BASIS", "averageSellPrice")
    PRICE_STALE_DAYS = int(os.environ.get("PRICE_STALE_DAYS", "25"))

    # --- scheduler ---------------------------------------------------------
    SCHEDULER_ENABLED = _bool("SCHEDULER_ENABLED", False)
    SCHEDULER_CRON_DAY = int(os.environ.get("SCHEDULER_CRON_DAY", "1"))
    SCHEDULER_CRON_HOUR = int(os.environ.get("SCHEDULER_CRON_HOUR", "4"))

    @classmethod
    def ensure_dirs(cls) -> None:
        for d in (cls.DATA_DIR, cls.MEDIA_DIR, cls.CATALOG_IMG_DIR,
                  cls.COLLECTION_IMG_DIR, cls.THUMB_DIR):
            d.mkdir(parents=True, exist_ok=True)


# Domain vocabularies — single source of truth for API validation and the UI.
# Hall of Fame rank, 0-8. 0 means unranked.
#
# Hall of Fame is the Japanese ban-list concept — a statement about how strong a
# card is — not a favourites list. Descriptive labels ("Joya", "Obra maestra")
# read as sentiment and were actively misleading, so the scale is the number and
# nothing else.
MAX_RATING = 8
RATING_LABELS = {n: ("—" if n == 0 else f"★ {n}") for n in range(MAX_RATING + 1)}

CONDITIONS = ["M/NM", "EX", "GD", "PL", "PO"]
CONDITION_LABELS = {
    "M/NM": "Mint/Near Mint", "EX": "Excellent", "GD": "Good",
    "PL": "Played", "PO": "Poor",
}
CONDITION_ORDER = {c: i for i, c in enumerate(CONDITIONS)}   # 0 = best

LANGUAGES = ["es", "en", "pt", "other"]
LANGUAGE_LABELS = {"es": "Español", "en": "Inglés", "pt": "Portugués", "other": "Otro"}

VARIANTS = ["normal", "holo", "reverse", "first_edition", "shadowless", "other"]
VARIANT_LABELS = {
    "normal": "Normal", "holo": "Holo", "reverse": "Reverse Holo",
    "first_edition": "1st Edition", "shadowless": "Shadowless", "other": "Otra",
}

DEFAULT_MODIFIERS = [
    ("condition", "M/NM", 1.00), ("condition", "EX", 0.85), ("condition", "GD", 0.70),
    ("condition", "PL", 0.50), ("condition", "PO", 0.35),
    ("language", "en", 1.00), ("language", "es", 1.00),
    ("language", "pt", 0.85), ("language", "other", 1.00),
    # The feed never prices a 1st edition apart from its unstamped twin, so
    # the premium lives here. 2.0 is a starting point, not a measurement.
    ("variant", "first_edition", 2.00),
]
