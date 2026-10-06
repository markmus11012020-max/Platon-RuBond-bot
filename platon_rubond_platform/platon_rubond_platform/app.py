"""
Точка входа: Platon-RuBond-bot Platform (Streamlit).

Запуск:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.ui.sidebar import SidebarRenderer
from src.ui.tabs import TabsRenderer
from src.ui.theme import apply_theme


def main() -> None:
    st.set_page_config(
        page_title="Platon-RuBond-bot Platform",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Тема по умолчанию до рендера sidebar (чтобы не мигало)
    if "ui_theme" not in st.session_state:
        st.session_state.ui_theme = "light"

    sidebar = SidebarRenderer()
    config = sidebar.render()

    # Применяем выбранную тему после toggle
    apply_theme(config.theme)

    st.title("📈 Platon-RuBond-bot Platform")
    st.caption(
        "ИИ-агент рынка облигаций РФ · MOEX · LangChain · Pinecone · Risk Officer"
    )

    tabs = TabsRenderer(config=config)
    tabs.render()


if __name__ == "__main__":
    main()
