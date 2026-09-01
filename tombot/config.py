"""Environment-driven configuration. Nothing here reads the database."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def load_dotenv(path=None) -> None:
    """Read .env into the environment before the settings are read.

    Docker Compose reads .env itself, so inside a container this finds nothing
    and does nothing. Run the app or a script straight from a shell, though,
    and without this the file is ignored — which reads as "the key is not
    configured" while the key is sitting right there.

    Anything already exported wins, so an inline override still works.
    """
    import os
    import pathlib as _pathlib

    f = _pathlib.Path(path or _pathlib.Path(__file__).resolve().parent.parent / ".env")
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1] and len(value) > 1:
            value = value[1:-1]
        else:
            # Unquoted values here carry trailing comments; only a # after
            # whitespace starts one, so a # inside a key survives.
            cut = value.find(" #")
            if cut == -1:
                cut = value.find("\t#")
            if cut != -1:
                value = value[:cut]
            value = value.strip()
        if key:
            os.environ.setdefault(key, value)


load_dotenv()


class Config:
    # --- storage -----------------------------------------------------------
    DATA_DIR = _path("DATA_DIR", BASE_DIR / "data")
    MEDIA_DIR = _path("MEDIA_DIR", BASE_DIR / "media")
    DB_PATH = Path(os.environ.get("DB_PATH", "")) if os.environ.get("DB_PATH") else DATA_DIR / "pokemon.db"

    CATALOG_IMG_DIR = MEDIA_DIR / "catalog"
    COLLECTION_IMG_DIR = MEDIA_DIR / "collection"
    THUMB_DIR = MEDIA_DIR / "thumbs"

    # --- http --------------------------------------------------------------
    HOST = os.environ.get("HOST", "127.0.0.1")   # bind loopback, not 0.0.0.0
    PORT = int(os.environ.get("PORT", "8080"))
    DEBUG = _bool("DEBUG", False)

    # Optional shared secret. Unset => no auth. Set => X-App-Token required.
    APP_TOKEN = os.environ.get("APP_TOKEN") or None

    # --- uploads -----------------------------------------------------------
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    IMAGE_MAX_EDGE = int(os.environ.get("IMAGE_MAX_EDGE", "1600"))
    THUMB_MAX_EDGE = int(os.environ.get("THUMB_MAX_EDGE", "400"))
    JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "85"))

    # --- catalog / price source -------------------------------------------
    # --- tcggo (CardMarket API TCG, via RapidAPI) --------------------------
    # The one and only source: catalogue, images, versions and prices all come
    # from importing a set. Cardmarket's own API is application-gated, and the
    # old pokemontcg.io / TCGdex path is gone (each mapped a card to one price
    # for all its printings, which mispriced every reprint).
    # Metered: the plan bills per request past a daily allowance, so the cap
    # below is enforced in code and deliberately sits under the real limit.
    # Raising it costs money, so it is an explicit decision, not a default.
    TCGGO_API_KEY = os.environ.get("TCGGO_API_KEY") or None
    TCGGO_BASE_URL = os.environ.get(
        "TCGGO_BASE_URL", "https://cardmarket-api-tcg.p.rapidapi.com")
    TCGGO_RAPIDAPI_HOST = os.environ.get(
        "TCGGO_RAPIDAPI_HOST", "cardmarket-api-tcg.p.rapidapi.com")
    TCGGO_GAME = os.environ.get("TCGGO_GAME", "pokemon")
    TCGGO_DAILY_LIMIT = int(os.environ.get("TCGGO_DAILY_LIMIT", "40"))
    HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "45"))
    HTTP_RETRIES = int(os.environ.get("HTTP_RETRIES", "5"))  # upstream 500s are routine
    HTTP_MAX_BACKOFF = int(os.environ.get("HTTP_MAX_BACKOFF", "30"))

    # Cardmarket locale for outbound product links (en/es/fr/it/de).
    CARDMARKET_LOCALE = os.environ.get("CARDMARKET_LOCALE", "es")

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

DEFAULT_CONDITION = CONDITIONS[0]

# What the grades used to be called, so rows written under the old names can be
# carried over. Kept next to CONDITIONS because that is where anyone renaming
# them will be looking, and the last rename left four places behind.
RETIRED_CONDITIONS = {
    "NM": "M/NM", "LP": "EX", "MP": "GD", "HP": "PL", "DMG": "PO",
}

LANGUAGES = ["es", "en", "pt", "other"]
LANGUAGE_LABELS = {"es": "Español", "en": "Inglés", "pt": "Portugués", "other": "Otro"}

VARIANTS = ["normal", "holo", "reverse", "first_edition", "shadowless", "other"]
VARIANT_LABELS = {
    "normal": "Normal", "holo": "Holo", "reverse": "Reverse Holo",
    "first_edition": "1st Edition", "shadowless": "Shadowless", "other": "Otra",
}
