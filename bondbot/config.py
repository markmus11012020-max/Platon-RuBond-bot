from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: str = "bondbot.db"
    smartlab_base: str = "https://smart-lab.ru"
    smartlab_pages: int = 3
    request_timeout: int = 30
    health_port: int = 8081
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124 Safari/537.36"
    )

    # CBR key rate -> dynamic max screening yield
    dynamic_max_yield: bool = True
    key_rate_margin_pct: float = 10.0
    key_rate_ttl_hours: int = 6
    key_rate_timeout: int = 15
    key_rate_url: str = "https://www.cbr.ru/hd_base/KeyRate/"

    # Portfolio sizing / liquidity
    position_size_rub: float = 1_000_000
    portfolio_size_rub: float = 5_000_000
    max_pct_daily_volume: float = 0.05
    min_issue_size_rub: float = 5_000_000_000

    # Default screening profile
    min_yield_pct: float = 14.0
    max_yield_pct: float = 35.0
    max_duration_years: float = 5.0
    min_rating: str = "A-"
    min_price_pct: float = 90.0
    max_price_pct: float = 110.0

    # VK (separate community, do not reuse FreelanceBot token)
    vk_group_token: str = field(default="", repr=False)
    vk_group_id: int = 0
    vk_api_version: str = "5.199"
    vk_admin_user_id: int = 0

    # LLM
    openai_base_url: str = "https://api.aitunnel.ru/v1"
    openai_api_key: str = field(default="", repr=False)
    openai_model: str = "deepseek-v4.1-flash-1017"

    @property
    def vk_configured(self) -> bool:
        return bool(self.vk_group_token and self.vk_group_id)

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key)


def load_settings() -> Settings:
    return Settings(
        db_path=_env("BONDBOT_DB_PATH", "bondbot.db") or "bondbot.db",
        smartlab_base=_env("BONDBOT_SMARTLAB_BASE", "https://smart-lab.ru").rstrip("/"),
        smartlab_pages=_int("BONDBOT_SMARTLAB_PAGES", 3),
        request_timeout=_int("BONDBOT_REQUEST_TIMEOUT", 30),
        health_port=_int("BONDBOT_HEALTH_PORT", 8081),
        user_agent=_env("BONDBOT_USER_AGENT", Settings.user_agent),
        dynamic_max_yield=_bool("BONDBOT_DYNAMIC_MAX_YIELD", True),
        key_rate_margin_pct=_float("BONDBOT_KEY_RATE_MARGIN_PCT", 10.0),
        key_rate_ttl_hours=_int("BONDBOT_KEY_RATE_TTL_HOURS", 6),
        key_rate_timeout=_int("BONDBOT_KEY_RATE_TIMEOUT", 15),
        key_rate_url=(
            _env("BONDBOT_KEY_RATE_URL", "https://www.cbr.ru/hd_base/KeyRate/")
            or "https://www.cbr.ru/hd_base/KeyRate/"
        ),
        position_size_rub=_float("BONDBOT_POSITION_SIZE_RUB", 1_000_000),
        portfolio_size_rub=_float("BONDBOT_PORTFOLIO_SIZE_RUB", 5_000_000),
        max_pct_daily_volume=_float("BONDBOT_MAX_PCT_DAILY_VOLUME", 0.05),
        min_issue_size_rub=_float("BONDBOT_MIN_ISSUE_SIZE_RUB", 5_000_000_000),
        min_yield_pct=_float("BONDBOT_MIN_YIELD_PCT", 14.0),
        max_yield_pct=_float("BONDBOT_MAX_YIELD_PCT", 35.0),
        max_duration_years=_float("BONDBOT_MAX_DURATION_YEARS", 5.0),
        min_rating=_env("BONDBOT_MIN_RATING", "A-") or "A-",
        min_price_pct=_float("BONDBOT_MIN_PRICE_PCT", 90.0),
        max_price_pct=_float("BONDBOT_MAX_PRICE_PCT", 110.0),
        vk_group_token=_env("BONDBOT_VK_GROUP_TOKEN"),
        vk_group_id=_int("BONDBOT_VK_GROUP_ID", 0),
        vk_api_version=_env("BONDBOT_VK_API_VERSION", "5.199") or "5.199",
        vk_admin_user_id=_int("BONDBOT_VK_ADMIN_USER_ID", 0),
        openai_base_url=(
            _env("BONDBOT_OPENAI_BASE_URL")
            or _env("OPENAI_BASE_URL")
            or _env("AITUNNEL_BASE_URL")
            or "https://api.aitunnel.ru/v1"
        ).rstrip("/"),
        openai_api_key=(
            _env("BONDBOT_OPENAI_API_KEY")
            or _env("OPENAI_API_KEY")
            or _env("AITUNNEL_API_KEY")
        ),
        openai_model=(
            _env("BONDBOT_OPENAI_MODEL")
            or _env("OPENAI_MODEL")
            or _env("LLM_MODEL")
            or "deepseek-v4.1-flash-1017"
        ),
    )
