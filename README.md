Platon-RuBond-bot

Автономный ИИ-агент рынка облигаций РФ: мониторинг Московской Биржи, анализ новостей, расчёт доходности, Risk-Officer и уведомления. В репозитории два продукта: исследовательский Streamlit-агент и production VK-бот bondbot.

ДВА ПРОДУКТА В ОДНОМ РЕПОЗИТОРИИ

Streamlit-агент
Точка входа: app.py, src/
Назначение: исследовательский UI с LangGraph, RAG, Risk-Officer, новостями и портфелем.

VK-БОТ BONDBOT
Точка входа: bondbot/
Назначение: текущий production-фокус. Детерминированная аналитика облигаций и помощник в VK для участников сообщества.

Краткая документация по VK-боту находится в bondbot/README.md.


АРХИТЕКТУРА

Проект построен на принципах SOLID, ООП и модульности. Каждый компонент отвечает за свою зону. Новый источник данных или канал уведомлений добавляется через наследников абстрактных интерфейсов без изменения ядра.

Высокоуровневая схема

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


СТРУКТУРА ПРОЕКТА

```
Platon-RuBond-bot/
│
├── app.py                          Точка входа Streamlit
├── requirements.txt                Зависимости Python
├── pytest.ini                      Конфигурация pytest
├── .env.example                    Шаблон переменных окружения
├── .gitignore                      Исключения для Git
│
├── start.bat                       Оркестратор запуска (Windows)
├── start.sh                        Оркестратор запуска (Linux/macOS)
│
├── src/
│   ├── config.py                   Config: загрузка .env, пути, ключи
│   │
│   ├── data_providers/             Слой сбора данных (Open/Closed)
│   │   ├── base_parser.py          ABC: BaseParser
│   │   ├── moex_api.py             MoexParser (ISS MOEX)
│   │   ├── news_scraper.py         NewsParser (RSS + DDG)
│   │   └── macro_parser.py         MacroParser (ЦБ РФ)
│   │
│   ├── analytics/                  Финансовая математика
│   │   ├── bond_math.py            BondAnalyzer (YTM, спреды, флоатеры)
│   │   └── portfolio.py            PortfolioManager (SQLite, метрики)
│   │
│   ├── agent/                      LangChain/LangGraph агент
│   │   ├── agent_factory.py        PlatonAgentFactory (entry point)
│   │   ├── graph.py                LangGraph StateGraph + PipelineRunner
│   │   ├── tools.py                @tool-обёртки для LLM
│   │   ├── schemas.py              Pydantic: AgentFinalResponse, RiskReview
│   │   ├── prompts.py              Системные промпты
│   │   ├── cache.py                ToolCache (SQLite TTL)
│   │   ├── rag_quality.py          RAGQualityTracker (метрики)
│   │   └── observability.py        LocalTracer + LangSmith
│   │
│   ├── memory/                     Долговременная память
│   │   ├── sql_history.py          SQLiteHistoryManager (диалоги)
│   │   └── pinecone_store.py       PineconeMemoryManager (RAG)
│   │
│   ├── ui/                         Streamlit UI
│   │   ├── sidebar.py              SidebarRenderer + SidebarConfig
│   │   ├── tabs.py                 TabsRenderer (4 вкладки)
│   │   └── theme.py                LIGHT_CSS / DARK_CSS
│   │
│   └── utils/                      Утилиты
│       ├── logger.py               setup_logger
│       └── telegram_alerts.py      TelegramNotifier
│
├── bondbot/                        VK-бот и брокерские интеграции
│   ├── main.py                     Запуск VK-бота и планировщика
│   ├── cli.py                      CLI для данных, портфеля и брокеров
│   ├── config.py                   Настройки BONDBOT
│   ├── db.py                       SQLite: бумаги, позиции, аудит, LLM-лимиты
│   ├── brokers/
│   │   ├── base.py                 Общие модели брокеров
│   │   └── tinvest.py              Read-only клиент T-Invest API
│   ├── services/
│   │   ├── broker_sync.py          Синхронизация портфеля брокера
│   │   └── scheduler.py            Фоновые задачи
│   ├── certs/                      Russian Trusted Root/Sub CA для T-Invest
│   ├── Dockerfile                  Образ production-бота
│   └── README.md                   Документация VK-бота
│
└── tests/                          Pytest suite
    ├── agent/
    │   └── test_module2_upgrades.py
    ├── analytics/
    │   ├── test_bond_math.py
    │   ├── test_macro.py
    │   └── test_portfolio.py
    └── bondbot/
        ├── test_brokers.py
        ├── test_handlers.py
        ├── test_services.py
        └── ...
```


ПРИНЦИПЫ ПРОЕКТИРОВАНИЯ

- Single Responsibility: каждый класс решает одну задачу. MoexParser только парсит ISS, BondAnalyzer только считает YTM, PortfolioManager только управляет позициями.
- Open/Closed: новый источник данных — новый наследник BaseParser. Новый канал алертов — новый наследник TelegramNotifier. Ядро не меняется.
- Liskov Substitution: MoexParser, NewsParser и MacroParser взаимозаменяемы через интерфейс BaseParser.
- Interface Segregation: BaseParser содержит только fetch_data и parse_data — минимальный контракт.
- Dependency Inversion: PlatonAgentFactory зависит от абстракций BaseParser и ToolCache, а не от конкретных реализаций.


VK-БОТ BONDBOT

Детерминированное ядро без LLM в расчётах: данные smart-lab и MOEX, ставка ЦБ, скрининг, портфель, стратегии и аудит.

CLI

```powershell
.\.venv\Scripts\python -m bondbot.cli update --pages 3
.\.venv\Scripts\python -m bondbot.cli rate
.\.venv\Scripts\python -m bondbot.cli safe --limit 5
.\.venv\Scripts\python -m bondbot.cli exit
.\.venv\Scripts\python -m bondbot.cli alloc
.\.venv\Scripts\python -m bondbot.cli audit
```

Команды VK

/portfolio, /bond ISIN, /issuer НАЗВАНИЕ, /value ISIN, /watch, /screen постоянный 2 4 12, /safe, /exit, /alloc, /risk, /stress, /news, /new, /idea, /journal, /strategy, /relative, /calendar, /doctor, /whatsnew, /position, /ask, /clear, /keyboard, /status, /help.

Любой обычный текст без команды уходит в диалог с ИИ. История хранит последние 12 сообщений, сброс — /clear.

Планировщик обновляет рынок и новости, формирует утренний дайджест, алерты и стратегию недели. LLM используется только для объяснений: все числа берутся из детерминированных инструментов.

Публичный режим

Доступ открыт только участникам VK-сообщества. Персональные профили и портфели пользователей не сохраняются. Короткая память диалога живёт 2 часа. Лимит LLM — BONDBOT_LLM_DAILY_TOKEN_LIMIT, по умолчанию 500 000 токенов на пользователя в день.

Администратору доступны портфель, позиции, watchlist, стратегии, стресс-тест, журнал и брокерские команды. Публичным пользователям — аналитика, скрининг, карточки бумаг, новости, налоги и ИИ-ассистент.

Портфель

Портфель администратора обновляется файлом portfolio.html из Smart-Lab, отправленным боту в VK. Бот заменяет состав портфеля, удаляет старые позиции и обновляет карточки бумаг.

Если VK не передаёт файл, используется команда:

/portfolio url https://прямая-ссылка-на-portfolio.html

Брокерские интеграции

T-Invest
Официальный read-only API. Команды /broker accounts и /broker sync tinvest. Синхронизация заменяет бумажный портфель реальными позициями, не выставляет заявки и не требует торговых прав. Автосинк включается через BONDBOT_BROKER_SYNC_ENABLED. В Docker-образ добавлены сертификаты Russian Trusted Root/Sub CA, без них TLS-запросы к T-Invest API не проходят.

СберИнвестиции
Официального публичного API для брокерских счетов физлиц нет. Sber API предназначен для бизнес-сценариев, а не для портфеля частного инвестора. Рабочий вариант — импорт брокерского отчёта Сбера. Неофициальные и скрапинговые коннекторы не используются.

Скрининг

Полная сортировка и фильтры по доходности, дюрации, дате погашения, дате оферты, типу и частоте купона, рейтингу, цене, объёму, размеру выпуска, эмитенту и признаку полных данных.

Примеры:

/screen постоянный 2 4 12
/screen погашение до 2028-12-31 сортировка доходность
/preset консервативный

Налоги и ИИС

Справочные команды /tax и /iis. Материалы содержат датированные ссылки на официальные источники и не являются налоговой консультацией.

Развёртывание

Production-развёртывание выполняется отдельным compose-проектом platon-bond-bot. Health-check доступен на 127.0.0.1:8081. Существующий freelance-бот на порту 8080 и Caddy не затрагиваются.


PREMARKET PWA

Новый слой для конкурса «Инвест. Премаркет»: мобильное PWA на Next.js и FastAPI gateway с MCP-клиентом.

Структура:

- apps/web — Next.js PWA: портфель, чат с агентом, сделки, второй бот Freelance Radar;
- services/api — FastAPI: API gateway, mock/sandbox данные, read-only адаптеры;
- modules/bond — логика Bond Copilot;
- modules/freelance — read-only лента заказов;
- infra — Caddy и схема деплоя.

Запуск:

```bash
docker compose -p platon-premarket -f docker-compose.premarket.yml up -d --build
```

Локально:

```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir services/api --port 8000
cd apps/web
npm install
npm run dev
```

PWA: https://platoninvest.pro

API: https://platoninvest.pro/api

Документация API: https://platoninvest.pro/api/docs

T-Invest MCP подключается через PREMARKET_TINVEST_MCP_* в .env. Токен хранится только на backend. Сделки выполняются в sandbox и только после подтверждения. LLM включается через PREMARKET_LLM_ENABLED и используется только для объяснений; при ошибке чат переходит на детерминированные ответы. В демо-режиме используются данные портфеля и mock-сценарии, чтобы интерфейс работал без токена.

Риск-гейт: credit events, ручной блоклист, новости, просадка 7/30 дней, объём, bid/ask и кредитные проверки. Пока проверка не пройдена, бумага не показывается как идея. Управление блоклистом: /api/risk и раздел Risk Admin в профиле PWA.

Конкурсный сценарий и план демо: COMPETITION.md.


БЫСТРЫЙ СТАРТ

1. Клонирование и настройка

```bash
git clone https://github.com/markmus11012020-max/Platon-RuBond-bot.git
cd Platon-RuBond-bot
cp .env.example .env
```

Отредактируйте .env и впишите свои API-ключи.

2. Запуск одной командой

Windows:

```cmd
start.bat
```

Linux и macOS:

```bash
chmod +x start.sh
./start.sh
```

Скрипт автоматически:

1. Останавливает старые процессы Streamlit.
2. Очищает __pycache__, .pytest_cache и кэш tools.
3. Создаёт .venv, если его нет, и устанавливает зависимости.
4. Запускает Streamlit на http://localhost:8501.

3. Ручной запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Для Windows активация окружения: .venv\Scripts\activate.


КОНФИГУРАЦИЯ .ENV

Streamlit-агент:

- AITUNNEL_API_KEY — API-ключ LLM-провайдера, OpenAI-compatible.
- AITUNNEL_BASE_URL — базовый URL API, по умолчанию https://api.aitunnel.ru/v1.
- LLM_MODEL — модель LLM, по умолчанию gpt-4o-mini.
- EMBEDDING_MODEL — модель эмбеддингов, по умолчанию text-embedding-3-small.
- AGENT_TEMPERATURE — температура LLM, по умолчанию 0.1.
- AGENT_MAX_ITERATIONS — максимум итераций агента, по умолчанию 8.
- PINECONE_API_KEY — API-ключ Pinecone.
- PINECONE_ENV — окружение Pinecone.
- PINECONE_INDEX — имя индекса, по умолчанию platon-rubond.
- HISTORY_DB — путь к SQLite истории, по умолчанию history.db.
- PORTFOLIO_DB — путь к SQLite портфеля, по умолчанию portfolio.db.

VK-бот:

- BONDBOT_DB_PATH — путь к базе бота.
- BONDBOT_VK_GROUP_TOKEN, BONDBOT_VK_GROUP_ID, BONDBOT_VK_ADMIN_USER_ID — доступ к VK.
- BONDBOT_PUBLIC_ACCESS, BONDBOT_COMMUNITY_MEMBERS_ONLY — публичный режим.
- BONDBOT_DIALOGUE_TTL_MINUTES — срок жизни памяти диалога.
- BONDBOT_LLM_DAILY_TOKEN_LIMIT — дневной лимит токенов на пользователя.
- BONDBOT_TINVEST_TOKEN, BONDBOT_TINVEST_ACCOUNT_ID — доступ к T-Invest API.
- BONDBOT_BROKER_SYNC_ENABLED, BONDBOT_BROKER_SYNC_MINUTES — автосинхронизация брокера.
- BONDBOT_SCHEDULER_ENABLED, BONDBOT_REFRESH_HOUR, BONDBOT_ALERTS_ENABLED — планировщик и алерты.
- BONDBOT_NEWS_ENABLED, BONDBOT_NEWS_FEEDS, BONDBOT_NEWS_INTERVAL_MINUTES — новости.
- BONDBOT_LLM_ENABLED, BONDBOT_OPENAI_BASE_URL, BONDBOT_OPENAI_API_KEY, BONDBOT_OPENAI_MODEL — LLM-ассистент.

Полный список находится в .env.example.


ТЕСТИРОВАНИЕ

```bash
pytest -v
```

Покрытие:

- BondAnalyzer: YTM методом Newton-Raphson, амортизация, НКД, спреды, налоги, фильтры.
- MacroParser: fallback, парсинг HTML, кэш, интеграция с флоатерами.
- PortfolioManager: CRUD, persistence, метрики, диверсификация.
- ToolCache: TTL и инвалидация.
- RAGQualityTracker: логирование, feedback, статистика.
- LocalTracer: span lifecycle.
- PipelineRunner: intent routing, streaming, Risk Officer.
- VK-бот: фильтры, сортировка, публичный доступ, портфель, брокеры, планировщик.


ТЕХНОЛОГИЧЕСКИЙ СТЕК

- LLM Orchestration: LangChain 0.3+, LangGraph StateGraph.
- LLM Provider: OpenAI-compatible через AiTunnel.
- UI: Streamlit с light/dark темой и custom CSS.
- Data Sources: ISS MOEX API, RSS Интерфакс, DuckDuckGo Search.
- Vector DB: Pinecone с offline-fallback на cosine и HashEmbedding.
- Persistence: SQLite для истории, портфеля, tool cache и RAG quality.
- Observability: LocalTracer JSONL и опциональный LangSmith.
- Notifications: Telegram Bot API.
- Testing: pytest.
- VK-бот: aiohttp, VK LongPoll, T-Invest REST API, APScheduler.


КЛЮЧЕВЫЕ МОДУЛИ

PlatonAgentFactory — фабрика агента

```python
from src.agent.agent_factory import PlatonAgentFactory

factory = PlatonAgentFactory()
response = factory.run("Проанализируй SU26238RMFS7", session_id="u1")
print(response.summary, response.bond_report.ytm_pct)

for step, state in factory.stream("Какая ставка ЦБ?", session_id="u1"):
    print(step, state.get("intermediate"))
```

BondAnalyzer — финансовая математика

```python
from src.analytics.bond_math import BondAnalyzer

analyzer = BondAnalyzer()
ytm = analyzer.calculate_ytm(bond_data, tax_rate=0.13)
spread = analyzer.calculate_z_spread(bond_data, 0.16)
floater = analyzer.estimate_floater_yield(bond_data, 0.16)
```

PortfolioManager — портфель

```python
from src.analytics.portfolio import PortfolioManager

pm = PortfolioManager(db_path="portfolio.db", tax_rate=0.13)
pm.add_to_portfolio("RU000A105XX3", 10, 98.5, issuer="Gazprom")
metrics = pm.calculate_portfolio_metrics(market_data)
print(metrics["weighted_ytm_net"], metrics["diversification_ok"])
```

Новый источник данных

```python
from src.data_providers.base_parser import BaseParser

class CbondsParser(BaseParser):
    def fetch_data(self, request):
        ...

    def parse_data(self, raw_data):
        ...
```

Регистрация выполняется в src/agent/tools.py без изменения ядра агента.


RISK OFFICER И HUMAN-IN-THE-LOOP

Агент классифицирует уровень риска LOW, MEDIUM, HIGH или CRITICAL на основе:

- YTM выше 25% — пометка ВДО.
- Отсутствие рейтинга — требуется ручная проверка.
- Негативные кредитные события в новостях.

При HIGH или CRITICAL граф останавливается на ноде human_gate и ждёт решения оператора: approve или reject.


ROADMAP

Сделано:

- LangGraph state machine с Risk Officer.
- Точная YTM методом Newton-Raphson, амортизация, НКД и налоги.
- RAG-слой с Pinecone и offline fallback.
- Tool cache с TTL.
- Observability: LocalTracer и LangSmith.
- Streamlit UI с light/dark темами и 4 вкладками.
- Portfolio persistence и метрики.
- VK-бот: smart-lab, MOEX ISS, ставка ЦБ, скрининг, портфель, /safe, /exit, /alloc.
- Аудит стратегических расчётов в strategy_audit.
- Планировщик обновления данных и проактивные алерты.
- Новости RSS, новые выпуски, риск-скор и стресс-тест.
- LLM-ассистент /ask, журнал идей /journal и стратегия недели.
- Публичный доступ для участников VK-сообщества.
- Read-only интеграция T-Invest и команды /broker.
- Импорт портфеля по файлу или прямой ссылке.

Планы:

- Импорт брокерского отчёта СберИнвестиций.
- Telegram-алерты: заглушка готова, нужен токен бота.
- Backtesting стратегий на исторических данных.
- Интеграция с Cbonds и БКС для расширенных данных.
- Multi-user auth и персональные портфели.


ЛИЦЕНЗИЯ

MIT. Copyright Platon-RuBond-bot.


КОНТАКТЫ

GitHub: https://github.com/markmus11012020-max
Репозиторий: https://github.com/markmus11012020-max/Platon-RuBond-bot


ДИСКЛЕЙМЕР

Проект предназначен для исследовательских и аналитических целей. Не является инвестиционной рекомендацией. Все решения по сделкам принимаются оператором после подтверждения human-in-the-loop.
