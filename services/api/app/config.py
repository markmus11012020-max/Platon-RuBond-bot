from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_prefix="PREMARKET_",
    )

    app_name: str = "Platon API"
    environment: str = "development"
    api_prefix: str = "/api"
    demo_mode: bool = True
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    bond_db_path: str = str(ROOT / "bondbot.db")
    freelance_db_path: str = ""

    tinvest_mcp_enabled: bool = False
    tinvest_mcp_mode: str = "sandbox"
    tinvest_mcp_sandbox_url: str = "https://sandbox-invest-public-api.tbank.ru/mcp"
    tinvest_mcp_prod_url: str = "https://invest-public-api.tbank.ru/mcp"
    tinvest_mcp_token: str = ""
    tinvest_mcp_timeout: int = 30

    openai_api_key: str = ""
    openai_base_url: str = "https://api.aitunnel.ru/v1"
    openai_model: str = "deepseek-v4.1-flash-1017"
    llm_enabled: bool = False
    llm_timeout: int = 45
    llm_max_tokens: int = 1200

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@platoninvest.pro"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def mcp_url(self) -> str:
        if self.tinvest_mcp_mode.lower() == "prod":
            return self.tinvest_mcp_prod_url
        return self.tinvest_mcp_sandbox_url

    @property
    def mcp_ready(self) -> bool:
        return self.tinvest_mcp_enabled and bool(self.tinvest_mcp_token)

    @property
    def freelance_db_available(self) -> bool:
        return bool(self.freelance_db_path) and Path(self.freelance_db_path).exists()


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["ROOT", "Settings", "get_settings"]
