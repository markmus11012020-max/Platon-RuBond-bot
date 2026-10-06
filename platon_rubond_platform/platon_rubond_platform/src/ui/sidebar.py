"""
Боковая панель Streamlit — настройки модели, риска и сервисные действия.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import streamlit as st

from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.ui.sidebar")

MODEL_OPTIONS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "claude-3-5-sonnet",
]

RATING_OPTIONS = [
    "AAA",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "BB-",
]


@dataclass
class SidebarConfig:
    """Снимок настроек из боковой панели."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.1
    min_rating: str = "BBB-"
    key_rate: float = 0.16
    tax_rate: float = 0.13
    max_position_weight: float = 0.20
    session_id: str = "operator-1"
    theme: str = "light"  # "light" | "dark"


class SidebarRenderer:
    """
    Рендерер боковой панели оператора.

    Не содержит бизнес-логики агента — только UI и session_state.
    """

    def __init__(self) -> None:
        self._init_defaults()

    def _init_defaults(self) -> None:
        defaults = {
            "ui_model": "gpt-4o-mini",
            "ui_temperature": 0.1,
            "ui_min_rating": "BBB-",
            "ui_key_rate": 0.16,
            "ui_tax_rate": 0.13,
            "ui_max_weight": 0.20,
            "ui_session_id": "operator-1",
            "ui_theme": "light",
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v

    def render(self) -> SidebarConfig:
        """Отрисовывает sidebar и возвращает актуальный SidebarConfig."""
        with st.sidebar:
            st.title("⚙️ Platon-RuBond")
            st.caption("Операторская панель")

            st.subheader("Оформление")
            theme_label = st.toggle(
                "Тёмная тема",
                value=(st.session_state.ui_theme == "dark"),
                key="ui_theme_toggle",
                help="Переключение светлой / тёмной темы интерфейса",
            )
            theme = "dark" if theme_label else "light"
            st.session_state.ui_theme = theme
            badge = "🌙 Dark" if theme == "dark" else "☀️ Light"
            st.markdown(
                f'<span class="prb-theme-badge">{badge}</span>',
                unsafe_allow_html=True,
            )

            st.divider()
            st.subheader("Модель LLM")
            model = st.selectbox(
                "Модель",
                options=MODEL_OPTIONS,
                index=MODEL_OPTIONS.index(st.session_state.ui_model)
                if st.session_state.ui_model in MODEL_OPTIONS
                else 0,
                key="ui_model_select",
            )
            st.session_state.ui_model = model

            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=float(st.session_state.ui_temperature),
                step=0.05,
                key="ui_temp_slider",
            )
            st.session_state.ui_temperature = temperature

            st.divider()
            st.subheader("Риск-профиль")
            min_rating = st.selectbox(
                "Мин. кредитный рейтинг",
                options=RATING_OPTIONS,
                index=RATING_OPTIONS.index(st.session_state.ui_min_rating)
                if st.session_state.ui_min_rating in RATING_OPTIONS
                else RATING_OPTIONS.index("BBB-"),
                help="Облигации ниже порога будут отфильтрованы / помечены",
                key="ui_rating_select",
            )
            st.session_state.ui_min_rating = min_rating

            key_rate_pct = st.number_input(
                "Ключевая ставка ЦБ, %",
                min_value=0.0,
                max_value=30.0,
                value=float(st.session_state.ui_key_rate) * 100.0,
                step=0.25,
                help="Используется для оценки флоатеров",
                key="ui_key_rate_input",
            )
            key_rate = key_rate_pct / 100.0
            st.session_state.ui_key_rate = key_rate

            tax_rate_pct = st.number_input(
                "НДФЛ на купон, %",
                min_value=0.0,
                max_value=30.0,
                value=float(st.session_state.ui_tax_rate) * 100.0,
                step=1.0,
                key="ui_tax_input",
            )
            tax_rate = tax_rate_pct / 100.0
            st.session_state.ui_tax_rate = tax_rate

            max_weight = st.slider(
                "Макс. доля позиции",
                min_value=0.05,
                max_value=0.50,
                value=float(st.session_state.ui_max_weight),
                step=0.05,
                format="%.0f%%",
                key="ui_weight_slider",
            )
            # slider shows 0.05 as number; format doesn't multiply — display as fraction
            st.session_state.ui_max_weight = max_weight

            st.divider()
            st.subheader("Сессия")
            session_id = st.text_input(
                "Session ID",
                value=st.session_state.ui_session_id,
                key="ui_session_input",
            )
            st.session_state.ui_session_id = session_id or "operator-1"

            st.divider()
            st.subheader("Сервис")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑 История чата", use_container_width=True):
                    self._clear_chat_history(session_id)
            with col2:
                if st.button("🔄 Сброс кэша", use_container_width=True):
                    self._clear_caches()

            if st.button("⚠ Полный сброс индексов", use_container_width=True):
                self._reset_indexes()

            st.caption("Platon-RuBond-bot · LangChain · MOEX")

        return SidebarConfig(
            model=model,
            temperature=temperature,
            min_rating=min_rating,
            key_rate=key_rate,
            tax_rate=tax_rate,
            max_position_weight=max_weight,
            session_id=session_id or "operator-1",
            theme=st.session_state.get("ui_theme", "light"),
        )

    def _clear_chat_history(self, session_id: str) -> None:
        try:
            from src.memory.sql_history import SQLiteHistoryManager
            from src.config import Config

            cfg = Config()
            hm = SQLiteHistoryManager(db_path=cfg.history_db)
            hm.clear_session(session_id)
            hm.close()
            if "chat_messages" in st.session_state:
                st.session_state.chat_messages = []
            st.sidebar.success("История диалога очищена")
        except Exception as exc:
            logger.exception("clear history failed")
            st.sidebar.error(f"Ошибка: {exc}")

    def _clear_caches(self) -> None:
        try:
            from src.agent.cache import get_tool_cache

            n = get_tool_cache().invalidate()
            st.sidebar.success(f"Кэш tools очищен ({n} записей)")
        except Exception as exc:
            st.sidebar.error(f"Ошибка кэша: {exc}")

    def _reset_indexes(self) -> None:
        try:
            from src.agent.cache import get_tool_cache
            from src.config import Config
            from src.memory.pinecone_store import PineconeMemoryManager

            get_tool_cache().invalidate()
            cfg = Config()
            pm = PineconeMemoryManager(
                api_key=cfg.pinecone_api_key,
                environment=cfg.pinecone_env,
                index_name=cfg.pinecone_index,
                aitunnel_api_key=cfg.aitunnel_api_key,
                aitunnel_base_url=cfg.aitunnel_base_url,
            )
            pm.delete_namespace("bonds-news")
            st.sidebar.success("Кэш и namespace Pinecone сброшены")
        except Exception as exc:
            logger.exception("reset indexes failed")
            st.sidebar.error(f"Ошибка сброса: {exc}")
