"""Central configuration. All secrets come from environment variables (or a local .env file).

Nothing secret is ever hardcoded. See `.env.example` for every supported variable.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    for candidate in (PROJECT_DIR / ".env", BACKEND_DIR / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def env_float(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    """Read lazily so tests can override env vars at runtime."""

    @property
    def data_dir(self) -> Path:
        p = Path(env("DPS_DATA_DIR", str(PROJECT_DIR / "data")))
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def output_dir(self) -> Path:
        p = self.data_dir / "products"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def database_url(self) -> str:
        return env("DATABASE_URL", f"sqlite:///{self.data_dir / 'studio.db'}")

    # --- Credentials (all optional; features degrade gracefully) ---
    @property
    def etsy_api_key(self) -> str | None:
        return env("ETSY_API_KEY")  # keystring

    @property
    def etsy_shared_secret(self) -> str | None:
        return env("ETSY_SHARED_SECRET")

    @property
    def etsy_redirect_uri(self) -> str:
        return env("ETSY_REDIRECT_URI", "http://localhost:8000/api/etsy/oauth/callback")

    @property
    def openai_api_key(self) -> str | None:
        return env("OPENAI_API_KEY")

    @property
    def openai_image_model(self) -> str:
        return env("OPENAI_IMAGE_MODEL", "gpt-image-1")

    @property
    def anthropic_api_key(self) -> str | None:
        return env("ANTHROPIC_API_KEY")

    @property
    def anthropic_model(self) -> str:
        return env("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    @property
    def canva_client_id(self) -> str | None:
        return env("CANVA_CLIENT_ID")

    @property
    def canva_client_secret(self) -> str | None:
        return env("CANVA_CLIENT_SECRET")

    # --- Limits ---
    @property
    def etsy_qps(self) -> float:
        return env_float("ETSY_MAX_QPS", 4.0)

    @property
    def etsy_daily_calls(self) -> int:
        return env_int("ETSY_MAX_DAILY_CALLS", 5000)

    @property
    def etsy_cache_hours(self) -> float:
        # Etsy API terms: listing content shown must not be more than 6 hours stale.
        return min(env_float("ETSY_CACHE_HOURS", 6.0), 6.0)

    @property
    def render_dpi(self) -> int:
        return env_int("DPS_RENDER_DPI", 300)

    @property
    def max_workers(self) -> int:
        return env_int("DPS_MAX_WORKERS", 2)


settings = Settings()

ETSY_ATTRIBUTION = (
    "The term 'Etsy' is a trademark of Etsy, Inc. This application uses the Etsy API "
    "but is not endorsed or certified by Etsy, Inc."
)


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("dps")
    if logger.handlers:
        return logger
    logger.setLevel(env("DPS_LOG_LEVEL", "INFO"))
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    fh = RotatingFileHandler(log_dir / "studio.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


log = setup_logging()
