"""Central configuration. All secrets come from environment variables."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _flag(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    ENV = os.environ.get("RESQAI_ENV", "development")
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SECRET_KEY_IS_RANDOM = not os.environ.get("SECRET_KEY")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / "resqai.db"))

    # Admin bootstrap (only used the first time, when no admin exists yet)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    # AI provider (Anthropic Messages API). Leave key empty to use demo mode.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    AI_MODEL = os.environ.get("AI_MODEL", "claude-sonnet-5-5")
    AI_TIMEOUT = (5, 25)  # (connect, read) seconds
    AI_MAX_MESSAGE_CHARS = 500
    AI_MAX_HISTORY = 8

    # Weather: Open-Meteo needs no key. Default location = Chennai.
    WEATHER_DEFAULT_LAT = 13.0827
    WEATHER_DEFAULT_LON = 80.2707
    WEATHER_DEFAULT_NAME = "Chennai, Tamil Nadu"
    WEATHER_TIMEOUT = 6
    WEATHER_CACHE_SECONDS = 600

    # Security
    MAX_CONTENT_LENGTH = 32 * 1024  # 32 KB request bodies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", ENV == "production")
    PERMANENT_SESSION_LIFETIME = 2 * 60 * 60  # 2 hours
    RATELIMIT_ENABLED = True
    DEBUG = _flag("FLASK_DEBUG", False) and ENV != "production"
