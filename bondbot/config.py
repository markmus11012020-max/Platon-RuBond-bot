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
    exit_horizon_days: int = 5

    # Scheduler / refresh
    scheduler_enabled: bool = True
    refresh_hour: int = 23
    refresh_minute: int = 30
    detail_refresh_hour: int = 10
    detail_refresh_minute: int = 0
    digest_hour: int = 9
    digest_minute: int = 0
    data_stale_hours: int = 36

    # Alerts / owner
    owner_peer_id: int = 0
    alerts_enabled: bool = True
    alert_quiet_start: int = 23
    alert_quiet_end: int = 8
    alert_max_per_day: int = 5

    # Backups
    backup_enabled: bool = True
    backup_dir: str = "/data/backups"
    backup_keep: int = 14

    # MOEX ISS
    moex_enabled: bool = True
    moex_base: str = "https://iss.moex.com"

    # News
    news_enabled: bool = True
    news_feeds: str = ""
    news_interval_minutes: int = 30
    news_hours: int = 24

    # Live web search for issuer/news queries
    live_search_enabled: bool = True
    live_search_timeout: int = 15
    live_search_ttl_hours: int = 6

    # LLM assistant
    llm_enabled: bool = True
    llm_max_tool_rounds: int = 6
    llm_max_tokens: int = 1800
    llm_timeout: int = 45
    llm_daily_token_limit: int = 500_000

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
    public_access: bool = True
    community_members_only: bool = True
    dialogue_ttl_minutes: int = 120

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
        exit_horizon_days=_int("BONDBOT_EXIT_HORIZON_DAYS", 5),
        scheduler_enabled=_bool("BONDBOT_SCHEDULER_ENABLED", True),
        refresh_hour=_int("BONDBOT_REFRESH_HOUR", 23),
        refresh_minute=_int("BONDBOT_REFRESH_MINUTE", 30),
        detail_refresh_hour=_int("BONDBOT_DETAIL_REFRESH_HOUR", 10),
        detail_refresh_minute=_int("BONDBOT_DETAIL_REFRESH_MINUTE", 0),
        digest_hour=_int("BONDBOT_DIGEST_HOUR", 9),
        digest_minute=_int("BONDBOT_DIGEST_MINUTE", 0),
        data_stale_hours=_int("BONDBOT_DATA_STALE_HOURS", 36),
        owner_peer_id=_int("BONDBOT_OWNER_PEER_ID", 0),
        alerts_enabled=_bool("BONDBOT_ALERTS_ENABLED", True),
        alert_quiet_start=_int("BONDBOT_ALERT_QUIET_START", 23),
        alert_quiet_end=_int("BONDBOT_ALERT_QUIET_END", 8),
        alert_max_per_day=_int("BONDBOT_ALERT_MAX_PER_DAY", 5),
        backup_enabled=_bool("BONDBOT_BACKUP_ENABLED", True),
        backup_dir=_env("BONDBOT_BACKUP_DIR", "/data/backups") or "/data/backups",
        backup_keep=_int("BONDBOT_BACKUP_KEEP", 14),
        moex_enabled=_bool("BONDBOT_MOEX_ENABLED", True),
        moex_base=_env("BONDBOT_MOEX_BASE", "https://iss.moex.com").rstrip("/")
        or "https://iss.moex.com",
        news_enabled=_bool("BONDBOT_NEWS_ENABLED", True),
        news_feeds=_env("BONDBOT_NEWS_FEEDS"),
        news_interval_minutes=_int("BONDBOT_NEWS_INTERVAL_MINUTES", 30),
        news_hours=_int("BONDBOT_NEWS_HOURS", 24),
        live_search_enabled=_bool("BONDBOT_LIVE_SEARCH_ENABLED", True),
        live_search_timeout=_int("BONDBOT_LIVE_SEARCH_TIMEOUT", 15),
        live_search_ttl_hours=_int("BONDBOT_LIVE_SEARCH_TTL_HOURS", 6),
        llm_enabled=_bool("BONDBOT_LLM_ENABLED", True),
        llm_max_tool_rounds=_int("BONDBOT_LLM_MAX_TOOL_ROUNDS", 6),
        llm_max_tokens=_int("BONDBOT_LLM_MAX_TOKENS", 1800),
        llm_timeout=_int("BONDBOT_LLM_TIMEOUT", 45),
        llm_daily_token_limit=_int("BONDBOT_LLM_DAILY_TOKEN_LIMIT", 500_000),
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
        public_access=_bool("BONDBOT_PUBLIC_ACCESS", True),
        community_members_only=_bool("BONDBOT_COMMUNITY_MEMBERS_ONLY", True),
        dialogue_ttl_minutes=_int("BONDBOT_DIALOGUE_TTL_MINUTES", 120),
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
