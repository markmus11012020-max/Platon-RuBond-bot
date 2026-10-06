"""
Темы оформления UI: светлая / тёмная (переключение в runtime).
"""

from __future__ import annotations

LIGHT_CSS = """
<style>
:root {
  --prb-bg: #f7f8fa;
  --prb-surface: #ffffff;
  --prb-text: #1a1d23;
  --prb-muted: #5c6570;
  --prb-border: #e2e6eb;
  --prb-accent: #1f6feb;
  --prb-accent-soft: #e8f0fe;
  --prb-success: #0f7b4c;
  --prb-warning: #b54708;
  --prb-danger: #c62828;
  --prb-sidebar: #f0f2f5;
}
.stApp {
  background: var(--prb-bg) !important;
  color: var(--prb-text) !important;
}
.block-container { padding-top: 1.2rem; max-width: 100%; }
section[data-testid="stSidebar"] {
  background: var(--prb-sidebar) !important;
  border-right: 1px solid var(--prb-border);
}
section[data-testid="stSidebar"] * { color: var(--prb-text); }
h1, h2, h3, h4 { color: var(--prb-text) !important; letter-spacing: -0.02em; }
div[data-testid="stMetricValue"] { font-size: 1.35rem; color: var(--prb-text) !important; }
div[data-testid="stMetricLabel"] { color: var(--prb-muted) !important; }
div[data-testid="stChatMessage"] {
  background: var(--prb-surface) !important;
  border: 1px solid var(--prb-border);
  border-radius: 12px;
}
.stTabs [data-baseweb="tab-list"] {
  gap: 4px;
  background: transparent;
  border-bottom: 1px solid var(--prb-border);
}
.stTabs [data-baseweb="tab"] {
  border-radius: 8px 8px 0 0;
  color: var(--prb-muted);
}
.stTabs [aria-selected="true"] {
  background: var(--prb-accent-soft) !important;
  color: var(--prb-accent) !important;
}
hr { border-color: var(--prb-border) !important; }
.prb-theme-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.75rem;
  background: var(--prb-accent-soft);
  color: var(--prb-accent);
  border: 1px solid var(--prb-border);
}
</style>
"""

DARK_CSS = """
<style>
:root {
  --prb-bg: #0e1117;
  --prb-surface: #161b22;
  --prb-text: #e6edf3;
  --prb-muted: #8b949e;
  --prb-border: #30363d;
  --prb-accent: #58a6ff;
  --prb-accent-soft: #1f2a3a;
  --prb-success: #3fb950;
  --prb-warning: #d29922;
  --prb-danger: #f85149;
  --prb-sidebar: #010409;
}
.stApp {
  background: var(--prb-bg) !important;
  color: var(--prb-text) !important;
}
.block-container { padding-top: 1.2rem; max-width: 100%; }
section[data-testid="stSidebar"] {
  background: var(--prb-sidebar) !important;
  border-right: 1px solid var(--prb-border);
}
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] p {
  color: var(--prb-text) !important;
}
h1, h2, h3, h4 { color: var(--prb-text) !important; letter-spacing: -0.02em; }
p, span, label, .stMarkdown { color: var(--prb-text); }
div[data-testid="stMetricValue"] { font-size: 1.35rem; color: var(--prb-text) !important; }
div[data-testid="stMetricLabel"] { color: var(--prb-muted) !important; }
div[data-testid="stChatMessage"] {
  background: var(--prb-surface) !important;
  border: 1px solid var(--prb-border);
  border-radius: 12px;
}
[data-testid="stExpander"] {
  background: var(--prb-surface);
  border: 1px solid var(--prb-border);
  border-radius: 10px;
}
.stTabs [data-baseweb="tab-list"] {
  gap: 4px;
  border-bottom: 1px solid var(--prb-border);
}
.stTabs [data-baseweb="tab"] {
  border-radius: 8px 8px 0 0;
  color: var(--prb-muted) !important;
}
.stTabs [aria-selected="true"] {
  background: var(--prb-accent-soft) !important;
  color: var(--prb-accent) !important;
}
/* Inputs */
.stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {
  background-color: var(--prb-surface) !important;
  color: var(--prb-text) !important;
  border-color: var(--prb-border) !important;
}
.stTextInput input::placeholder { color: var(--prb-muted) !important; }
/* Buttons */
.stButton > button {
  border-radius: 8px;
  border-color: var(--prb-border);
}
.stButton > button[kind="primary"] {
  background: var(--prb-accent);
  color: #0e1117;
  border: none;
}
hr { border-color: var(--prb-border) !important; }
/* Dataframes */
[data-testid="stDataFrame"] {
  background: var(--prb-surface);
  border: 1px solid var(--prb-border);
  border-radius: 8px;
}
.prb-theme-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.75rem;
  background: var(--prb-accent-soft);
  color: var(--prb-accent);
  border: 1px solid var(--prb-border);
}
/* Status / alerts soft override */
div[data-testid="stAlert"] {
  border-radius: 10px;
}
</style>
"""


def get_theme_css(theme: str) -> str:
    """Возвращает CSS для выбранной темы: 'dark' | 'light'."""
    if (theme or "").lower() == "dark":
        return DARK_CSS
    return LIGHT_CSS


def apply_theme(theme: str) -> None:
    """Инжектит CSS темы в текущую Streamlit-страницу."""
    import streamlit as st

    st.markdown(get_theme_css(theme), unsafe_allow_html=True)
