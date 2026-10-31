# 📈 Platon-RuBond-bot

> **Автономный ИИ-агент рынка облигаций РФ** — мониторинг Московской Биржи, семантический анализ новостей, расчёт доходности, Risk-Officer и уведомления в Telegram.

## 🧭 Два продукта в одном репозитории

| Продукт | Точка входа | Назначение |
|---|---|---|
| **Streamlit-агент** | `app.py`, `src/` | исследовательский UI: LangGraph, RAG, Risk-Officer, новости, портфель |
| **VK-бот `bondbot`** | `bondbot/` | текущий production-фокус: детерминированная аналитика облигаций, приватный помощник в VK |

Дальше в этом README описаны оба слоя. Краткая документация по VK-боту — в [`bondbot/README.md`](bondbot/README.md).

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3%2B-green?logo=langchain&logoColor=white)](https://python.langchain.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-orange)](https://langchain-ai.github.io/langgraph/)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-red?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Pinecone](https://img.shields.io/badge/Pinecone-RAG-purple)](https://www.pinecone.io/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)
[![Status](https://img.shields.io/badge/status-MVP-success)]()

---

## 🏗 Архитектура

Проект построен на принципах **SOLID**, **ООП** и **модульности**. Каждый компонент — отдельный класс с единственной зоной ответственности. Расширение функциональности (новый источник данных, новый канал уведомлений) выполняется через наследование от абстрактных интерфейсов без изменения ядра (**Open/Closed Principle**).

### 📐 Высокоуровневая схема

```
+---------------------------------------------------------------------+
|                       Streamlit UI (app.py)                         |
|  +--------------+--------------+--------------+------------------+  |
|  | Chat Agent   | Market       | Portfolio    | News + RAG       |  |
|  +--------------+--------------+--------------+------------------+  |
+-------------------------------+-------------------------------------+
                                |
                                v
+---------------------------------------------------------------------+
|         PlatonAgentFactory  (src/agent/agent_factory.py)           |
|  +------------------------------------------------------------+     |
|  |             LangGraph State Machine (graph.py)            |     |
|  |                                                            |     |
|  |   parse_intent -> route -> [fetch_bond | analyze_bond |    |     |
|  |                            search_news | fetch_key_rate]   |     |
|  |                                          |                 |     |
|  |                                          v                 |     |
|  |                                  risk_officer              |     |
|  |                                          |                 |     |
|  |                                          v                 |     |
|  |                                  human_gate (HITL)         |     |
|  |                                          |                 |     |
|  |                                          v                 |     |
|  |                                       respond              |     |
|  +------------------------------------------------------------+     |
+-------------------------------+-------------------------------------+
                                |
              +-----------------+-----------------+
              v                 v                 v
+-------------------+  +-------------------+  +-------------------+
|  Data Providers   |  |    Analytics      |  |      Memory       |
|  (parsers)        |  |    (math)         |  |  (history/RAG)    |
+-------------------+  +-------------------+  +-------------------+
|  MoexParser       |  |  BondAnalyzer     |  |  SQLiteHistory    |
|  NewsParser       |  |  PortfolioManager |  |  PineconeMemory   |
|  MacroParser      |  |                   |  |  ToolCache        |
|     ^             |  |                   |  |  RAGQualityTrack  |
|  BaseParser (ABC) |  |                   |  |  LocalTracer      |
+-------------------+  +-------------------+  +-------------------+
```

### 🗂 Структура проекта

```
Platon-RuBond-bot/
│
├── app.py                          # Точка входа Streamlit
├── requirements.txt                # Зависимости Python
├── pytest.ini                      # Конфигурация pytest
├── .env.example                    # Шаблон переменных ок��ужения
├── .gitignore                      # Исключения для Git
│
├── start.bat                       # Оркестратор запуска (Windows)
├── start.sh                        # Оркестратор запуска (Linux/macOS)
│
├── src/
│   ├── config.py                   # Config: загрузка .env, пути, ключи
│   │
│   ├── data_providers/             # 🔌 Слой сбора данных (Open/Closed)
│   │   ├── base_parser.py          #   ABC: BaseParser
│   │   ├── moex_api.py             #   MoexParser (ISS MOEX)
│   │   ├── news_scraper.py         #   NewsParser (RSS + DDG)
│   │   └── macro_parser.py         #   MacroParser (ЦБ РФ)
│   │
│   ├── analytics/                  # 📐 Финансовая математика
│   │   ├── bond_math.py            #   BondAnalyzer (YTM, спреды, флоатеры)
│   │   └── portfolio.py            #   PortfolioManager (SQLite, метрики)
│   │
│   ├── agent/                      # 🤖 LangChain/LangGraph агент
│   │   ├── agent_factory.py        #   PlatonAgentFactory (entry point)
│   │   ├── graph.py                #   LangGraph StateGraph + PipelineRunner
│   │   ├── tools.py                #   @tool-обёртки для LLM
│   │   ├── schemas.py              #   Pydantic: AgentFinalResponse, RiskReview
│   │   ├── prompts.py              #   Системные промпты
│   │   ├── cache.py                #   ToolCache (SQLite TTL)
│   │   ├── rag_quality.py          #   RAGQualityTracker (метрики)
│   │   └── observability.py        #   LocalTracer + LangSmith
│   │
│   ├── memory/                     # 💾 Долговременная память
│   │   ├── sql_history.py          #   SQLiteHistoryManager (диалоги)
│   │   └── pinecone_store.py       #   PineconeMemoryManager (RAG)
│   │
│   ├── ui/                         # 🎨 Streamlit UI
│   │   ├── sidebar.py              #   SidebarRenderer + SidebarConfig
│   │   ├── tabs.py                 #   TabsRenderer (4 вкладки)
│   │   └── theme.py                #   LIGHT_CSS / DARK_CSS
│   │
│   └── utils/                      # 🔧 Утилиты
│       ├── logger.py               #   setup_logger
│       └── telegram_alerts.py      #   TelegramNotifier
│
└── tests/                          # ✅ Pytest suite
    ├── agent/
    │   └── test_module2_upgrades.py
    └── analytics/
        ├── test_bond_math.py
        ├── test_macro.py
        └── test_portfolio.py
```

### 🧬 Принципы проектирования

| Принцип | Реализация |
|---|---|
| **S** — Single Responsibility | Каждый класс решает одну задачу: `MoexParser` только парсит ISS, `BondAnalyzer` только считает YTM, `PortfolioManager` только управляет позициями |
| **O** — Open/Closed | Новый источник данных = новый класс-наследник `BaseParser`. Новый канал алертов = новый класс-наследник `TelegramNotifier`. Ядро не меняется |
| **L** — Liskov Substitution | `MoexParser`, `NewsParser`, `MacroParser` взаимозаменяемы через интерфейс `BaseParser` |
| **I** — Interface Segregation | `BaseParser` имеет только `fetch_data` + `parse_data` — минимальный контракт |
| **D** — Dependency Inversion | `PlatonAgentFactory` зависит от абстракций (`BaseParser`, `ToolCache`), а не от конкретных реализаций |

---

## 🤖 VK-бот `bondbot`

Детерминированное ядро без LLM в расчётах: данные smart-lab/MOEX, ставка ЦБ, скрининг, портфель, стратегии и аудит.

```powershell
.\.venv\Scripts\python -m bondbot.cli update --pages 3
.\.venv\Scripts\python -m bondbot.cli rate
.\.venv\Scripts\python -m bondbot.cli safe --limit 5
.\.venv\Scripts\python -m bondbot.cli exit
.\.venv\Scripts\python -m bondbot.cli alloc
.\.venv\Scripts\python -m bondbot.cli audit
```

Команды VK: `/portfolio`, `/bond ISIN`, `/issuer НАЗВАНИЕ`, `/value ISIN`, `/watch`, `/screen постоянный 2 4 12`, `/safe`, `/exit`, `/alloc`, `/risk`, `/stress`, `/news`, `/new`, `/idea`, `/journal`, `/strategy`, `/relative`, `/calendar`, `/doctor`, `/whatsnew`, `/position`, `/ask`, `/clear`, `/keyboard`, `/status`, `/help`.

Любой обычный текст (без команды) уходит в диалог с ИИ; история — последние 12 сообщений, сброс — `/clear`.

Планировщик обновляет рынок и новости, формирует утренний дайджест, алерты и стратегию недели. LLM используется только для объяснений: все числа берутся из детерминированных инструментов.

Публичный режим — только для участников VK-сообщества. Персональные профили и портфели не сохраняются; короткая память диалога живёт 2 часа. Портфель администратора обновляется файлом `portfolio.html` из Smart-Lab, отправленным боту в VK. Лимит LLM — `BONDBOT_LLM_DAILY_TOKEN_LIMIT` (по умолчанию 500 000 токенов на пользователя в день). Для налоговой справки — `/tax` и `/iis`.

Скрининг с полной сортировкой: `/screen постоянный 2 4 12`, `/screen погашение до 2028-12-31 сортировка доходность`, `/preset консервативный`.

Production-развёртывание — отдельный compose-project `platon-bond-bot`, health на `127.0.0.1:8081`; существующий freelance-бот (порт 8080) и Caddy не затрагиваются.

---

## 🚀 Быстрый старт

### 1. Клонирование и настройка

```bash
git clone https://github.com/markmus11012020-max/Platon-RuBond-bot.git
cd Platon-RuBond-bot
cp .env.example .env
# Отредактируйте .env и впишите свои API-ключи
```

### 2. Запуск одной командой

**Windows:**
```cmd
start.bat
```

**Linux / macOS:**
```bash
chmod +x start.sh
./start.sh
```

Скрипт автоматически:
1. 🛑 Останавливает старые процессы Streamlit
2. 🧹 Очищает `__pycache__`, `.pytest_cache`, кэш tools
3. 🐍 Создаёт `.venv` (если нет) и устанавливает зависимости
4. 🚀 Запускает Streamlit на `http://localhost:8501`

### 3. Ручной запуск

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

---

## ⚙️ Конфигурация (`.env`)

| Переменная | Описание | По умолчанию |
|---|---|---|
| `AITUNNEL_API_KEY` | API-ключ LLM-провайдера (OpenAI-compatible) | — |
| `AITUNNEL_BASE_URL` | Базовый URL API | `https://api.aitunnel.ru/v1` |
| `LLM_MODEL` | Модель LLM | `gpt-4o-mini` |
| `EMBEDDING_MODEL` | Модель эмбеддингов | `text-embedding-3-small` |
| `AGENT_TEMPERATURE` | Температура LLM | `0.1` |
| `AGENT_MAX_ITERATIONS` | Макс. итераций агента | `8` |
| `PINECONE_API_KEY` | API-ключ Pinecone | — |
| `PINECONE_ENV` | Окружение Pinecone | — |
| `PINECONE_INDEX` | Имя индекса | `platon-rubond` |
| `HISTORY_DB` | Путь к SQLite истории | `history.db` |
| `PORTFOLIO_DB` | Путь к SQLite портфеля | `portfolio.db` |

---

## 🧪 Тестирование

```bash
pytest -v
```

Покрытие:
- ✅ `BondAnalyzer` — YTM (Newton-Raphson), амортизация, НКД, спреды, налоги, фильтры
- ✅ `MacroParser` — fallback, парсинг HTML, кэш, интеграция с флоатерами
- ✅ `PortfolioManager` — CRUD, persistence, метрики, диверсификация
- ✅ `ToolCache` — TTL, ��нвалидация
- ✅ `RAGQualityTracker` — логирование, feedback, статистика
- ✅ `LocalTracer` — span lifecycle
- ✅ `PipelineRunner` — intent routing, streaming, risk officer

---

## 🛠 Технологический стек

| Слой | Технологии |
|---|---|
| **LLM Orchestration** | LangChain 0.3+, LangGraph (StateGraph) |
| **LLM Provider** | OpenAI-compatible через AiTunnel |
| **UI** | Streamlit (light/dark theme, custom CSS) |
| **Data Sources** | ISS MOEX API, RSS Интерфакс, DuckDuckGo Search |
| **Vector DB** | Pinecone (с offline-fallback на cosine + HashEmbedding) |
| **Persistence** | SQLite (history, portfolio, tool cache, RAG quality) |
| **Observability** | LocalTracer (JSONL) + опциональный LangSmith |
| **Notifications** | Telegram Bot API |
| **Testing** | pytest |

---

## 📊 Ключевые модули

### 🤖 `PlatonAgentFactory` — фабрика агента

```python
from src.agent.agent_factory import PlatonAgentFactory

factory = PlatonAgentFactory()
response = factory.run("Проанализируй SU26238RMFS7", session_id="u1")
print(response.summary, response.bond_report.ytm_pct)

# Streaming для UI
for step, state in factory.stream("Какая ставка ЦБ?", session_id="u1"):
    print(step, state.get("intermediate"))
```

### 📐 `BondAnalyzer` — финансовая математика

```python
from src.analytics.bond_math import BondAnalyzer

analyzer = BondAnalyzer()
ytm = analyzer.calculate_ytm(bond_data, tax_rate=0.13)        # Newton-Raphson
spread = analyzer.calculate_z_spread(bond_data, 0.16)         # Z-spread
floater = analyzer.estimate_floater_yield(bond_data, 0.16)    # Флоатер
```

### 💼 `PortfolioManager` — портфель

```python
from src.analytics.portfolio import PortfolioManager

pm = PortfolioManager(db_path="portfolio.db", tax_rate=0.13)
pm.add_to_portfolio("RU000A105XX3", 10, 98.5, issuer="Gazprom")
metrics = pm.calculate_portfolio_metrics(market_data)
print(metrics["weighted_ytm_net"], metrics["diversification_ok"])
```

### 🔌 Расширение: новый источник данных

```python
from src.data_providers.base_parser import BaseParser

class CbondsParser(BaseParser):
    def fetch_data(self, *args, **kwargs):
        # ваша логика
        ...
    def parse_data(self, raw_data):
        # нормализация
        ...
```

Регистрация в `src/agent/tools.py` — без изменения ядра агента.

---

## 🛡 Risk Officer & Human-in-the-Loop

Агент автоматически классифицирует уровень риска (`LOW / MEDIUM / HIGH / CRITICAL`) на основе:
- YTM > 25% → пометка ВДО
- Отсутствие рейтинга → требуется ручная проверка
- Негативные кредитные события в новостях

При `HIGH/CRITICAL` граф останавливается на ноде `human_gate` и ждёт решения оператора (`approve` / `reject`).

---

## 📈 Roadmap

- [x] LangGraph state machine с Risk Officer
- [x] Точная YTM (Newton-Raphson) + амортизация + НКД + налоги
- [x] RAG-слой (Pinecone + offline fallback)
- [x] Tool cache с TTL
- [x] Observability (LocalTracer + LangSmith)
- [x] Streamlit UI (light/dark, 4 вкладки)
- [x] Portfolio persistence + метрики
- [x] VK-бот: smart-lab, MOEX ISS, CBR key rate, скрининг, портфель, `/safe`, `/exit`, `/alloc`
- [x] Аудит стратегических расчётов (`strategy_audit`)
- [x] Планировщик обновления данных и проактивные алерты
- [x] Новости RSS, новые выпуски, риск-скор, стресс-тест
- [x] LLM-ассистент `/ask`, журнал идей `/journal`, стратегия недели
- [ ] Telegram-алерты (заглушка готова, нужен бот-токен)
- [ ] Backtesting стратегий на исторических данных
- [ ] Интеграция с Cbonds/БКС для расширенных данных
- [ ] Multi-user auth + per-user portfolio

---

## 📄 Лицензия

MIT © Platon-RuBond-bot

---

## 🤝 Контакты

- GitHub: [@markmus11012020-max](https://github.com/markmus11012020-max)
- Repo: [Platon-RuBond-bot](https://github.com/markmus11012020-max/Platon-RuBond-bot)

> ⚠ **Дисклеймер:** Проект предназначен для исследовательских и аналитических целей. Не является инвестиционной рекомендацией. Все решения по сделкам принимаются оператором после human-in-the-loop подтверждения.
