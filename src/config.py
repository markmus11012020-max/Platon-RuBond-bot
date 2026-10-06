"""
Класс загрузки конфигураций и констант (.env, пути к БД).
"""

from pathlib import Path
from typing import Optional

import os

from dotenv import load_dotenv


class Config:
    """Централизованная конфигурация приложения."""

    def __init__(self, env_path: Optional[str] = None) -> None:
        env_file = env_path or Path(__file__).resolve().parents[1] / ".env"
        load_dotenv(env_file)

        self.project_root: Path = Path(__file__).resolve().parents[1]

        # LLM / AiTunnel (OpenAI-compatible)
        self.aitunnel_api_key: Optional[str] = os.getenv("AITUNNEL_API_KEY")
        self.aitunnel_base_url: str = os.getenv(
            "AITUNNEL_BASE_URL", "https://api.aitunnel.ru/v1"
        )
        self.llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.embedding_model: str = os.getenv(
            "EMBEDDING_MODEL", "text-embedding-3-small"
        )

        # Pinecone
        self.pinecone_api_key: Optional[str] = os.getenv("PINECONE_API_KEY")
        self.pinecone_env: Optional[str] = os.getenv("PINECONE_ENV")
        self.pinecone_index: str = os.getenv("PINECONE_INDEX", "platon-rubond")

        # Local DBs
        self.history_db: str = os.getenv(
            "HISTORY_DB", str(self.project_root / "history.db")
        )
        self.portfolio_db: str = os.getenv(
            "PORTFOLIO_DB", str(self.project_root / "portfolio.db")
        )

        # Agent
        self.agent_temperature: float = float(os.getenv("AGENT_TEMPERATURE", "0.1"))
        self.agent_max_iterations: int = int(os.getenv("AGENT_MAX_ITERATIONS", "8"))
